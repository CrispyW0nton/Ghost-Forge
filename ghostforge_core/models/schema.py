"""Schema for declared model artifacts.

A *model artifact* is a declarative record of a single set of weights
(or a multi-file checkpoint family) the system knows how to fetch and
verify. Workers reference artifacts by ``model_id`` so the rest of
the system never embeds raw URLs or paths.

Two truths the schema enforces:

1. **Reproducibility.** Every file carries a recorded ``sha256`` (or
   accepts an empty string when the source has no published digest —
   in which case the registry caches the post-download digest so a
   later mismatch is loud). This keeps "model drift" out of asset
   provenance: if the same prompt produces a different mesh tomorrow,
   the manifest's referenced ``model_id`` plus its artifact
   fingerprints make it provable.

2. **License visibility.** Models commonly ship under their own
   non-commercial or weight-only licenses. Tracking them here lets
   the audit layer flag handoffs that would breach the model's terms
   (e.g. shipping a Tencent Hunyuan3D-textured asset to a commercial
   game without checking the license).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from ..types import FrozenModel, utc_now


class ModelFile(FrozenModel):
    """A single file inside a model artifact."""

    path: str  # relative path inside the cache dir
    sha256: str = ""  # blank means "compute on first download"
    size_bytes: int | None = Field(default=None, ge=0)


class ModelArtifact(FrozenModel):
    """Declarative record of a model checkpoint family."""

    model_id: str
    repo_id: str
    revision: str | None = None
    files: list[ModelFile] = Field(default_factory=list)
    description: str = ""
    license: str | None = None
    homepage: str | None = None
    paper_url: str | None = None
    requires_login: bool = False
    total_size_bytes: int | None = Field(default=None, ge=0)
    pinned_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, str] = Field(default_factory=dict)


class ModelStatus(FrozenModel):
    """Cache state of a registered model."""

    model_id: str
    cache_dir: Path
    cached: bool
    files_present: int
    files_total: int
    total_bytes: int
    missing_files: list[str] = Field(default_factory=list)
    integrity: Literal["unknown", "verified", "failed", "pending"] = "unknown"
    last_verified_at: datetime | None = None


__all__ = ["ModelArtifact", "ModelFile", "ModelStatus"]
