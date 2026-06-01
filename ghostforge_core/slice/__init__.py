"""Vertical slice planning and execution.

A *vertical slice* in GhostForge is the smallest end-to-end deliverable
unit: a small list of assets generated, audited, and delivered to a
game engine in one orchestrated pipeline. This package provides:

* :class:`GameBrief` and :class:`AssetSpec` — declarative inputs the
  agent edits (likely produced by an LLM decomposing a higher-level
  pitch).
* :class:`VerticalSlicePlan` — the persisted blueprint.
* :class:`SliceStore` — file-backed persistence under
  ``data/slices/<slice_id>/``.
* :func:`plan_vertical_slice` — validate and persist a plan.
* :func:`execute_vertical_slice` — run a plan asset-by-asset through
  the foundry pipeline (KB → generate → unwrap → texture → cite →
  annotate → audit → engine handoff), persisting per-stage state.

The slice layer reuses every other GhostForge subsystem rather than
re-implementing them — workers, KB, manifest, audit, engine adapters
all stay independent and testable on their own.
"""

from __future__ import annotations

from .executor import SliceExecutionError, execute_vertical_slice
from .planner import PlanValidationError, plan_vertical_slice, update_plan_assets
from .schema import (
    AssetKind,
    AssetRunState,
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    SLICE_SCHEMA_VERSION,
    SliceSummary,
    StageRecord,
    StageStatus,
    VerticalSlicePlan,
    VerticalSliceRun,
)
from .store import PLAN_FILENAME, RUN_FILENAME, SliceNotFound, SliceStore

__all__ = [
    "AssetKind",
    "AssetRunState",
    "AssetSpec",
    "GameBrief",
    "GenerationStrategy",
    "PLAN_FILENAME",
    "PlanValidationError",
    "RUN_FILENAME",
    "SLICE_SCHEMA_VERSION",
    "SliceExecutionError",
    "SliceNotFound",
    "SliceStore",
    "SliceSummary",
    "StageRecord",
    "StageStatus",
    "VerticalSlicePlan",
    "VerticalSliceRun",
    "execute_vertical_slice",
    "plan_vertical_slice",
    "update_plan_assets",
]
