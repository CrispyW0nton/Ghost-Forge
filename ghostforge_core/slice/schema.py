"""Vertical slice schemas.

A *vertical slice* is the smallest end-to-end deliverable: a small
asset list (props, structures, characters) generated, validated, and
delivered to a game engine in one orchestrated run. The schemas in
this module describe both the *plan* (the agent's intent) and the
*run* (what actually happened).

Plans are mostly declarative — agents can edit them, version-control
them, and re-run them. Run state is the executor's append-only log,
recording every stage transition for every asset so a session can be
inspected, paused, or resumed without losing history.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from ..manifest import EngineTarget, LicenseSpec
from ..types import FrozenModel, utc_now

SLICE_SCHEMA_VERSION: Literal["1.0"] = "1.0"


class AssetKind(str, Enum):
    prop = "prop"
    character = "character"
    environment = "environment"
    structure = "structure"
    vehicle = "vehicle"
    weapon = "weapon"
    other = "other"


class GenerationStrategy(str, Enum):
    text_to_3d = "text_to_3d"
    image_to_3d = "image_to_3d"
    skip_generation = "skip_generation"


class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    skipped = "skipped"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class GameBrief(FrozenModel):
    """High-level intent for the slice.

    Captures what the agent and operator agreed on: the game's title
    and pitch, which engine the slice targets, art-style guidance for
    KB queries, and the default license that all slice-produced assets
    inherit unless an :class:`AssetSpec` overrides it.
    """

    title: str
    description: str = ""
    target_engine: EngineTarget = EngineTarget.unity
    art_style: str | None = None
    genre: str | None = None
    license: LicenseSpec = Field(default_factory=lambda: LicenseSpec(spdx="CC0-1.0"))
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class AssetSpec(FrozenModel):
    """Per-asset plan entry.

    The agent populates these declaratively. Each field carries a
    sensible default so a minimal spec (``asset_id`` + ``description``)
    still drives the executor through generation, audit, and handoff.
    """

    asset_id: str
    name: str = ""
    description: str
    kind: AssetKind = AssetKind.prop

    # Generation
    strategy: GenerationStrategy = GenerationStrategy.image_to_3d
    reference_image_path: Path | None = None
    input_mesh_path: Path | None = None
    worker: str | None = None
    seed: int | None = None
    output_format: str = "glb"
    generation_extras: dict[str, Any] = Field(default_factory=dict)

    # Knowledge base grounding
    concept_query: str | None = None
    concept_tags: list[str] | None = None
    concept_k: int = Field(default=3, ge=1, le=20)

    # UV unwrap
    run_unwrap: bool = False
    unwrap_atlas_size: int = Field(default=1024, ge=256, le=4096)

    # Texture
    run_texture: bool = False
    texture_prompt: str | None = None
    texture_size: int = Field(default=1024, ge=256, le=4096)

    # Audit + handoff
    target_engine: EngineTarget | None = None
    handoff_target_path: str | None = None
    audit_preset: str | None = None

    # License/notes can override the brief's defaults if set.
    license: LicenseSpec | None = None
    tags: list[str] = Field(default_factory=list)


class VerticalSlicePlan(FrozenModel):
    """The agent-edited blueprint for a slice."""

    schema_version: Literal["1.0"] = SLICE_SCHEMA_VERSION
    slice_id: str
    brief: GameBrief
    assets: list[AssetSpec] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    fail_fast: bool = False
    skip_handoff: bool = False
    skip_audit: bool = False


class StageRecord(FrozenModel):
    """One stage in an asset's pipeline."""

    stage: str
    status: StageStatus = StageStatus.pending
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: float = Field(default=0.0, ge=0.0)
    notes: str | None = None
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class AssetRunState(FrozenModel):
    """Per-asset execution snapshot."""

    asset_id: str
    asset_dir: Path
    status: StageStatus = StageStatus.pending
    stages: list[StageRecord] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class VerticalSliceRun(FrozenModel):
    """Top-level run record persisted alongside the plan."""

    schema_version: Literal["1.0"] = SLICE_SCHEMA_VERSION
    slice_id: str
    plan_path: Path
    status: StageStatus = StageStatus.pending
    assets: dict[str, AssetRunState] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class SliceSummary(FrozenModel):
    """Lightweight listing entry for ``list_vertical_slices``."""

    slice_id: str
    title: str
    target_engine: str
    asset_count: int
    status: StageStatus
    created_at: datetime
    updated_at: datetime


__all__ = [
    "AssetKind",
    "AssetRunState",
    "AssetSpec",
    "GameBrief",
    "GenerationStrategy",
    "SLICE_SCHEMA_VERSION",
    "SliceSummary",
    "StageRecord",
    "StageStatus",
    "VerticalSlicePlan",
    "VerticalSliceRun",
]
