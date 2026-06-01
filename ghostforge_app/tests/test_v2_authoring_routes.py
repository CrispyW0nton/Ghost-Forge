"""Black-box HTTP tests for the P11 authoring v2 routes."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh


@pytest.fixture
def cube_path(tmp_path: Path) -> Path:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    out = tmp_path / "cube.glb"
    mesh.export(str(out))
    return out


def _create_graph(client, **payload):
    resp = client.post("/api/v2/graphs", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def test_list_operations_returns_descriptors(client):
    resp = client.get("/api/v2/operations")
    assert resp.status_code == 200
    body = resp.get_json()
    kinds = {op["kind"] for op in body["operations"]}
    assert {"transform", "recenter", "apply_material"}.issubset(kinds)


def test_list_graphs_initially_empty(client):
    resp = client.get("/api/v2/graphs")
    assert resp.status_code == 200
    assert resp.get_json() == {"graphs": []}


def test_create_graph_returns_201_with_assigned_id(client):
    body = _create_graph(client, name="hero")
    assert body["graph_id"]
    assert body["name"] == "hero"
    assert body["nodes"] == []


def test_create_graph_with_initial_nodes(client):
    body = _create_graph(
        client,
        name="hero",
        nodes=[{"kind": "transform", "params": {"translate": [1, 0, 0]}}],
    )
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["kind"] == "transform"


def test_get_graph_returns_404_for_missing(client):
    resp = client.get("/api/v2/graphs/does-not-exist")
    assert resp.status_code == 404


def test_append_node_round_trip(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    resp = client.post(
        f"/api/v2/graphs/{gid}/nodes",
        json={"kind": "transform", "params": {"translate": [1, 2, 3]}},
    )
    assert resp.status_code == 201
    body = resp.get_json()
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["kind"] == "transform"
    assert body["version"] == graph["version"] + 1


def test_append_node_rejects_unknown_kind(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    resp = client.post(
        f"/api/v2/graphs/{gid}/nodes",
        json={"kind": "not_a_real_op", "params": {}},
    )
    assert resp.status_code == 400


def test_update_node_changes_only_supplied_fields(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    resp = client.post(
        f"/api/v2/graphs/{gid}/nodes",
        json={"kind": "transform", "label": "before", "params": {"scale": 1.0}},
    )
    node_id = resp.get_json()["nodes"][0]["id"]
    resp = client.put(
        f"/api/v2/graphs/{gid}/nodes/{node_id}",
        json={"label": "after", "enabled": False},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    node = body["nodes"][0]
    assert node["label"] == "after"
    assert node["enabled"] is False
    assert node["kind"] == "transform"
    assert node["params"] == {"scale": 1.0}


def test_remove_node(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    resp = client.post(
        f"/api/v2/graphs/{gid}/nodes", json={"kind": "transform"}
    )
    node_id = resp.get_json()["nodes"][0]["id"]
    resp = client.delete(f"/api/v2/graphs/{gid}/nodes/{node_id}")
    assert resp.status_code == 200
    assert resp.get_json()["nodes"] == []


def test_remove_node_404_when_missing(client):
    graph = _create_graph(client)
    resp = client.delete(f"/api/v2/graphs/{graph['graph_id']}/nodes/missing")
    assert resp.status_code == 404


def test_reorder_nodes(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    client.post(
        f"/api/v2/graphs/{gid}/nodes",
        json={"kind": "transform", "id": "a"},
    )
    last = client.post(
        f"/api/v2/graphs/{gid}/nodes",
        json={"kind": "recenter", "id": "b"},
    ).get_json()
    assert [n["id"] for n in last["nodes"]] == ["a", "b"]
    resp = client.post(
        f"/api/v2/graphs/{gid}/reorder", json={"order": ["b", "a"]}
    )
    assert resp.status_code == 200
    assert [n["id"] for n in resp.get_json()["nodes"]] == ["b", "a"]


def test_reorder_rejects_mismatched_order(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    client.post(f"/api/v2/graphs/{gid}/nodes", json={"kind": "transform"})
    resp = client.post(
        f"/api/v2/graphs/{gid}/reorder", json={"order": ["nonexistent"]}
    )
    assert resp.status_code == 400


def test_evaluate_writes_output_and_persists_report(client, cube_path, tmp_path):
    graph = _create_graph(
        client,
        name="cube-evaluation",
        base_asset_path=str(cube_path),
        output_path=str(tmp_path / "out.glb"),
        nodes=[
            {"kind": "transform", "params": {"translate": [1.0, 0.0, 0.0]}}
        ],
    )
    gid = graph["graph_id"]
    resp = client.post(f"/api/v2/graphs/{gid}/evaluate", json={})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["status"] == "succeeded"
    assert body["output_path"]
    assert Path(body["output_path"]).exists()
    # Re-fetch returns the persisted report.
    follow_up = client.get(f"/api/v2/graphs/{gid}")
    assert "evaluation" in follow_up.get_json()


def test_delete_graph_removes_it(client):
    graph = _create_graph(client)
    gid = graph["graph_id"]
    resp = client.delete(f"/api/v2/graphs/{gid}")
    assert resp.status_code == 200
    follow_up = client.get(f"/api/v2/graphs/{gid}")
    assert follow_up.status_code == 404
