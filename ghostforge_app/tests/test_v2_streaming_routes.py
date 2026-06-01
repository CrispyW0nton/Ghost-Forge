"""Black-box HTTP tests for the SSE streaming evaluator route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh


@pytest.fixture
def cube_path(tmp_path: Path) -> Path:
    out = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(out))
    return out


def _create_graph(client, **payload):
    resp = client.post("/api/v2/graphs", json=payload)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _parse_sse(body: bytes) -> list[dict]:
    out: list[dict] = []
    for chunk in body.decode("utf-8").split("\n\n"):
        line = chunk.strip()
        if not line.startswith("data: "):
            continue
        out.append(json.loads(line[len("data: ") :]))
    return out


def test_evaluate_stream_emits_started_step_and_completed(client, cube_path, tmp_path):
    graph = _create_graph(
        client,
        base_asset_path=str(cube_path),
        nodes=[{"kind": "recompute_normals"}],
        output_path=str(tmp_path / "out.glb"),
    )
    resp = client.post(
        f"/api/v2/graphs/{graph['graph_id']}/evaluate/stream",
        json={"output_path": str(tmp_path / "out.glb")},
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.mimetype
    events = _parse_sse(resp.data)
    assert events[0]["event"] == "started"
    assert any(e["event"] == "step" for e in events)
    assert events[-1]["event"] == "completed"
    assert events[-1]["result"]["status"] == "succeeded"


def test_evaluate_stream_emits_exported_event(client, cube_path, tmp_path):
    out = tmp_path / "out.glb"
    graph = _create_graph(
        client,
        base_asset_path=str(cube_path),
        nodes=[{"kind": "recompute_normals"}],
        output_path=str(out),
    )
    resp = client.post(
        f"/api/v2/graphs/{graph['graph_id']}/evaluate/stream",
        json={"output_path": str(out)},
    )
    events = _parse_sse(resp.data)
    assert any(e["event"] == "exported" for e in events)
    assert out.exists()


def test_evaluate_stream_unknown_graph_returns_404(client):
    resp = client.post("/api/v2/graphs/no-such/evaluate/stream", json={})
    assert resp.status_code == 404


def test_evaluate_stream_get_with_query_params(client, cube_path, tmp_path):
    out = tmp_path / "out.glb"
    graph = _create_graph(
        client,
        base_asset_path=str(cube_path),
        nodes=[{"kind": "recompute_normals"}],
        output_path=str(out),
    )
    resp = client.get(
        f"/api/v2/graphs/{graph['graph_id']}/evaluate/stream",
        query_string={"output_path": str(out)},
    )
    events = _parse_sse(resp.data)
    assert events[-1]["event"] == "completed"


def test_evaluate_stream_failed_status_when_input_missing(client, tmp_path):
    graph = _create_graph(
        client,
        base_asset_path=str(tmp_path / "no-such-file.glb"),
        nodes=[{"kind": "recompute_normals"}],
    )
    resp = client.post(
        f"/api/v2/graphs/{graph['graph_id']}/evaluate/stream",
        json={"output_path": str(tmp_path / "out.glb")},
    )
    events = _parse_sse(resp.data)
    completed = events[-1]
    assert completed["event"] == "completed"
    assert completed["result"]["status"] == "failed"


def test_evaluate_stream_writes_manifest_on_collision_bake(client, cube_path, tmp_path):
    out = tmp_path / "out.glb"
    graph = _create_graph(
        client,
        base_asset_path=str(cube_path),
        nodes=[{"kind": "bake_convex_collision"}],
        output_path=str(out),
    )
    resp = client.post(
        f"/api/v2/graphs/{graph['graph_id']}/evaluate/stream",
        json={"output_path": str(out), "manifest_dir": str(tmp_path)},
    )
    events = _parse_sse(resp.data)
    manifest_event = next((e for e in events if e["event"] == "manifest"), None)
    assert manifest_event is not None
    assert manifest_event["manifest"]["collision"]["intent"] == "convex"
