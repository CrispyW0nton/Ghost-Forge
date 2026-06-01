from __future__ import annotations

import time

from PySide6 import QtCore

from ghostforge_core import CoreConfig
from ghostforge_core.manifest import read_manifest
from ghostforge_core.workers.stub import StubTextTo3DWorker
from ghostforge_qt.models.scene_model import TransformState
from ghostforge_qt.services.core_bridge import CoreBridge
from ghostforge_qt.windows.main_window import MainWindow
import trimesh


def _wait_for_graph_jobs(window: MainWindow, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and (window._graph_job_contexts or window._graph_audit_job_contexts):
        window.job_controller.refresh()
        QtCore.QCoreApplication.processEvents()
        if not window._graph_job_contexts and not window._graph_audit_job_contexts:
            return
        time.sleep(0.05)
    assert not window._graph_job_contexts
    assert not window._graph_audit_job_contexts


def test_main_window_registers_editor_actions(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        ids = set(window.actions.ids())

        assert "file.import_mesh" in ids
        assert "asset.unwrap" in ids
        assert "asset.texture" in ids
        assert "asset.audit" in ids
        assert "asset.export_bridge" in ids
        assert window.centralWidget() is window.viewport
        assert window.worker_panel.model.rowCount() >= 1
        assert window.content_panel.project.root == (tmp_path / "project").resolve()
        assert window.modeling_panel is not None
        assert window.operation_graph_panel.palette_model.rowCount() >= 1
        assert window.theme_panel is not None
    finally:
        window.close()


def test_main_window_evaluates_selected_mesh_operation_graph(qapp, tmp_path):
    source = tmp_path / "offset.glb"
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh.apply_translation((5.0, 0.0, 0.0))
    mesh.export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        before = window.scene_model.records()[0]
        operation = next(row for row in bridge.list_operations() if row.kind == "recenter")
        window.operation_graph_panel.graph_model.append_operation(operation, {"pivot": "centroid"})

        window._evaluate_operation_graph()
        assert window._graph_job_contexts
        _wait_for_graph_jobs(window)

        after = window.scene_model.records()[0]
        assert after.path != before.path
        assert after.path.exists()
        assert "evaluate_authoring_graph" in after.operations
        assert window.operation_graph_panel.graph_model.data(
            window.operation_graph_panel.graph_model.index(0, 3)
        ) == "succeeded"
        assert "succeeded" in window.operation_graph_panel.job_status.text()
        assert window.operation_graph_panel.job_progress.value() == 100
        manifest = read_manifest(after.asset_dir)
        steps = [step for step in manifest.provenance if step.kind == "evaluate_authoring_graph"]
        assert steps[-1].parameters["graph_id"] == window.operation_graph_panel.graph().graph_id
    finally:
        window.close()


def test_main_window_source_graph_creates_scene_object(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    bridge.context.workers.register(StubTextTo3DWorker())
    window = MainWindow(bridge=bridge)
    try:
        operation = next(row for row in bridge.list_operations() if row.kind == "generate_text_to_3d")
        window.operation_graph_panel.graph_model.append_operation(
            operation,
            {"prompt": "small test obelisk", "worker": "stub_text_to_3d"},
        )

        window._evaluate_operation_graph()
        assert window._graph_job_contexts
        _wait_for_graph_jobs(window)

        records = window.scene_model.records()
        assert len(records) == 1
        record = records[0]
        assert record.path.exists()
        assert record.asset_dir is not None
        manifest = read_manifest(record.asset_dir)
        graph_steps = [step for step in manifest.provenance if step.kind == "evaluate_authoring_graph"]
        assert graph_steps[-1].parameters["source_mode"] == "operation"
        assert graph_steps[-1].parameters["side_effects"][0]["operation"] == "generate_text_to_3d"
        assert "succeeded" in window.operation_graph_panel.job_status.text()
    finally:
        window.close()


def test_main_window_runs_graph_result_audit_and_refreshes_history(qapp, tmp_path):
    source = tmp_path / "offset.glb"
    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh.apply_translation((5.0, 0.0, 0.0))
    mesh.export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        operation = next(row for row in bridge.list_operations() if row.kind == "recenter")
        window.operation_graph_panel.graph_model.append_operation(operation, {"pivot": "centroid"})
        window._evaluate_operation_graph()
        _wait_for_graph_jobs(window)

        window._audit_operation_graph_result()
        assert window._graph_audit_job_contexts
        _wait_for_graph_jobs(window)

        record = window.scene_model.records()[0]
        manifest = read_manifest(record.asset_dir)
        assert manifest.custom["audit_history"]
        assert window.operation_graph_panel.history_model.rowCount() >= 2
        assert window.operation_graph_panel.history_model.data(
            window.operation_graph_panel.history_model.index(0, 4)
        ) in {"passed", "warnings", "failed", "skipped"}
    finally:
        window.close()


def test_main_window_routes_graph_job_cancel(qapp, tmp_path, monkeypatch):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    calls: list[str] = []
    try:
        monkeypatch.setattr(window.job_controller, "cancel", lambda job_id: calls.append(job_id))
        window._graph_job_contexts["job-cancel-123456"] = {"output_path": tmp_path / "unused.glb"}

        window._cancel_graph_job("job-cancel-123456")

        assert calls == ["job-cancel-123456"]
    finally:
        window.close()


def test_main_window_applies_and_undoes_mesh_operation(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(2, 4, 8)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        before = window.scene_model.records()[0]

        window._modeling_tool_requested("normalize_scale")
        after = window.scene_model.records()[0]

        assert after.path != before.path
        assert after.path.exists()
        window.undo_operation()
        undone = window.scene_model.records()[0]
        assert undone.path == source
        window.redo_operation()
        redone = window.scene_model.records()[0]
        assert redone.path == after.path
    finally:
        window.close()


def test_main_window_saves_and_reopens_scene_with_manifest(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    scene_path = tmp_path / "data" / "project" / "scenes" / "saved.gforge"
    transform = TransformState(translate=(4.0, 5.0, 6.0), rotate_euler_deg=(0.0, 45.0, 0.0))
    try:
        window.import_mesh(source)
        imported = window.scene_model.records()[0]
        assert imported.asset_dir is not None
        assert imported.manifest_path is not None
        assert imported.manifest_path.exists()
        manifest = read_manifest(imported.asset_dir)
        assert manifest.geometry is not None
        assert any(artifact.role == "mesh.primary" for artifact in manifest.artifacts)

        window.scene_model.update_transform(imported.object_id, transform)
        saved = window.save_scene(scene_path)
        assert saved == scene_path
        assert scene_path.exists()

        window.new_scene()
        assert window.scene_model.rowCount() == 0

        window.open_scene(scene_path)
        restored = window.scene_model.records()[0]
        assert restored.path == source
        assert restored.transform.translate == (4.0, 5.0, 6.0)
        assert restored.transform.rotate_euler_deg == (0.0, 45.0, 0.0)
        assert restored.manifest_path == imported.manifest_path
    finally:
        window.close()


def test_main_window_saves_and_reopens_scene_operation_graph(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    scene_path = tmp_path / "data" / "project" / "scenes" / "graph_scene.gforge"
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]
        operation = next(row for row in bridge.list_operations() if row.kind == "recenter")
        window.operation_graph_panel.graph_model.append_operation(operation, {"pivot": "centroid"})
        window._operation_graph_changed(window.operation_graph_panel.graph())
        history = (
            {
                "graph_id": window.operation_graph_panel.graph().graph_id,
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_graph_out.glb"),
                "duration_ms": 7.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "audit passed",
            },
        )
        window.operation_graph_panel.set_history_payloads(history)
        window.scene_model.update_record(
            record.object_id,
            operation_graph_history=window.operation_graph_panel.history_payloads(),
        )

        stored = window.scene_model.records()[0]
        assert stored.operation_graph is not None
        assert stored.operation_graph_history == history
        assert bridge.context.graphs.load(stored.operation_graph.graph_id).nodes[0].kind == "recenter"
        window.save_scene(scene_path)

        window.new_scene()
        assert window.scene_model.rowCount() == 0

        window.open_scene(scene_path)
        restored = window.scene_model.records()[0]
        assert restored.object_id == record.object_id
        assert restored.operation_graph is not None
        assert restored.operation_graph.nodes[0].kind == "recenter"
        assert restored.operation_graph_history == history
        assert window.operation_graph_panel.graph().graph_id == restored.operation_graph.graph_id
        assert window.operation_graph_panel.graph_model.rowCount() == 1
        assert window.operation_graph_panel.history_model.rowCount() == 1
        assert window.operation_graph_panel.history_model.data(
            window.operation_graph_panel.history_model.index(0, 4)
        ) == "passed"
    finally:
        window.close()


def test_main_window_updates_selection_from_viewport_pick(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]
        window.viewport.renderer.canvas.resize(640, 480)
        window.viewport.set_selection_mode("vertex")
        frame = window.viewport.renderer.canvas.projected_objects()
        vertex_point = frame[0].projected[0]
        pick = window.viewport.renderer.canvas.pick_at(
            QtCore.QPointF(float(vertex_point[0]), float(vertex_point[1])),
            mode="vertex",
        )
        assert pick is not None

        window._viewport_pick_requested(pick)

        assert window.mesh_selection.active_object_id == record.object_id
        assert pick.vertex_index in window.mesh_selection.selected_vertices
        assert window.viewport.renderer.canvas.active_object_id == record.object_id
        assert pick.vertex_index in window.viewport.renderer.canvas.selected_vertices
    finally:
        window.close()


def test_main_window_applies_selected_face_delete(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]
        window.mesh_selection.set_mode("face")
        window.mesh_selection.active_object_id = record.object_id
        window.mesh_selection.selected_object_ids = {record.object_id}
        window.mesh_selection.selected_faces = {0}

        window._modeling_tool_requested("delete")
        updated = window.scene_model.records()[0]

        assert updated.path != source
        assert updated.faces == 11
        assert window.mesh_selection.selected_faces == set()
        assert updated.asset_dir is not None
        manifest = read_manifest(updated.asset_dir)
        delete_steps = [step for step in manifest.provenance if step.kind == "delete"]
        assert delete_steps[-1].parameters["selection"]["faces"] == [0]
        window.undo_operation()
        assert window.scene_model.records()[0].path == source
    finally:
        window.close()
