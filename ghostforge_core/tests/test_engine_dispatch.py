"""Operation-level + job-runner integration for engine handoff."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.engines import EngineHandoffError, RecordingTransport
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    read_manifest,
)
from ghostforge_core.operations.engines import run_send_to_engine
from ghostforge_core.types import JobStatus, SendToEngineRequest


def _seed_asset(tmp_path: Path, target: EngineTarget = EngineTarget.unity) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(2.0, 2.0, 2.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="dispatch-test")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    builder.add_engine_target(EngineTargetSpec(engine=target))
    builder.write()
    return asset_dir


def test_operation_dry_run_no_transport_required(tmp_path):
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    asset_dir = _seed_asset(tmp_path)

    spec = SendToEngineRequest(
        asset_dir=asset_dir,
        engine="unity",
        dry_run=True,
        target_path="Assets/GhostForge/dispatch-test",
        audit=False,
    )
    result = run_send_to_engine(spec)
    assert result["dry_run"] is True
    assert result["engine"] == "unity"
    assert result["target_path"] == "Assets/GhostForge/dispatch-test"

    manifest = read_manifest(asset_dir)
    assert "engine_handoffs" in manifest.custom


def test_operation_unconfigured_real_call_errors(tmp_path):
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    asset_dir = _seed_asset(tmp_path)

    spec = SendToEngineRequest(
        asset_dir=asset_dir, engine="unity", dry_run=False, audit=False
    )
    with pytest.raises(EngineHandoffError):
        run_send_to_engine(spec)


def test_operation_with_injected_transport(tmp_path):
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    asset_dir = _seed_asset(tmp_path)

    transport = RecordingTransport(
        handler=lambda name, args: {
            "content": [{"type": "text", "text": "ok"}],
            "structured": {"engine_id": "unity-1"},
            "isError": False,
        }
    )
    ctx.engines.get("unity").set_transport(transport)

    spec = SendToEngineRequest(asset_dir=asset_dir, engine="unity", audit=False)
    result = run_send_to_engine(spec)
    assert result["engine"] == "unity"
    assert result["engine_response"]["structured"]["engine_id"] == "unity-1"
    assert transport.calls and transport.calls[0][0] == "import_asset"


def test_operation_unknown_engine_errors(tmp_path):
    bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    asset_dir = _seed_asset(tmp_path)
    spec = SendToEngineRequest(asset_dir=asset_dir, engine="godot")
    with pytest.raises(EngineHandoffError):
        run_send_to_engine(spec)


def test_send_to_engine_through_job_runner(tmp_path):
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    try:
        asset_dir = _seed_asset(tmp_path)
        ctx.engines.get("unity").set_transport(RecordingTransport())

        spec = SendToEngineRequest(asset_dir=asset_dir, engine="unity", audit=False)
        handle = ctx.runner.submit("send_to_engine", spec)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            handle = ctx.jobs.get(handle.id)
            if handle.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                break
            time.sleep(0.05)
        assert handle.status == JobStatus.succeeded, handle.error
        assert handle.result is not None
        assert handle.result["engine"] == "unity"
    finally:
        ctx.runner.shutdown(wait=True)


def test_dry_run_through_job_runner_unconfigured(tmp_path):
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    try:
        asset_dir = _seed_asset(tmp_path)

        spec = SendToEngineRequest(
            asset_dir=asset_dir, engine="unreal", dry_run=True, audit=False
        )
        handle = ctx.runner.submit("send_to_engine", spec)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            handle = ctx.jobs.get(handle.id)
            if handle.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                break
            time.sleep(0.05)
        # The asset's engine_targets is unity, not unreal — without force this
        # should fail at the EngineAssetInvalid stage.
        assert handle.status == JobStatus.failed
        assert handle.error is not None

        spec_force = SendToEngineRequest(
            asset_dir=asset_dir,
            engine="unreal",
            dry_run=True,
            force=True,
            audit=False,
        )
        handle2 = ctx.runner.submit("send_to_engine", spec_force)
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            handle2 = ctx.jobs.get(handle2.id)
            if handle2.status in {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}:
                break
            time.sleep(0.05)
        assert handle2.status == JobStatus.succeeded, handle2.error
        assert handle2.result is not None and handle2.result["dry_run"] is True
    finally:
        ctx.runner.shutdown(wait=True)
