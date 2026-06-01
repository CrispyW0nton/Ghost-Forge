"""Black-box tests for the v2 retarget routes."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def asset_dir(tmp_path: Path) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    from ghostforge_core.manifest import (
        EngineTarget,
        EngineTargetSpec,
        LicenseSpec,
        ManifestBuilder,
    )

    base = tmp_path / "asset"
    base.mkdir()
    mesh_path = base / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 2.0, 3.0)).export(mesh_path)
    builder = ManifestBuilder.for_dir(base, asset_id="hero_box")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unreal))
    builder.write()
    return base


def test_retarget_profiles_lists_three(client):
    resp = client.get("/api/v2/retarget/profiles")
    assert resp.status_code == 200
    body = resp.get_json()
    names = {p["name"] for p in body["profiles"]}
    assert names == {"gltf_canonical", "unity", "unreal"}


def test_retarget_lint_requires_target(client, asset_dir):
    resp = client.post(
        "/api/v2/retarget/lint",
        json={"asset_dir": str(asset_dir)},
    )
    assert resp.status_code == 400


def test_retarget_lint_unreal_returns_report(client, asset_dir):
    resp = client.post(
        "/api/v2/retarget/lint",
        json={"asset_dir": str(asset_dir), "target_engine": "unreal"},
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["preset"] == "unreal"
    issue_codes = {i["code"] for i in body["issues"]}
    assert "axis_mismatch_assumed" in issue_codes
    assert "units_scale_required" in issue_codes


def test_retarget_lint_missing_asset_returns_404(client, tmp_path):
    resp = client.post(
        "/api/v2/retarget/lint",
        json={"asset_dir": str(tmp_path / "nope"), "target_engine": "unity"},
    )
    assert resp.status_code == 404


def test_retarget_plan_returns_graph_and_report(client, asset_dir):
    resp = client.post(
        "/api/v2/retarget/plan",
        json={
            "asset_dir": str(asset_dir),
            "target_engine": "unreal",
            "base_name": "HeroBox",
        },
    )
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert "graph" in body and "report" in body
    kinds = [n["kind"] for n in body["graph"]["nodes"]]
    assert "retarget_axis" in kinds
    assert "retarget_units" in kinds


def test_retarget_plan_persist_writes_graph(client, asset_dir):
    resp = client.post(
        "/api/v2/retarget/plan",
        json={
            "asset_dir": str(asset_dir),
            "target_engine": "unreal",
            "base_name": "HeroBox",
            "persist_graph": True,
        },
    )
    assert resp.status_code == 200
    gid = resp.get_json()["graph"]["graph_id"]
    listed = client.get("/api/v2/graphs").get_json()["graphs"]
    assert any(g["graph_id"] == gid for g in listed)


def test_retarget_plan_unknown_target(client, asset_dir):
    resp = client.post(
        "/api/v2/retarget/plan",
        json={"asset_dir": str(asset_dir), "target_engine": "godot"},
    )
    assert resp.status_code == 400
