from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest


def _make_dummy_mesh(tmp_path: Path) -> Path:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh_path = tmp_path / "cube.obj"
    mesh.export(str(mesh_path))
    return mesh_path


def _extract_payload(result: object) -> dict:
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, dict):
            return structured
        for item in content:
            text = getattr(item, "text", None)
            if text is None:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
        raise AssertionError(f"no JSON payload in result {result!r}")

    for item in result:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"no JSON payload in result {result!r}")


def test_mesh_info_tool_returns_geometry_stats(tmp_path):
    pytest.importorskip("trimesh")

    mesh_path = _make_dummy_mesh(tmp_path)
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("mesh_info", {"mesh_path": str(mesh_path)}))
    payload = _extract_payload(result)

    assert payload["vertices"] > 0
    assert payload["faces"] > 0
    assert payload["format"] == ".obj"


def test_submit_unwrap_then_get_job_via_mcp(tmp_path):
    pytest.importorskip("trimesh")
    pytest.importorskip("xatlas")

    mesh_path = _make_dummy_mesh(tmp_path)
    from ghostforge_mcp.server import build_server, get_context

    server = build_server()
    submit_result = asyncio.run(
        server.call_tool(
            "submit_unwrap",
            {
                "input_mesh_path": str(mesh_path),
                "output_dir": str(tmp_path / "out"),
                "atlas_size": 512,
            },
        )
    )
    handle = _extract_payload(submit_result)
    assert handle["kind"] == "unwrap_uvs"
    assert handle["status"] in {"pending", "running", "succeeded"}
    job_id = handle["id"]

    deadline = time.monotonic() + 60
    final = handle
    while time.monotonic() < deadline:
        get_result = asyncio.run(server.call_tool("get_job", {"job_id": job_id}))
        final = _extract_payload(get_result)
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.25)

    runner = get_context().runner
    runner.shutdown(wait=True)

    assert final["status"] == "succeeded", (
        f"unwrap job did not succeed: status={final['status']} error={final.get('error')}"
    )
