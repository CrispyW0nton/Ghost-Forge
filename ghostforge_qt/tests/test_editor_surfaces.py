from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh
from PySide6 import QtCore

from ghostforge_core.authoring import EditGraph, OperationNode
from ghostforge_qt.models.scene_model import SceneObjectRecord, TransformState
from ghostforge_qt.panels.content_browser import ContentBrowserPanel
from ghostforge_qt.panels.modeling_tools import ModelingToolsPanel
from ghostforge_qt.services.editable_mesh import EditableMeshHistory, EditableMeshSnapshot
from ghostforge_qt.services.project_service import ProjectService
from ghostforge_qt.services.scene_document import SceneDocumentService
from ghostforge_qt.services.mesh_operation_service import MeshOperationSelection, MeshOperationService
from ghostforge_qt.services.mesh_diagnostics import analyze_mesh
from ghostforge_qt.services.mesh_selection import MeshSelectionState
from ghostforge_qt.services.operation_history import OperationHistory, ScenePathCommand
from ghostforge_qt.theme import ThemeManager
from ghostforge_qt.viewports.mesh_preview import load_mesh_preview
from ghostforge_qt.viewports.viewport_host import ViewportHost


def test_project_service_creates_project_folders(qapp, tmp_path):
    project = ProjectService(tmp_path / "project")

    state = project.state()

    assert state.root == (tmp_path / "project").resolve()
    for name in ("assets", "imports", "outputs", "references", "scenes"):
        assert state.dirs[name].is_dir()


def test_content_browser_roots_itself_at_project(qapp, tmp_path):
    project = ProjectService(tmp_path / "project")
    panel = ContentBrowserPanel(project)

    try:
        assert Path(panel.model.rootPath()) == project.root
        new_root = tmp_path / "another_project"
        project.set_root(new_root)
        assert Path(panel.model.rootPath()) == new_root.resolve()
    finally:
        panel.deleteLater()


def test_scene_document_service_round_trips_records(tmp_path):
    service = SceneDocumentService()
    project_root = tmp_path / "project"
    record = SceneObjectRecord(
        object_id="obj_cube",
        name="Cube",
        path=tmp_path / "cube.glb",
        asset_dir=project_root / "assets" / "obj_cube",
        manifest_path=project_root / "assets" / "obj_cube" / "asset_manifest.json",
        vertices=8,
        faces=12,
        watertight=True,
        transform=TransformState(
            translate=(1.0, 2.0, 3.0),
            rotate_euler_deg=(10.0, 20.0, 30.0),
            scale=(2.0, 2.0, 2.0),
        ),
        operations=("normalize_scale",),
        operation_graph=EditGraph(
            graph_id="obj_cube_graph",
            asset_id="obj_cube",
            name="Cube Graph",
            base_asset_path=str(tmp_path / "cube.glb"),
            nodes=(OperationNode(id="n1_recenter", kind="recenter", params={"pivot": "centroid"}),),
        ),
        operation_graph_history=(
            {
                "history_id": "obj_cube_graph_succeeded_0",
                "graph_id": "obj_cube_graph",
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_out.glb"),
                "duration_ms": 12.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "audit passed",
            },
            {
                "history_id": "obj_cube_graph_succeeded_1",
                "graph_id": "obj_cube_graph",
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_blockout.glb"),
                "duration_ms": 7.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "blockout passed",
            },
        ),
        operation_graph_comparison_pair={
            "left_history_id": "obj_cube_graph_succeeded_1",
            "right_history_id": "obj_cube_graph_succeeded_0",
        },
    )
    scene_path = service.default_scene_path(project_root, "test scene")

    service.write(scene_path, project_root=project_root, records=[record])
    loaded = service.read(scene_path)

    assert loaded.path == scene_path
    assert loaded.scene_id == "test_scene"
    assert loaded.project_root == project_root.resolve()
    assert len(loaded.records) == 1
    restored = loaded.records[0]
    assert restored.object_id == "obj_cube"
    assert restored.transform.translate == (1.0, 2.0, 3.0)
    assert restored.operations == ("normalize_scale",)
    assert restored.manifest_path == record.manifest_path
    assert restored.operation_graph is not None
    assert restored.operation_graph.graph_id == "obj_cube_graph"
    assert restored.operation_graph.nodes[0].kind == "recenter"
    assert restored.operation_graph_history[0]["audit_badge"] == "passed"
    assert restored.operation_graph_history[0]["history_id"] == "obj_cube_graph_succeeded_0"
    assert restored.operation_graph_history[0]["mcp_links"]["graph"] == "ghostforge://graphs/obj_cube_graph"
    assert (
        restored.operation_graph_history[0]["mcp_links"]["scene_object_graph_history"]
        == restored.operation_graph_history[0]["resource_uri"]
    )
    assert restored.operation_graph_comparison_pair == {
        "left_history_id": "obj_cube_graph_succeeded_1",
        "right_history_id": "obj_cube_graph_succeeded_0",
    }


