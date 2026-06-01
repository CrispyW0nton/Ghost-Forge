"""MCP tool surface for game-readiness audit."""

from __future__ import annotations

import asyncio
import json
import time
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


def _seed_asset(tmp_path: Path) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    from ghostforge_core.manifest import (
        EngineTarget,
        EngineTargetSpec,
        LicenseSpec,
        ManifestBuilder,
    )

    asset_dir = tmp_path / "asset_audit"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="asset_audit")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unity))
    builder.write()
    return asset_dir


def test_audit_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {"list_audit_presets", "audit_asset", "submit_audit"}.issubset(names)


def test_list_audit_presets_returns_three():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("list_audit_presets", {}))
    payload = _payload(result)
    assert isinstance(payload, list)
    names = {p["name"] for p in payload}
    assert names == {"default", "unity", "unreal"}


def test_audit_asset_default_preset_passes_basic(tmp_path):
    from ghostforge_mcp.server import build_server

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    result = asyncio.run(
        server.call_tool(
            "audit_asset",
            {
                "asset_dir": str(asset_dir),
                "preset": "default",
                "run_gltf_validator": False,
            },
        )
    )
    payload = _payload(result)
    assert payload["preset"] == "default"
    assert payload["status"] in {"passed", "warnings"}
    assert "rules" in payload and len(payload["rules"]) >= 1


def test_audit_asset_unity_preset_fails_for_uv_less_box(tmp_path):
    from ghostforge_mcp.server import build_server

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    result = asyncio.run(
        server.call_tool(
            "audit_asset",
            {
                "asset_dir": str(asset_dir),
                "preset": "unity",
                "run_gltf_validator": False,
                "persist": False,
            },
        )
    )
    payload = _payload(result)
    assert payload["status"] == "failed"
    assert payload["error_count"] >= 1


def test_audit_asset_persists_history_in_manifest(tmp_path):
    from ghostforge_core.manifest import read_manifest
    from ghostforge_mcp.server import build_server

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    asyncio.run(
        server.call_tool(
            "audit_asset",
            {
                "asset_dir": str(asset_dir),
                "preset": "default",
                "run_gltf_validator": False,
            },
        )
    )
    manifest = read_manifest(asset_dir)
    assert "audit_history" in manifest.custom
    assert len(manifest.custom["audit_history"]) == 1


def test_audit_asset_unknown_preset_errors(tmp_path):
    from ghostforge_mcp.server import build_server

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "audit_asset",
                {"asset_dir": str(asset_dir), "preset": "godot"},
            )
        )


def test_submit_audit_runs_through_runner(tmp_path):
    from ghostforge_mcp.server import build_server, get_context

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    submit = asyncio.run(
        server.call_tool(
            "submit_audit",
            {
                "asset_dir": str(asset_dir),
                "preset": "default",
                "run_gltf_validator": False,
            },
        )
    )
    handle = _payload(submit)
    assert handle["kind"] == "audit_asset"
    job_id = handle["id"]

    deadline = time.monotonic() + 10.0
    final = handle
    while time.monotonic() < deadline:
        final = _payload(asyncio.run(server.call_tool("get_job", {"job_id": job_id})))
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    get_context().runner.shutdown(wait=True)
    assert final["status"] == "succeeded", f"job did not succeed: {final}"
    assert final["result"]["preset"] == "default"
