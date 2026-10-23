from __future__ import annotations

from dataclasses import replace
import time

from PySide6 import QtCore, QtWidgets

from ghostforge_core import CoreConfig
from ghostforge_core.manifest import read_manifest
from ghostforge_core.workers.stub import StubTextTo3DWorker
from ghostforge_qt.layouts import ToolbarLayout, WorkspaceLayoutLoadResult, default_workspace_layouts, settings_scope_for_path
from ghostforge_qt.models.scene_model import SceneObjectRecord, TransformState
from ghostforge_qt.services.core_bridge import CoreBridge
from ghostforge_qt.viewports.transform_gizmo import TransformGizmoEdit
from ghostforge_qt.workspaces import WorkspaceModuleLoadResult, WorkspaceViewportDefaults, default_workspace_modules
from ghostforge_qt.windows.main_window import MainWindow, WINDOW_LAYOUT_STATE_VERSION
import ghostforge_qt.windows.main_window as main_window_module
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
        assert "edit.delete_selection" in ids
        assert "view.frame_selected" in ids
        assert "asset.unwrap" in ids
        assert "asset.texture" in ids
        assert "asset.audit" in ids
        assert "asset.export_bridge" in ids
        assert "asset.delete_generated" in ids
        assert "workspace.modeling" in ids
        assert "workspace.generation" in ids
        assert "view.save_layout" in ids
        assert "view.reset_layout" in ids
        assert "help.testing_guide" in ids
        assert "help.create_test_cube" in ids
        assert window.centralWidget() is window.central_splitter
        assert window.central_splitter.widget(0) is window.viewport
        assert window.central_splitter.widget(1) is window.editor_status_strip
        assert bool(window.dockOptions() & QtWidgets.QMainWindow.DockOption.AllowNestedDocks)
        assert bool(window.dockOptions() & QtWidgets.QMainWindow.DockOption.AllowTabbedDocks)
        assert window.viewport.minimumWidth() <= 680
        assert window._dock_widgets["graph"].minimumWidth() <= 180
        assert window.worker_panel.model.rowCount() >= 1
        assert window.content_panel.project.root == (tmp_path / "project").resolve()
        assert window.workspace_panel.current_module_id() == "modeling"
        assert window.modeling_panel is not None
        assert window.operation_graph_panel.palette_model.rowCount() >= 1
        assert window.viewport_panel.model.rowCount() > 0
        assert "viewport" in window._dock_widgets
        assert window.theme_panel is not None
        assert any(theme.id == "ghost_rigger_dark" for theme in window.theme_manager.themes())
        assert not window.actions.get("file.save_scene").icon().isNull()
        assert not window.actions.get("workspace.modeling").icon().isNull()
        assert window.main_toolbar.objectName() == "GhostForgeMainToolbar"
        assert window.workspace_toolbar.objectName() == "GhostForgeWorkspaceToolbar"
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        assert window.workspace_toolbar.iconSize() == QtCore.QSize(18, 18)
        assert window.editor_status_strip.objectName() == "GhostForgeEditorBottomStrip"
        assert "Workspace: Modeling" in window.editor_status_strip.workspace_label.text()
        assert window.workspace_command_ids() == [
            "file.import_mesh",
            "edit.delete_selection",
            "edit.undo",
            "edit.redo",
            "view.frame_all",
            "view.frame_selected",
        ]

        window.activate_workspace_module("generation")

        assert window.workspace_panel.current_module_id() == "generation"
        assert window.actions.get("workspace.generation").isChecked()
        assert window.workspace_command_ids() == ["view.refresh_runtime", "tools.worker_models"]
        assert window.viewport.renderer.canvas.display_mode == "shaded"
        assert window.viewport.renderer.canvas.selection_mode == "object"
        assert window._dock_widgets["viewport"].isHidden()
        assert not window._dock_widgets["workers"].isHidden()
        assert not window._dock_widgets["jobs"].isHidden()
        assert window._dock_widgets["scene"].isHidden()
        assert "Workspace: Generation" in window.editor_status_strip.workspace_label.text()

        window.activate_workspace_module("uv_materials")

        assert window.viewport.renderer.canvas.display_mode == "uv"
        assert window.viewport.renderer.canvas.selection_mode == "face"
        assert window.viewport.renderer.canvas.navigation.profile == "blender"
        assert window.viewport.renderer.canvas.navigation.grid_visible is False
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon

        window.activate_workspace_module("sculpt_retopo")

        assert window.workspace_command_ids() == ["view.frame_all", "view.frame_selected"]
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        assert window.workspace_toolbar.iconSize() == QtCore.QSize(20, 20)
        assert not window.editor_status_strip.isHidden()
    finally:
        window.close()


