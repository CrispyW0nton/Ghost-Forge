from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path

from .types import Artifact


def _detect_mime(path: Path) -> str:
    try:
        import magic  # type: ignore

        detected = magic.from_file(str(path), mime=True)
        if detected:
            return detected
    except Exception:
        pass

    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def compute_artifact(path: Path | str, role: str = "artifact") -> Artifact:
    """Hash, size, and mime-detect a file into an :class:`Artifact`.

    Free function (no ``Storage`` instance required) so that the manifest
    builder and other helpers can register artifacts without taking a
    dependency on the data root.
    """
    artifact_path = Path(path).resolve()
    digest = hashlib.sha256()
    total = 0
    with artifact_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            digest.update(chunk)

    return Artifact(
        path=artifact_path,
        sha256=digest.hexdigest(),
        bytes=total,
        mime=_detect_mime(artifact_path),
        role=role,
    )


class Storage:
    """Owns every path under the GhostForge data root.

    Other modules should request paths from this class rather than constructing
    `data/...` paths directly. That keeps the core relocatable in tests, the
    desktop app, and MCP server deployments.
    """

    def __init__(self, root: Path | str = "./data") -> None:
        self.root = Path(root).resolve()
        self.uploads_dir = self.root / "uploads"
        self.outputs_dir = self.root / "outputs"
        self.jobs_db_path = self.root / "jobs.sqlite"
        self.kb_dir = self.root / "kb.lance"
        self.cache_dir = self.root / "cache"
        self.slices_dir = self.root / "slices"
        for path in (
            self.root,
            self.uploads_dir,
            self.outputs_dir,
            self.kb_dir,
            self.cache_dir,
            self.slices_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def new_asset_dir(self) -> Path:
        asset_id = uuid.uuid4().hex
        path = self.asset_dir(asset_id)
        path.mkdir(parents=True, exist_ok=False)
        return path

    def asset_dir(self, asset_id: str) -> Path:
        safe = Path(asset_id).name
        return self.outputs_dir / safe

    def upload_path(self, filename: str) -> Path:
        safe = Path(filename).name
        return self.uploads_dir / safe

    def slice_dir(self, slice_id: str) -> Path:
        safe = Path(slice_id).name
        return self.slices_dir / safe

    def register_artifact(self, path: Path | str, role: str = "artifact") -> Artifact:
        return compute_artifact(path, role=role)

    @staticmethod
    def _detect_mime(path: Path) -> str:
        return _detect_mime(path)
