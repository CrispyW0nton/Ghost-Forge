"""Plan a vertical slice.

The planner is intentionally thin and deterministic: it takes a
:class:`GameBrief` plus an explicit list of :class:`AssetSpec` entries
and produces a persisted :class:`VerticalSlicePlan`. LLM-driven asset
expansion belongs *outside* this layer — agents are perfectly capable
of decomposing "build a haunted forest slice" into a list of props
and characters, and we don't want to bake one-shot heuristics in here.

What the planner *does* enforce:

* A unique ``slice_id`` (auto-generated if not provided).
* Unique, filesystem-safe ``asset_id`` per spec (collisions raise).
* Defaults inherited from the brief (target_engine, license).
* Validation that referenced files (reference_image_path,
  input_mesh_path) exist.
* Persistence under ``data/slices/<slice_id>/plan.json``.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from ..manifest import EngineTarget
from ..types import utc_now
from .schema import (
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    VerticalSlicePlan,
)
from .store import SliceStore

ASSET_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-./]+$")
SLICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]+$")


class PlanValidationError(ValueError):
    """Raised when the planner refuses an input plan."""


def _make_slice_id() -> str:
    # Short prefix + uuid keeps slice ids globally unique while still
    # being readable in directory listings.
    return f"slice-{uuid.uuid4().hex[:12]}"


def _validate_asset_spec(
    spec: AssetSpec,
    brief: GameBrief,
    *,
    seen_ids: set[str],
) -> AssetSpec:
    if not ASSET_ID_PATTERN.match(spec.asset_id):
        raise PlanValidationError(
            f"asset_id '{spec.asset_id}' contains characters that may break engine paths; "
            "use only [A-Za-z0-9_-./]"
        )
    if spec.asset_id in seen_ids:
        raise PlanValidationError(f"duplicate asset_id '{spec.asset_id}'")
    seen_ids.add(spec.asset_id)

    if spec.strategy == GenerationStrategy.image_to_3d and spec.reference_image_path is None:
        raise PlanValidationError(
            f"asset '{spec.asset_id}' uses image_to_3d but no reference_image_path is set"
        )
    if spec.strategy == GenerationStrategy.skip_generation and spec.input_mesh_path is None:
        raise PlanValidationError(
            f"asset '{spec.asset_id}' uses skip_generation but no input_mesh_path is set"
        )
    if spec.reference_image_path is not None and not Path(spec.reference_image_path).exists():
        raise PlanValidationError(
            f"asset '{spec.asset_id}' references missing image: {spec.reference_image_path}"
        )
    if spec.input_mesh_path is not None and not Path(spec.input_mesh_path).exists():
        raise PlanValidationError(
            f"asset '{spec.asset_id}' references missing mesh: {spec.input_mesh_path}"
        )

    updates: dict = {}
    if not spec.name:
        updates["name"] = spec.asset_id
    if spec.target_engine is None:
        updates["target_engine"] = brief.target_engine
    if spec.license is None:
        updates["license"] = brief.license
    return spec.model_copy(update=updates) if updates else spec


def plan_vertical_slice(
    *,
    store: SliceStore,
    brief: GameBrief,
    assets: list[AssetSpec],
    slice_id: str | None = None,
    fail_fast: bool = False,
    skip_audit: bool = False,
    skip_handoff: bool = False,
) -> VerticalSlicePlan:
    """Build, validate, and persist a slice plan.

    Returns the saved :class:`VerticalSlicePlan`. Re-running with the
    same ``slice_id`` overwrites the existing plan but preserves the
    run history (which lives in a sibling ``run.json``).
    """

    if slice_id is None:
        slice_id = _make_slice_id()
    if not SLICE_ID_PATTERN.match(slice_id):
        raise PlanValidationError(
            f"slice_id '{slice_id}' must match {SLICE_ID_PATTERN.pattern}"
        )

    seen_ids: set[str] = set()
    validated = [
        _validate_asset_spec(spec, brief, seen_ids=seen_ids) for spec in assets
    ]

    now = utc_now()
    plan = VerticalSlicePlan(
        slice_id=slice_id,
        brief=brief,
        assets=validated,
        created_at=now,
        updated_at=now,
        fail_fast=fail_fast,
        skip_audit=skip_audit,
        skip_handoff=skip_handoff,
    )
    store.save_plan(plan)
    return plan


def update_plan_assets(
    store: SliceStore,
    slice_id: str,
    assets: list[AssetSpec],
) -> VerticalSlicePlan:
    """Replace the plan's asset list (typical agent edit operation)."""

    def _apply(plan: VerticalSlicePlan) -> VerticalSlicePlan:
        seen: set[str] = set()
        validated = [
            _validate_asset_spec(spec, plan.brief, seen_ids=seen) for spec in assets
        ]
        return plan.model_copy(update={"assets": validated})

    return store.update_plan(slice_id, _apply)


__all__ = [
    "PlanValidationError",
    "plan_vertical_slice",
    "update_plan_assets",
]