def test_theme_manager_switches_builtin_themes(qapp):
    manager = ThemeManager()

    theme = manager.select("studio_light")

    assert theme.id == "studio_light"
    assert "QMainWindow" in manager.stylesheet(theme)


def test_viewport_host_updates_modes_and_theme(qapp):
    viewport = ViewportHost()
    manager = ThemeManager()

    try:
        viewport.set_selection_mode("face")
        viewport.set_transform_mode("rotate")
        viewport.set_display_mode("wireframe")
        viewport.apply_theme(manager.select("studio_light"))

        canvas = viewport.renderer.canvas
        assert canvas.selection_mode == "face"
        assert canvas.transform_mode == "rotate"
        assert canvas.display_mode == "wireframe"
        assert canvas.theme.id == "studio_light"
    finally:
        viewport.deleteLater()


def test_viewport_canvas_picks_projected_object_vertex_and_edge(qapp, tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(path)
    viewport = ViewportHost()
    record = SceneObjectRecord(object_id="obj_cube", name="Cube", path=path)

    try:
        viewport.resize(640, 480)
        viewport.renderer.canvas.resize(640, 480)
        viewport.set_scene_records([record])
        canvas = viewport.renderer.canvas
        frame = canvas.projected_objects()
        assert len(frame) == 1

        center = frame[0].projected.mean(axis=0)
        object_pick = canvas.pick_at(QtCore.QPointF(float(center[0]), float(center[1])), mode="object")
        assert object_pick is not None
        assert object_pick.object_id == "obj_cube"

        vertex_point = frame[0].projected[0]
        vertex_pick = canvas.pick_at(
            QtCore.QPointF(float(vertex_point[0]), float(vertex_point[1])),
            mode="vertex",
        )
        assert vertex_pick is not None
        assert vertex_pick.vertex_index == 0

        a, b = frame[0].mesh.edges[0]
        midpoint = (frame[0].projected[a] + frame[0].projected[b]) * 0.5
        edge_pick = canvas.pick_at(QtCore.QPointF(float(midpoint[0]), float(midpoint[1])), mode="edge")
        assert edge_pick is not None
        assert edge_pick.edge == tuple(sorted((int(a), int(b))))

        border_pick = canvas.pick_at(QtCore.QPointF(float(midpoint[0]), float(midpoint[1])), mode="border")
        assert border_pick is not None
        assert border_pick.edge_index is not None

        face = frame[0].mesh.faces[0]
        face_center = frame[0].projected[face].mean(axis=0)
        face_pick = canvas.pick_at(QtCore.QPointF(float(face_center[0]), float(face_center[1])), mode="face")
        assert face_pick is not None
        assert face_pick.face_index is not None

        element_pick = canvas.pick_at(QtCore.QPointF(float(face_center[0]), float(face_center[1])), mode="element")
        assert element_pick is not None
        assert element_pick.element_index is not None
    finally:
        viewport.deleteLater()


def test_mesh_preview_loads_real_geometry(tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(path)

    preview = load_mesh_preview(path)

    assert len(preview.vertices) == 8
    assert len(preview.faces) == 12
    assert len(preview.edges) >= 12
    assert preview.extent == 3


def test_mesh_operation_service_writes_normalized_output(tmp_path):
    input_path = tmp_path / "wide.glb"
    trimesh.creation.box(extents=(2, 4, 8)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply("normalize_scale", input_path)

    assert result.path.exists()
    assert result.info.faces == 12
    assert max(result.info.size or []) <= 1.000001


def test_mesh_operation_service_writes_smooth_and_subdivide_outputs(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    smooth = service.apply("smooth_laplacian", input_path, smooth_iterations=1)
    subdivide = service.apply("subdivide", input_path, subdivide_iterations=1)

    assert smooth.path.exists()
    assert subdivide.path.exists()
    assert subdivide.info.faces > 12


def test_mesh_operation_service_deletes_selected_face(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "delete",
        input_path,
        selection=MeshOperationSelection(mode="face", faces={0}),
    )

    assert result.path.exists()
    assert result.info.faces == 11


def test_mesh_operation_service_welds_selected_vertices(tmp_path):
    input_path = tmp_path / "quad.glb"
    mesh = trimesh.Trimesh(
        vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        faces=[(0, 1, 2), (1, 3, 2)],
        process=False,
    )
    mesh.export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "weld",
        input_path,
        selection=MeshOperationSelection(mode="vertex", vertices={0, 1}),
    )

    assert result.path.exists()
    assert result.info.vertices == 3
    assert result.info.faces == 1


def test_mesh_operation_service_flips_selected_face_normals(tmp_path):
    input_path = tmp_path / "quad.glb"
    mesh = trimesh.Trimesh(
        vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        faces=[(0, 1, 2), (1, 3, 2)],
        process=False,
    )
    mesh.export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "flip_normals",
        input_path,
        selection=MeshOperationSelection(mode="face", faces={0}),
    )
    reloaded = trimesh.load(str(result.path), force="mesh", process=False)

    assert result.path.exists()
    assert reloaded.face_normals[0][2] < 0
    assert reloaded.face_normals[1][2] > 0


def test_mesh_diagnostics_reports_topology_summary(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)

    summary = analyze_mesh(input_path)

    assert summary.vertices == 8
    assert summary.faces == 12
    assert summary.edges >= 12
    assert summary.connected_elements == 1
    assert summary.warning_text


def test_editable_mesh_snapshot_builds_stable_topology(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)

    snapshot = EditableMeshSnapshot.from_path(input_path)
    validation = snapshot.validate()

    assert snapshot.vertex_order[0] == "v_000000"
    assert snapshot.face_order[0] == "f_000000"
    assert snapshot.vertex_count == 8
    assert snapshot.face_count == 12
    assert snapshot.edge_count >= 18
    assert validation.status == "passed"
    assert snapshot.face_neighbors("f_000000")


def test_editable_mesh_validation_and_components_for_open_mesh():
    snapshot = EditableMeshSnapshot.from_arrays(
        np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (3.0, 0.0, 0.0),
                (4.0, 0.0, 0.0),
                (3.0, 1.0, 0.0),
            ]
        ),
        np.asarray([(0, 1, 2), (3, 4, 5)]),
    )

    validation = snapshot.validate()

    assert validation.status == "warnings"
    assert "boundary edges" in " ".join(validation.warnings)
    assert snapshot.connected_face_component("f_000000") == {"f_000000"}
    assert snapshot.connected_face_component("f_000001") == {"f_000001"}


