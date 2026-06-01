"""Filesystem-backed slice storage.

Slices live under ``data/slices/<slice_id>/`` with two JSON files:

* ``plan.json`` — the agent-edited blueprint (:class:`VerticalSlicePlan`)
* ``run.json`` — the executor's append-only run record
  (:class:`VerticalSliceRun`)

Per-asset directories sit under ``data/slices/<slice_id>/assets/<asset_id>/``
so each asset gets its own manifest, mesh artifacts, and audit history.

JSON storage is the right call here:
* Slices are small (rarely more than a few dozen assets).
* Plans are agent-editable and human-readable.
* No need for a query index; ``list_vertical_slices`` walks directories.
* Atomic writes via ``os.replace`` keep readers from seeing torn files.
"""

from __future__ import annotations

import os
from pathlib import Path

from ..storage import Storage
from ..types import utc_now
from .schema import (
    AssetRunState,
    SliceSummary,
    StageStatus,
    VerticalSlicePlan,
    VerticalSliceRun,
)

PLAN_FILENAME = "plan.json"
RUN_FILENAME = "run.json"


class SliceNotFound(KeyError):
    """Raised when a requested slice id is unknown."""


class SliceStore:
    """Read/write slice plans and run state."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def slice_dir(self, slice_id: str) -> Path:
        return self.storage.slice_dir(slice_id)

    def assets_dir(self, slice_id: str) -> Path:
        return self.slice_dir(slice_id) / "assets"

    def asset_dir(self, slice_id: str, asset_id: str) -> Path:
        safe = Path(asset_id).name
        return self.assets_dir(slice_id) / safe

    def plan_path(self, slice_id: str) -> Path:
        return self.slice_dir(slice_id) / PLAN_FILENAME

    def run_path(self, slice_id: str) -> Path:
        return self.slice_dir(slice_id) / RUN_FILENAME

    # ------------------------------------------------------------------
    # Plan I/O
    # ------------------------------------------------------------------

    def save_plan(self, plan: VerticalSlicePlan) -> Path:
        slice_root = self.slice_dir(plan.slice_id)
        slice_root.mkdir(parents=True, exist_ok=True)
        self.assets_dir(plan.slice_id).mkdir(parents=True, exist_ok=True)
        return self._atomic_write(self.plan_path(plan.slice_id), plan.model_dump_json(indent=2))

    def load_plan(self, slice_id: str) -> VerticalSlicePlan:
        path = self.plan_path(slice_id)
        if not path.exists():
            raise SliceNotFound(slice_id)
        return VerticalSlicePlan.model_validate_json(path.read_text(encoding="utf-8"))

    def update_plan(
        self,
        slice_id: str,
        updater,
    ) -> VerticalSlicePlan:
        """Read-modify-write helper.

        ``updater`` receives the current :class:`VerticalSlicePlan` and
        returns a (possibly new) plan. Marks ``updated_at`` on the way out
        so dashboards see the change without each callsite remembering.
        """

        current = self.load_plan(slice_id)
        updated = updater(current)
        if updated is None:
            updated = current
        updated = updated.model_copy(update={"updated_at": utc_now()})
        self.save_plan(updated)
        return updated

    # ------------------------------------------------------------------
    # Run I/O
    # ------------------------------------------------------------------

    def save_run(self, run: VerticalSliceRun) -> Path:
        slice_root = self.slice_dir(run.slice_id)
        slice_root.mkdir(parents=True, exist_ok=True)
        return self._atomic_write(
            self.run_path(run.slice_id), run.model_dump_json(indent=2)
        )

    def load_run(self, slice_id: str) -> VerticalSliceRun | None:
        path = self.run_path(slice_id)
        if not path.exists():
            return None
        return VerticalSliceRun.model_validate_json(path.read_text(encoding="utf-8"))

    def get_or_init_run(self, plan: VerticalSlicePlan) -> VerticalSliceRun:
        """Return the existing run, or seed a fresh one from the plan.

        Pre-creates an :class:`AssetRunState` for each asset in the plan
        so executors don't have to do bookkeeping for new asset_ids that
        appear only at run time.
        """

        existing = self.load_run(plan.slice_id)
        if existing is not None:
            return existing

        asset_states: dict[str, AssetRunState] = {}
        for spec in plan.assets:
            asset_states[spec.asset_id] = AssetRunState(
                asset_id=spec.asset_id,
                asset_dir=self.asset_dir(plan.slice_id, spec.asset_id),
                status=StageStatus.pending,
            )
        run = VerticalSliceRun(
            slice_id=plan.slice_id,
            plan_path=self.plan_path(plan.slice_id),
            status=StageStatus.pending,
            assets=asset_states,
        )
        self.save_run(run)
        return run

    # ------------------------------------------------------------------
    # Listings
    # ------------------------------------------------------------------

    def list_summaries(self) -> list[SliceSummary]:
        out: list[SliceSummary] = []
        if not self.storage.slices_dir.exists():
            return out
        for entry in sorted(self.storage.slices_dir.iterdir()):
            if not entry.is_dir():
                continue
            plan_path = entry / PLAN_FILENAME
            if not plan_path.exists():
                continue
            try:
                plan = VerticalSlicePlan.model_validate_json(
                    plan_path.read_text(encoding="utf-8")
                )
            except Exception:
                continue
            run = self.load_run(plan.slice_id)
            status = run.status if run is not None else StageStatus.pending
            out.append(
                SliceSummary(
                    slice_id=plan.slice_id,
                    title=plan.brief.title,
                    target_engine=plan.brief.target_engine.value,
                    asset_count=len(plan.assets),
                    status=status,
                    created_at=plan.created_at,
                    updated_at=plan.updated_at,
                )
            )
        return out

    def delete(self, slice_id: str) -> None:
        slice_root = self.slice_dir(slice_id)
        if not slice_root.exists():
            raise SliceNotFound(slice_id)
        # Best-effort recursive delete; refuses to follow symlinks.
        for entry in sorted(slice_root.rglob("*"), reverse=True):
            try:
                if entry.is_symlink():
                    entry.unlink()
                elif entry.is_file():
                    entry.unlink()
                elif entry.is_dir():
                    entry.rmdir()
            except OSError:
                continue
        try:
            slice_root.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Atomic write
    # ------------------------------------------------------------------

    @staticmethod
    def _atomic_write(target: Path, contents: str) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(contents, encoding="utf-8")
        os.replace(tmp, target)
        return target


__all__ = ["PLAN_FILENAME", "RUN_FILENAME", "SliceNotFound", "SliceStore"]
