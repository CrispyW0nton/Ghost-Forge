"""Adapter contract: probe states, manifest validation, dry-run flow.

Uses :class:`RecordingTransport` so no real Unity/Unreal MCP server is
required. Each test scopes its work to a fresh ``tmp_path`` and an
isolated ``ManifestBuilder``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.engines import (
    EngineAssetInvalid,
    EngineConfig,
    EngineNotConfigured,
    RecordingTransport,
    UnityEngineAdapter,
    UnrealEngineAdapter,
)
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    read_manifest,
)


def _make_asset(tmp_path: Path, *, with_engine_target: EngineTarget | None = EngineTarget.unity) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    asset_dir = tmp_path / "asset_pkg"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    box.export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="asset_pkg")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0", holder="Test"))
    if with_engine_target is not None:
        builder.add_engine_target(EngineTargetSpec(engine=with_engine_target))
    builder.write()
    return asset_dir


def test_unconfigured_probe_reports_reason():
    adapter = UnityEngineAdapter()
    probe = adapter.probe()
    assert probe.configured is False
    assert probe.transport == "none"
    assert probe.reason and "configure" in probe.reason.lower()


def test_configure_with_mismatched_name_raises():
    adapter = UnityEngineAdapter()
    with pytest.raises(ValueError):
        adapter.configure(EngineConfig(name="not-unity", transport="none"))


def test_stdio_probe_requires_command():
    adapter = UnityEngineAdapter()
    adapter.configure(EngineConfig(name="unity", transport="stdio"))
    probe = adapter.probe()
    assert probe.configured is False
    assert probe.transport == "stdio"
    assert "command" in (probe.reason or "")


def test_stdio_probe_when_command_set():
    adapter = UnityEngineAdapter()
    adapter.configure(
        EngineConfig(
            name="unity",
            transport="stdio",
            command=["python", "-m", "unity_mcp_ghost"],
        )
    )
    probe = adapter.probe()
    assert probe.configured is True
    assert probe.transport == "stdio"
    assert probe.metadata["command"] == ["python", "-m", "unity_mcp_ghost"]


def test_http_probe_requires_url():
    adapter = UnrealEngineAdapter()
    adapter.configure(EngineConfig(name="unreal", transport="http"))
    probe = adapter.probe()
    assert probe.configured is False
    assert "url" in (probe.reason or "")


def test_injected_transport_makes_probe_runnable():
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport(name="unity-test"))
    probe = adapter.probe()
    assert probe.configured is True
    assert probe.transport == "injected"


def test_send_asset_missing_dir_raises(tmp_path):
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    with pytest.raises(EngineAssetInvalid):
        adapter.send_asset(tmp_path / "does-not-exist")


def test_send_asset_missing_manifest_raises(tmp_path):
    asset_dir = tmp_path / "no_manifest"
    asset_dir.mkdir()
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    with pytest.raises(EngineAssetInvalid):
        adapter.send_asset(asset_dir)


def test_send_asset_no_mesh_artifact_raises(tmp_path):
    pytest.importorskip("trimesh")
    asset_dir = tmp_path / "no_mesh"
    asset_dir.mkdir()
    builder = ManifestBuilder.for_dir(asset_dir, asset_id="no_mesh")
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unity))
    builder.write()
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    with pytest.raises(EngineAssetInvalid):
        adapter.send_asset(asset_dir)


def test_send_asset_missing_engine_target_blocks_without_force(tmp_path):
    asset_dir = _make_asset(tmp_path, with_engine_target=EngineTarget.unreal)
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    with pytest.raises(EngineAssetInvalid):
        adapter.send_asset(asset_dir)


def test_send_asset_force_skips_engine_target_check(tmp_path):
    asset_dir = _make_asset(tmp_path, with_engine_target=EngineTarget.unreal)
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    result = adapter.send_asset(asset_dir, force=True, audit=False)
    assert result.engine == "unity"
    assert result.target_path is not None
    assert result.target_path.startswith("Assets/GhostForge/")


def test_send_asset_dry_run_does_not_call_transport(tmp_path):
    asset_dir = _make_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport()
    adapter.set_transport(transport)
    result = adapter.send_asset(asset_dir, dry_run=True, audit=False)
    assert transport.calls == []
    assert result.dry_run is True
    assert result.engine_response["dry_run"] is True
    assert result.transport == "injected"


def test_send_asset_records_provenance_and_handoff_history(tmp_path):
    asset_dir = _make_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport(
        handler=lambda name, args: {
            "content": [{"type": "text", "text": "imported"}],
            "structured": {"engine_id": "abc-123", "tool": name},
            "isError": False,
        }
    )
    adapter.set_transport(transport)
    result = adapter.send_asset(asset_dir, target_path="Assets/Foo/Bar", audit=False)

    assert transport.calls and transport.calls[0][0] == "import_asset"
    payload = transport.calls[0][1]
    assert payload["asset_path"].endswith(".glb")
    assert payload["target_path"] == "Assets/Foo/Bar"
    assert payload["engine"] == "unity"
    assert payload["manifest"]["asset_id"] == "asset_pkg"

    assert result.engine == "unity"
    assert result.engine_response["structured"]["engine_id"] == "abc-123"
    assert result.duration_seconds >= 0.0

    manifest = read_manifest(asset_dir)
    kinds = [step.kind for step in manifest.provenance]
    assert "send_to_unity" in kinds
    history = manifest.custom["engine_handoffs"]
    assert isinstance(history, list) and len(history) == 1
    assert history[0]["engine"] == "unity"
    assert history[0]["transport"] == "injected"
    assert history[0]["target_path"] == "Assets/Foo/Bar"
    assert history[0]["dry_run"] is False


def test_send_asset_extra_args_override_defaults(tmp_path):
    asset_dir = _make_asset(tmp_path)
    adapter = UnityEngineAdapter()
    adapter.configure(
        EngineConfig(
            name="unity",
            transport="none",
            import_args_extra={"static": True, "compress": "uncompressed"},
        )
    )
    transport = RecordingTransport()
    adapter.set_transport(transport)
    adapter.send_asset(
        asset_dir, extra_args={"compress": "max", "version": 7}, audit=False
    )

    payload = transport.calls[0][1]
    assert payload["static"] is True
    # per-call extra_args override import_args_extra defaults
    assert payload["compress"] == "max"
    assert payload["version"] == 7


def test_unreal_default_target_path(tmp_path):
    asset_dir = _make_asset(tmp_path, with_engine_target=EngineTarget.unreal)
    adapter = UnrealEngineAdapter()
    adapter.set_transport(RecordingTransport())
    result = adapter.send_asset(asset_dir, audit=False)
    assert result.target_path is not None
    assert result.target_path.startswith("/Game/GhostForge/")


def test_send_asset_engine_returns_error_raises(tmp_path):
    from ghostforge_core.engines import EngineCallError

    asset_dir = _make_asset(tmp_path)
    adapter = UnityEngineAdapter()
    adapter.set_transport(
        RecordingTransport(
            handler=lambda name, args: {
                "content": [{"type": "text", "text": "import failed: missing UVs"}],
                "isError": True,
            }
        )
    )
    with pytest.raises(EngineCallError):
        adapter.send_asset(asset_dir, audit=False)


def test_send_asset_without_transport_raises(tmp_path):
    asset_dir = _make_asset(tmp_path)
    adapter = UnityEngineAdapter()  # transport='none', no injection
    with pytest.raises(EngineNotConfigured):
        adapter.send_asset(asset_dir, audit=False)


def test_send_asset_adds_engine_target_after_force(tmp_path):
    asset_dir = _make_asset(tmp_path, with_engine_target=EngineTarget.unreal)
    adapter = UnityEngineAdapter()
    adapter.set_transport(RecordingTransport())
    adapter.send_asset(asset_dir, force=True, audit=False)

    manifest = read_manifest(asset_dir)
    targets = {spec.engine for spec in manifest.engine_targets}
    assert EngineTarget.unity in targets
    assert EngineTarget.unreal in targets
