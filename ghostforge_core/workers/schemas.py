"""Pydantic request and result schemas for capability-keyed jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from ..types import FrozenModel


class _BaseWorkerRequest(FrozenModel):
    """Fields shared by every worker-driven job submission."""

    output_dir: Path
    worker: str | None = None
    seed: int | None = None
    output_format: str = "glb"
    job_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ImageTo3DRequest(_BaseWorkerRequest):
    input_image_path: Path
    prompt: str | None = None
    reference_camera: dict[str, Any] | None = None


class TextTo3DRequest(_BaseWorkerRequest):
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None


class TextureMeshRequest(_BaseWorkerRequest):
    input_mesh_path: Path
    prompt: str = Field(min_length=1)
    reference_image_path: Path | None = None
    texture_size: int = Field(default=1024, ge=256, le=4096)


class RefineMeshRequest(_BaseWorkerRequest):
    input_mesh_path: Path
    target_face_count: int | None = Field(default=None, ge=4)
    preserve_uvs: bool = True


class WorkerResult(FrozenModel):
    """Common envelope for worker outputs.

    Workers should construct this via ``model_dump(mode="json")`` or simply
    return a dict matching the same shape — the dispatch layer normalises
    both. Keeping the contract explicit makes it easy to add new fields
    (texture maps, validation reports) without breaking downstream code.
    """

    worker: str
    output_mesh: Path
    texture_map: Path | None = None
    extra_paths: list[Path] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "ImageTo3DRequest",
    "RefineMeshRequest",
    "TextTo3DRequest",
    "TextureMeshRequest",
    "WorkerResult",
]
