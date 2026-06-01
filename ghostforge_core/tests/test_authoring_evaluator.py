"""Evaluator semantics: ordering, disabled nodes, error capture, output."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from ghostforge_core.authoring import (
    EditGraph,
    OperationContext,
    OperationNode,
    default_operation_registry,
    evaluate_graph,
    make_operation,
)


@pytest.fixture
def registry():
    return default_operation_registry()


@pytest.fixture
def cube_path(tmp_path: Path) -> Path:
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    path = tmp_path / "cube.glb"
    mesh.export(str(path))
    return path


def _graph(graph_id: str, base: Path, out: Path, *nodes: OperationNode) -> EditGraph:
    g = EditGraph(
        graph_id=graph_id,
        base_asset_path=str(base),
        output_path=str(out),
    )
    return g.with_nodes(list(nodes))


def test_evaluator_writes_output_and_returns_succeeded(cube_path, tmp_path, registry):
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(
            id="t1",
            kind="transform",
            params={"translate": [3.0, 0.0, 0.0]},
        ),
    )
    result, mesh = evaluate_graph(graph, registry=registry)
    assert result.status == "succeeded"
    assert result.output_path == str(out)
    assert out.exists()
    assert mesh is not None
    assert np.allclose(mesh.centroid, np.array([3.0, 0.0, 0.0]), atol=1e-6)
    assert len(result.steps) == 1
    assert result.steps[0].status == "succeeded"


def test_evaluator_skips_disabled_nodes(cube_path, tmp_path, registry):
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(
            id="t1",
            kind="transform",
            enabled=False,
            params={"translate": [10.0, 0.0, 0.0]},
        ),
    )
    result, mesh = evaluate_graph(graph, registry=registry)
    assert result.status == "succeeded"
    assert result.steps[0].status == "skipped"
    assert np.allclose(mesh.centroid, np.zeros(3), atol=1e-6)


def test_evaluator_orders_operations(cube_path, tmp_path, registry):
    """Translate then scale != scale then translate."""

    out = tmp_path / "out.glb"
    graph_a = _graph(
        "ga",
        cube_path,
        out,
        OperationNode(id="t", kind="transform", params={"translate": [1.0, 0.0, 0.0]}),
        OperationNode(id="s", kind="transform", params={"scale": 2.0}),
    )
    graph_b = _graph(
        "gb",
        cube_path,
        tmp_path / "out_b.glb",
        OperationNode(id="s", kind="transform", params={"scale": 2.0}),
        OperationNode(id="t", kind="transform", params={"translate": [1.0, 0.0, 0.0]}),
    )
    _, mesh_a = evaluate_graph(graph_a, registry=registry)
    _, mesh_b = evaluate_graph(graph_b, registry=registry)
    # graph_a: translate(1,0,0) then scale 2 => centroid at (2, 0, 0).
    # graph_b: scale 2 then translate(1,0,0) => centroid at (1, 0, 0).
    assert np.allclose(mesh_a.centroid, np.array([2.0, 0.0, 0.0]), atol=1e-6)
    assert np.allclose(mesh_b.centroid, np.array([1.0, 0.0, 0.0]), atol=1e-6)


def test_evaluator_records_failure_per_node(cube_path, tmp_path, registry):
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(id="t1", kind="transform", params={"translate": [1.0, 0.0, 0.0]}),
        OperationNode(id="bad", kind="transform", params={"translate": [1.0, 0.0]}),
        OperationNode(id="t3", kind="recenter", params={}),
    )
    result, _ = evaluate_graph(graph, registry=registry)
    assert result.status == "failed"
    statuses = [s.status for s in result.steps]
    assert statuses == ["succeeded", "failed", "succeeded"]
    assert "translate" in (result.steps[1].error or "")


def test_evaluator_fail_fast_aborts_after_first_error(cube_path, tmp_path, registry):
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(id="bad", kind="transform", params={"translate": [1.0, 0.0]}),
        OperationNode(id="never", kind="recenter", params={}),
    )
    result, _ = evaluate_graph(graph, registry=registry, fail_fast=True)
    assert result.status == "failed"
    assert len(result.steps) == 1
    assert result.steps[0].status == "failed"


def test_evaluator_unknown_kind_marked_failed(cube_path, tmp_path, registry):
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(id="weird", kind="not_real", params={}),
    )
    result, _ = evaluate_graph(graph, registry=registry)
    assert result.status == "failed"
    assert "unknown" in (result.steps[0].error or "").lower()


def test_evaluator_no_input_path_returns_failed(tmp_path, registry):
    graph = EditGraph(graph_id="g1", output_path=str(tmp_path / "out.glb"))
    result, mesh = evaluate_graph(graph, registry=registry)
    assert mesh is None
    assert result.status == "failed"
    assert "no input" in (result.metadata.get("error") or "").lower()


def test_evaluator_invalid_input_path_returns_failed(tmp_path, registry):
    graph = EditGraph(
        graph_id="g1",
        base_asset_path=str(tmp_path / "missing.glb"),
        output_path=str(tmp_path / "out.glb"),
    )
    result, mesh = evaluate_graph(graph, registry=registry)
    assert mesh is None
    assert result.status == "failed"


def test_evaluator_input_path_override(tmp_path, registry):
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    explicit = tmp_path / "explicit.glb"
    cube.export(str(explicit))
    graph = EditGraph(
        graph_id="g1",
        base_asset_path=str(tmp_path / "ignored.glb"),
        output_path=str(tmp_path / "out.glb"),
    )
    graph = graph.with_nodes(
        [OperationNode(id="t1", kind="recenter", params={})]
    )
    result, mesh = evaluate_graph(graph, registry=registry, input_path=explicit)
    assert result.status == "succeeded"
    assert mesh is not None


def test_evaluator_returns_failed_when_handler_returns_non_mesh(cube_path, tmp_path, registry):
    rogue = make_operation(
        kind="rogue",
        label="Rogue",
        handler=lambda ctx: "not a mesh",  # type: ignore[return-value,arg-type]
    )
    registry.register(rogue)
    out = tmp_path / "out.glb"
    graph = _graph(
        "g1",
        cube_path,
        out,
        OperationNode(id="r", kind="rogue", params={}),
    )
    result, _ = evaluate_graph(graph, registry=registry)
    assert result.status == "failed"
    assert "Trimesh" in (result.steps[0].error or "")
