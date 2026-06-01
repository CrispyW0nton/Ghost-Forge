from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from .types import Artifact, Error, JobHandle, JobProgress, JobStatus, utc_now


class CancelledError(RuntimeError):
    pass


def _dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _dump_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _uuid7_like() -> str:
    # Python 3.12 does not include uuid7. Prefix uuid4 entropy with a sortable
    # millisecond timestamp so job IDs keep roughly chronological ordering.
    return f"{int(time.time() * 1000):013x}-{uuid.uuid4()}"


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def _loads(value: str | None) -> Any:
    return json.loads(value) if value else None


class JobStore:
    """Durable SQLite job store.

    SQLite is opened in WAL mode with `synchronous=NORMAL`. This is a good
    throughput/durability tradeoff for a creator workflow: committed data is
    safe across process crashes, but power-loss durability is weaker than
    `FULL`. Use `FULL` for a deployment where sudden power loss must never lose
    the most recent transaction, at roughly half the write throughput.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._setup()
        self._mark_interrupted()

    def _setup(self) -> None:
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    spec_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress_json TEXT,
                    result_json TEXT,
                    error_json TEXT,
                    artifacts_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def _mark_interrupted(self) -> None:
        now = _dump_dt(utc_now())
        error = Error(code="interrupted", message="Process exited before job completed")
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?, error_json=?, updated_at=?, finished_at=?
                WHERE status=?
                """,
                (JobStatus.failed.value, json.dumps(_jsonable(error)), now, now, JobStatus.running.value),
            )

    def submit(self, kind: str, spec: BaseModel) -> JobHandle:
        job_id = _uuid7_like()
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO jobs (
                    id, kind, spec_json, status, progress_json, result_json,
                    error_json, artifacts_json, created_at, updated_at,
                    started_at, finished_at, cancel_requested
                )
                VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?, NULL, NULL, 0)
                """,
                (
                    job_id,
                    kind,
                    spec.model_dump_json(),
                    JobStatus.pending.value,
                    None,
                    json.dumps([]),
                    _dump_dt(now),
                    _dump_dt(now),
                ),
            )
        return self.get(job_id)

    def get(self, job_id: str) -> JobHandle:
        with self._lock:
            row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return self._row_to_handle(row)

    def list(
        self,
        status: JobStatus | str | None = None,
        kind: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[JobHandle]:
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status=?")
            params.append(status.value if isinstance(status, JobStatus) else status)
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [self._row_to_handle(row) for row in rows]

    def start(self, job_id: str) -> None:
        now = _dump_dt(utc_now())
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE jobs SET status=?, started_at=?, updated_at=? WHERE id=?",
                (JobStatus.running.value, now, now, job_id),
            )

    def update_progress(self, job_id: str, progress: JobProgress) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE jobs SET progress_json=?, updated_at=? WHERE id=?",
                (progress.model_dump_json(), _dump_dt(utc_now()), job_id),
            )

    def complete(self, job_id: str, result: Any, artifacts: list[Artifact] | None = None) -> None:
        now = _dump_dt(utc_now())
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?, result_json=?, artifacts_json=?, updated_at=?, finished_at=?
                WHERE id=?
                """,
                (
                    JobStatus.succeeded.value,
                    json.dumps(_jsonable(result)),
                    json.dumps(_jsonable(artifacts or [])),
                    now,
                    now,
                    job_id,
                ),
            )

    def fail(self, job_id: str, error: Error) -> None:
        now = _dump_dt(utc_now())
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?, error_json=?, updated_at=?, finished_at=?
                WHERE id=?
                """,
                (JobStatus.failed.value, error.model_dump_json(), now, now, job_id),
            )

    def cancel(self, job_id: str, message: str = "Job cancelled") -> None:
        now = _dump_dt(utc_now())
        error = Error(code="cancelled", message=message)
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE jobs
                SET status=?, error_json=?, updated_at=?, finished_at=?
                WHERE id=?
                """,
                (JobStatus.cancelled.value, error.model_dump_json(), now, now, job_id),
            )

    def request_cancel(self, job_id: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=?",
                (_dump_dt(utc_now()), job_id),
            )

    def is_cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT cancel_requested FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
        return bool(row and row["cancel_requested"])

    def spec_json(self, job_id: str) -> str:
        with self._lock:
            row = self._conn.execute("SELECT spec_json FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(job_id)
        return str(row["spec_json"])

    def pending(self) -> list[JobHandle]:
        return self.list(status=JobStatus.pending, limit=1000)

    @staticmethod
    def _row_to_handle(row: sqlite3.Row) -> JobHandle:
        progress_raw = _loads(row["progress_json"])
        error_raw = _loads(row["error_json"])
        artifacts_raw = _loads(row["artifacts_json"]) or []
        return JobHandle(
            id=row["id"],
            kind=row["kind"],
            status=JobStatus(row["status"]),
            progress=JobProgress.model_validate(progress_raw) if progress_raw else None,
            result=_loads(row["result_json"]),
            error=Error.model_validate(error_raw) if error_raw else None,
            artifacts=[Artifact.model_validate(a) for a in artifacts_raw],
            created_at=_dt(row["created_at"]) or utc_now(),
            updated_at=_dt(row["updated_at"]) or utc_now(),
            started_at=_dt(row["started_at"]),
            finished_at=_dt(row["finished_at"]),
            cancel_requested=bool(row["cancel_requested"]),
        )


class ProgressReporter:
    def __init__(self, store: JobStore, job_id: str) -> None:
        self.store = store
        self.job_id = job_id

    def report(self, stage: str, percent: float, message: str = "") -> None:
        self.store.update_progress(
            self.job_id,
            JobProgress(percent=percent, stage=stage, message=message),
        )

    __call__ = report


class CancelToken:
    def __init__(self, store: JobStore, job_id: str) -> None:
        self.store = store
        self.job_id = job_id

    def is_cancel_requested(self) -> bool:
        return self.store.is_cancel_requested(self.job_id)

    def throw_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise CancelledError("Job cancellation requested")


Handler = Callable[[BaseModel, ProgressReporter, CancelToken], Any]


class JobRunner:
    """In-process dispatcher for jobs persisted in `JobStore`.

    Set `dispatch=False` for adapters that share a SQLite store with another
    owner process (for example, an MCP server peering with a desktop app). The
    runner still records submissions but never claims pending work, so exactly
    one process drives execution while every adapter sees the same job state.
    """

    def __init__(self, store: JobStore, max_workers: int = 2, dispatch: bool = True) -> None:
        self.store = store
        self.max_workers = max_workers
        self.dispatch = dispatch
        self._handlers: dict[str, tuple[type[BaseModel], Handler]] = {}
        self._executor: ThreadPoolExecutor | None = (
            ThreadPoolExecutor(max_workers=max_workers) if dispatch else None
        )
        self._futures: dict[str, Future[Any]] = {}
        self._lock = threading.RLock()

    def register(self, kind: str, spec_model: type[BaseModel], handler: Handler) -> None:
        self._handlers[kind] = (spec_model, handler)

    def submit(self, kind: str, spec: BaseModel) -> JobHandle:
        handle = self.store.submit(kind, spec)
        if self.dispatch:
            self.dispatch_pending()
        return handle

    def dispatch_pending(self) -> None:
        if not self.dispatch or self._executor is None:
            return
        for job in self.store.pending():
            with self._lock:
                if job.id in self._futures:
                    continue
                if job.kind not in self._handlers:
                    self.store.fail(
                        job.id,
                        Error(code="unknown_job_kind", message=f"No handler registered for {job.kind}"),
                    )
                    continue
                self._futures[job.id] = self._executor.submit(self._run_job, job.id)

    def shutdown(self, wait: bool = True) -> None:
        if self._executor is None:
            return
        self._executor.shutdown(wait=wait, cancel_futures=not wait)

    def _run_job(self, job_id: str) -> None:
        job = self.store.get(job_id)
        spec_model, handler = self._handlers[job.kind]
        self.store.start(job_id)
        reporter = ProgressReporter(self.store, job_id)
        token = CancelToken(self.store, job_id)
        try:
            spec = spec_model.model_validate_json(self.store.spec_json(job_id))
            result = handler(spec, reporter, token)
            if token.is_cancel_requested():
                self.store.cancel(job_id)
            else:
                self.store.complete(job_id, result)
        except CancelledError:
            self.store.cancel(job_id)
        except Exception as exc:
            self.store.fail(
                job_id,
                Error(code=exc.__class__.__name__, message=str(exc)),
            )
        finally:
            with self._lock:
                self._futures.pop(job_id, None)
