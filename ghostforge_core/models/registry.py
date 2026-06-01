"""Model artifact registry + cache.

Two responsibilities:

* **Registration** — workers (and any other code) declare which model
  artifacts they need by id. Registration is a pure dict update; no
  network IO happens until a download is requested.
* **Cache management** — files live under
  ``data/cache/models/<model_id>/`` and the registry tracks presence,
  total size, and verification state. Verification recomputes the
  sha256 of every file recorded for the artifact; expensive, so it's
  invoked only on user request (``verify_model``) or after a fresh
  download.

Downloading uses :mod:`huggingface_hub` when available. The function
falls back to ``urllib`` for direct URL files (rare; HF Hub is the
common case). Both paths are guarded by the registry-level cache so
re-runs are no-ops.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .schema import ModelArtifact, ModelStatus

logger = logging.getLogger(__name__)


class ModelNotFound(KeyError):
    """Raised when a caller references an unregistered ``model_id``."""


class ModelDownloadError(RuntimeError):
    """Raised when a download fails or post-download verification mismatches."""


class ModelRegistry:
    """In-memory registry over a filesystem-backed cache."""

    def __init__(self, cache_root: Path | str) -> None:
        self._cache_root = Path(cache_root).resolve()
        self._cache_root.mkdir(parents=True, exist_ok=True)
        self._artifacts: dict[str, ModelArtifact] = {}
        self._verified_at: dict[str, datetime] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, artifact: ModelArtifact, *, replace: bool = True) -> None:
        with self._lock:
            if artifact.model_id in self._artifacts and not replace:
                raise ValueError(f"Model {artifact.model_id!r} already registered")
            self._artifacts[artifact.model_id] = artifact

    def register_many(self, artifacts: Iterable[ModelArtifact], *, replace: bool = True) -> None:
        for artifact in artifacts:
            self.register(artifact, replace=replace)

    def unregister(self, model_id: str) -> None:
        with self._lock:
            self._artifacts.pop(model_id, None)
            self._verified_at.pop(model_id, None)

    def get(self, model_id: str) -> ModelArtifact:
        with self._lock:
            try:
                return self._artifacts[model_id]
            except KeyError as exc:
                raise ModelNotFound(model_id) from exc

    def list(self) -> list[ModelArtifact]:
        with self._lock:
            return list(self._artifacts.values())

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    def model_dir(self, model_id: str) -> Path:
        # ``Path(name).name`` strips path-separator tricks so a malicious
        # ``model_id`` cannot escape ``cache_root``.
        safe = Path(model_id).name
        return self._cache_root / safe

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self, model_id: str) -> ModelStatus:
        artifact = self.get(model_id)
        cache_dir = self.model_dir(model_id)
        if not cache_dir.exists():
            return ModelStatus(
                model_id=model_id,
                cache_dir=cache_dir,
                cached=False,
                files_present=0,
                files_total=len(artifact.files),
                total_bytes=0,
                missing_files=[f.path for f in artifact.files],
                integrity="unknown",
            )

        present = 0
        total_bytes = 0
        missing: list[str] = []
        for entry in artifact.files:
            target = cache_dir / entry.path
            if target.exists():
                present += 1
                total_bytes += target.stat().st_size
            else:
                missing.append(entry.path)
        cached = present == len(artifact.files) and not missing
        verified_at = self._verified_at.get(model_id)
        integrity = (
            "verified"
            if verified_at is not None and cached
            else ("pending" if cached else "unknown")
        )
        return ModelStatus(
            model_id=model_id,
            cache_dir=cache_dir,
            cached=cached,
            files_present=present,
            files_total=len(artifact.files),
            total_bytes=total_bytes,
            missing_files=missing,
            integrity=integrity,
            last_verified_at=verified_at,
        )

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download(
        self,
        model_id: str,
        *,
        force: bool = False,
        token: str | None = None,
        progress: Any = None,
    ) -> ModelStatus:
        """Fetch ``model_id`` into the cache.

        * Idempotent: returns immediately if already cached unless
          ``force`` is set.
        * Uses :mod:`huggingface_hub` when available; falls back to
          ``urllib`` for direct URLs (treats ``repo_id`` starting with
          ``http://`` or ``https://`` as a single-file download).
        * Verifies sha256 on every declared file post-download.
        """

        artifact = self.get(model_id)
        cache_dir = self.model_dir(model_id)
        cache_dir.mkdir(parents=True, exist_ok=True)

        existing = self.status(model_id)
        if existing.cached and not force and existing.integrity == "verified":
            return existing

        try:
            if artifact.repo_id.startswith(("http://", "https://")):
                self._download_direct(artifact, cache_dir, progress=progress)
            else:
                self._download_hf(artifact, cache_dir, token=token, progress=progress)
        except ModelDownloadError:
            raise
        except Exception as exc:
            raise ModelDownloadError(
                f"failed to download model {model_id!r}: {type(exc).__name__}: {exc}"
            ) from exc

        return self.verify(model_id)

    def verify(self, model_id: str) -> ModelStatus:
        """Recompute sha256 for every declared file. Persists timestamp."""

        artifact = self.get(model_id)
        cache_dir = self.model_dir(model_id)
        for entry in artifact.files:
            target = cache_dir / entry.path
            if not target.exists():
                return self.status(model_id).model_copy(update={"integrity": "failed"})
            if entry.sha256:
                actual = _sha256_file(target)
                if actual.lower() != entry.sha256.lower():
                    raise ModelDownloadError(
                        f"sha256 mismatch for {model_id}/{entry.path}: "
                        f"expected {entry.sha256}, got {actual}"
                    )
        with self._lock:
            self._verified_at[model_id] = datetime.now(timezone.utc)
        return self.status(model_id)

    def clear(self, model_id: str | None = None) -> int:
        """Delete cached files. Returns count of removed model directories."""

        removed = 0
        with self._lock:
            ids = [model_id] if model_id is not None else list(self._artifacts)
            for mid in ids:
                target = self.model_dir(mid)
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                    removed += 1
                self._verified_at.pop(mid, None)
        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _download_hf(
        self,
        artifact: ModelArtifact,
        cache_dir: Path,
        *,
        token: str | None,
        progress: Any,
    ) -> None:
        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except ImportError as exc:
            raise ModelDownloadError(
                "huggingface_hub is required to download HF Hub models. "
                "Install with `pip install ghostforge[models]` or "
                "`pip install huggingface_hub`."
            ) from exc

        for index, entry in enumerate(artifact.files):
            if progress is not None:
                progress(
                    "download",
                    100.0 * index / max(len(artifact.files), 1),
                    f"fetching {entry.path}",
                )
            local_path = hf_hub_download(
                repo_id=artifact.repo_id,
                filename=entry.path,
                revision=artifact.revision,
                token=token,
                cache_dir=str(cache_dir / "_hf_cache"),
            )
            target = cache_dir / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            shutil.copy2(local_path, target)

    def _download_direct(
        self,
        artifact: ModelArtifact,
        cache_dir: Path,
        *,
        progress: Any,
    ) -> None:
        # repo_id is a URL pointing at a single file when files=[] or
        # joined as URL/path for each file.
        from urllib.error import URLError
        from urllib.request import urlopen

        if not artifact.files:
            raise ModelDownloadError(
                "direct-URL artifacts require an explicit `files` list"
            )

        for index, entry in enumerate(artifact.files):
            url = artifact.repo_id.rstrip("/") + "/" + entry.path.lstrip("/")
            target = cache_dir / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            if progress is not None:
                progress("download", 100.0 * index / len(artifact.files), f"fetching {url}")
            try:
                with urlopen(url) as response, target.open("wb") as out:
                    shutil.copyfileobj(response, out)
            except URLError as exc:
                raise ModelDownloadError(f"GET {url} failed: {exc}") from exc


def _sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(chunk), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["ModelDownloadError", "ModelNotFound", "ModelRegistry"]
