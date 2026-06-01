from __future__ import annotations

from pathlib import Path

import pytest


def _asset_with_manifest(tmp_path: Path):
    trimesh = pytest.importorskip("trimesh")
    from ghostforge_core.manifest import (
        EngineTarget,
        EngineTargetSpec,
        ManifestBuilder,
    )
    from ghostforge_core.storage import compute_artifact

    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(str(mesh_path))

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="crate_01")
    builder.add_artifact(compute_artifact(mesh_path, role="mesh.primary"))
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unreal))
    manifest, _ = builder.write()
    return asset_dir, mesh_path, manifest


def test_create_export_bridge_package_writes_json_and_manifest_record(tmp_path):
    from ghostforge_core.export_bridge import create_export_bridge_package
    from ghostforge_core.manifest import read_manifest

    asset_dir, mesh_path, _ = _asset_with_manifest(tmp_path)

    package, package_path = create_export_bridge_package(
        asset_dir,
        target_engine="unreal",
        target_path="/Game/GhostForge/crate_01",
    )

    assert package_path.exists()
    assert package.target_engine.value == "unreal"
    assert package.recommended_mcp_server == "Unreal-MCP-Ghost"
    assert package.asset_path == mesh_path.resolve()
    assert package.target_path == "/Game/GhostForge/crate_01"

    manifest = read_manifest(asset_dir)
    assert any(a.role == "engine.bridge.unreal" for a in manifest.artifacts)
    assert manifest.custom["engine_export_bridges"][-1]["direct_engine_call"] is False
    assert any(step.kind == "export_bridge_unreal" for step in manifest.provenance)


def test_create_export_bridge_package_supports_custom_bridge_dir(tmp_path):
    from ghostforge_core.export_bridge import create_export_bridge_package

    asset_dir, _, _ = _asset_with_manifest(tmp_path)
    bridge_dir = tmp_path / "bridges"
    _, package_path = create_export_bridge_package(
        asset_dir,
        target_engine="unity",
        bridge_dir=bridge_dir,
    )

    assert package_path.parent == bridge_dir.resolve()
    assert package_path.name == "ghostforge_bridge_unity.json"


def test_create_export_bridge_package_rejects_missing_manifest(tmp_path):
    from ghostforge_core.export_bridge import ExportBridgeError, create_export_bridge_package

    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    with pytest.raises(ExportBridgeError):
        create_export_bridge_package(asset_dir, target_engine="unreal")


def test_create_export_bridge_package_rejects_unsupported_engine(tmp_path):
    from ghostforge_core.export_bridge import ExportBridgeError, create_export_bridge_package

    asset_dir, _, _ = _asset_with_manifest(tmp_path)
    with pytest.raises(ExportBridgeError):
        create_export_bridge_package(asset_dir, target_engine="godot")
