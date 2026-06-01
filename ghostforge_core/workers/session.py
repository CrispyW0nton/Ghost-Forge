"""Long-lived worker resources: model checkpoints, pipelines, tokenisers.

Loading a Stable Diffusion checkpoint takes 30+ seconds; loading TRELLIS
takes minutes. Real workers cannot afford to do that on every job — but
they also cannot keep weights pinned forever, because a single 16 GB
model parked in VRAM blocks every other GPU job.

:class:`WorkerSession` is the small bookkeeping layer that resolves the
tension. Each worker owns one session keyed by the resources it loads;
the session lazily builds the resource on first :meth:`get`, hands the
same instance to every concurrent caller, and disposes of it when
:meth:`free` (or :meth:`free_idle`) decides it has been idle long
enough.

The class is deliberately minimal: it neither knows nor cares about
torch/cuda specifics. Workers pass a plain ``loader`` callable that
returns whatever they need (a pipeline, a checkpoint dict, …) and a
``disposer`` that releases it. That keeps the heavy ML imports out of
the core module entirely.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass
class _Holding(Generic[T]):
    value: T
    loaded_at: float
    last_used_at: float
    in_use: int = 0


class WorkerSession(Generic[T]):
    """Lazy-load + idle-evict cache for a single worker resource.

    Typical usage from inside a worker::

        session = WorkerSession(loader=_load_pipeline, disposer=_unload_pipeline)

        def run(self, spec, reporter, cancel):
            with session.lease() as pipe:
                pipe(spec.prompt, ...)

    The session is thread-safe so the scheduler can run multiple
    same-worker invocations on a single shared pipeline (when the
    worker's :class:`WorkerResources.max_concurrent_per_gpu` allows it).
    """

    def __init__(
        self,
        *,
        loader: Callable[[], T],
        disposer: Callable[[T], None] | None = None,
        idle_timeout_seconds: float = 300.0,
        name: str = "session",
    ) -> None:
        self._loader = loader
        self._disposer = disposer
        self._idle_timeout = idle_timeout_seconds
        self.name = name
        # Two-lock design:
        #   * ``_state_lock`` guards _holding mutation; held briefly.
        #   * ``_load_lock`` serialises the loader call so concurrent
        #     callers wait for the first one to finish instead of
        #     racing into duplicate loads. Loaders may take 30+ seconds
        #     for SD checkpoints and many GBs of GPU memory, so we
        #     never want two of them in flight.
        self._state_lock = threading.RLock()
        self._load_lock = threading.RLock()
        self._holding: _Holding[T] | None = None

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    def get(self) -> T:
        """Return the resource, loading it on demand."""

        with self._state_lock:
            if self._holding is not None:
                self._holding.last_used_at = time.monotonic()
                self._holding.in_use += 1
                return self._holding.value

        # Serialise concurrent first-loads. Once the first thread
        # populates ``_holding``, every subsequent thread re-enters the
        # fast path above on its next attempt.
        with self._load_lock:
            with self._state_lock:
                if self._holding is not None:
                    self._holding.last_used_at = time.monotonic()
                    self._holding.in_use += 1
                    return self._holding.value

            value = self._loader()
            now = time.monotonic()
            with self._state_lock:
                self._holding = _Holding(value=value, loaded_at=now, last_used_at=now)
                self._holding.in_use += 1
                return self._holding.value

    def release(self) -> None:
        """Decrement the in-use counter; pair with every :meth:`get`."""

        with self._state_lock:
            if self._holding is not None and self._holding.in_use > 0:
                self._holding.in_use -= 1

    class _Lease:
        def __init__(self, session: "WorkerSession") -> None:
            self._session = session
            self.value: Any = None

        def __enter__(self) -> Any:
            self.value = self._session.get()
            return self.value

        def __exit__(self, exc_type, exc, tb) -> None:
            self._session.release()

    def lease(self) -> "_Lease":
        """Context manager: ``with session.lease() as resource: ...``."""

        return WorkerSession._Lease(self)

    # ------------------------------------------------------------------
    # Eviction
    # ------------------------------------------------------------------

    def free(self, *, force: bool = False) -> bool:
        """Drop the cached resource. Returns True when something was freed."""

        with self._state_lock:
            holding = self._holding
            if holding is None:
                return False
            if holding.in_use > 0 and not force:
                return False
            self._holding = None

        if holding is not None and self._disposer is not None:
            try:
                self._disposer(holding.value)
            except Exception:
                pass
        return holding is not None

    def free_idle(self, *, idle_for_seconds: float | None = None) -> bool:
        """Free if the resource has been idle longer than the threshold.

        Returns True when something was freed.
        """

        threshold = self._idle_timeout if idle_for_seconds is None else idle_for_seconds
        with self._state_lock:
            holding = self._holding
            if holding is None or holding.in_use > 0:
                return False
            idle = time.monotonic() - holding.last_used_at
            if idle < threshold:
                return False
        return self.free()

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            holding = self._holding
            if holding is None:
                return {"name": self.name, "loaded": False}
            return {
                "name": self.name,
                "loaded": True,
                "in_use": holding.in_use,
                "loaded_at": holding.loaded_at,
                "last_used_at": holding.last_used_at,
                "idle_seconds": max(0.0, time.monotonic() - holding.last_used_at),
                "idle_timeout_seconds": self._idle_timeout,
            }


class WorkerSessionRegistry:
    """Global registry so MCP/UI can list and free all sessions in one shot."""

    def __init__(self) -> None:
        self._sessions: dict[str, WorkerSession[Any]] = {}
        self._lock = threading.RLock()

    def register(self, session: WorkerSession[Any]) -> WorkerSession[Any]:
        with self._lock:
            self._sessions[session.name] = session
        return session

    def get(self, name: str) -> WorkerSession[Any] | None:
        with self._lock:
            return self._sessions.get(name)

    def all(self) -> list[WorkerSession[Any]]:
        with self._lock:
            return list(self._sessions.values())

    def free(self, name: str | None = None, *, force: bool = False) -> int:
        targets = [self._sessions[name]] if name else list(self.all())
        count = 0
        for session in targets:
            if session.free(force=force):
                count += 1
        return count

    def free_idle(self, *, idle_for_seconds: float | None = None) -> int:
        count = 0
        for session in self.all():
            if session.free_idle(idle_for_seconds=idle_for_seconds):
                count += 1
        return count

    def status(self) -> list[dict[str, Any]]:
        return [session.status() for session in self.all()]


_GLOBAL_REGISTRY = WorkerSessionRegistry()


def get_session_registry() -> WorkerSessionRegistry:
    return _GLOBAL_REGISTRY


__all__ = [
    "WorkerSession",
    "WorkerSessionRegistry",
    "get_session_registry",
]
