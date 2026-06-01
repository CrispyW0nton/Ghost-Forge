"""Schema-level tests for the authoring layer (P11)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostforge_core.authoring import (
    EditGraph,
    EvaluationResult,
    EvaluationStep,
    OperationNode,
)


def test_node_defaults_sane():
    node = OperationNode(id="n1", kind="transform")
    assert node.enabled is True
    assert node.params == {}
    assert node.label == ""
    assert node.notes is None


def test_node_is_frozen():
    node = OperationNode(id="n1", kind="transform")
    with pytest.raises(ValidationError):
        node.label = "mutated"  # type: ignore[misc]


def test_node_id_required_non_empty():
    with pytest.raises(ValidationError):
        OperationNode(id="", kind="transform")


def test_graph_with_nodes_returns_new_instance():
    g1 = EditGraph(graph_id="g1")
    n = OperationNode(id="n1", kind="transform")
    g2 = g1.with_nodes([n])
    assert g1 is not g2
    assert g1.nodes == ()
    assert g2.nodes == (n,)
    assert g2.version == g1.version + 1


def test_graph_with_nodes_preserves_metadata():
    g1 = EditGraph(graph_id="g1", name="hero", description="hero asset")
    g2 = g1.with_nodes([OperationNode(id="n1", kind="transform")])
    assert g2.name == "hero"
    assert g2.description == "hero asset"
    assert g2.graph_id == "g1"


def test_evaluation_step_status_literal_enforced():
    EvaluationStep(node_id="n1", kind="transform", status="succeeded")
    EvaluationStep(node_id="n1", kind="transform", status="skipped")
    EvaluationStep(node_id="n1", kind="transform", status="failed")
    with pytest.raises(ValidationError):
        EvaluationStep(node_id="n1", kind="transform", status="weird")  # type: ignore[arg-type]


def test_evaluation_result_round_trips_json():
    result = EvaluationResult(
        graph_id="g1",
        status="succeeded",
        steps=(
            EvaluationStep(node_id="n1", kind="transform", status="succeeded"),
        ),
    )
    decoded = EvaluationResult.model_validate_json(result.model_dump_json())
    assert decoded == result
