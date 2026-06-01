"""End-to-end MCP tests for the P12 retarget tool surface."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _unwrap(value):
    if (
        isinstance(value, dict)
        and set(value.keys()) == {"result"}
        and not isinstance(value["result"], dict)
    ):
        return value["result"]
    return value


def _payload(result):
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, (dict, list)):
            return _unwrap(structured)
        for item in content:
            text = getattr(item, "text", None)
            if text is None:
                continue
            try:
                return _unwrap(json.loads(text))
            except json.JSONDecodeError:
                continue
        raise AssertionError(f"no payload in {result!r}")

    for item in result:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            return _unwrap(json.loads(text))
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"no payload in {result!r}")


@pytest.fixture(autouse=True)
def isolated_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "0")

    from ghostforge_mcp import server as server_mod

    server_mod.reset_context_for_tests()
    yield
    server_mod.reset_context_for_tests()


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


def _server():
    from ghostforge_mcp.server import build_server

    return build_server()


def _call(server, name, args=None):
    return _payload(asyncio.run(server.call_tool(name, args or {})))


def test_p12_tools_registered():
    tools = asyncio.run(_server().list_tools())
    names = {t.name for t in tools}
    expected = {"list_engine_profiles", "lint_for_engine", "generate_retarget_graph"}
    missing = expected - names
    assert not missing, f"missing P12 tools: {missing}"


def test_list_engine_profiles_returns_known_profiles():
    payload = _call(_server(), "list_engine_profiles")
    names = {p["name"] for p in payload}
    assert names == {"gltf_canonical", "unity", "unreal"}


def test_lint_for_engine_unreal_returns_diagnostics(asset_dir):
    payload = _call(
        _server(),
        "lint_for_engine",
        {"asset_dir": str(asset_dir), "target_engine": "unreal"},
    )
    issue_codes = {i["code"] for i in payload["issues"]}
    assert "axis_mismatch_assumed" in issue_codes
    assert "units_scale_required" in issue_codes


def test_lint_for_engine_rejects_unknown_target(asset_dir):
    with pytest.raises(Exception):
        _call(
            _server(),
            "lint_for_engine",
            {"asset_dir": str(asset_dir), "target_engine": "godot"},
        )


def test_generate_retarget_graph_yields_full_chain(asset_dir):
    payload = _call(
        _server(),
        "generate_retarget_graph",
        {
            "asset_dir": str(asset_dir),
            "target_engine": "unreal",
            "base_name": "HeroBox",
        },
    )
    kinds = [n["kind"] for n in payload["graph"]["nodes"]]
    assert "retarget_axis" in kinds
    assert "retarget_units" in kinds
    assert "retarget_apply_naming" in kinds


def test_generate_retarget_graph_persist_saves_to_store(asset_dir):
    server = _server()
    payload = _call(
        server,
        "generate_retarget_graph",
        {
            "asset_dir": str(asset_dir),
            "target_engine": "unreal",
            "base_name": "HeroBox",
            "persist_graph": True,
        },
    )
    gid = payload["graph"]["graph_id"]
    listed = _call(server, "list_edit_graphs")
    assert any(g["graph_id"] == gid for g in listed)
