"""Vertical slice executor end-to-end (via stub workers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.engines import (
    EngineConfig,
    RecordingTransport,
)
from ghostforge_core.manifest import (
    EngineTarget,
    LicenseSpec,
    manifest_exists,
    read_manifest,
)
from ghostforge_core.slice import (
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    StageStatus,
    execute_vertical_slice,
    plan_vertical_slice,
)


pytest.importorskip("trimesh")


@pytest.fixture
def ctx(tmp_path: Path):
    config = CoreConfig(data_root=tmp_path, dispatch_jobs=False)
    return bootstrap(config)


def _brief(engine: EngineTarget = EngineTarget.unity) -> GameBrief:
    return GameBrief(
        title="Haunted Forest Slice",
        description="A short atmospheric vertical slice.",
        target_engine=engine,
        license=LicenseSpec(spdx="CC0-1.0"),
        tags=["forest", "horror"],
    )


def _spec(asset_id: str, **overrides) -> AssetSpec:
    base = dict(
        asset_id=asset_id,
        description=f"A {asset_id} prop",
        strategy=GenerationStrategy.image_to_3d,
        reference_image_path=Path(__file__),
        worker="stub_image_to_3d",
        run_unwrap=False,
        run_texture=False,
        # Stub workers emit a bare cube with no UVs/normals; default preset
        # is permissive enough that the executor's audit stage passes.
        audit_preset="default",
    )
    base.update(overrides)
    return AssetSpec(**base)


def test_executor_runs_image_to_3d_slice_with_stub(ctx):
    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(),
        assets=[_spec("rock_01"), _spec("tree_01")],
        slice_id="slice-stub",
        skip_handoff=True,  # no engine adapter configured
    )

    run = execute_vertical_slice(
        plan,
        store=ctx.slices,
        kb=ctx.kb,
        engines=ctx.engines,
    )

    assert run.status == StageStatus.succeeded
    assert set(run.assets) == {"rock_01", "tree_01"}
    for state in run.assets.values():
        assert state.status == StageStatus.succeeded
        # Generate, audit, handoff (skipped) all recorded
        stage_names = [s.stage for s in state.stages]
        assert "generate" in stage_names
        assert "audit" in stage_names
        assert "handoff" in stage_names
        # Manifest emitted with engine target and license
        manifest = read_manifest(state.asset_dir)
        assert manifest.license is not None and manifest.license.spdx == "CC0-1.0"
        assert any(t.engine == EngineTarget.unity for t in manifest.engine_targets)


def test_executor_runs_text_to_3d_slice_with_explicit_worker(ctx):
    from ghostforge_core.workers.stub import StubTextTo3DWorker

    ctx.workers.register(StubTextTo3DWorker())
    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(),
        assets=[
            _spec(
                "obelisk_01",
                strategy=GenerationStrategy.text_to_3d,
                reference_image_path=None,
                worker="stub_text_to_3d",
                generation_extras={"smart_low_poly": True, "face_limit": 8000},
            )
        ],
        slice_id="slice-text-stub",
        skip_handoff=True,
    )

    run = execute_vertical_slice(
        plan,
        store=ctx.slices,
        kb=ctx.kb,
        engines=ctx.engines,
    )

    state = run.assets["obelisk_01"]
    assert state.status == StageStatus.succeeded
    generate = next(stage for stage in state.stages if stage.stage == "generate")
    assert generate.output["strategy"] == "text_to_3d"
    manifest = read_manifest(state.asset_dir)
    step = next(s for s in manifest.provenance if s.kind == "text_to_3d")
    assert step.parameters["worker"] == "stub_text_to_3d"
    assert step.parameters["extras"]["smart_low_poly"] is True


def test_executor_skips_handoff_when_adapter_unconfigured(ctx):
    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(),
        assets=[_spec("rock")],
        slice_id="slice-unconfigured",
    )
    run = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )
    handoff = [
        s for s in run.assets["rock"].stages if s.stage == "handoff"
    ][-1]
    assert handoff.status == StageStatus.skipped
    assert "unconfigured" in (handoff.notes or "").lower()


def test_executor_delivers_to_engine_via_recording_transport(tmp_path):
    config = CoreConfig(data_root=tmp_path, dispatch_jobs=False)
    ctx = bootstrap(config)

    transport = RecordingTransport(name="unity-rec")
    unity = ctx.engines.get("unity")
    unity.configure(
        EngineConfig(
            name="unity",
            transport="none",
            import_tool="ghost.import_asset",
            description="recording adapter",
        )
    )
    unity.set_transport(transport)

    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(EngineTarget.unity),
        assets=[
            _spec(
                "rock_engine",
                target_engine=EngineTarget.unity,
                handoff_target_path="Assets/GhostForge/Slices/rock_engine.glb",
                audit_preset="default",  # avoid strict UV requirement on the bare cube
            )
        ],
        slice_id="slice-delivery",
        skip_audit=False,
    )
    run = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )

    state = run.assets["rock_engine"]
    handoff_records = [s for s in state.stages if s.stage == "handoff"]
    assert handoff_records, "handoff stage should run"
    assert handoff_records[-1].status == StageStatus.succeeded
    assert transport.calls, "transport should have been invoked"
    tool_name, args = transport.calls[-1]
    assert tool_name == "ghost.import_asset"
    assert "manifest" in args


def test_executor_fail_fast_aborts_on_failure(tmp_path):
    config = CoreConfig(data_root=tmp_path, dispatch_jobs=False)
    ctx = bootstrap(config)

    bad_spec = AssetSpec(
        asset_id="bad",
        description="Should fail because no input mesh exists",
        strategy=GenerationStrategy.skip_generation,
    )
    # plan_vertical_slice rejects this up-front because the path is None;
    # so we save by hand to test the executor's failure path.
    from ghostforge_core.slice.schema import VerticalSlicePlan

    plan = VerticalSlicePlan(
        slice_id="slice-fail",
        brief=_brief(),
        assets=[bad_spec, _spec("good")],
        fail_fast=True,
        skip_handoff=True,
    )
    ctx.slices.save_plan(plan)

    run = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )
    assert run.status == StageStatus.failed
    # The "good" asset should never have been touched
    assert run.assets["bad"].status == StageStatus.failed
    assert run.assets["good"].status == StageStatus.pending


def test_executor_resumes_skipping_completed_assets(ctx):
    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(),
        assets=[_spec("a"), _spec("b")],
        slice_id="slice-resume",
        skip_handoff=True,
    )
    first = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )
    assert first.status == StageStatus.succeeded
    a_finished = first.assets["a"].finished_at

    # Mutate the asset_dir to verify the second run does NOT touch it
    asset_a_dir = ctx.slices.asset_dir("slice-resume", "a")
    sentinel = asset_a_dir / "DO_NOT_DELETE.txt"
    sentinel.write_text("kept", encoding="utf-8")

    second = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )
    assert second.assets["a"].finished_at == a_finished, "completed asset should be skipped"
    assert sentinel.exists()


def test_executor_writes_manifest_with_concept_citations_when_kb_seeded(ctx):
    pytest.importorskip("PIL")
    from PIL import Image

    img_path = ctx.storage.uploads_dir / "sample.png"
    Image.new("RGB", (32, 32), (123, 200, 50)).save(img_path)

    from ghostforge_core.kb.ingest import ingest_local_image

    entry = ingest_local_image(
        kb=ctx.kb,
        path=img_path,
        title="Mossy Boulder Reference",
        license="CC0-1.0",
        tags=["rock"],
    )
    assert entry.id

    plan = plan_vertical_slice(
        store=ctx.slices,
        brief=_brief(),
        assets=[
            _spec(
                "boulder",
                concept_query="mossy boulder",
                concept_tags=["rock"],
                concept_k=1,
            )
        ],
        slice_id="slice-kb",
        skip_handoff=True,
    )
    run = execute_vertical_slice(
        plan, store=ctx.slices, kb=ctx.kb, engines=ctx.engines
    )
    state = run.assets["boulder"]
    assert state.status == StageStatus.succeeded
    cite_record = next(s for s in state.stages if s.stage == "cite")
    assert cite_record.status == StageStatus.succeeded

    manifest = read_manifest(state.asset_dir)
    assert manifest.concept_citations, "expected a concept citation on the manifest"
