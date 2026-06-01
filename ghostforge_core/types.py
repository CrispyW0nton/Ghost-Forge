from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class JobProgress(FrozenModel):
    percent: float = Field(ge=0.0, le=100.0)
    stage: str
    message: str = ""
    updated_at: datetime = Field(default_factory=utc_now)


class Artifact(FrozenModel):
    path: Path
    sha256: str
    bytes: int = Field(ge=0)
    mime: str
    role: str


class Error(FrozenModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class JobSpec(FrozenModel):
    asset_id: str | None = None
    input_path: Path | None = None
    output_dir: Path | None = None
    prompt: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class JobHandle(FrozenModel):
    id: str
    kind: str
    status: JobStatus
    progress: JobProgress | None = None
    result: dict[str, Any] | None = None
    error: Error | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False


class MeshInfo(FrozenModel):
    vertices: int
    faces: int
    edges: int | None = None
    watertight: bool
    bounds: list[list[float]] | None = None
    size: list[float] | None = None
    format: str


class UnwrapRequest(FrozenModel):
    input_mesh_path: Path
    output_dir: Path
    atlas_size: int = Field(default=1024, ge=256, le=4096)
    padding: int = Field(default=2, ge=1, le=64)
    output_format: str = "glb"
    force_unwrap: bool = False
    uv_only: bool = True
    job_id: str | None = None


class UnwrapResult(FrozenModel):
    output_mesh: Path
    uv_layout: Path | None = None
    metadata_path: Path | None = None
    original_stats: dict[str, Any] = Field(default_factory=dict)
    uv_stats: dict[str, Any] = Field(default_factory=dict)
    processing_time_seconds: float | None = None


class TextureRequest(FrozenModel):
    input_mesh_path: Path
    output_dir: Path
    prompt: str = "worn metal surface, detailed, high quality PBR"
    reference_image_path: Path | None = None
    texture_size: int = Field(default=1024, ge=256, le=4096)
    use_ai: bool = False
    ai_steps: int = Field(default=20, ge=1, le=100)
    output_format: str = "glb"
    force_unwrap: bool = False
    job_id: str | None = None


class TextureResult(FrozenModel):
    output_mesh: Path
    texture_map: Path | None = None
    uv_layout: Path | None = None
    metadata_path: Path | None = None
    original_stats: dict[str, Any] = Field(default_factory=dict)
    uv_stats: dict[str, Any] = Field(default_factory=dict)
    processing_time_seconds: float | None = None


class ExecuteVerticalSliceRequest(FrozenModel):
    """Run a previously planned vertical slice end to end."""

    slice_id: str
    job_id: str | None = None


class AuditAssetRequest(FrozenModel):
    """Request to run a game-readiness audit over an asset directory."""

    asset_dir: Path
    preset: str = "default"
    run_gltf_validator: bool = True
    persist: bool = True
    job_id: str | None = None


class SendToEngineRequest(FrozenModel):
    """Background-friendly engine handoff request.

    ``engine`` selects which configured adapter receives the asset
    (``"unity"`` or ``"unreal"`` today). ``dry_run`` skips the actual
    engine MCP call but still records the planned handoff in the
    manifest so agents can preview what would happen. ``force=True``
    bypasses both the manifest's ``engine_targets`` enforcement and
    audit error gating; useful for re-targeting an asset that was
    originally generated for a different engine. ``audit`` runs the
    pre-handoff game-readiness audit; turn it off only when you know
    the asset is good (or when the audit itself is the unit under
    test).
    """

    asset_dir: Path
    engine: str
    target_path: str | None = None
    dry_run: bool = False
    force: bool = False
    extra_args: dict[str, Any] = Field(default_factory=dict)
    audit: bool = True
    audit_preset: str | None = None
    job_id: str | None = None
