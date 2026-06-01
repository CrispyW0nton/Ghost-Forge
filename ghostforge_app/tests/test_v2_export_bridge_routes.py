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
    builder.write()
    return asset_dir


def test_export_bridge_route_writes_package(client, tmp_path):
    asset_dir = _asset_with_manifest(tmp_path)

    resp = client.post(
        "/api/v2/engines/unreal/export-bridge",
        json={"asset_dir": str(asset_dir), "target_path": "/Game/GhostForge/crate_01"},
    )

    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["direct_engine_call"] is False
    assert Path(body["package_path"]).exists()
    assert body["package"]["recommended_mcp_server"] == "Unreal-MCP-Ghost"


def test_export_bridge_route_rejects_unknown_target(client, tmp_path):
    asset_dir = _asset_with_manifest(tmp_path)
    resp = client.post(
        "/api/v2/engines/godot/export-bridge",
        json={"asset_dir": str(asset_dir)},
    )
    assert resp.status_code == 404


def test_export_bridge_route_requires_asset_dir(client):
    resp = client.post("/api/v2/engines/unreal/export-bridge", json={})
    assert resp.status_code == 400
