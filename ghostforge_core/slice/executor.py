"""Vertical slice executor.

Walks a :class:`VerticalSlicePlan` asset by asset, running each
through a deterministic stage pipeline:

1. ``kb_search``   — optional KB lookup; records concept hits in run state.
2. ``generate``    — image_to_3d / skip (uses an existing mesh).
3. ``unwrap``      — optional UV unwrap pass (xatlas via the existing op).
4. ``texture``     — optional texturing pass (worker-driven).
5. ``cite``        — write KB concept citations into the asset manifest.
6. ``annotate``    — set engine_targets/license/tags on the manifest.
7. ``audit``       — game-readiness audit (engine-specific preset).
8. ``handoff``     — deliver to the engine MCP via the configured adapter.

Each stage is independently optional. Failures default to "asset
failed; continue to the next asset"; pass ``fail_fast=True`` (on the
plan) to abort the whole slice on the first failure instead.

The executor persists run state after every stage transition so a
crash leaves a recoverable record. Resuming a slice picks up at the
first asset whose status is not ``succeeded`` or ``skipped``.
"""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any, Callable

from ..audit import audit_asset as run_audit
from ..engines import EngineHandoffError, EngineRegistry
from ..jobs import CancelToken, ProgressReporter
from ..kb import KnowledgeBase
from ..manifest import (
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    manifest_exists,
)
from ..types import (
    UnwrapRequest,
    utc_now,
)
from ..workers.schemas import (
    ImageTo3DRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from .schema import (
    AssetRunState,
    AssetSpec,
    GenerationStrategy,
    StageRecord,
    StageStatus,
    VerticalSlicePlan,
    VerticalSliceRun,
)
from .store import SliceStore


class SliceExecutionError(RuntimeError):
    """Raised when a slice with ``fail_fast=True`` aborts."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stage_done(
    stage: str,
    *,
    status: StageStatus,
    started: float,
    notes: str | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
) -> StageRecord:
    duration = max(time.monotonic() - started, 0.0)
    started_at = utc_now()
    return StageRecord(
        stage=stage,
        status=status,
        started_at=started_at,
        finished_at=started_at,
        duration_seconds=duration,
        notes=notes,
        output=output or {},
        error=error,
    )


def _set_asset_state(
    run: VerticalSliceRun,
    asset_id: str,
    *,
    state: AssetRunState,
) -> VerticalSliceRun:
    new_assets = dict(run.assets)
    new_assets[asset_id] = state
    return run.model_copy(update={"assets": new_assets})


def _append_stage(state: AssetRunState, record: StageRecord) -> AssetRunState:
    return state.model_copy(update={"stages": list(state.stages) + [record]})


# ---------------------------------------------------------------------------
# Stage runners
# ---------------------------------------------------------------------------


def _run_kb_search(
    spec: AssetSpec,
    *,
    kb: KnowledgeBase,
) -> tuple[StageRecord, list[str]]:
    started = time.monotonic()
    if not spec.concept_query:
        return (
            _stage_done("kb_search", status=StageStatus.skipped, started=started, notes="no concept_query"),
            [],
        )
    try:
        results = kb.search_text(
            spec.concept_query,
            k=spec.concept_k,
            tags=spec.concept_tags,
        )
        concept_ids = [r.entry.id for r in results]
        return (
            _stage_done(
                "kb_search",
                status=StageStatus.succeeded,
                started=started,
                output={
                    "query": spec.concept_query,
                    "k": spec.concept_k,
                    "concept_ids": concept_ids,
                    "scores": [r.score for r in results],
                },
            ),
            concept_ids,
        )
    except Exception as exc:
        return (
            _stage_done(
                "kb_search",
                status=StageStatus.failed,
                started=started,
                error=f"{type(exc).__name__}: {exc}",
            ),
            [],
        )


def _run_generate(
    spec: AssetSpec,
    *,
    asset_dir: Path,
) -> tuple[StageRecord, Path | None]:
    started = time.monotonic()
    asset_dir.mkdir(parents=True, exist_ok=True)

    if spec.strategy == GenerationStrategy.skip_generation:
        if spec.input_mesh_path is None or not spec.input_mesh_path.exists():
            return (
                _stage_done(
                    "generate",
                    status=StageStatus.failed,
                    started=started,
                    error="skip_generation requires an existing input_mesh_path",
                ),
                None,
            )
        # Copy the mesh into the asset_dir so the manifest references a
        # local path; otherwise the engine handoff would point outside
        # the slice directory.
        import shutil

        target = asset_dir / spec.input_mesh_path.name
        shutil.copy2(spec.input_mesh_path, target)
        builder = ManifestBuilder.for_dir(asset_dir, asset_id=spec.asset_id)
        builder.with_geometry_from_mesh(target)
        builder.add_artifact_from_path(target, role="mesh.primary")
        builder.write()
        return (
            _stage_done(
                "generate",
                status=StageStatus.succeeded,
                started=started,
                notes="copied input mesh",
                output={"output_mesh": str(target), "strategy": "skip_generation"},
            ),
            target,
        )

    try:
        from ..operations import workers as worker_ops

        if spec.strategy == GenerationStrategy.text_to_3d:
            t2d = TextTo3DRequest(
                prompt=spec.description,
                output_dir=asset_dir,
                worker=spec.worker,
                seed=spec.seed,
                output_format=spec.output_format,
                extras=spec.generation_extras,
            )
            result = worker_ops.run_text_to_3d(t2d)
        elif spec.strategy == GenerationStrategy.image_to_3d:
            if spec.reference_image_path is None:
                raise ValueError("image_to_3d requires reference_image_path")
            i2d = ImageTo3DRequest(
                input_image_path=spec.reference_image_path,
                prompt=spec.description,
                output_dir=asset_dir,
                worker=spec.worker,
                seed=spec.seed,
                output_format=spec.output_format,
                extras=spec.generation_extras,
            )
            result = worker_ops.run_image_to_3d(i2d)
        else:
            raise ValueError(f"unknown generation strategy: {spec.strategy}")

        output_mesh = Path(result["output_mesh"])
        return (
            _stage_done(
                "generate",
                status=StageStatus.succeeded,
                started=started,
                notes=f"worker={result.get('worker')}",
                output={
                    "strategy": spec.strategy.value,
                    "worker": result.get("worker"),
                    "output_mesh": str(output_mesh),
                    "metadata": result.get("metadata", {}),
                },
            ),
            output_mesh,
        )
    except Exception as exc:
        return (
            _stage_done(
                "generate",
                status=StageStatus.failed,
                started=started,
                error=f"{type(exc).__name__}: {exc}",
                notes=traceback.format_exc(limit=2),
            ),
            None,
        )


def _run_unwrap(
    spec: AssetSpec,
    *,
    asset_dir: Path,
    mesh_path: Path,
) -> tuple[StageRecord, Path]:
    started = time.monotonic()
    if not spec.run_unwrap:
        return (
            _stage_done("unwrap", status=StageStatus.skipped, started=started, notes="run_unwrap=False"),
            mesh_path,
        )
    try:
        from ..operations import unwrap as unwrap_op

        request = UnwrapRequest(
            input_mesh_path=mesh_path,
            output_dir=asset_dir,
            atlas_size=spec.unwrap_atlas_size,
            output_format=spec.output_format,
        )
        result = unwrap_op.run(request)
        output_mesh = Path(result.get("output_mesh", mesh_path))
        return (
            _stage_done(
                "unwrap",
                status=StageStatus.succeeded,
                started=started,
                output={"output_mesh": str(output_mesh)},
            ),
            output_mesh,
        )
    except Exception as exc:
        return (
            _stage_done(
                "unwrap",
                status=StageStatus.failed,
                started=started,
                error=f"{type(exc).__name__}: {exc}",
            ),
            mesh_path,
        )


def _run_texture(
    spec: AssetSpec,
    *,
    asset_dir: Path,
    mesh_path: Path,
) -> tuple[StageRecord, Path]:
    started = time.monotonic()
    if not spec.run_texture:
        return (
            _stage_done("texture", status=StageStatus.skipped, started=started, notes="run_texture=False"),
            mesh_path,
        )
    try:
        from ..operations import workers as worker_ops

        request = TextureMeshRequest(
            input_mesh_path=mesh_path,
            prompt=spec.texture_prompt or spec.description,
            output_dir=asset_dir,
            worker=None,
            seed=spec.seed,
            output_format=spec.output_format,
            texture_size=spec.texture_size,
        )
        result = worker_ops.run_texture_mesh(request)
        return (
            _stage_done(
                "texture",
                status=StageStatus.succeeded,
                started=started,
                output={
                    "output_mesh": str(result.get("output_mesh", mesh_path)),
                    "texture_map": result.get("texture_map"),
                    "worker": result.get("worker"),
                },
            ),
            Path(result.get("output_mesh", mesh_path)),
        )
    except Exception as exc:
        return (
            _stage_done(
                "texture",
                status=StageStatus.failed,
                started=started,
                error=f"{type(exc).__name__}: {exc}",
            ),
            mesh_path,
        )


def _run_cite(
    spec: AssetSpec,
    *,
    kb: KnowledgeBase,
    asset_dir: Path,
    concept_ids: list[str],
) -> StageRecord:
    started = time.monotonic()
    if not concept_ids:
        return _stage_done(
            "cite",
            status=StageStatus.skipped,
            started=started,
            notes="no concept hits to cite",
        )
    try:
        builder = ManifestBuilder.for_dir(asset_dir, asset_id=spec.asset_id)
        for concept_id in concept_ids:
            citation = kb.make_citation(
                concept_id, note=f"concept query: {spec.concept_query}"
            )
            builder.add_concept_citation(citation)
        builder.write()
        return _stage_done(
            "cite",
            status=StageStatus.succeeded,
            started=started,
            output={"concept_ids": concept_ids},
        )
    except Exception as exc:
        return _stage_done(
            "cite",
            status=StageStatus.failed,
            started=started,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_annotate(
    spec: AssetSpec,
    *,
    plan: VerticalSlicePlan,
    asset_dir: Path,
) -> StageRecord:
    started = time.monotonic()
    if not manifest_exists(asset_dir):
        return _stage_done(
            "annotate",
            status=StageStatus.skipped,
            started=started,
            notes="no manifest yet",
        )
    try:
        builder = ManifestBuilder.for_dir(asset_dir, asset_id=spec.asset_id)
        builder.with_name(spec.name)
        license_spec = spec.license or plan.brief.license
        builder.with_license(license_spec)
        target_engine = spec.target_engine or plan.brief.target_engine
        if not builder.has_engine_target(target_engine):
            builder.add_engine_target(EngineTargetSpec(engine=target_engine))
        for tag in plan.brief.tags + spec.tags + [spec.kind.value]:
            builder.add_tag(tag)
        builder.write()
        return _stage_done(
            "annotate",
            status=StageStatus.succeeded,
            started=started,
            output={"target_engine": target_engine.value},
        )
    except Exception as exc:
        return _stage_done(
            "annotate",
            status=StageStatus.failed,
            started=started,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_audit(
    spec: AssetSpec,
    *,
    plan: VerticalSlicePlan,
    asset_dir: Path,
) -> StageRecord:
    started = time.monotonic()
    if plan.skip_audit:
        return _stage_done(
            "audit",
            status=StageStatus.skipped,
            started=started,
            notes="plan.skip_audit=True",
        )
    target_engine = spec.target_engine or plan.brief.target_engine
    preset_name = spec.audit_preset or target_engine.value
    if preset_name not in {"default", "unity", "unreal"}:
        preset_name = "default"
    try:
        report = run_audit(asset_dir, preset=preset_name, run_gltf_validator=True)
        return _stage_done(
            "audit",
            status=StageStatus.succeeded if report.status != "failed" else StageStatus.failed,
            started=started,
            output={
                "preset": report.preset,
                "status": report.status,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "info_count": report.info_count,
            },
            notes=f"audit {report.status}",
        )
    except Exception as exc:
        return _stage_done(
            "audit",
            status=StageStatus.failed,
            started=started,
            error=f"{type(exc).__name__}: {exc}",
        )


def _run_handoff(
    spec: AssetSpec,
    *,
    plan: VerticalSlicePlan,
    asset_dir: Path,
    engines: EngineRegistry,
) -> StageRecord:
    started = time.monotonic()
    if plan.skip_handoff:
        return _stage_done(
            "handoff",
            status=StageStatus.skipped,
            started=started,
            notes="plan.skip_handoff=True",
        )
    target_engine = spec.target_engine or plan.brief.target_engine
    try:
        adapter = engines.get(target_engine.value)
    except KeyError:
        return _stage_done(
            "handoff",
            status=StageStatus.skipped,
            started=started,
            notes=f"no adapter for engine {target_engine.value}",
        )

    probe = adapter.probe()
    if not probe.configured:
        return _stage_done(
            "handoff",
            status=StageStatus.skipped,
            started=started,
            notes=f"adapter unconfigured: {probe.reason}",
        )

    try:
        result = adapter.send_asset(
            asset_dir,
            target_path=spec.handoff_target_path,
            audit=False,  # already audited in the previous stage
            force=False,
        )
        return _stage_done(
            "handoff",
            status=StageStatus.succeeded,
            started=started,
            output={
                "engine": result.engine,
                "target_path": result.target_path,
                "transport": result.transport,
                "tool": result.tool,
            },
            notes=f"delivered to {result.engine}",
        )
    except EngineHandoffError as exc:
        return _stage_done(
            "handoff",
            status=StageStatus.failed,
            started=started,
            error=f"{type(exc).__name__}: {exc}",
        )


# ---------------------------------------------------------------------------
# Top-level executor
# ---------------------------------------------------------------------------


def execute_vertical_slice(
    plan: VerticalSlicePlan,
    *,
    store: SliceStore,
    kb: KnowledgeBase,
    engines: EngineRegistry,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> VerticalSliceRun:
    """Run every asset in the plan and return the persisted run state.

    The function is designed to be safe to re-call: assets that already
    finished successfully in a prior run are skipped. Cancellation
    halts the slice between assets (not mid-stage) so the underlying
    operation always completes once started.
    """

    run = store.get_or_init_run(plan)
    run = run.model_copy(
        update={
            "status": StageStatus.running,
            "started_at": run.started_at or utc_now(),
        }
    )
    store.save_run(run)

    total = max(len(plan.assets), 1)
    failed_count = 0

    for index, spec in enumerate(plan.assets):
        if cancel is not None and cancel.is_cancel_requested():
            run = run.model_copy(
                update={
                    "status": StageStatus.cancelled,
                    "finished_at": utc_now(),
                }
            )
            store.save_run(run)
            return run

        existing_state = run.assets.get(spec.asset_id)
        if existing_state is not None and existing_state.status in {
            StageStatus.succeeded,
            StageStatus.skipped,
        }:
            _emit(reporter, "asset", _percent(index + 1, total), f"skip {spec.asset_id} (already done)")
            continue

        asset_dir = store.asset_dir(plan.slice_id, spec.asset_id)
        asset_dir.mkdir(parents=True, exist_ok=True)
        asset_state = AssetRunState(
            asset_id=spec.asset_id,
            asset_dir=asset_dir,
            status=StageStatus.running,
            stages=[],
            started_at=utc_now(),
        )
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)
        _emit(reporter, "asset", _percent(index, total), f"start {spec.asset_id}")

        # Stage 1: KB search
        kb_record, concept_ids = _run_kb_search(spec, kb=kb)
        asset_state = _append_stage(asset_state, kb_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)

        # Stage 2: Generate
        gen_record, generated_mesh = _run_generate(spec, asset_dir=asset_dir)
        asset_state = _append_stage(asset_state, gen_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)
        if gen_record.status == StageStatus.failed:
            asset_state, run, failed_count = _fail_asset(
                run, store, asset_state, spec.asset_id, gen_record.error, failed_count, plan
            )
            if plan.fail_fast:
                return _finalize_run(run, store, status=StageStatus.failed)
            continue

        mesh_path = generated_mesh or _existing_primary_mesh(asset_dir)
        if mesh_path is None:
            asset_state, run, failed_count = _fail_asset(
                run,
                store,
                asset_state,
                spec.asset_id,
                "no primary mesh after generate",
                failed_count,
                plan,
            )
            if plan.fail_fast:
                return _finalize_run(run, store, status=StageStatus.failed)
            continue

        # Stage 3: Unwrap
        unwrap_record, mesh_path = _run_unwrap(spec, asset_dir=asset_dir, mesh_path=mesh_path)
        asset_state = _append_stage(asset_state, unwrap_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)

        # Stage 4: Texture
        texture_record, mesh_path = _run_texture(
            spec, asset_dir=asset_dir, mesh_path=mesh_path
        )
        asset_state = _append_stage(asset_state, texture_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)

        # Stage 5: Cite
        cite_record = _run_cite(spec, kb=kb, asset_dir=asset_dir, concept_ids=concept_ids)
        asset_state = _append_stage(asset_state, cite_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)

        # Stage 6: Annotate
        annotate_record = _run_annotate(spec, plan=plan, asset_dir=asset_dir)
        asset_state = _append_stage(asset_state, annotate_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)

        # Stage 7: Audit
        audit_record = _run_audit(spec, plan=plan, asset_dir=asset_dir)
        asset_state = _append_stage(asset_state, audit_record)
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)
        if audit_record.status == StageStatus.failed and plan.fail_fast:
            asset_state, run, failed_count = _fail_asset(
                run,
                store,
                asset_state,
                spec.asset_id,
                "audit failed and fail_fast=True",
                failed_count,
                plan,
            )
            return _finalize_run(run, store, status=StageStatus.failed)

        # Stage 8: Handoff (skipped if audit failed; engine adapter
        # gates on its own audit, which would also reject this asset).
        if audit_record.status != StageStatus.failed:
            handoff_record = _run_handoff(
                spec, plan=plan, asset_dir=asset_dir, engines=engines
            )
        else:
            handoff_record = _stage_done(
                "handoff",
                status=StageStatus.skipped,
                started=time.monotonic(),
                notes="audit failed; skipping handoff",
            )
        asset_state = _append_stage(asset_state, handoff_record)

        # Determine final asset status: any failed stage marks the
        # asset failed; otherwise succeeded.
        had_failure = any(
            s.status == StageStatus.failed for s in asset_state.stages
        )
        asset_state = asset_state.model_copy(
            update={
                "status": StageStatus.failed if had_failure else StageStatus.succeeded,
                "finished_at": utc_now(),
                "error": "; ".join(
                    s.error for s in asset_state.stages if s.error
                )
                or None,
            }
        )
        run = _set_asset_state(run, spec.asset_id, state=asset_state)
        store.save_run(run)
        if had_failure:
            failed_count += 1
            if plan.fail_fast:
                return _finalize_run(run, store, status=StageStatus.failed)
        _emit(reporter, "asset", _percent(index + 1, total), f"done {spec.asset_id} ({asset_state.status.value})")

    overall = StageStatus.succeeded if failed_count == 0 else StageStatus.failed
    return _finalize_run(run, store, status=overall)


def _fail_asset(
    run: VerticalSliceRun,
    store: SliceStore,
    asset_state: AssetRunState,
    asset_id: str,
    error: str | None,
    failed_count: int,
    plan: VerticalSlicePlan,
):
    asset_state = asset_state.model_copy(
        update={
            "status": StageStatus.failed,
            "finished_at": utc_now(),
            "error": error or asset_state.error,
        }
    )
    run = _set_asset_state(run, asset_id, state=asset_state)
    store.save_run(run)
    return asset_state, run, failed_count + 1


def _finalize_run(
    run: VerticalSliceRun,
    store: SliceStore,
    *,
    status: StageStatus,
) -> VerticalSliceRun:
    finalized = run.model_copy(
        update={
            "status": status,
            "finished_at": utc_now(),
        }
    )
    store.save_run(finalized)
    return finalized


def _emit(reporter: ProgressReporter | None, stage: str, percent: float, message: str) -> None:
    if reporter is not None:
        reporter(stage, percent, message)


def _percent(done: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return min(100.0, max(0.0, 100.0 * done / total))


def _existing_primary_mesh(asset_dir: Path) -> Path | None:
    if not manifest_exists(asset_dir):
        return None
    from ..manifest import read_manifest

    manifest = read_manifest(asset_dir)
    for artifact in manifest.artifacts:
        if artifact.role == "mesh.primary":
            candidate = Path(artifact.path)
            if not candidate.is_absolute():
                candidate = (asset_dir / candidate).resolve()
            return candidate
    return None


__all__ = ["SliceExecutionError", "execute_vertical_slice"]
