"""End-to-end MCP coverage for the streaming evaluator tool."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
import trimesh


def _payload(result):
    """Mirror the helper used by the other MCP test modules."""
    if isinstance(result, tuple):
        _, structured = result
        if isinstance(structured, (dict, list)):
            return structured
    for item in result if isinstance(result, list) else result[0]:
        text = getattr(item, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
    raise AssertionError(f"no payload in {result!r}")


def _call(server, name, args=None):
    return _payload(asyncio.run(server.call_tool(name, args or {})))


@pytest.fixture(autouse=True)
def isolated_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "0")

    from ghostforge_mcp import server as server_mod

    server_mod.reset_context_for_tests()
    yield
    server_mod.reset_context_for_tests()


def _server():
    from ghostforge_mcp.server import build_server

    return build_server()


def test_streaming_tool_registered():
    server = _server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert "evaluate_edit_graph_streaming" in names


def test_streaming_tool_returns_terminal_result(tmp_path):
    base = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(base))
    out = tmp_path / "out.glb"

    server = _server()
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "stream",
            "base_asset_path": str(base),
            "output_path": str(out),
        },
    )["graph_id"]
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "recompute_normals"},
    )

    payload = _call(server, "evaluate_edit_graph_streaming", {"graph_id": gid})
    assert payload["events_seen"] is True
    final = payload["result"]
    assert final["status"] == "succeeded"
    assert Path(final["output_path"]).exists()


def test_streaming_tool_writes_manifest_when_collision_baked(tmp_path):
    base = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(base))
    out = tmp_path / "asset" / "out.glb"
    out.parent.mkdir(parents=True, exist_ok=True)

    server = _server()
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "with_coll",
            "base_asset_path": str(base),
            "output_path": str(out),
        },
    )["graph_id"]
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "bake_convex_collision"},
    )

    payload = _call(
        server,
        "evaluate_edit_graph_streaming",
        {
            "graph_id": gid,
            "manifest_dir": str(out.parent),
            "asset_id": "stream_test",
        },
    )
    final = payload["result"]
    assert final["status"] == "succeeded"
    side_effects = final.get("metadata", {}).get("side_effects") or []
    assert any(se.get("kind") == "convex_collision" for se in side_effects)
    manifest = final.get("manifest")
    assert manifest is not None
    assert manifest["collision"]["intent"] == "convex"