def test_main_window_persists_workspace_layout_state(qapp, tmp_path):
    data_root = tmp_path / "data"
    bridge = CoreBridge(config=CoreConfig(data_root=data_root, dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.activate_workspace_module("uv_materials")
        window._dock_widgets["theme"].setVisible(True)
        window.viewport.set_navigation_profile("blender")
        window.viewport.set_camera_preset("left")
        window.viewport.set_grid_visible(False)
        window.save_window_layout()

        assert int(window._settings.value(window._layout_settings_key("chrome_version"))) == WINDOW_LAYOUT_STATE_VERSION
    finally:
        window.close()

    restored_bridge = CoreBridge(config=CoreConfig(data_root=data_root, dispatch_jobs=False))
    restored = MainWindow(bridge=restored_bridge)
    try:
        assert restored.workspace_panel.current_module_id() == "uv_materials"
        assert restored.actions.get("workspace.uv_materials").isChecked()
        assert restored.viewport.renderer.canvas.navigation.profile == "blender"
        assert restored.viewport.renderer.canvas.camera_preset == "left"
        assert restored.viewport.renderer.canvas.navigation.grid_visible is False
        assert not restored._dock_widgets["content"].isHidden()
        assert not restored._dock_widgets["graph"].isHidden()

        restored.reset_workspace_layout()

        assert restored.workspace_panel.current_module_id() == "uv_materials"
        assert restored._dock_widgets["workers"].isHidden()
        assert int(restored._settings.value(restored._layout_settings_key("chrome_version"))) == WINDOW_LAYOUT_STATE_VERSION
    finally:
        restored.close()


def test_main_window_discards_stale_saved_chrome_state(qapp, tmp_path):
    data_root = tmp_path / "stale_data"
    scope = settings_scope_for_path(data_root)
    settings = QtCore.QSettings("Ghost Forge", "Ghost Forge")
    settings.setValue(f"layouts/{scope}/workspace", "generation")
    settings.setValue(f"layouts/{scope}/chrome_version", 0)
    settings.setValue(f"layouts/{scope}/geometry", QtCore.QByteArray(b"old_geometry"))
    settings.setValue(f"layouts/{scope}/state", QtCore.QByteArray(b"old_state"))
    settings.sync()

    bridge = CoreBridge(config=CoreConfig(data_root=data_root, dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        assert window.workspace_panel.current_module_id() == "generation"
        assert window._settings.value(window._layout_settings_key("geometry")) is None
        assert window._settings.value(window._layout_settings_key("state")) is None
        assert int(window._settings.value(window._layout_settings_key("chrome_version"))) == WINDOW_LAYOUT_STATE_VERSION
        assert window._dock_widgets["viewport"].isHidden()
        assert not window._dock_widgets["workers"].isHidden()
    finally:
        window.close()


def test_main_window_reloads_workspace_layouts_and_reapplies_active_module(qapp, tmp_path, monkeypatch):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.activate_workspace_module("generation")
        layouts = default_workspace_layouts()
        layouts["generation"] = replace(
            layouts["generation"],
            layout_id="generation_reloaded_test",
            name="Generation Reloaded Test",
            toolbar=ToolbarLayout(workspace_button_mode="iconOnly", workspace_icon_size=15),
            spacing={
                "margin": 4,
                "panelSpacing": 4,
                "toolbarSpacing": 2,
                "inputHeight": 32,
                "tableRowHeight": 31,
                "treeRowHeight": 29,
            },
        )

        def fake_load_workspace_layouts(*, selected_layout_ids=None):
            return WorkspaceLayoutLoadResult(
                layouts=layouts,
                diagnostics=("custom generation layout warning",),
            )

        monkeypatch.setattr(main_window_module, "load_workspace_layouts", fake_load_workspace_layouts)

        window.reload_workspace_layouts()

        assert window.workspace_layouts["generation"].layout_id == "generation_reloaded_test"
        assert window.workspace_panel.current_module_id() == "generation"
        assert "Generation Reloaded Test" in window.workspace_panel.summary.text()
        assert "custom generation layout warning" in window.workspace_panel.layout_diagnostics.text()
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        assert window.workspace_toolbar.iconSize() == QtCore.QSize(15, 15)
        assert window.workspace_toolbar.layout().spacing() == 2
        assert window.workspace_panel.layout().spacing() == 4
        assert window.workspace_panel.view.verticalHeader().defaultSectionSize() == 31
        assert window.viewport.camera_combo.minimumHeight() == 32
        assert window.central_splitter.handleWidth() == 6
        assert window.content_panel.tree.uniformRowHeights() is True
        assert "1 diagnostics" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_main_window_loads_and_reloads_workspace_modules(qapp, tmp_path, monkeypatch):
    base_modules = default_workspace_modules()
    module_path = tmp_path / "modeling_plus.json"
    first_modeling = replace(
        base_modules[0],
        label="Modeling Plus",
        status="custom",
        toolbar_action_ids=("view.frame_all",),
        viewport_defaults=WorkspaceViewportDefaults(
            display_mode="xray",
            selection_mode="face",
            transform_mode="move",
            navigation_profile="blender",
            grid_visible=False,
            snap_enabled=True,
            gizmo_orientation="local",
            gizmo_pivot="object_origin",
        ),
        source_path=module_path,
    )
    reloaded_modeling = replace(
        first_modeling,
        label="Modeling Reloaded",
        toolbar_action_ids=("file.import_mesh", "view.frame_all"),
        viewport_defaults=replace(first_modeling.viewport_defaults, display_mode="solid"),
    )
    current_result = {
        "value": WorkspaceModuleLoadResult(
            modules=(first_modeling, *base_modules[1:]),
            diagnostics=("custom module warning",),
        )
    }

    def fake_load_workspace_modules():
        return current_result["value"]

    monkeypatch.setattr(main_window_module, "load_workspace_modules", fake_load_workspace_modules)

    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        canvas = window.viewport.renderer.canvas

        assert window.workspace_modules[0].label == "Modeling Plus"
        assert window.actions.get("workspace.modeling").text() == "Modeling Plus"
        assert "custom module warning" in window.workspace_panel.module_diagnostics.text()
        assert window.workspace_command_ids() == ["view.frame_all"]
        assert canvas.display_mode == "xray"
        assert canvas.selection_mode == "face"
        assert canvas.navigation.profile == "blender"
        assert canvas.navigation.grid_visible is False
        assert canvas.navigation.snap_enabled is True
        assert canvas.gizmo_orientation == "local"
        assert canvas.gizmo_pivot == "object_origin"

        current_result["value"] = WorkspaceModuleLoadResult(
            modules=(reloaded_modeling, *base_modules[1:]),
            diagnostics=(),
        )
        window.reload_workspace_modules()

        assert window.workspace_modules[0].label == "Modeling Reloaded"
        assert window.actions.get("workspace.modeling").text() == "Modeling Reloaded"
        assert window.workspace_panel.current_module_id() == "modeling"
        assert "Module diagnostics: clean." in window.workspace_panel.module_diagnostics.text()
        assert window.workspace_command_ids() == ["file.import_mesh", "view.frame_all"]
        assert canvas.display_mode == "solid"
    finally:
        window.close()


def test_main_window_workspace_resource_watcher_reloads_modules_and_layouts(qapp, tmp_path, monkeypatch):
    module_dir = tmp_path / "workspace_modules"
    layout_dir = tmp_path / "workspace_layouts"
    module_dir.mkdir()
    layout_dir.mkdir()
    base_modules = default_workspace_modules()
    base_layouts = default_workspace_layouts()
    reloaded_modeling = replace(
        base_modules[0],
        label="Modeling Watched",
        toolbar_action_ids=("view.frame_all",),
        source_path=module_dir / "modeling.json",
    )
    watched_layouts = dict(base_layouts)
    watched_layouts["modeling"] = replace(
        base_layouts["modeling"],
        layout_id="modeling_watched_layout",
        name="Modeling Watched Layout",
        toolbar=ToolbarLayout(workspace_button_mode="iconOnly", workspace_icon_size=13),
        source_path=str(layout_dir / "modeling.json"),
    )
    module_result = {
        "value": WorkspaceModuleLoadResult(
            modules=base_modules,
            diagnostics=(),
            module_dirs=(module_dir,),
        )
    }
    layout_result = {
        "value": WorkspaceLayoutLoadResult(
            layouts=base_layouts,
            diagnostics=(),
            layout_dirs=(layout_dir,),
        )
    }

    def fake_load_workspace_modules():
        return module_result["value"]

    def fake_load_workspace_layouts(*, selected_layout_ids=None):
        return layout_result["value"]

    monkeypatch.setattr(main_window_module, "load_workspace_modules", fake_load_workspace_modules)
    monkeypatch.setattr(main_window_module, "load_workspace_layouts", fake_load_workspace_layouts)

    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.set_workspace_live_reload_enabled(True)

        assert window.workspace_panel.live_reload_check.isChecked()
        assert "Workspace resources: watching" in window.workspace_panel.resource_watch_label.text()

        module_result["value"] = WorkspaceModuleLoadResult(
            modules=(reloaded_modeling, *base_modules[1:]),
            diagnostics=("module watch warning",),
            module_dirs=(module_dir,),
        )
        window.workspace_resource_watcher.trigger_reload("modules")

        assert window.workspace_modules[0].label == "Modeling Watched"
        assert window.actions.get("workspace.modeling").text() == "Modeling Watched"
        assert "module watch warning" in window.workspace_panel.module_diagnostics.text()

        layout_result["value"] = WorkspaceLayoutLoadResult(
            layouts=watched_layouts,
            diagnostics=("layout watch warning",),
            layout_dirs=(layout_dir,),
        )
        window.workspace_resource_watcher.trigger_reload("layouts")

        assert window.workspace_layouts["modeling"].layout_id == "modeling_watched_layout"
        assert "Modeling Watched Layout" in window.workspace_panel.summary.text()
        assert "layout watch warning" in window.workspace_panel.layout_diagnostics.text()
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        assert window.workspace_toolbar.iconSize() == QtCore.QSize(13, 13)
    finally:
        window.close()


def test_main_window_selects_and_persists_workspace_layout_preset(qapp, tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    base_layouts = default_workspace_layouts()
    modeling_preset = replace(
        base_layouts["modeling"],
        layout_id="modeling_artist_test",
        name="Modeling Artist Test",
        toolbar=ToolbarLayout(workspace_button_mode="iconOnly", workspace_icon_size=14),
        spacing={
            "margin": 4,
            "panelSpacing": 4,
            "toolbarSpacing": 2,
            "inputHeight": 24,
            "tableRowHeight": 21,
            "treeRowHeight": 21,
        },
    )
    available = {module_id: (layout,) for module_id, layout in base_layouts.items()}
    available["modeling"] = (base_layouts["modeling"], modeling_preset)

    def fake_load_workspace_layouts(*, selected_layout_ids=None):
        selected_layout_ids = selected_layout_ids or {}
        layouts = dict(base_layouts)
        if selected_layout_ids.get("modeling") == "modeling_artist_test":
            layouts["modeling"] = modeling_preset
        return WorkspaceLayoutLoadResult(
            layouts=layouts,
            available_layouts=available,
            selected_layout_ids={module_id: layout.layout_id for module_id, layout in layouts.items()},
        )

    monkeypatch.setattr(main_window_module, "load_workspace_layouts", fake_load_workspace_layouts)

    bridge = CoreBridge(config=CoreConfig(data_root=data_root, dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        assert window.workspace_layouts["modeling"].layout_id == "modeling_default"
        assert window.workspace_panel.layout_combo.findData("modeling_artist_test") >= 0

        window.select_workspace_layout("modeling", "modeling_artist_test")

        assert window.workspace_layouts["modeling"].layout_id == "modeling_artist_test"
        assert window.workspace_panel.layout_combo.currentData() == "modeling_artist_test"
        assert window.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
        assert window.workspace_toolbar.iconSize() == QtCore.QSize(14, 14)
        assert window.workspace_toolbar.layout().spacing() == 2
    finally:
        window.close()

    restored_bridge = CoreBridge(config=CoreConfig(data_root=data_root, dispatch_jobs=False))
    restored = MainWindow(bridge=restored_bridge)
    try:
        assert restored.workspace_layouts["modeling"].layout_id == "modeling_artist_test"
        assert restored.workspace_panel.layout_combo.currentData() == "modeling_artist_test"
        assert restored.workspace_toolbar.toolButtonStyle() == QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly
    finally:
        restored.close()


def test_main_window_opens_and_reveals_graph_result_paths(qapp, tmp_path, monkeypatch):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    output_path = tmp_path / "asset.glb"
    asset_dir = tmp_path / "asset"
    output_path.write_text("mesh")
    asset_dir.mkdir()
    opened: list[object] = []
    revealed: list[object] = []

    def fake_open(path):
        opened.append(path)
        return True

    def fake_reveal(path):
        revealed.append(path)
        return True

    monkeypatch.setattr(window, "_open_local_path_url", fake_open)
    monkeypatch.setattr(window, "_reveal_local_path", fake_reveal)
    try:
        assert window._open_graph_result_path(str(output_path))
        assert opened[-1] == output_path

        assert window._reveal_graph_result_path(str(output_path))
        assert revealed[-1] == output_path

        assert window._reveal_graph_result_path(str(asset_dir))
        assert revealed[-1] == asset_dir

        assert not window._open_graph_result_path(str(tmp_path / "missing.glb"))
    finally:
        window.close()


def test_main_window_create_test_cube_imports_known_mesh(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        target = window.create_test_cube()

        assert target is not None
        assert target.exists()
        assert target.name == "ghostforge_test_cube.glb"
        assert window.scene_model.rowCount() == 1
        assert window.scene_model.records()[0].path == target
        assert "Test cube imported" in window.statusBar().currentMessage()
    finally:
        window.close()


def test_main_window_deletes_scene_objects_and_undoes(qapp, tmp_path):
    source_a = tmp_path / "cube_a.glb"
    source_b = tmp_path / "cube_b.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source_a)
    trimesh.creation.box(extents=(2, 1, 1)).export(source_b)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source_a)
        window.import_mesh(source_b)
        first = window.scene_model.records()[0]
        second = window.scene_model.records()[1]
        window.scene_panel.view.selectRow(0)

        removed = window._delete_selected_scene_objects(confirm=False)

        assert [record.object_id for record in removed] == [first.object_id]
        assert window.scene_model.rowCount() == 1
        assert window.scene_model.records()[0].object_id == second.object_id
        assert len(window.viewport.renderer.canvas.objects) == 1
        assert window.operation_history.undo_stack[-1].label == "delete_scene_objects"

        window.undo_operation()

        assert window.scene_model.rowCount() == 2
        assert [record.object_id for record in window.scene_model.records()] == [first.object_id, second.object_id]
        assert len(window.viewport.renderer.canvas.objects) == 2

        window.redo_operation()

        assert window.scene_model.rowCount() == 1
        assert window.scene_model.records()[0].object_id == second.object_id
    finally:
        window.close()


def test_main_window_deletes_selected_generated_files_safely(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        graph_dir = window.project_service.root / "outputs" / "graphs" / "graph_cleanup"
        graph_dir.mkdir(parents=True)
        mesh_path = graph_dir / "graph_result.glb"
        trimesh.creation.box(extents=(1, 1, 1)).export(mesh_path)
        asset_dir = window.project_service.root / "assets" / "generated_obj" / "graph_result"
        asset_dir.mkdir(parents=True)
        manifest_path = asset_dir / "asset_manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        (graph_dir / "side_effect.txt").write_text("artifact", encoding="utf-8")
        info = bridge.mesh_info(mesh_path)
        record = SceneObjectRecord(
            object_id="generated_obj",
            name="generated_obj",
            path=mesh_path,
            vertices=info.vertices,
            faces=info.faces,
            watertight=info.watertight,
            asset_dir=asset_dir,
            manifest_path=manifest_path,
            operation_graph_history=({"status": "succeeded", "output_path": str(mesh_path)},),
        )
        window.scene_model.add_record(record)
        window.scene_panel.view.selectRow(0)

        removed = window._delete_selected_generated_assets(confirm=False)

        assert set(removed) == {graph_dir.resolve(), asset_dir.resolve()}
        assert not graph_dir.exists()
        assert not asset_dir.exists()
        assert window.scene_model.rowCount() == 0
        assert not window.operation_history.undo_stack
    finally:
        window.close()


def test_main_window_generated_delete_does_not_remove_imported_source(qapp, tmp_path):
    source = tmp_path / "external_source.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]

        removed = window._delete_selected_generated_assets(confirm=False)

        assert removed == ()
        assert source.exists()
        assert record.asset_dir is not None
        assert record.asset_dir.exists()
        assert window.scene_model.rowCount() == 1
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


def test_main_window_creates_engine_bridge_from_selected_manifest(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]

        package_path = window._create_graph_result_engine_bridge("unity")

        assert package_path is not None
        assert package_path.exists()
        assert package_path.name == "ghostforge_bridge_unity.json"
        refreshed = read_manifest(record.asset_dir)
        assert refreshed.custom["engine_export_bridges"][-1]["target_engine"] == "unity"
        assert "Bridges: unity" in window.operation_graph_panel.result_readiness.text()
        assert window.operation_graph_panel.create_unity_bridge_button.isEnabled()
    finally:
        window.close()


def test_main_window_plans_retarget_graph_from_selected_manifest(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    scene_path = tmp_path / "data" / "project" / "scenes" / "retarget_scene.gforge"
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]

        graph = window._plan_graph_result_retarget("unreal")

        assert graph is not None
        assert graph.graph_id == f"{record.object_id}_retarget_unreal"
        assert graph.base_asset_path == str(source)
        assert graph.output_path.endswith("retarget_result.glb")
        assert graph.nodes
        assert window.scene_model.records()[0].operation_graph == graph
        assert window.scene_model.records()[0].operation_graph_history[0]["status"] == "planned"
        assert (
            window.scene_model.records()[0].operation_graph_history[0]["details"]["retarget_target"]
            == "unreal"
        )
        assert window.operation_graph_panel.graph().graph_id == graph.graph_id
        assert window.operation_graph_panel.graph_model.rowCount() == len(graph.nodes)
        assert "Unreal retarget plan" in window.operation_graph_panel.retarget_diagnostics.text()
        assert bridge.context.graphs.load(graph.graph_id).nodes == graph.nodes

        window.save_scene(scene_path)
        window.new_scene()
        window.open_scene(scene_path)

        restored = window.scene_model.records()[0]
        assert restored.operation_graph is not None
        assert restored.operation_graph.graph_id == graph.graph_id
        assert restored.operation_graph_history[0]["details"]["retarget_target"] == "unreal"
        assert "Unreal retarget plan" in window.operation_graph_panel.retarget_diagnostics.text()
        assert "axis_mismatch_assumed" in window.operation_graph_panel.retarget_diagnostics.text()
    finally:
        window.close()


def test_main_window_records_retarget_comparison_after_graph_evaluation(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)

        graph = window._plan_graph_result_retarget("unreal")
        assert graph is not None
        assert graph.nodes

        window._evaluate_operation_graph()
        assert window._graph_job_contexts
        _wait_for_graph_jobs(window)

        history = window.scene_model.records()[0].operation_graph_history
        assert history[0]["status"] == "verified"
        assert history[0]["details"]["retarget_target"] == "unreal"
        assert "retarget_after_report" in history[0]["details"]
        assert "planned diagnostics resolved" in window.operation_graph_panel.retarget_diagnostics.text()
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
                "history_id": "cube_graph_latest",
                "graph_id": window.operation_graph_panel.graph().graph_id,
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_graph_out.glb"),
                "duration_ms": 7.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "audit passed",
            },
            {
                "history_id": "cube_graph_previous",
                "graph_id": window.operation_graph_panel.graph().graph_id,
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_graph_blockout.glb"),
                "duration_ms": 5.0,
                "artifact_count": 1,
                "audit_badge": "warnings",
                "message": "blockout warnings",
            },
        )
        comparison_pair = {
            "left_history_id": "cube_graph_previous",
            "right_history_id": "cube_graph_latest",
        }
        window.operation_graph_panel.set_history_payloads(history)
        window.operation_graph_panel.set_history_comparison_pair(comparison_pair)
        window.scene_model.update_record(
            record.object_id,
            operation_graph_history=window.operation_graph_panel.history_payloads(),
            operation_graph_comparison_pair=window.operation_graph_panel.history_comparison_pair(),
        )

        stored = window.scene_model.records()[0]
        assert stored.operation_graph is not None
        assert stored.operation_graph_history == history
        assert stored.operation_graph_comparison_pair == comparison_pair
        assert bridge.context.graphs.load(stored.operation_graph.graph_id).nodes[0].kind == "recenter"
        window.save_scene(scene_path)

        window.new_scene()
        assert window.scene_model.rowCount() == 0

        window.open_scene(scene_path)
        restored = window.scene_model.records()[0]
        assert restored.object_id == record.object_id
        assert restored.operation_graph is not None
        assert restored.operation_graph.nodes[0].kind == "recenter"
        assert restored.operation_graph_history[0]["graph_id"] == history[0]["graph_id"]
        assert restored.operation_graph_history[0]["history_id"] == "cube_graph_latest"
        assert restored.operation_graph_comparison_pair == comparison_pair
        assert restored.operation_graph_history[0]["mcp_links"]["graph"] == (
            f"ghostforge://graphs/{history[0]['graph_id']}"
        )
        assert "scene_object_graph_history" in restored.operation_graph_history[0]["mcp_links"]
        assert window.operation_graph_panel.graph().graph_id == restored.operation_graph.graph_id
        assert window.operation_graph_panel.graph_model.rowCount() == 1
        assert window.operation_graph_panel.history_model.rowCount() == 2
        assert window.operation_graph_panel.history_comparison_pair() == comparison_pair
        assert window.operation_graph_panel.history_compare_left.currentData() == 1
        assert window.operation_graph_panel.history_compare_right.currentData() == 0
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


def test_main_window_applies_viewport_transform_gizmo_edits(qapp, tmp_path):
    source = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(source)
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    window = MainWindow(bridge=bridge)
    try:
        window.import_mesh(source)
        record = window.scene_model.records()[0]
        before = record.transform
        transform = TransformState(translate=(2.5, 0.0, 0.0))
        edit = TransformGizmoEdit(
            object_id=record.object_id,
            mode="move",
            axis="x",
            transform=transform,
            scalar_delta=2.5,
            phase="end",
            before_transform=before,
        )

        window._viewport_transform_edited(edit)

        updated = window.scene_model.records()[0]
        assert updated.transform.translate == (2.5, 0.0, 0.0)
        assert window.mesh_selection.active_object_id == record.object_id
        assert window.mesh_selection.selected_object_ids == {record.object_id}
        assert window.viewport.renderer.canvas.objects[0].transform.translate == (2.5, 0.0, 0.0)
        assert window.modeling_panel.transform().translate == (2.5, 0.0, 0.0)
        assert len(window.operation_history.undo_stack) == 1

        window.undo_operation()
        assert window.scene_model.records()[0].transform == before
        assert window.viewport.renderer.canvas.objects[0].transform == before
        assert window.modeling_panel.transform() == before

        window.redo_operation()
        assert window.scene_model.records()[0].transform == transform
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
