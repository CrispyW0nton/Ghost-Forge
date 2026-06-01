from __future__ import annotations

from ghostforge_core.authoring import EditGraph, OperationNode
from ghostforge_core import CoreConfig
from ghostforge_qt.services.core_bridge import CoreBridge


def test_core_bridge_reports_worker_capability_honestly(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    rows = bridge.list_workers()
    names = {row.name for row in rows}

    assert "stub_image_to_3d" in names
    assert "stub_texture_mesh" in names
    assert any(row.runnable for row in rows)
    assert any(row.is_stub and row.runnable for row in rows)


def test_core_bridge_runtime_snapshot_includes_core_domains(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    snapshot = bridge.runtime_snapshot()

    assert snapshot.data_root == tmp_path.resolve()
    assert snapshot.kb_backend
    assert snapshot.kb_embedder
    assert len(snapshot.workers) >= 1
    assert {engine.name for engine in snapshot.engines} == {"unity", "unreal"}


def test_core_bridge_lists_authoring_operations_with_worker_status(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    rows = {row.kind: row for row in bridge.list_operations()}

    assert rows["recenter"].status == "available"
    assert rows["generate_image_to_3d"].operation_type == "source"
    assert rows["generate_image_to_3d"].capability == "image_to_3d"
    assert rows["worker_texture_mesh"].operation_type == "worker"
    assert rows["worker_texture_mesh"].capability == "texture_mesh"
    assert rows["worker_texture_mesh"].status in {"runnable", "stub", "missing"}


def test_core_bridge_submits_authoring_graph_evaluation_job(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))
    graph = EditGraph(
        graph_id="qt_job_graph",
        base_asset_path=str(tmp_path / "missing.glb"),
        nodes=(OperationNode(id="n1", kind="recenter"),),
    )

    handle = bridge.submit_authoring_graph_evaluation(graph)

    assert handle.kind == "evaluate_edit_graph"
    assert handle.status.value == "pending"
    assert bridge.context.graphs.load("qt_job_graph").nodes[0].kind == "recenter"
