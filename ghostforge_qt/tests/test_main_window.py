from __future__ import annotations

from PySide6 import QtCore

from ghostforge_core import CoreConfig
from ghostforge_core.manifest import read_manifest
from ghostforge_qt.models.scene_model import TransformState
from ghostforge_qt.services.core_bridge import CoreBridge
from ghostforge_qt.windows.main_window import MainWindow
import trimesh


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
        assert window.theme_panel is not None
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
