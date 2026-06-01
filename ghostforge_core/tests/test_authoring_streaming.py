"""Tests for the streaming evaluator."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from ghostforge_core.authoring import (
    EditGraph,
    OperationNode,
    default_operation_registry,
    evaluate_graph_streaming,
)


def _seed_box(path: Path) -> Path:
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(path))
    return path


def _graph(base: Path, *nodes: OperationNode, output: Path | None = None) -> EditGraph:
    return EditGraph(
        graph_id="g1",
        base_asset_path=str(base),
        output_path=str(output) if output else None,
        nodes=tuple(nodes),
    )


def test_streaming_emits_started_step_completed_in_order(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    kinds = [e["event"] for e in events]
    assert kinds[0] == "started"
    assert "step" in kinds
    assert kinds[-1] == "completed"


def test_streaming_progress_monotonic(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals"),
        OperationNode(id="n2", kind="merge_vertices"),
        OperationNode(id="n3", kind="recompute_normals"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    progresses = [e["progress"] for e in events if e["event"] == "step"]
    assert progresses == sorted(progresses)
    assert progresses[-1] == pytest.approx(100.0)


def test_streaming_records_step_status_and_geometry_counts(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    step_event = next(e for e in events if e["event"] == "step")
    assert step_event["status"] == "succeeded"
    assert step_event["vertex_count"] > 0
    assert step_event["face_count"] > 0


def test_streaming_emits_exported_event_when_output_path_set(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    out = tmp_path / "out.glb"
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals"),
        output=out,
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    assert any(e["event"] == "exported" for e in events)
    assert out.exists()


def test_streaming_completed_carries_full_result(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    completed = events[-1]
    assert completed["event"] == "completed"
    result = completed["result"]
    assert result["status"] == "succeeded"
    assert result["graph_id"] == "g1"
    assert len(result["steps"]) == 1
    assert result["metadata"]["faces"] > 0


def test_streaming_failed_step_propagates(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="this_kind_does_not_exist"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    step = next(e for e in events if e["event"] == "step")
    assert step["status"] == "failed"
    assert "unknown operation" in (step.get("error") or "")
    completed = events[-1]
    assert completed["event"] == "completed"
    assert completed["result"]["status"] == "failed"


def test_streaming_skipped_node_yields_skipped_status(tmp_path):
    base = _seed_box(tmp_path / "base.glb")
    graph = _graph(
        base,
        OperationNode(id="n1", kind="recompute_normals", enabled=False),
        OperationNode(id="n2", kind="recompute_normals"),
        output=tmp_path / "out.glb",
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    statuses = [e["status"] for e in events if e["event"] == "step"]
    assert statuses[0] == "skipped"
    assert statuses[1] == "succeeded"


def test_streaming_invalid_input_path_emits_failed_completed(tmp_path):
    graph = EditGraph(
        graph_id="g1",
        base_asset_path=str(tmp_path / "no-such-file.glb"),
        nodes=(),
    )
    events = list(evaluate_graph_streaming(graph, registry=default_operation_registry()))
    assert events[0]["event"] == "started"
    completed = events[-1]
    assert completed["event"] == "completed"
    assert completed["result"]["status"] == "failed"