def test_editable_mesh_history_deletes_faces_and_undoes():
    snapshot = EditableMeshSnapshot.from_arrays(
        np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (1.0, 1.0, 0.0),
            ]
        ),
        np.asarray([(0, 1, 2), (1, 3, 2)]),
    )
    history = EditableMeshHistory(snapshot)
    shared_edge_before = _edge_for_vertices(snapshot, "v_000001", "v_000002")

    delta = history.delete_faces({"f_000000"})

    assert delta.removed_face_ids == ("f_000000",)
    assert history.current.face_order == ("f_000001",)
    assert "v_000000" not in history.current.vertices
    assert _edge_for_vertices(history.current, "v_000001", "v_000002") == shared_edge_before
    assert history.undo() == delta
    assert history.current.face_count == 2
    assert history.redo() == delta
    assert history.current.face_count == 1


def _edge_for_vertices(snapshot: EditableMeshSnapshot, a: str, b: str) -> str | None:
    target = tuple(sorted((a, b)))
    for edge in snapshot.edges.values():
        if tuple(sorted(edge.vertex_ids)) == target:
            return edge.id
    return None


def test_mesh_selection_state_counts_and_mode_clear():
    state = MeshSelectionState(active_object_id="obj")
    state.selected_vertices = {1, 2, 3}
    state.set_mode("face")

    assert state.selected_vertices == set()
    assert state.mode == "face"
    assert state.counts()["vertices"] == 0


def test_operation_history_undo_redo_path_commands(tmp_path):
    history = OperationHistory()
    command = ScenePathCommand(
        label="normalize_scale",
        object_id="obj",
        before_path=tmp_path / "before.glb",
        after_path=tmp_path / "after.glb",
    )

    history.record(command)

    assert history.undo() == command
    assert history.redo() == command


def test_modeling_tools_emit_viewport_modes(qapp):
    panel = ModelingToolsPanel()
    seen: list[tuple[str, str]] = []
    panel.selectionModeRequested.connect(lambda mode: seen.append(("selection", mode)))
    panel.transformModeRequested.connect(lambda mode: seen.append(("transform", mode)))

    try:
        panel._selection_buttons["face"].click()
        panel._transform_buttons["scale"].click()

        assert ("selection", "face") in seen
        assert ("transform", "scale") in seen
    finally:
        panel.deleteLater()


def test_modeling_tools_emit_transform_edits(qapp):
    panel = ModelingToolsPanel()
    seen = []
    panel.transformEdited.connect(seen.append)

    try:
        panel._translate["X"].setValue(3.5)

        assert seen
        assert seen[-1].translate[0] == 3.5
    finally:
        panel.deleteLater()


def test_modeling_tools_exposes_operation_options(qapp):
    panel = ModelingToolsPanel()
    try:
        panel.decimate_ratio.setValue(0.25)
        panel.smooth_iterations.setValue(7)

        options = panel.operation_options()

        assert options["target_ratio"] == 0.25
        assert options["smooth_iterations"] == 7
    finally:
        panel.deleteLater()
