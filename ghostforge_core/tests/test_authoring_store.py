"""EditGraphStore persistence + evaluation report round-trip tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.authoring import (
    EditGraph,
    EditGraphStore,
    EvaluationResult,
    EvaluationStep,
    GraphNotFound,
    OperationNode,
)
from ghostforge_core.storage import Storage


@pytest.fixture
def store(tmp_path: Path) -> EditGraphStore:
    return EditGraphStore(Storage(root=tmp_path))


def _graph(graph_id: str = "g1") -> EditGraph:
    return EditGraph(
        graph_id=graph_id,
        name="Test",
        nodes=(OperationNode(id="n1", kind="transform"),),
    )


def test_save_and_load_round_trip(store):
    saved = store.save(_graph())
    loaded = store.load("g1")
    assert loaded == saved


def test_load_missing_raises(store):
    with pytest.raises(GraphNotFound):
        store.load("nope")


def test_list_skips_evaluation_reports(store):
    store.save(_graph("a"))
    store.save(_graph("b"))
    store.save_evaluation(
        EvaluationResult(
            graph_id="a",
            status="succeeded",
            steps=(),
        )
    )
    listed_ids = sorted(g.graph_id for g in store.list())
    assert listed_ids == ["a", "b"]


def test_list_tolerates_corrupt_entries(store, tmp_path):
    store.save(_graph("a"))
    bogus = store.dir / "broken.json"
    bogus.write_text("not json", encoding="utf-8")
    listed_ids = sorted(g.graph_id for g in store.list())
    assert listed_ids == ["a"]


def test_delete_removes_graph_and_evaluation(store):
    store.save(_graph("g1"))
    store.save_evaluation(
        EvaluationResult(
            graph_id="g1",
            status="succeeded",
            steps=(EvaluationStep(node_id="n1", kind="transform", status="succeeded"),),
        )
    )
    assert store.evaluation_path("g1").exists()
    store.delete("g1")
    assert not store.graph_path("g1").exists()
    assert not store.evaluation_path("g1").exists()
    with pytest.raises(GraphNotFound):
        store.delete("g1")


def test_invalid_graph_id_rejected(store):
    with pytest.raises(ValueError):
        store.graph_path("../escape")
    with pytest.raises(ValueError):
        store.graph_path("")


def test_make_id_unique(store):
    ids = {store.make_id() for _ in range(50)}
    assert len(ids) == 50


def test_evaluation_report_round_trip(store):
    store.save(_graph("g1"))
    report = EvaluationResult(
        graph_id="g1",
        status="succeeded",
        steps=(
            EvaluationStep(node_id="n1", kind="transform", status="succeeded"),
        ),
    )
    store.save_evaluation(report)
    reloaded = store.load_evaluation("g1")
    assert reloaded == report


def test_load_evaluation_missing_returns_none(store):
    assert store.load_evaluation("never-saved") is None
