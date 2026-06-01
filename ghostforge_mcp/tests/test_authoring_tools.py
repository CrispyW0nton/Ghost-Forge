"""End-to-end MCP coverage for the P11 authoring tool surface."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest
import trimesh


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
    """Each MCP test gets its own data root so graphs don't leak."""

    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "0")

    from ghostforge_mcp import server as server_mod

    server_mod.reset_context_for_tests()
    yield
    server_mod.reset_context_for_tests()


def _server():
    from ghostforge_mcp.server import build_server

    return build_server()


def _call(server, name, args=None):
    return _payload(asyncio.run(server.call_tool(name, args or {})))


def test_graph_tools_registered():
    server = _server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_operations",
        "create_edit_graph",
        "list_edit_graphs",
        "get_edit_graph",
        "delete_edit_graph",
        "append_graph_node",
        "update_graph_node",
        "remove_graph_node",
        "reorder_graph_nodes",
        "evaluate_edit_graph",
    }
    missing = expected - names
    assert not missing, f"missing P11 tools: {missing}"


def test_list_operations_includes_builtins():
    server = _server()
    payload = _call(server, "list_operations")
    assert isinstance(payload, list)
    kinds = {op["kind"] for op in payload}
    assert {"transform", "recenter", "apply_material"}.issubset(kinds)


def test_create_get_delete_graph_round_trip():
    server = _server()
    created = _call(server, "create_edit_graph", {"name": "demo"})
    gid = created["graph_id"]
    listed = _call(server, "list_edit_graphs")
    assert any(g["graph_id"] == gid for g in listed)
    fetched = _call(server, "get_edit_graph", {"graph_id": gid})
    assert fetched["graph"]["graph_id"] == gid
    assert "evaluation" not in fetched
    deleted = _call(server, "delete_edit_graph", {"graph_id": gid})
    assert deleted == {"deleted": gid}


def test_append_update_remove_node_lifecycle():
    server = _server()
    graph = _call(server, "create_edit_graph", {"name": "demo"})
    gid = graph["graph_id"]
    after_append = _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "transform", "label": "first"},
    )
    assert len(after_append["nodes"]) == 1
    node_id = after_append["nodes"][0]["id"]

    after_update = _call(
        server,
        "update_graph_node",
        {"graph_id": gid, "node_id": node_id, "label": "renamed", "enabled": False},
    )
    node = after_update["nodes"][0]
    assert node["label"] == "renamed"
    assert node["enabled"] is False

    after_remove = _call(
        server, "remove_graph_node", {"graph_id": gid, "node_id": node_id}
    )
    assert after_remove["nodes"] == []


def test_reorder_graph_nodes_round_trip():
    server = _server()
    gid = _call(server, "create_edit_graph", {"name": "ord"})["graph_id"]
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "transform", "node_id": "alpha"},
    )
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "recenter", "node_id": "beta"},
    )
    after = _call(
        server,
        "reorder_graph_nodes",
        {"graph_id": gid, "order": ["beta", "alpha"]},
    )
    assert [n["id"] for n in after["nodes"]] == ["beta", "alpha"]


def test_evaluate_edit_graph_writes_output(tmp_path):
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    base = tmp_path / "cube.glb"
    cube.export(str(base))
    out = tmp_path / "out.glb"

    server = _server()
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "eval",
            "base_asset_path": str(base),
            "output_path": str(out),
        },
    )["graph_id"]
    _call(
        server,
        "append_graph_node",
        {
            "graph_id": gid,
            "kind": "transform",
            "params": {"translate": [1.0, 0.0, 0.0]},
        },
    )
    result = _call(server, "evaluate_edit_graph", {"graph_id": gid})
    assert result["status"] == "succeeded"
    assert result["output_path"]
    assert Path(result["output_path"]).exists()

    fetched = _call(server, "get_edit_graph", {"graph_id": gid})
    assert "evaluation" in fetched
    assert fetched["evaluation"]["status"] == "succeeded"


def test_append_unknown_kind_surfaces_error():
    server = _server()
    gid = _call(server, "create_edit_graph", {"name": "x"})["graph_id"]
    with pytest.raises(Exception):
        _call(
            server,
            "append_graph_node",
            {"graph_id": gid, "kind": "totally_invalid"},
        )
