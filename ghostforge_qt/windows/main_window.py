from __future__ import annotations

import json
import shutil
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ghostforge_core.authoring import EditGraph, SOURCE_OPERATION_KINDS
from ghostforge_core.manifest import ManifestBuilder, ProvenanceStep, read_manifest
from ghostforge_qt.actions import DEFAULT_ACTIONS, ActionRegistry, ActionSpec
from ghostforge_qt.layouts import (
    PanelLayout,
    WorkspaceLayout,
    dock_area,
    load_workspace_layouts,
    settings_scope_for_path,
    tool_button_style,
)
from ghostforge_qt.models.scene_model import SceneObjectRecord, SceneTableModel
from ghostforge_qt.panels import (
    ContentBrowserPanel,
    EditorStatusStrip,
    JobPanel,
    ModelingToolsPanel,
    OperationGraphPanel,
    PlaceholderPanel,
    SceneOutlinerPanel,
    ThemePanel,
    ViewportPanel,
    WorkerPanel,
    WorkspaceModulePanel,
)
from ghostforge_qt.services.core_bridge import CoreBridge
from ghostforge_qt.services.job_controller import JobController
from ghostforge_qt.services.mesh_diagnostics import MeshTopologySummary, analyze_mesh
from ghostforge_qt.services.mesh_operation_service import MeshOperationSelection, MeshOperationService
from ghostforge_qt.services.mesh_selection import MeshSelectionState, normalize_edge
from ghostforge_qt.services.operation_history import (
    OperationHistory,
    SceneDeleteCommand,
    ScenePathCommand,
    SceneTransformCommand,
)
from ghostforge_qt.services.project_service import ProjectService
from ghostforge_qt.services.scene_document import SceneDocumentService
from ghostforge_qt.theme import ThemeManager
from ghostforge_qt.viewports.viewport_host import ViewportHost
from ghostforge_qt.workspace_watcher import WorkspaceResourceWatcher
from ghostforge_qt.workspaces import WorkspaceModule, load_workspace_modules


WINDOW_LAYOUT_STATE_VERSION = 3
EDITOR_CHROME_THEME_VERSION = 2
PREFERRED_EDITOR_THEME_ID = "ghost_rigger_dark"

TESTING_GUIDE_TEXT = """Ghost Forge testing path available today:

1. Launch the Qt editor:
   python -m ghostforge_qt.main

2. Create a known mesh:
   Help > Create Test Cube
   This writes project/samples/ghostforge_test_cube.glb and imports it into the scene.

3. Test viewport basics:
   Select the cube in Scene, use F to Frame All, . to Frame Selected, and try Maya/Blender/3ds Max navigation profiles from the viewport toolbar.

4. Test object transforms:
   Use Modeling > Move/Rotate/Scale or drag the viewport gizmo. Undo/redo should restore transform edits.

5. Test graph operations:
   Open Graph, use Build > Operations to select cleanup/recenter/normalize-style operations, Add Node, adjust Params / Job, then Evaluate.

6. Test deletion:
   Select a row in Scene, press Delete or use Modeling > Select > Delete From Scene. Undo should restore it.
   Use Asset > Delete Generated Files only for project-generated outputs you want permanently removed from disk.

7. Test image/reference generation quality:
   Treat Generate Image To 3D as a blockout/source mesh. For higher fidelity, chain Worker Refine Mesh using a Hero Cleanup preset, then Worker Texture Mesh using a Hero 4K-style preset when those workers are runnable.
   Check Workers before expecting final quality; stub/silhouette workers are for pipeline tests, not production assets.

8. Test persistence:
   File > Save Scene, restart Ghost Forge, then File > Open Scene. The scene, selected graph, and result history should come back.

9. Test project content:
   Open Project chooses the project root. Content shows files under that project instead of a game library.

Current limits:
- The viewport is still the CPU-projected editor viewport, not the final GPU DCC renderer.
- AI generation depends on configured workers or hosted credentials; unavailable workers should show honest runnable/stub/missing status.
- Unity/Unreal handoff is manifest/package oriented first; direct engine import is the next bridge layer.
"""


class MainWindow(QtWidgets.QMainWindow):
    """First Qt desktop shell for Ghost Forge."""

    def __init__(self, *, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("GhostForgeMainWindow")
        self.setWindowTitle("Ghost Forge")
        self.setDockOptions(
            QtWidgets.QMainWindow.DockOption.AllowNestedDocks
            | QtWidgets.QMainWindow.DockOption.AllowTabbedDocks
            | QtWidgets.QMainWindow.DockOption.GroupedDragging
            | QtWidgets.QMainWindow.DockOption.AnimatedDocks
        )
        self.setDockNestingEnabled(True)

        self.actions = ActionRegistry(self)
        self.scene_model = SceneTableModel(self)
        self.job_controller = JobController(bridge, interval_ms=1000)
        self.project_service = ProjectService(self.bridge.data_root / "project", self)
        self.mesh_operations = MeshOperationService(self.project_service.root / "outputs")
        self.scene_documents = SceneDocumentService()
        self.current_scene_path: Path | None = None
        self.mesh_selection = MeshSelectionState()
        self.operation_history = OperationHistory()
        self._graph_job_contexts: dict[str, dict[str, object]] = {}
        self._graph_audit_job_contexts: dict[str, dict[str, object]] = {}
        self._last_jobs: tuple[object, ...] = ()
        workspace_modules = load_workspace_modules()
        self.workspace_modules = workspace_modules.modules
        self.workspace_module_diagnostics = list(workspace_modules.diagnostics)
        self.workspace_module_dirs = workspace_modules.module_dirs
        self._settings = QtCore.QSettings("Ghost Forge", "Ghost Forge")
        self._settings_scope = settings_scope_for_path(self.bridge.data_root)
        self._selected_workspace_layout_ids = self._load_selected_workspace_layout_ids()
        workspace_layouts = load_workspace_layouts(selected_layout_ids=self._selected_workspace_layout_ids)
        self.workspace_layouts = workspace_layouts.layouts
        self.workspace_layout_catalog = self._workspace_layout_catalog_from_result(workspace_layouts)
        self.workspace_layout_diagnostics = list(workspace_layouts.diagnostics)
        self.workspace_layout_dirs = workspace_layouts.layout_dirs
        self.workspace_resource_watcher = WorkspaceResourceWatcher(
            self.workspace_module_dirs,
            self.workspace_layout_dirs,
            self,
        )
        self._current_workspace_id = "modeling"
        self._workspace_actions: dict[str, QtGui.QAction] = {}
        self._dock_widgets: dict[str, QtWidgets.QDockWidget] = {}
        self.current_topology: MeshTopologySummary | None = None
        self.theme_manager = ThemeManager(self)
        self._apply_editor_chrome_theme_migration()
        self.viewport = ViewportHost(parent=self)
        self.editor_status_strip = EditorStatusStrip(self)
        self.central_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.central_splitter.setObjectName("GhostForgeCentralViewportSplitter")
        self.central_splitter.setChildrenCollapsible(False)
        self.central_splitter.addWidget(self.viewport)
        self.central_splitter.addWidget(self.editor_status_strip)
        self.central_splitter.setStretchFactor(0, 1)
        self.central_splitter.setStretchFactor(1, 0)
        self.setCentralWidget(self.central_splitter)

        self._build_actions()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_docks()
        self._restore_window_layout()
        self._restore_viewport_state()
        self._connect_models()
        self._connect_tools()
        self._connect_workspace_resource_watcher()
        self.workspace_resource_watcher.set_enabled(_settings_bool(self._settings, "workspace/live_reload", True))
        self._refresh_workspace_resource_watch_state()
        self.theme_manager.apply()
        self.viewport.apply_theme(self.theme_manager.current_theme())
        self.statusBar().showMessage(f"Ghost Forge Qt ready - data root: {self.bridge.data_root}")
        self._refresh_editor_status_strip()
        self.job_controller.start()

    def _build_actions(self) -> None:
        callbacks = {
            "file.new_scene": self.new_scene,
            "file.open_project": self.open_project_dialog,
            "file.open_scene": self.open_scene_dialog,
            "file.import_mesh": self.import_mesh_dialog,
            "file.save_scene": self.save_scene,
            "file.save_scene_as": self.save_scene_as_dialog,
            "file.quit": self.close,
            "edit.undo": self.undo_operation,
            "edit.redo": self.redo_operation,
            "edit.delete_selection": self.delete_selected_scene_objects,
            "view.refresh_runtime": self.refresh_runtime,
            "view.frame_all": self.viewport.frame_all,
            "view.frame_selected": self.viewport.frame_selected,
            "view.save_layout": self.save_window_layout,
            "view.reset_layout": self.reset_workspace_layout,
            "asset.unwrap": self.not_implemented_yet,
            "asset.texture": self.not_implemented_yet,
            "asset.audit": self.not_implemented_yet,
            "asset.export_bridge": self.not_implemented_yet,
            "asset.delete_generated": self.delete_selected_generated_assets,
            "tools.worker_models": self.refresh_runtime,
            "help.testing_guide": self.show_testing_guide,
            "help.create_test_cube": self.create_test_cube,
            "help.about": self.about,
        }
        for spec in DEFAULT_ACTIONS:
            self.actions.register(spec, callbacks.get(spec.action_id))
        self._workspace_action_group = QtGui.QActionGroup(self)
        self._workspace_action_group.setExclusive(True)
        self._register_workspace_actions()

    def _register_workspace_actions(self) -> None:
        for module in self.workspace_modules:
            self._register_workspace_action(module)

    def _register_workspace_action(self, module: WorkspaceModule) -> QtGui.QAction:
        action = self.actions.register(
            spec=ActionSpec(
                module.action_id,
                module.label,
                module.shortcut,
                module.summary,
                True,
            ),
            callback=lambda _checked=False, module_id=module.module_id: self.activate_workspace_module(module_id),
        )
        self._workspace_action_group.addAction(action)
        self._workspace_actions[module.module_id] = action
        return action

    def _build_menu_bar(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(self.actions.get("file.new_scene"))
        file_menu.addAction(self.actions.get("file.open_project"))
        file_menu.addAction(self.actions.get("file.open_scene"))
        file_menu.addAction(self.actions.get("file.import_mesh"))
        file_menu.addAction(self.actions.get("file.save_scene"))
        file_menu.addAction(self.actions.get("file.save_scene_as"))
        file_menu.addSeparator()
        file_menu.addAction(self.actions.get("file.quit"))

        asset_menu = self.menuBar().addMenu("&Asset")
        for action_id in ("asset.unwrap", "asset.texture", "asset.audit", "asset.export_bridge"):
            asset_menu.addAction(self.actions.get(action_id))
        asset_menu.addSeparator()
        asset_menu.addAction(self.actions.get("asset.delete_generated"))

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.actions.get("edit.undo"))
        edit_menu.addAction(self.actions.get("edit.redo"))
        edit_menu.addSeparator()
        edit_menu.addAction(self.actions.get("edit.delete_selection"))

        view_menu = self.menuBar().addMenu("&View")
        self.view_menu = view_menu
        self.view_menu.addAction(self.actions.get("view.refresh_runtime"))
        self.view_menu.addAction(self.actions.get("view.frame_all"))
        self.view_menu.addAction(self.actions.get("view.frame_selected"))
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.actions.get("view.save_layout"))
        self.view_menu.addAction(self.actions.get("view.reset_layout"))
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.actions.get("tools.worker_models"))

        workspace_menu = self.menuBar().addMenu("&Workspaces")
        self.workspace_menu = workspace_menu
        self._rebuild_workspace_menu()

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.actions.get("help.testing_guide"))
        help_menu.addAction(self.actions.get("help.create_test_cube"))
        help_menu.addSeparator()
        help_menu.addAction(self.actions.get("help.about"))

    def _rebuild_workspace_menu(self) -> None:
        menu = getattr(self, "workspace_menu", None)
        if menu is None:
            return
        menu.clear()
        for module in self.workspace_modules:
            action = self._workspace_actions.get(module.module_id)
            if action is None:
                action = self._register_workspace_action(module)
            menu.addAction(action)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("GhostForgeMainToolbar")
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        for action_id in (
            "file.new_scene",
            "file.open_project",
            "file.open_scene",
            "file.save_scene",
            "edit.undo",
            "edit.redo",
            "view.refresh_runtime",
        ):
            toolbar.addAction(self.actions.get(action_id))
        self.main_toolbar = toolbar

        workspace_toolbar = self.addToolBar("Workspace Commands")
        workspace_toolbar.setObjectName("GhostForgeWorkspaceToolbar")
        workspace_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        workspace_toolbar.setMovable(False)
        workspace_toolbar.setFloatable(False)
        self.workspace_toolbar = workspace_toolbar
        self._refresh_workspace_toolbar(self._workspace_module(self._current_workspace_id))

    def _build_docks(self) -> None:
        self.scene_panel = SceneOutlinerPanel(self.scene_model, self)
        self.content_panel = ContentBrowserPanel(self.project_service, self)
        self.viewport_panel = ViewportPanel(self.viewport, self)
        self.workspace_panel = WorkspaceModulePanel(
            self.workspace_modules,
            layouts=self.workspace_layouts,
            available_layouts=self.workspace_layout_catalog,
            module_diagnostics=tuple(self.workspace_module_diagnostics),
            layout_diagnostics=tuple(self.workspace_layout_diagnostics),
            parent=self,
        )
        self.modeling_panel = ModelingToolsPanel(self)
        self.operation_graph_panel = OperationGraphPanel(self.bridge, self)
        self.worker_panel = WorkerPanel(self.bridge, self)
        self.job_panel = JobPanel(self.job_controller, self)
        self.theme_panel = ThemePanel(self.theme_manager, self)
        self.properties_panel = PlaceholderPanel(
            "Properties",
            "Selected object properties, transforms, materials, and manifest metadata will live here.",
            self,
        )
        self.audit_panel = PlaceholderPanel(
            "Audit",
            "Game-readiness reports, validation history, and engine gates will live here.",
            self,
        )

        self._add_dock("workspace", "Workspace", self.workspace_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("viewport", "Viewport Tools", self.viewport_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("scene", "Scene", self.scene_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("content", "Content", self.content_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("modeling", "Modeling", self.modeling_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("graph", "Graph", self.operation_graph_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("workers", "Workers", self.worker_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("jobs", "Jobs", self.job_panel, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("properties", "Properties", self.properties_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("audit", "Audit", self.audit_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("theme", "Theme", self.theme_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self._build_dock_view_menu()
        self.activate_workspace_module("modeling", show_status=False)

    def _add_dock(
        self,
        dock_id: str,
        title: str,
        widget: QtWidgets.QWidget,
        area: QtCore.Qt.DockWidgetArea,
    ) -> QtWidgets.QDockWidget:
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(f"GhostForge{title.replace(' ', '')}Dock")
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self._dock_widgets[dock_id] = dock
        return dock

    def _build_dock_view_menu(self) -> None:
        dock_menu = self.view_menu.addMenu("Docks")
        for dock_id, dock in self._dock_widgets.items():
            action = dock.toggleViewAction()
            action.setText(dock.windowTitle())
            action.setObjectName(f"view.dock.{dock_id}")
            dock_menu.addAction(action)

    def _connect_models(self) -> None:
        self.scene_model.rowsInserted.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_model.rowsRemoved.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_model.modelReset.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_model.rowsInserted.connect(lambda *_: self._refresh_editor_status_strip())
        self.scene_model.rowsRemoved.connect(lambda *_: self._refresh_editor_status_strip())
        self.scene_model.modelReset.connect(lambda *_: self._refresh_editor_status_strip())
        self.scene_panel.view.selectionModel().selectionChanged.connect(lambda *_: self._sync_selected_context())

    def _connect_tools(self) -> None:
        self.modeling_panel.selectionModeRequested.connect(self.viewport.set_selection_mode)
        self.modeling_panel.selectionModeRequested.connect(self._set_mesh_selection_mode)
        self.modeling_panel.selectionToolRequested.connect(self._selection_tool_requested)
        self.modeling_panel.transformModeRequested.connect(self.viewport.set_transform_mode)
        self.viewport.selectionModeChanged.connect(self.modeling_panel.set_selection_mode)
        self.viewport.transformModeChanged.connect(self.modeling_panel.set_transform_mode)
        self.viewport.itemPicked.connect(self._viewport_pick_requested)
        self.viewport.transformEdited.connect(self._viewport_transform_edited)
        self.modeling_panel.toolRequested.connect(self._modeling_tool_requested)
        self.modeling_panel.transformEdited.connect(self._apply_transform_to_selection)
        self.modeling_panel.deleteSceneRequested.connect(self.delete_selected_scene_objects)
        self.modeling_panel.deleteGeneratedRequested.connect(self.delete_selected_generated_assets)
        self.operation_graph_panel.evaluateRequested.connect(self._evaluate_operation_graph)
        self.operation_graph_panel.graphChanged.connect(self._operation_graph_changed)
        self.operation_graph_panel.cancelGraphJobRequested.connect(self._cancel_graph_job)
        self.operation_graph_panel.auditGraphResultRequested.connect(self._audit_operation_graph_result)
        self.operation_graph_panel.createEngineBridgeRequested.connect(self._create_graph_result_engine_bridge)
        self.operation_graph_panel.planRetargetGraphRequested.connect(self._plan_graph_result_retarget)
        self.operation_graph_panel.openGraphPathRequested.connect(self._open_graph_result_path)
        self.operation_graph_panel.revealGraphPathRequested.connect(self._reveal_graph_result_path)
        self.operation_graph_panel.historyComparisonPairChanged.connect(self._operation_graph_comparison_pair_changed)
        self.operation_graph_panel.historyAuditFollowupRequested.connect(self._audit_operation_graph_result)
        self.workspace_panel.moduleSelected.connect(self._workspace_module_selected)
        self.workspace_panel.moduleActivated.connect(self.activate_workspace_module)
        self.workspace_panel.moduleReloadRequested.connect(self.reload_workspace_modules)
        self.workspace_panel.layoutReloadRequested.connect(self.reload_workspace_layouts)
        self.workspace_panel.layoutSelected.connect(self.select_workspace_layout)
        self.workspace_panel.liveReloadToggled.connect(self.set_workspace_live_reload_enabled)
        self.job_controller.jobsChanged.connect(self._editor_jobs_changed)
        self.job_controller.jobsChanged.connect(self._graph_jobs_changed)
        self.content_panel.fileActivated.connect(lambda path: self.import_mesh(Path(path)))
        self.theme_manager.themeChanged.connect(self._theme_changed)

    @QtCore.Slot(object)
    def _theme_changed(self, theme: object) -> None:
        self.theme_manager.apply()
        self.viewport.apply_theme(theme)

    def _apply_editor_chrome_theme_migration(self) -> None:
        stored = _settings_int(self._settings, "ui/editor_chrome_theme_version", 0)
        if stored >= EDITOR_CHROME_THEME_VERSION:
            return
        current = self.theme_manager.current_theme().id
        if current in {"forge_dark", "studio_light", "graphite_studio"}:
            self.theme_manager.select(PREFERRED_EDITOR_THEME_ID)
        self._settings.setValue("ui/editor_chrome_theme_version", EDITOR_CHROME_THEME_VERSION)
        self._settings.sync()

    def _connect_workspace_resource_watcher(self) -> None:
        self.workspace_resource_watcher.modulesChanged.connect(self.reload_workspace_modules)
        self.workspace_resource_watcher.layoutsChanged.connect(self.reload_workspace_layouts)
        self.workspace_resource_watcher.enabledChanged.connect(self._workspace_resource_reload_enabled_changed)
        self.workspace_resource_watcher.watchedPathsChanged.connect(self._workspace_resource_paths_changed)

    @QtCore.Slot(bool)
    def set_workspace_live_reload_enabled(self, enabled: bool) -> None:
        self._settings.setValue("workspace/live_reload", bool(enabled))
        self.workspace_resource_watcher.set_enabled(bool(enabled))
        self._refresh_workspace_resource_watch_state()

    @QtCore.Slot(bool)
    def _workspace_resource_reload_enabled_changed(self, _enabled: bool) -> None:
        self._refresh_workspace_resource_watch_state()

    @QtCore.Slot(object)
    def _workspace_resource_paths_changed(self, _paths: object) -> None:
        self._refresh_workspace_resource_watch_state()

    def _refresh_workspace_resource_watch_state(self) -> None:
        panel = getattr(self, "workspace_panel", None)
        if panel is None:
            return
        panel.set_resource_watch_state(
            self.workspace_resource_watcher.is_enabled(),
            self.workspace_resource_watcher.watched_paths(),
        )

    @QtCore.Slot(str)
    def _workspace_module_selected(self, module_id: str) -> None:
        module = self._workspace_module(module_id)
        if module is not None:
            self.statusBar().showMessage(f"Workspace selected: {module.label} - {module.status}.")

    @QtCore.Slot(str)
    def activate_workspace_module(self, module_id: str, *, show_status: bool = True) -> None:
        module = self._workspace_module(module_id)
        if module is None:
            return
        self._current_workspace_id = module.module_id
        self.workspace_panel.select_module(module.module_id, emit=False)
        action = self._workspace_actions.get(module.module_id)
        if action is not None and not action.isChecked():
            action.setChecked(True)
        self._refresh_workspace_toolbar(module)
        self._apply_workspace_layout(module.module_id, resize_window=False)
        self._apply_workspace_viewport_defaults(module)
        layout = self.workspace_layouts.get(module.module_id)
        for dock_id in module.dock_ids:
            dock = self._dock_widgets.get(dock_id)
            if dock is None:
                continue
            if layout is not None and not layout.panel(dock_id).visible:
                continue
            dock.setVisible(True)
            dock.raise_()
        focus = None
        for dock_id in module.primary_dock_ids:
            if layout is not None and not layout.panel(dock_id).visible:
                continue
            focus = self._dock_widgets.get(dock_id)
            if focus is not None:
                break
        if focus is not None:
            focus.raise_()
        if show_status:
            panels = ", ".join(module.primary_dock_ids)
            self.statusBar().showMessage(f"{module.label} workspace active - primary panels: {panels}.")
        self._refresh_editor_status_strip()

    @QtCore.Slot(list)
    def _editor_jobs_changed(self, jobs: list[object]) -> None:
        self._last_jobs = tuple(jobs)
        self._refresh_editor_status_strip()

    def _refresh_editor_status_strip(self) -> None:
        strip = getattr(self, "editor_status_strip", None)
        if strip is None:
            return
        module = self._workspace_module(getattr(self, "_current_workspace_id", "modeling"))
        if module is not None:
            strip.set_workspace(module.label, module.status)
        else:
            strip.set_workspace(str(getattr(self, "_current_workspace_id", "")))
        strip.set_project_root(getattr(self.project_service, "root", None))
        records = self.scene_model.records()
        strip.set_scene_counts(
            len(records),
            sum(int(record.vertices or 0) for record in records),
            sum(int(record.faces or 0) for record in records),
        )
        selected = self._selected_record()
        if selected is None:
            selection = ""
        else:
            counts = self.mesh_selection.counts()
            active_counts = [f"{key}:{value}" for key, value in counts.items() if value]
            suffix = f" | {', '.join(active_counts)}" if active_counts else ""
            selection = f"{selected.name} | {self.mesh_selection.mode}{suffix}"
        strip.set_selection_summary(selection)
        strip.set_renderer_summary(self.viewport.viewport_diagnostics())
        strip.set_jobs(self._last_jobs)

    def _apply_workspace_viewport_defaults(self, module: WorkspaceModule) -> None:
        defaults = module.viewport_defaults
        self.viewport.set_display_mode(defaults.display_mode)
        self.viewport.set_selection_mode(defaults.selection_mode)
        self.viewport.set_transform_mode(defaults.transform_mode)
        self.viewport.set_navigation_profile(defaults.navigation_profile)
        if defaults.camera_preset:
            self.viewport.set_camera_preset(defaults.camera_preset)
        if defaults.projection_mode:
            self.viewport.set_projection_mode(defaults.projection_mode)
        if defaults.grid_visible is not None:
            self.viewport.set_grid_visible(defaults.grid_visible)
        if defaults.snap_enabled is not None:
            self.viewport.set_snap_enabled(defaults.snap_enabled)
        if defaults.view_cube_visible is not None:
            self.viewport.set_view_cube_visible(defaults.view_cube_visible)
        if defaults.gizmo_orientation is not None:
            self.viewport.set_gizmo_orientation(defaults.gizmo_orientation)
        if defaults.gizmo_pivot is not None:
            self.viewport.set_gizmo_pivot(defaults.gizmo_pivot)

    def _apply_workspace_layout(self, module_id: str, *, resize_window: bool = False) -> WorkspaceLayout | None:
        layout = self.workspace_layouts.get(module_id)
        if layout is None:
            return None
        self.setUpdatesEnabled(False)
        try:
            if resize_window and not self.isMaximized():
                self.resize(layout.main_width, layout.main_height)
            viewport_min_width = min(max(420, layout.viewport.min_width), layout.spacing_value("viewportHardMinWidth", 680))
            viewport_min_height = layout.spacing_value("viewportHardMinHeight", 320)
            self.viewport.setMinimumWidth(viewport_min_width)
            self.viewport.setMinimumSize(viewport_min_width, viewport_min_height)
            if getattr(self, "editor_status_strip", None) is not None:
                self.editor_status_strip.setVisible(layout.viewport.bottom_strip_visible)
            if getattr(self, "central_splitter", None) is not None:
                bottom_height = max(24, layout.spacing_value("bottomStripHeight", 32))
                self.central_splitter.setHandleWidth(layout.spacing_value("splitterHandleWidth", 6))
                self.central_splitter.setSizes([max(420, layout.main_height - bottom_height), bottom_height])
            if getattr(self, "main_toolbar", None) is not None:
                self.main_toolbar.setVisible(layout.viewport.toolbar_visible and layout.toolbar.main_visible)
            if getattr(self, "workspace_toolbar", None) is not None:
                self.workspace_toolbar.setVisible(layout.viewport.toolbar_visible and layout.toolbar.workspace_visible)
                self.workspace_toolbar.setToolButtonStyle(tool_button_style(layout.toolbar.workspace_button_mode))
                self.workspace_toolbar.setIconSize(
                    QtCore.QSize(layout.toolbar.workspace_icon_size, layout.toolbar.workspace_icon_size)
                )
            for dock_id, dock in self._dock_widgets.items():
                panel = layout.panel(dock_id)
                self.addDockWidget(dock_area(panel.area), dock)
                dock.setVisible(panel.visible)
                self._apply_dock_size_constraints(dock, panel, layout)
                dock.resize(panel.preferred_width, panel.preferred_height)
            self._apply_dock_groups(layout)
            self._resize_workspace_docks(layout)
            self._apply_workspace_density_metrics(layout)
            self._notify_layout_aware_widgets(layout)
        finally:
            self.setUpdatesEnabled(True)
            self.update()
            self._refresh_editor_status_strip()
        return layout

    @QtCore.Slot()
    def reload_workspace_modules(self) -> None:
        result = load_workspace_modules()
        self.workspace_modules = result.modules
        self.workspace_module_diagnostics = list(result.diagnostics)
        self.workspace_module_dirs = result.module_dirs
        self.workspace_resource_watcher.set_dirs(module_dirs=self.workspace_module_dirs)
        self._workspace_actions.clear()
        self._workspace_action_group = QtGui.QActionGroup(self)
        self._workspace_action_group.setExclusive(True)
        self._register_workspace_actions()
        self._rebuild_workspace_menu()
        self.workspace_panel.set_modules(
            self.workspace_modules,
            layouts=self.workspace_layouts,
            available_layouts=self.workspace_layout_catalog,
            module_diagnostics=self.workspace_module_diagnostics,
            layout_diagnostics=self.workspace_layout_diagnostics,
        )
        active_id = self._current_workspace_id
        if self._workspace_module(active_id) is None and self.workspace_modules:
            active_id = self.workspace_modules[0].module_id
        self.activate_workspace_module(active_id, show_status=False)
        if self.workspace_module_diagnostics:
            self.statusBar().showMessage(
                f"Workspace modules reloaded with {len(self.workspace_module_diagnostics)} diagnostics."
            )
        else:
            self.statusBar().showMessage("Workspace modules reloaded.")
        self._refresh_workspace_resource_watch_state()

    @QtCore.Slot()
    def reload_workspace_layouts(self) -> None:
        result = load_workspace_layouts(selected_layout_ids=self._selected_workspace_layout_ids)
        self.workspace_layouts = result.layouts
        self.workspace_layout_catalog = self._workspace_layout_catalog_from_result(result)
        self.workspace_layout_diagnostics = list(result.diagnostics)
        self.workspace_layout_dirs = result.layout_dirs
        self.workspace_resource_watcher.set_dirs(layout_dirs=self.workspace_layout_dirs)
        self.workspace_panel.set_layouts(
            self.workspace_layouts,
            available_layouts=self.workspace_layout_catalog,
            layout_diagnostics=self.workspace_layout_diagnostics,
        )
        self._apply_workspace_layout(self._current_workspace_id, resize_window=False)
        if self.workspace_layout_diagnostics:
            self.statusBar().showMessage(
                f"Workspace layouts reloaded with {len(self.workspace_layout_diagnostics)} diagnostics."
            )
        else:
            self.statusBar().showMessage("Workspace layouts reloaded.")
        self._refresh_workspace_resource_watch_state()

    @QtCore.Slot(str, str)
    def select_workspace_layout(self, module_id: str, layout_id: str) -> None:
        if self._workspace_module(module_id) is None or not layout_id:
            return
        if not any(layout.layout_id == layout_id for layout in self.workspace_layout_catalog.get(module_id, ())):
            self.statusBar().showMessage(f"Workspace layout '{layout_id}' is not available for {module_id}.")
            return
        self._selected_workspace_layout_ids[module_id] = layout_id
        result = load_workspace_layouts(selected_layout_ids=self._selected_workspace_layout_ids)
        self.workspace_layouts = result.layouts
        self.workspace_layout_catalog = self._workspace_layout_catalog_from_result(result)
        self.workspace_layout_diagnostics = list(result.diagnostics)
        self.workspace_layout_dirs = result.layout_dirs
        self.workspace_resource_watcher.set_dirs(layout_dirs=self.workspace_layout_dirs)
        self._save_selected_workspace_layout_ids()
        self.workspace_panel.set_layouts(
            self.workspace_layouts,
            available_layouts=self.workspace_layout_catalog,
            layout_diagnostics=self.workspace_layout_diagnostics,
        )
        self.workspace_panel.select_module(module_id, emit=False)
        if module_id == self._current_workspace_id:
            self._apply_workspace_layout(module_id, resize_window=False)
        selected = self.workspace_layouts.get(module_id)
        name = selected.name if selected is not None else layout_id
        self.statusBar().showMessage(f"{module_id.replace('_', ' ').title()} layout preset selected: {name}.")

    def _apply_dock_size_constraints(
        self,
        dock: QtWidgets.QDockWidget,
        panel: PanelLayout,
        layout: WorkspaceLayout,
    ) -> None:
        min_width_cap = layout.spacing_value("dockHardMinWidth", 180)
        min_height_cap = layout.spacing_value("dockHardMinHeight", 90)
        dock_min_width = max(80, min(panel.min_width, min_width_cap))
        dock_min_height = max(48, min(panel.min_height, min_height_cap))
        dock.setMinimumSize(dock_min_width, dock_min_height)
        dock.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        child = dock.widget()
        if child is not None:
            child.setMinimumSize(max(60, dock_min_width - 20), max(36, dock_min_height - 24))
            child.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)

    def _apply_dock_groups(self, layout: WorkspaceLayout) -> None:
        split_modes = {
            "horizontal": QtCore.Qt.Orientation.Horizontal,
            "vertical": QtCore.Qt.Orientation.Vertical,
        }
        for group in layout.dock_groups:
            docks = [self._dock_widgets[dock_id] for dock_id in group.docks if dock_id in self._dock_widgets]
            if not docks:
                continue
            area = dock_area(group.area)
            anchor = docks[0]
            for dock in docks:
                self.addDockWidget(area, dock)
            if group.mode == "tabbed":
                for dock in docks[1:]:
                    self.tabifyDockWidget(anchor, dock)
                active = self._dock_widgets.get(group.active) or anchor
                active.raise_()
            elif group.mode in split_modes:
                previous = anchor
                for dock in docks[1:]:
                    self.splitDockWidget(previous, dock, split_modes[group.mode])
                    previous = dock

    def _resize_workspace_docks(self, layout: WorkspaceLayout) -> None:
        for area_name in ("left", "right"):
            docks: list[QtWidgets.QDockWidget] = []
            sizes: list[int] = []
            for dock_id, dock in self._dock_widgets.items():
                panel = layout.panel(dock_id)
                if panel.visible and panel.area == area_name:
                    docks.append(dock)
                    sizes.append(panel.preferred_width)
            if docks:
                self.resizeDocks(docks, sizes, QtCore.Qt.Orientation.Horizontal)
        bottom_docks: list[QtWidgets.QDockWidget] = []
        bottom_sizes: list[int] = []
        for dock_id, dock in self._dock_widgets.items():
            panel = layout.panel(dock_id)
            if panel.visible and panel.area == "bottom":
                bottom_docks.append(dock)
                bottom_sizes.append(panel.preferred_height)
        if bottom_docks:
            self.resizeDocks(bottom_docks, bottom_sizes, QtCore.Qt.Orientation.Vertical)

    def _apply_workspace_density_metrics(self, layout: WorkspaceLayout) -> None:
        margin = layout.spacing_value("margin", 6)
        spacing = layout.spacing_value("panelSpacing", layout.spacing_value("panel.spacing", 6))
        toolbar_spacing = layout.spacing_value("toolbarSpacing", layout.spacing_value("toolbar.spacing", spacing))
        input_height = layout.spacing_value("inputHeight", 0)
        table_row = layout.spacing_value("tableRowHeight", 0)
        tree_row = layout.spacing_value("treeRowHeight", table_row)
        tab_height = layout.spacing_value("tabHeight", 0)
        tab_width = layout.spacing_value("tabWidth", 0)
        tab_padding_x = layout.spacing_value("tabPaddingX", layout.spacing_value("tabPadding", 0))
        tab_padding_y = layout.spacing_value("tabPaddingY", layout.spacing_value("tabPadding", 0))
        group_margin = layout.spacing_value("groupboxMargin", margin + 4)
        group_spacing = layout.spacing_value("groupboxSpacing", spacing)

        for child in self.findChildren(QtWidgets.QWidget):
            child_layout = child.layout()
            if child_layout is not None:
                child_layout.setSpacing(spacing)
                if isinstance(
                    child_layout,
                    (QtWidgets.QVBoxLayout, QtWidgets.QHBoxLayout, QtWidgets.QGridLayout, QtWidgets.QFormLayout),
                ):
                    child_layout.setContentsMargins(margin, margin, margin, margin)
                if isinstance(child, QtWidgets.QGroupBox):
                    child_layout.setContentsMargins(group_margin, group_margin, group_margin, group_margin)
                    child_layout.setSpacing(group_spacing)
            if input_height and isinstance(
                child,
                (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox),
            ):
                child.setMinimumHeight(input_height)
                child.setMaximumHeight(max(input_height + 6, input_height))
            if table_row and isinstance(child, (QtWidgets.QTableView, QtWidgets.QTableWidget)):
                child.verticalHeader().setDefaultSectionSize(table_row)
            if tree_row and isinstance(child, (QtWidgets.QTreeView, QtWidgets.QTreeWidget)):
                try:
                    child.setUniformRowHeights(True)
                except Exception:
                    pass
            if tab_height and isinstance(child, QtWidgets.QTabWidget):
                child.tabBar().setMinimumHeight(tab_height)
                tab_parts = [f"min-height: {tab_height}px;"]
                if tab_width:
                    tab_parts.append(f"min-width: {tab_width}px;")
                if tab_padding_x or tab_padding_y:
                    tab_parts.append(f"padding: {tab_padding_y}px {tab_padding_x}px;")
                child.tabBar().setStyleSheet("QTabBar::tab {" + " ".join(tab_parts) + "}")

        for toolbar in (getattr(self, "main_toolbar", None), getattr(self, "workspace_toolbar", None)):
            if toolbar is None:
                continue
            toolbar_layout = toolbar.layout()
            if toolbar_layout is not None:
                toolbar_layout.setSpacing(toolbar_spacing)

    def _notify_layout_aware_widgets(self, layout: WorkspaceLayout) -> None:
        for widget in self.findChildren(QtWidgets.QWidget):
            hook = getattr(widget, "apply_ghost_layout", None)
            if callable(hook):
                hook(layout)

    @QtCore.Slot()
    def save_window_layout(self) -> None:
        self._save_window_layout()
        self.statusBar().showMessage("Window layout saved.")

    @QtCore.Slot()
    def reset_workspace_layout(self) -> None:
        self._settings.remove(self._layout_settings_key("geometry"))
        self._settings.remove(self._layout_settings_key("state"))
        self._settings.setValue(self._layout_settings_key("chrome_version"), WINDOW_LAYOUT_STATE_VERSION)
        self._apply_workspace_layout(self._current_workspace_id, resize_window=True)
        module = self._workspace_module(self._current_workspace_id)
        if module is not None:
            self.workspace_panel.select_module(module.module_id, emit=False)
        self.statusBar().showMessage(f"{self._current_workspace_id.replace('_', ' ').title()} layout reset.")

    def _restore_window_layout(self) -> None:
        workspace_id = str(self._settings.value(self._layout_settings_key("workspace"), "modeling"))
        if self._workspace_module(workspace_id) is None:
            workspace_id = "modeling"
        self.activate_workspace_module(workspace_id, show_status=False)
        if not self._saved_window_chrome_is_current():
            self._discard_saved_window_chrome()
            return
        geometry = self._settings.value(self._layout_settings_key("geometry"))
        state = self._settings.value(self._layout_settings_key("state"))
        if isinstance(geometry, QtCore.QByteArray) and not geometry.isEmpty():
            if not self.restoreGeometry(geometry):
                self._settings.remove(self._layout_settings_key("geometry"))
        if isinstance(state, QtCore.QByteArray) and not state.isEmpty():
            if not self.restoreState(state, WINDOW_LAYOUT_STATE_VERSION):
                self._settings.remove(self._layout_settings_key("state"))
                self._apply_workspace_layout(self._current_workspace_id, resize_window=False)

    def _save_window_layout(self) -> None:
        self._settings.setValue(self._layout_settings_key("workspace"), self._current_workspace_id)
        self._settings.setValue(self._layout_settings_key("geometry"), self.saveGeometry())
        self._settings.setValue(self._layout_settings_key("state"), self.saveState(WINDOW_LAYOUT_STATE_VERSION))
        self._settings.setValue(self._layout_settings_key("chrome_version"), WINDOW_LAYOUT_STATE_VERSION)
        self._save_selected_workspace_layout_ids(sync=False)
        self._save_viewport_state()
        self._settings.sync()

    def _layout_settings_key(self, name: str) -> str:
        return f"layouts/{self._settings_scope}/{name}"

    def _saved_window_chrome_is_current(self) -> bool:
        return _settings_int(self._settings, self._layout_settings_key("chrome_version"), 0) >= WINDOW_LAYOUT_STATE_VERSION

    def _discard_saved_window_chrome(self) -> None:
        self._settings.remove(self._layout_settings_key("geometry"))
        self._settings.remove(self._layout_settings_key("state"))
        self._settings.setValue(self._layout_settings_key("chrome_version"), WINDOW_LAYOUT_STATE_VERSION)
        self._settings.sync()

    def _load_selected_workspace_layout_ids(self) -> dict[str, str]:
        value = self._settings.value(self._layout_settings_key("layout_presets"))
        if not value:
            return {}
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return {str(key): str(item) for key, item in payload.items() if item}

    def _save_selected_workspace_layout_ids(self, *, sync: bool = True) -> None:
        self._settings.setValue(
            self._layout_settings_key("layout_presets"),
            json.dumps(self._selected_workspace_layout_ids, sort_keys=True),
        )
        if sync:
            self._settings.sync()

    def _workspace_layout_catalog_from_result(self, result) -> dict[str, tuple[WorkspaceLayout, ...]]:  # noqa: ANN001
        if getattr(result, "available_layouts", None):
            return {module_id: tuple(layouts) for module_id, layouts in result.available_layouts.items()}
        return {module_id: (layout,) for module_id, layout in result.layouts.items()}

    def _restore_viewport_state(self) -> None:
        value = self._settings.value(self._layout_settings_key("viewport"))
        if not value:
            return
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return
        if isinstance(payload, dict):
            self.viewport.restore_navigation_state(payload)

    def _save_viewport_state(self) -> None:
        self._settings.setValue(
            self._layout_settings_key("viewport"),
            json.dumps(self.viewport.navigation_state(), sort_keys=True),
        )

    def _workspace_module(self, module_id: str) -> WorkspaceModule | None:
        for module in self.workspace_modules:
            if module.module_id == module_id:
                return module
        return None

    def _refresh_workspace_toolbar(self, module: WorkspaceModule | None) -> None:
        toolbar = getattr(self, "workspace_toolbar", None)
        if toolbar is None or module is None:
            return
        toolbar.clear()
        label = QtWidgets.QLabel(module.label, toolbar)
        label.setObjectName("GhostForgeWorkspaceToolbarLabel")
        label.setToolTip(module.summary)
        label.setMinimumWidth(128)
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
        toolbar.addWidget(label)
        toolbar.addSeparator()
        for action_id in module.toolbar_action_ids:
            try:
                toolbar.addAction(self.actions.get(action_id))
            except KeyError:
                continue
        toolbar.addSeparator()
        for workspace_module in self.workspace_modules:
            toolbar.addAction(self.actions.get(workspace_module.action_id))

    def workspace_command_ids(self) -> list[str]:
        toolbar = getattr(self, "workspace_toolbar", None)
        if toolbar is None:
            return []
        command_ids = {module.action_id for module in self.workspace_modules}
        result: list[str] = []
        for action in toolbar.actions():
            action_id = action.objectName()
            if action_id and action_id not in command_ids:
                result.append(action_id)
        return result

    @QtCore.Slot()
    def new_scene(self) -> None:
        self.scene_model.clear()
        self.mesh_selection.clear()
        self.mesh_selection.active_object_id = None
        self.operation_history.clear()
        self._graph_job_contexts.clear()
        self._graph_audit_job_contexts.clear()
        self.current_scene_path = None
        self.current_topology = None
        self.operation_graph_panel.set_active_object(None)
        self.operation_graph_panel.reset_graph()
        self.operation_graph_panel.clear_graph_job_state()
        self.operation_graph_panel.set_result_manifest(None)
        self._refresh_mesh_status()
        self._update_window_title()
        self.statusBar().showMessage("New scene")

    @QtCore.Slot()
    def import_mesh_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Mesh",
            str(Path.home()),
            "Meshes (*.glb *.gltf *.obj *.stl *.ply *.dae *.fbx);;All Files (*)",
        )
        if path:
            self.import_mesh(Path(path))

    @QtCore.Slot()
    def open_project_dialog(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Ghost Forge Project", str(self.project_service.root))
        if path:
            state = self._set_project_root(Path(path))
            self.statusBar().showMessage(f"Project opened: {state.root}")

    @QtCore.Slot()
    def open_scene_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Ghost Forge Scene",
            str(self.project_service.root / "scenes"),
            "Ghost Forge Scenes (*.gforge);;All Files (*)",
        )
        if path:
            self.open_scene(Path(path))

    def import_mesh(self, path: Path) -> None:
        try:
            info = self.bridge.mesh_info(path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Import Mesh", f"Imported without mesh stats:\n{exc}")
            info = None
        record = self.scene_model.add_mesh(path, info)
        record = self._write_manifest_for_record(record, mesh_path=path, operation="import_mesh")
        self.mesh_selection.active_object_id = record.object_id
        self.mesh_selection.selected_object_ids = {record.object_id}
        self._select_scene_object(record.object_id)
        self._sync_graph_result_manifest(record)
        self._refresh_topology(record.path)
        self._refresh_mesh_status()
        self.statusBar().showMessage(f"Imported {record.name}")

    @QtCore.Slot()
    def refresh_runtime(self) -> None:
        self.worker_panel.refresh()
        self.job_controller.refresh()
        snapshot = self.bridge.runtime_snapshot()
        self.statusBar().showMessage(
            f"Workers: {len(snapshot.workers)} | Jobs: {len(snapshot.jobs)} | KB: {snapshot.kb_count}"
        )
        self.operation_graph_panel.refresh()

    @QtCore.Slot()
    def delete_selected_scene_objects(self) -> tuple[SceneObjectRecord, ...]:
        return self._delete_selected_scene_objects(confirm=True)

    def _delete_selected_scene_objects(
        self,
        *,
        confirm: bool = True,
        record_undo: bool = True,
    ) -> tuple[SceneObjectRecord, ...]:
        rows = self._selected_scene_rows()
        if not rows:
            self.statusBar().showMessage("Select one or more scene objects to delete.")
            return ()
        records = tuple(record for row in rows if (record := self.scene_model.record_at(row)) is not None)
        if not records:
            self.statusBar().showMessage("Selected scene rows are no longer available.")
            return ()
        if confirm:
            count_text = "object" if len(records) == 1 else "objects"
            response = QtWidgets.QMessageBox.question(
                self,
                "Delete From Scene",
                f"Remove {len(records)} selected {count_text} from the scene?\n\n"
                "Mesh files and generated asset folders will remain on disk.",
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Delete cancelled.")
                return ()
        removed = self._remove_scene_rows(rows, record_undo=record_undo, label="delete_scene_objects")
        self.statusBar().showMessage(f"Deleted {len(removed)} scene object(s). Use Undo to restore.")
        return removed

    @QtCore.Slot()
    def delete_selected_generated_assets(self) -> tuple[Path, ...]:
        return self._delete_selected_generated_assets(confirm=True)

    def _delete_selected_generated_assets(self, *, confirm: bool = True) -> tuple[Path, ...]:
        rows = self._selected_scene_rows()
        if not rows:
            self.statusBar().showMessage("Select generated scene objects before deleting files.")
            return ()
        records = tuple(record for row in rows if (record := self.scene_model.record_at(row)) is not None)
        targets = self._generated_cleanup_targets(records)
        if not targets:
            self.statusBar().showMessage("No project-generated files found for the selected scene objects.")
            return ()
        if confirm:
            file_word = "item" if len(targets) == 1 else "items"
            object_word = "object" if len(records) == 1 else "objects"
            preview = "\n".join(f"- {path}" for path in targets[:8])
            if len(targets) > 8:
                preview += f"\n- ... {len(targets) - 8} more"
            response = QtWidgets.QMessageBox.question(
                self,
                "Delete Generated Files",
                f"Permanently delete {len(targets)} project-generated {file_word} and remove "
                f"{len(records)} selected scene {object_word}?\n\n{preview}",
            )
            if response != QtWidgets.QMessageBox.StandardButton.Yes:
                self.statusBar().showMessage("Generated file deletion cancelled.")
                return ()
        removed_paths: list[Path] = []
        for target in targets:
            try:
                if not target.exists():
                    continue
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            except Exception as exc:
                QtWidgets.QMessageBox.warning(self, "Delete Generated Files", f"Could not delete {target}:\n{exc}")
                continue
            removed_paths.append(target)
        if removed_paths:
            self._remove_scene_rows(rows, record_undo=False, label="delete_generated_assets")
            self.operation_history.clear()
            self.content_panel.refresh()
        self.statusBar().showMessage(
            f"Deleted {len(removed_paths)} generated file/folder item(s) and removed {len(records)} scene object(s)."
        )
        return tuple(removed_paths)

    @QtCore.Slot(str)
    def _modeling_tool_requested(self, tool_name: str) -> None:
        selected = self._selected_record()
        if selected is None:
            self.statusBar().showMessage("Select a mesh before running a modeling tool.")
            return
        if tool_name == "unwrap_uvs":
            self.not_implemented_yet()
            return
        if not self.mesh_operations.is_supported(tool_name):
            self.statusBar().showMessage(
                f"{tool_name.replace('_', ' ').title()} is staged for the operation graph."
            )
            return
        operation_selection = self._operation_selection_for(selected.object_id)
        try:
            output = self.mesh_operations.apply(
                tool_name,
                selected.path,
                **self.modeling_panel.operation_options(),
                selection=operation_selection,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Modeling Tool", str(exc))
            return
        updated = self.scene_model.append_operation(
            selected.object_id,
            output.label,
            path=output.path,
            vertices=output.info.vertices,
            faces=output.info.faces,
            watertight=output.info.watertight,
        )
        if updated is not None:
            updated = self._write_manifest_for_record(
                updated,
                mesh_path=output.path,
                operation=output.label,
                operation_parameters={"selection": self._selection_manifest_payload(operation_selection)},
            )
        self.viewport.set_scene_records(self.scene_model.records())
        if updated is not None:
            self.operation_history.record(
                ScenePathCommand(
                    label=output.label,
                    object_id=selected.object_id,
                    before_path=selected.path,
                    after_path=output.path,
                    before_vertices=selected.vertices,
                    before_faces=selected.faces,
                    before_watertight=selected.watertight,
                    after_vertices=output.info.vertices,
                    after_faces=output.info.faces,
                    after_watertight=output.info.watertight,
                )
            )
            self._refresh_topology(output.path)
            self.mesh_selection.clear_subobjects()
            self.mesh_selection.selected_object_ids = {selected.object_id}
            self._refresh_mesh_status()
            self.statusBar().showMessage(
                f"{tool_name.replace('_', ' ').title()} applied: {output.path.name}"
            )

    @QtCore.Slot()
    def _evaluate_operation_graph(self) -> None:
        graph = self.operation_graph_panel.graph()
        if not graph.nodes:
            self.statusBar().showMessage("Add graph nodes before evaluating.")
            return
        selected = self._selected_record()
        has_source_node = any(node.enabled and node.kind in SOURCE_OPERATION_KINDS for node in graph.nodes)
        if selected is None and not has_source_node:
            self.statusBar().showMessage("Select a mesh or add a source node before evaluating the graph.")
            return

        output_path = (
            self.project_service.root
            / "outputs"
            / "graphs"
            / graph.graph_id
            / "graph_result.glb"
        )
        base_asset_path = None if has_source_node else str(selected.path if selected is not None else "")
        eval_graph = graph.model_copy(
            update={
                "base_asset_path": base_asset_path,
                "output_path": str(output_path),
                "asset_id": None if selected is None or has_source_node else selected.object_id,
                "name": selected.name if selected is not None and not graph.name else graph.name,
            }
        )
        try:
            handle = self.bridge.submit_authoring_graph_evaluation(
                eval_graph,
                output_path=output_path,
                manifest_dir=self.project_service.root / "assets" / "graph_jobs" / eval_graph.graph_id,
                asset_id=selected.object_id if selected is not None and not has_source_node else eval_graph.graph_id,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Operation Graph", str(exc))
            return
        self._graph_job_contexts[handle.id] = {
            "graph": eval_graph,
            "selected_object_id": None if selected is None or has_source_node else selected.object_id,
            "source_graph": has_source_node or selected is None,
            "before_path": None if selected is None else selected.path,
            "before_vertices": None if selected is None else selected.vertices,
            "before_faces": None if selected is None else selected.faces,
            "before_watertight": None if selected is None else selected.watertight,
            "output_path": output_path,
        }
        self.operation_graph_panel.set_graph_job_submitted(handle.id)
        self.job_controller.refresh()
        self.statusBar().showMessage(f"Graph evaluation submitted: {handle.id[:12]}.")

    @QtCore.Slot(list)
    def _graph_jobs_changed(self, jobs: list) -> None:  # type: ignore[type-arg]
        if not self._graph_job_contexts and not self._graph_audit_job_contexts:
            return
        by_id = {job.id: job for job in jobs}
        for job_id in list(self._graph_job_contexts):
            job = by_id.get(job_id)
            if job is None:
                continue
            self.operation_graph_panel.set_graph_job_progress(job)
            if job.status.value not in {"succeeded", "failed", "cancelled"}:
                continue
            context = self._graph_job_contexts.pop(job_id)
            if job.status.value != "succeeded":
                message = job.error.message if job.error is not None else job.status.value
                self.operation_graph_panel.set_graph_job_finished(job, message=message)
                self.statusBar().showMessage(f"Graph job {job.id[:12]} {job.status.value}: {message}")
                continue
            message = self._apply_completed_graph_job(job.result or {}, context)
            self.operation_graph_panel.set_graph_job_finished(job, message=message)
        for job_id in list(self._graph_audit_job_contexts):
            job = by_id.get(job_id)
            if job is None:
                continue
            self.operation_graph_panel.set_graph_audit_progress(job)
            if job.status.value not in {"succeeded", "failed", "cancelled"}:
                continue
            context = self._graph_audit_job_contexts.pop(job_id)
            if job.status.value != "succeeded":
                message = job.error.message if job.error is not None else job.status.value
                self.operation_graph_panel.set_graph_audit_finished(job, message=message)
                self.statusBar().showMessage(f"Graph audit job {job.id[:12]} {job.status.value}: {message}")
                continue
            message = self._apply_completed_graph_audit(job.result or {}, context)
            self.operation_graph_panel.set_graph_audit_finished(job, message=message)

    @QtCore.Slot(str)
    def _cancel_graph_job(self, job_id: str) -> None:
        if job_id not in self._graph_job_contexts:
            self.statusBar().showMessage(f"Graph job {job_id[:12]} is no longer active.")
            return
        self.job_controller.cancel(job_id)
        self.statusBar().showMessage(f"Cancel requested for graph job {job_id[:12]}.")

    @QtCore.Slot(str)
    def _open_graph_result_path(self, path_text: str) -> bool:
        path = Path(path_text)
        if not path.exists():
            self.statusBar().showMessage(f"Graph result path missing: {path}")
            return False
        opened = self._open_local_path_url(path)
        if opened:
            self.statusBar().showMessage(f"Opened graph result path: {path}")
        else:
            self.statusBar().showMessage(f"Could not open graph result path: {path}")
        return opened

    @QtCore.Slot(str)
    def _reveal_graph_result_path(self, path_text: str) -> bool:
        path = Path(path_text)
        if not path.exists():
            self.statusBar().showMessage(f"Graph result path missing: {path}")
            return False
        opened = self._reveal_local_path(path)
        if opened:
            self.statusBar().showMessage(f"Revealed graph result path: {path}")
        else:
            self.statusBar().showMessage(f"Could not reveal graph result path: {path}")
        return opened

    def _open_local_path_url(self, path: Path) -> bool:
        return QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))

    def _reveal_local_path(self, path: Path) -> bool:
        if path.is_file() and QtCore.QOperatingSystemVersion.currentType() == QtCore.QOperatingSystemVersion.OSType.Windows:
            return QtCore.QProcess.startDetached("explorer.exe", [f"/select,{path}"])
        target = path if path.is_dir() else path.parent
        return self._open_local_path_url(target)

    @QtCore.Slot()
    @QtCore.Slot(str)
    def _audit_operation_graph_result(self, preset: str = "default") -> None:
        selected = self._selected_record()
        if selected is None or selected.asset_dir is None:
            self.statusBar().showMessage("Select a graph result with a manifest before auditing.")
            return
        if selected.manifest_path is not None and not selected.manifest_path.exists():
            self.statusBar().showMessage(f"Graph result manifest missing: {selected.manifest_path}")
            return
        try:
            handle = self.bridge.submit_audit_asset(
                selected.asset_dir,
                preset=preset or "default",
                run_gltf_validator=False,
                persist=True,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Graph Audit", str(exc))
            return
        self._graph_audit_job_contexts[handle.id] = {
            "asset_dir": selected.asset_dir,
            "object_id": selected.object_id,
        }
        self.operation_graph_panel.set_graph_audit_submitted(handle.id)
        self.job_controller.refresh()
        self.statusBar().showMessage(f"Graph audit submitted: {handle.id[:12]}.")

    def _apply_completed_graph_audit(self, result_payload: dict[str, object], context: dict[str, object]) -> str:
        asset_dir = Path(str(context["asset_dir"]))
        try:
            manifest = read_manifest(asset_dir)
        except Exception as exc:
            message = f"audit finished, but manifest refresh failed: {exc}"
            self.statusBar().showMessage(message)
            return message
        status = str(result_payload.get("status") or manifest.validation.status)
        message = (
            f"audit {status}: "
            f"{result_payload.get('error_count', manifest.validation.error_count)} errors, "
            f"{result_payload.get('warning_count', manifest.validation.warning_count)} warnings"
        )
        self.operation_graph_panel.apply_audit_manifest(manifest.model_dump(mode="json"), message=message)
        self.operation_graph_panel.set_result_manifest(
            manifest.model_dump(mode="json"),
            asset_dir=str(asset_dir),
            message=message,
        )
        self._store_selected_graph_history()
        self.statusBar().showMessage(f"Graph result {message}.")
        return message

    def _apply_completed_graph_job(self, result_payload: dict[str, object], context: dict[str, object]) -> str:
        result = self._evaluation_result_from_payload(result_payload)
        if result is not None:
            self.operation_graph_panel.set_evaluation_result(result, payload=result_payload)
        graph_history = self.operation_graph_panel.history_payloads()
        retarget_target = self._retarget_target_from_history(graph_history)
        output_raw = result_payload.get("output_path")
        output_path = Path(str(output_raw or context["output_path"]))
        if not output_path.exists():
            message = f"output missing: {output_path}"
            self.statusBar().showMessage(f"Graph job completed but {message}")
            return message
        try:
            info = self.bridge.mesh_info(output_path)
        except Exception:
            info = None
        graph_payload = result_payload.get("graph")
        graph = EditGraph.model_validate(graph_payload) if isinstance(graph_payload, dict) else context["graph"]
        metadata = result_payload.get("metadata") if isinstance(result_payload.get("metadata"), dict) else {}
        manifest_payload = {
            "graph_id": graph.graph_id if isinstance(graph, EditGraph) else "",
            "steps": result_payload.get("steps", []),
            "side_effects": metadata.get("side_effects") or [],
            "source_mode": metadata.get("source_mode"),
        }
        selected_object_id = context.get("selected_object_id")
        if selected_object_id is None:
            record = self.scene_model.add_mesh(output_path, info)
            record = (
                self.scene_model.update_record(
                    record.object_id,
                    operation_graph=graph,
                    operation_graph_history=graph_history,
                )
                or record
            )
            updated = self._write_manifest_for_record(
                record,
                mesh_path=output_path,
                operation="evaluate_authoring_graph",
                operation_parameters=manifest_payload,
            )
            self.mesh_selection.active_object_id = updated.object_id
            self.mesh_selection.selected_object_ids = {updated.object_id}
            self._select_scene_object(updated.object_id)
            self._sync_graph_result_manifest(updated)
            self._refresh_topology(output_path)
            self._refresh_mesh_status()
            self.statusBar().showMessage(f"Graph generated {output_path.name}.")
            return f"generated {output_path.name}"

        selected = self._record_by_id(str(selected_object_id))
        if selected is None:
            message = f"scene object {selected_object_id} is missing"
            self.statusBar().showMessage(f"Graph result ready, but {message}.")
            return message
        updated = self.scene_model.append_operation(
            selected.object_id,
            "evaluate_authoring_graph",
            path=output_path,
            vertices=info.vertices if info is not None else selected.vertices,
            faces=info.faces if info is not None else selected.faces,
            watertight=info.watertight if info is not None else selected.watertight,
            operation_graph=graph if isinstance(graph, EditGraph) else selected.operation_graph,
            operation_graph_history=graph_history,
        )
        if updated is not None:
            updated = self._write_manifest_for_record(
                updated,
                mesh_path=output_path,
                operation="evaluate_authoring_graph",
                operation_parameters=manifest_payload,
            )
            self.operation_history.record(
                ScenePathCommand(
                    label="evaluate_authoring_graph",
                    object_id=selected.object_id,
                    before_path=selected.path,
                    after_path=output_path,
                    before_vertices=context.get("before_vertices"),
                    before_faces=context.get("before_faces"),
                    before_watertight=context.get("before_watertight"),
                    after_vertices=updated.vertices,
                    after_faces=updated.faces,
                    after_watertight=updated.watertight,
                )
            )
            self._sync_graph_result_manifest(updated)
            self._record_retarget_comparison(updated, graph, retarget_target)
        self.viewport.set_scene_records(self.scene_model.records())
        self._refresh_topology(output_path)
        self.mesh_selection.clear_subobjects()
        self.mesh_selection.selected_object_ids = {selected.object_id}
        self._refresh_mesh_status()
        self.statusBar().showMessage(f"Graph evaluated: {output_path.name}.")
        return f"evaluated {output_path.name}"

    def _evaluation_result_from_payload(self, payload: dict[str, object]):
        try:
            from ghostforge_core.authoring import EvaluationResult

            result_payload = {
                key: payload[key]
                for key in EvaluationResult.model_fields
                if key in payload
            }
            return EvaluationResult.model_validate(result_payload)
        except Exception:
            return None

    @QtCore.Slot(object)
    def _operation_graph_changed(self, graph) -> None:  # type: ignore[no-untyped-def]
        selected = self._selected_record()
        if selected is None:
            return
        graph = graph.model_copy(
            update={
                "asset_id": selected.object_id,
                "name": selected.name if not graph.name else graph.name,
                "base_asset_path": str(selected.path),
            }
        )
        self.scene_model.update_record(
            selected.object_id,
            operation_graph=graph,
            operation_graph_history=self.operation_graph_panel.history_payloads(),
            operation_graph_comparison_pair=self.operation_graph_panel.history_comparison_pair(),
        )
        try:
            self.bridge.save_authoring_graph(graph)
        except Exception as exc:
            self.statusBar().showMessage(f"Graph save skipped: {exc}")

    @QtCore.Slot(object)
    def _operation_graph_comparison_pair_changed(self, pair: object) -> None:
        selected = self._selected_record()
        if selected is None:
            return
        self.scene_model.update_record(
            selected.object_id,
            operation_graph_comparison_pair=dict(pair) if isinstance(pair, dict) else {},
        )

    @QtCore.Slot(str)
    def _create_graph_result_engine_bridge(self, target_engine: str) -> Path | None:
        selected = self._selected_record()
        if selected is None or selected.asset_dir is None:
            self.statusBar().showMessage("Select a manifest-backed graph result before creating an engine bridge.")
            return None
        try:
            manifest = read_manifest(selected.asset_dir)
        except Exception as exc:
            self.statusBar().showMessage(f"Engine bridge blocked: manifest could not be read: {exc}")
            return None
        if manifest.validation.status not in {"passed", "warnings"} or manifest.validation.error_count:
            self.operation_graph_panel.set_result_manifest(
                manifest.model_dump(mode="json"),
                asset_dir=str(selected.asset_dir),
                message="Engine bridge blocked until audit errors are cleared.",
            )
            self.statusBar().showMessage("Engine bridge blocked until audit errors are cleared.")
            return None
        try:
            _package, package_path = self.bridge.create_engine_export_bridge(
                selected.asset_dir,
                target_engine=target_engine,
                bridge_dir=self.project_service.root / "bridges" / selected.object_id,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Engine Bridge", str(exc))
            return None
        refreshed = read_manifest(selected.asset_dir)
        self.operation_graph_panel.set_result_manifest(
            refreshed.model_dump(mode="json"),
            asset_dir=str(selected.asset_dir),
            message=f"{target_engine.title()} bridge package created: {package_path.name}",
        )
        self.statusBar().showMessage(f"{target_engine.title()} bridge package created: {package_path}")
        return package_path

    @QtCore.Slot(str)
    def _plan_graph_result_retarget(self, target_engine: str) -> EditGraph | None:
        selected = self._selected_record()
        if selected is None or selected.asset_dir is None:
            self.statusBar().showMessage("Select a manifest-backed graph result before planning retargeting.")
            return None
        graph_id = f"{selected.object_id}_retarget_{target_engine}"
        output_path = (
            self.project_service.root
            / "outputs"
            / "graphs"
            / graph_id
            / "retarget_result.glb"
        )
        try:
            graph, report = self.bridge.plan_engine_retarget_graph(
                selected.asset_dir,
                target_engine=target_engine,
                base_name=selected.name,
                graph_id=graph_id,
                output_path=output_path,
            )
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Retarget Graph", str(exc))
            return None
        graph = graph.model_copy(
            update={
                "asset_id": selected.object_id,
                "name": f"{selected.name} {target_engine.title()} Retarget",
                "base_asset_path": graph.base_asset_path or str(selected.path),
                "output_path": str(output_path),
            }
        )
        self.operation_graph_panel.set_graph(graph, emit=False)
        report_payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else {}
        message = (
            f"Planned {target_engine.title()} retarget graph: "
            f"{len(graph.nodes)} nodes from {len(getattr(report, 'issues', ()))} diagnostics."
        )
        self.operation_graph_panel.set_retarget_plan(
            target_engine=target_engine,
            graph=graph,
            report_payload=report_payload,
            message=message,
        )
        self.scene_model.update_record(
            selected.object_id,
            operation_graph=graph,
            operation_graph_history=self.operation_graph_panel.history_payloads(),
            operation_graph_comparison_pair=self.operation_graph_panel.history_comparison_pair(),
        )
        self.bridge.save_authoring_graph(graph)
        self._sync_graph_result_manifest(selected)
        self.statusBar().showMessage(message)
        self.operation_graph_panel.status.setText(message)
        return graph

    def _record_retarget_comparison(
        self,
        record: SceneObjectRecord,
        graph: EditGraph | object,
        target_engine: str,
    ) -> None:
        if not target_engine or record.asset_dir is None or not isinstance(graph, EditGraph):
            return
        try:
            report = self.bridge.lint_engine_retarget(record.asset_dir, target_engine=target_engine)
        except Exception as exc:
            self.statusBar().showMessage(f"Retarget comparison skipped: {exc}")
            return
        report_payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else {}
        self.operation_graph_panel.set_retarget_comparison(
            target_engine=target_engine,
            graph=graph,
            report_payload=report_payload,
        )
        self.scene_model.update_record(
            record.object_id,
            operation_graph_history=self.operation_graph_panel.history_payloads(),
            operation_graph_comparison_pair=self.operation_graph_panel.history_comparison_pair(),
        )

    def _retarget_target_from_history(self, history: tuple[dict[str, object], ...]) -> str:
        for payload in history:
            details = payload.get("details")
            if not isinstance(details, dict):
                continue
            target = details.get("retarget_target")
            if target:
                return str(target)
        return ""

    def _store_selected_graph_history(self) -> None:
        selected = self._selected_record()
        if selected is None:
            return
        self.scene_model.update_record(
            selected.object_id,
            operation_graph_history=self.operation_graph_panel.history_payloads(),
            operation_graph_comparison_pair=self.operation_graph_panel.history_comparison_pair(),
        )

    @QtCore.Slot(object)
    def _apply_transform_to_selection(self, transform) -> None:  # type: ignore[no-untyped-def]
        selected = self._selected_record()
        if selected is None:
            return
        if selected.transform == transform:
            return
        self.scene_model.update_transform(selected.object_id, transform)
        self.operation_history.record(
            SceneTransformCommand(
                label="edit_transform",
                object_id=selected.object_id,
                before_transform=selected.transform,
                after_transform=transform,
            )
        )
        self.viewport.set_scene_records(self.scene_model.records())

    @QtCore.Slot(object)
    def _viewport_transform_edited(self, edit) -> None:  # type: ignore[no-untyped-def]
        object_id = str(getattr(edit, "object_id", "") or "")
        transform = getattr(edit, "transform", None)
        if not object_id or transform is None:
            return
        before_transform = getattr(edit, "before_transform", None)
        phase = str(getattr(edit, "phase", "update") or "update").lower()
        updated = self.scene_model.update_transform(object_id, transform)
        if updated is None:
            return
        self._select_scene_object(object_id)
        self.mesh_selection.active_object_id = object_id
        self.mesh_selection.selected_object_ids = {object_id}
        self.viewport.set_scene_records(self.scene_model.records())
        self.modeling_panel.set_transform(transform, emit=False)
        axis = str(getattr(edit, "axis", "") or "").upper()
        mode = str(getattr(edit, "mode", "transform") or "transform").title()
        if phase == "end" and before_transform is not None and before_transform != transform:
            self.operation_history.record(
                SceneTransformCommand(
                    label=f"{mode.lower()}_gizmo_{axis.lower()}",
                    object_id=object_id,
                    before_transform=before_transform,
                    after_transform=transform,
                )
            )
        self.statusBar().showMessage(f"{mode} gizmo {axis} updated {updated.name}.")

    def _operation_selection_for(self, object_id: str) -> MeshOperationSelection:
        if self.mesh_selection.active_object_id != object_id:
            return MeshOperationSelection(mode=self.mesh_selection.mode)
        return MeshOperationSelection(
            mode=self.mesh_selection.mode,
            vertices=set(self.mesh_selection.selected_vertices),
            edges=set(self.mesh_selection.selected_edges),
            faces=set(self.mesh_selection.selected_faces),
            borders=set(self.mesh_selection.selected_borders),
            elements=set(self.mesh_selection.selected_elements),
        )

    def _selection_manifest_payload(self, selection: MeshOperationSelection) -> dict[str, object]:
        return {
            "mode": selection.mode,
            "vertices": sorted(selection.vertices),
            "edges": [list(edge) for edge in sorted(selection.edges)],
            "faces": sorted(selection.faces),
            "borders": sorted(selection.borders),
            "elements": sorted(selection.elements),
        }

    def _selected_record(self):
        selection = self.scene_panel.view.selectionModel()
        if selection is None or not selection.hasSelection():
            records = self.scene_model.records()
            return records[0] if records else None
        row = selection.selectedRows()[0].row()
        return self.scene_model.record_at(row)

    def _selected_scene_rows(self) -> tuple[int, ...]:
        selection = self.scene_panel.view.selectionModel()
        rows: set[int] = set()
        if selection is not None and selection.hasSelection():
            rows.update(index.row() for index in selection.selectedRows() if index.isValid())
        if not rows and self.mesh_selection.active_object_id:
            row = self.scene_model.row_for_object_id(self.mesh_selection.active_object_id)
            if row >= 0:
                rows.add(row)
        return tuple(sorted(row for row in rows if self.scene_model.record_at(row) is not None))

    def _remove_scene_rows(
        self,
        rows: tuple[int, ...] | list[int],
        *,
        record_undo: bool,
        label: str,
    ) -> tuple[SceneObjectRecord, ...]:
        valid_rows = tuple(sorted({int(row) for row in rows if self.scene_model.record_at(int(row)) is not None}))
        if not valid_rows:
            return ()
        records = tuple(self.scene_model.record_at(row) for row in valid_rows)
        removed_ids = {record.object_id for record in records if record is not None}
        preferred_row = valid_rows[0]
        removed: list[SceneObjectRecord] = []
        for row in sorted(valid_rows, reverse=True):
            record = self.scene_model.remove_row(row)
            if record is not None:
                removed.append(record)
        removed.reverse()
        if record_undo and removed:
            self.operation_history.record(
                SceneDeleteCommand(label=label, rows=valid_rows, records=tuple(removed))
            )
        self.mesh_selection.selected_object_ids.difference_update(removed_ids)
        if self.mesh_selection.active_object_id in removed_ids:
            self.mesh_selection.active_object_id = None
            self.mesh_selection.clear_subobjects()
        self._select_available_row(preferred_row)
        self.viewport.set_scene_records(self.scene_model.records())
        self._refresh_mesh_status()
        return tuple(removed)

    def _select_available_row(self, preferred_row: int = 0) -> None:
        selection = self.scene_panel.view.selectionModel()
        if selection is not None:
            selection.clearSelection()
        row_count = self.scene_model.rowCount()
        if row_count <= 0:
            self.mesh_selection.clear()
            self.current_topology = None
            self.operation_graph_panel.set_active_object(None)
            self.operation_graph_panel.reset_graph()
            self.operation_graph_panel.set_history_comparison_pair({})
            self.operation_graph_panel.set_result_manifest(None)
            return
        row = max(0, min(preferred_row, row_count - 1))
        self.scene_panel.view.selectRow(row)
        selected = self.scene_model.record_at(row)
        if selected is not None:
            self.mesh_selection.active_object_id = selected.object_id
            self.mesh_selection.selected_object_ids = {selected.object_id}
            self._sync_selected_context()

    def _generated_cleanup_targets(self, records: tuple[SceneObjectRecord, ...]) -> tuple[Path, ...]:
        candidates: list[Path] = []
        project_root = self.project_service.root.resolve()
        outputs_root = project_root / "outputs"
        graphs_root = outputs_root / "graphs"
        for record in records:
            path = record.path
            project_generated_path = self._path_is_under(path, outputs_root) or self._path_is_under(
                path,
                project_root / "assets",
            )
            if record.asset_dir is not None and (project_generated_path or bool(record.operation_graph_history)):
                candidates.append(record.asset_dir)
            if self._path_is_under(path, graphs_root) and path.parent != graphs_root:
                candidates.append(path.parent)
            elif self._path_is_under(path, outputs_root):
                candidates.append(path)
            elif self._path_is_under(path, project_root / "assets") and record.asset_dir is None:
                candidates.append(path.parent)
            if record.manifest_path is not None and record.asset_dir is None and project_generated_path:
                candidates.append(record.manifest_path)
        safe_candidates = [path.resolve() for path in candidates if self._is_safe_project_cleanup_target(path)]
        return self._collapse_cleanup_targets(safe_candidates)

    def _is_safe_project_cleanup_target(self, path: Path) -> bool:
        try:
            resolved = Path(path).resolve()
            project_root = self.project_service.root.resolve()
        except Exception:
            return False
        if resolved == project_root:
            return False
        return self._path_is_under(resolved, project_root)

    def _collapse_cleanup_targets(self, paths: list[Path]) -> tuple[Path, ...]:
        unique = sorted(dict.fromkeys(paths), key=lambda item: (len(item.parts), str(item).lower()))
        collapsed: list[Path] = []
        for path in unique:
            if any(path == existing or self._path_is_under(path, existing) for existing in collapsed):
                continue
            collapsed.append(path)
        return tuple(collapsed)

    def _path_is_under(self, path: Path, root: Path) -> bool:
        try:
            Path(path).resolve().relative_to(Path(root).resolve())
        except ValueError:
            return False
        return True

    @QtCore.Slot(str)
    def _set_mesh_selection_mode(self, mode: str) -> None:
        self.mesh_selection.set_mode(mode)
        self._refresh_mesh_status()

    @QtCore.Slot(str)
    def _selection_tool_requested(self, tool_name: str) -> None:
        selected = self._selected_record()
        if selected is None:
            return
        self.mesh_selection.active_object_id = selected.object_id
        if tool_name == "clear_selection":
            self.mesh_selection.clear_subobjects()
            self.mesh_selection.selected_object_ids = set()
        elif tool_name == "select_all":
            self.mesh_selection.selected_object_ids = {selected.object_id}
            if self.current_topology is not None:
                if self.mesh_selection.mode == "vertex":
                    self.mesh_selection.selected_vertices = set(range(self.current_topology.vertices))
                elif self.mesh_selection.mode == "edge":
                    self.mesh_selection.selected_edges = {(-1, i) for i in range(self.current_topology.edges)}
                elif self.mesh_selection.mode in {"face", "polygon"}:
                    self.mesh_selection.selected_faces = set(range(self.current_topology.faces))
                elif self.mesh_selection.mode == "element":
                    self.mesh_selection.selected_elements = set(range(self.current_topology.connected_elements))
        elif tool_name == "invert_selection":
            self.mesh_selection.status_message = "Invert selection is staged until picking stores full sub-object sets."
        self._refresh_mesh_status()

    @QtCore.Slot(object)
    def _viewport_pick_requested(self, pick) -> None:  # type: ignore[no-untyped-def]
        record = self._record_by_id(pick.object_id)
        if record is None:
            return
        active_changed = self.mesh_selection.active_object_id != pick.object_id
        self.mesh_selection.active_object_id = pick.object_id
        self._select_scene_object(pick.object_id)
        if active_changed:
            self.mesh_selection.clear_subobjects()

        if pick.mode == "object":
            self._apply_set_pick(self.mesh_selection.selected_object_ids, pick.object_id, pick)
            if not self.mesh_selection.selected_object_ids:
                self.mesh_selection.active_object_id = None
        else:
            if not pick.additive and not pick.toggle:
                self.mesh_selection.clear_subobjects()
            self.mesh_selection.selected_object_ids = {pick.object_id}
            if pick.mode == "vertex" and pick.vertex_index is not None:
                self._apply_set_pick(self.mesh_selection.selected_vertices, int(pick.vertex_index), pick)
            elif pick.mode == "edge" and pick.edge is not None:
                edge = normalize_edge(*pick.edge)
                self._apply_set_pick(self.mesh_selection.selected_edges, edge, pick)
            elif pick.mode == "border" and pick.edge_index is not None:
                self._apply_set_pick(self.mesh_selection.selected_borders, int(pick.edge_index), pick)
            elif pick.mode == "face" and pick.face_index is not None:
                self._apply_set_pick(self.mesh_selection.selected_faces, int(pick.face_index), pick)
            elif pick.mode == "element":
                seed = pick.element_index if pick.element_index is not None else pick.face_index
                if seed is not None:
                    self._apply_set_pick(self.mesh_selection.selected_elements, int(seed), pick)

        self._refresh_topology(record.path)
        self._refresh_mesh_status()
        self.statusBar().showMessage(self._pick_status_text(pick))

    def _apply_set_pick(self, target: set, value, pick) -> None:  # type: ignore[no-untyped-def]
        if pick.toggle:
            if value in target:
                target.remove(value)
            else:
                target.add(value)
            return
        if not pick.additive:
            target.clear()
        target.add(value)

    def _pick_status_text(self, pick) -> str:  # type: ignore[no-untyped-def]
        if pick.mode == "vertex" and pick.vertex_index is not None:
            return f"Picked vertex {pick.vertex_index} on {pick.object_name}."
        if pick.mode in {"edge", "border"} and pick.edge is not None:
            return f"Picked {pick.mode} {pick.edge} on {pick.object_name}."
        if pick.mode == "face" and pick.face_index is not None:
            return f"Picked face {pick.face_index} on {pick.object_name}."
        if pick.mode == "element":
            return f"Picked element seed on {pick.object_name}."
        return f"Picked {pick.object_name}."

    def _record_by_id(self, object_id: str) -> SceneObjectRecord | None:
        for record in self.scene_model.records():
            if record.object_id == object_id:
                return record
        return None

    def _select_scene_object(self, object_id: str) -> None:
        for row, record in enumerate(self.scene_model.records()):
            if record.object_id == object_id:
                self.scene_panel.view.selectRow(row)
                return

    def _sync_selected_context(self) -> None:
        selected = self._selected_record()
        if selected is not None:
            self.mesh_selection.active_object_id = selected.object_id
            self.mesh_selection.selected_object_ids = {selected.object_id}
            self.modeling_panel.set_transform(selected.transform, emit=False)
            self.operation_graph_panel.set_active_object(selected)
            self.operation_graph_panel.set_graph(self._graph_for_record(selected), emit=False)
            self.operation_graph_panel.set_history_payloads(selected.operation_graph_history)
            self.operation_graph_panel.set_history_comparison_pair(selected.operation_graph_comparison_pair)
            self._sync_graph_result_manifest(selected)
            self._refresh_topology(selected.path)
        else:
            self.operation_graph_panel.set_active_object(None)
            self.operation_graph_panel.reset_graph()
            self.operation_graph_panel.set_history_comparison_pair({})
            self.operation_graph_panel.set_result_manifest(None)
        self._refresh_mesh_status()

    def _graph_for_record(self, record: SceneObjectRecord) -> EditGraph:
        if record.operation_graph is not None:
            return record.operation_graph
        return EditGraph(
            graph_id=f"{record.object_id}_graph",
            asset_id=record.object_id,
            name=f"{record.name} Graph",
            base_asset_path=str(record.path),
        )

    def _sync_graph_result_manifest(self, record: SceneObjectRecord | None) -> None:
        if record is None or record.asset_dir is None:
            self.operation_graph_panel.set_result_manifest(None)
            return
        try:
            manifest = read_manifest(record.asset_dir)
        except Exception as exc:
            self.operation_graph_panel.set_result_manifest(
                None,
                asset_dir=str(record.asset_dir),
                message=f"Manifest unavailable: {exc}",
            )
            return
        self.operation_graph_panel.set_result_manifest(
            manifest.model_dump(mode="json"),
            asset_dir=str(record.asset_dir),
        )

    def _refresh_topology(self, path: Path) -> None:
        try:
            self.current_topology = analyze_mesh(path)
        except Exception:
            self.current_topology = None

    def _refresh_mesh_status(self) -> None:
        selected = self._selected_record()
        self.viewport.set_selection_state(self.mesh_selection)
        self.modeling_panel.set_mesh_status(
            active=selected.name if selected else "-",
            mode=self.mesh_selection.mode,
            selected=self.mesh_selection.counts(),
            topology=self.current_topology,
        )
        self._refresh_editor_status_strip()

    @QtCore.Slot()
    def undo_operation(self) -> None:
        command = self.operation_history.undo()
        if command is None:
            self.statusBar().showMessage("Nothing to undo.")
            return
        if isinstance(command, SceneTransformCommand):
            self._apply_history_transform(command, undo=True)
        elif isinstance(command, SceneDeleteCommand):
            self._apply_history_delete(command, undo=True)
        else:
            self._apply_history_path(command, undo=True)
        self.statusBar().showMessage(f"Undid {command.label}.")

    @QtCore.Slot()
    def redo_operation(self) -> None:
        command = self.operation_history.redo()
        if command is None:
            self.statusBar().showMessage("Nothing to redo.")
            return
        if isinstance(command, SceneTransformCommand):
            self._apply_history_transform(command, undo=False)
        elif isinstance(command, SceneDeleteCommand):
            self._apply_history_delete(command, undo=False)
        else:
            self._apply_history_path(command, undo=False)
        self.statusBar().showMessage(f"Redid {command.label}.")

    def _apply_history_path(self, command: ScenePathCommand, *, undo: bool) -> None:
        path = command.before_path if undo else command.after_path
        self.scene_model.update_record(
            command.object_id,
            path=path,
            vertices=command.before_vertices if undo else command.after_vertices,
            faces=command.before_faces if undo else command.after_faces,
            watertight=command.before_watertight if undo else command.after_watertight,
        )
        self.viewport.set_scene_records(self.scene_model.records())
        self._refresh_topology(path)
        self._refresh_mesh_status()

    def _apply_history_transform(self, command: SceneTransformCommand, *, undo: bool) -> None:
        transform = command.before_transform if undo else command.after_transform
        updated = self.scene_model.update_transform(command.object_id, transform)
        if updated is None:
            return
        self._select_scene_object(command.object_id)
        self.mesh_selection.active_object_id = command.object_id
        self.mesh_selection.selected_object_ids = {command.object_id}
        self.viewport.set_scene_records(self.scene_model.records())
        self.modeling_panel.set_transform(transform, emit=False)
        self._refresh_mesh_status()

    def _apply_history_delete(self, command: SceneDeleteCommand, *, undo: bool) -> None:
        if undo:
            for row, record in sorted(zip(command.rows, command.records), key=lambda item: item[0]):
                if self.scene_model.row_for_object_id(record.object_id) >= 0:
                    continue
                self.scene_model.insert_record(row, record)
            if command.records:
                self._select_scene_object(command.records[0].object_id)
                self.mesh_selection.active_object_id = command.records[0].object_id
                self.mesh_selection.selected_object_ids = {command.records[0].object_id}
                self._sync_selected_context()
            self.viewport.set_scene_records(self.scene_model.records())
            self._refresh_mesh_status()
            return
        rows = [
            self.scene_model.row_for_object_id(record.object_id)
            for record in command.records
            if self.scene_model.row_for_object_id(record.object_id) >= 0
        ]
        self._remove_scene_rows(rows, record_undo=False, label=command.label)

    @QtCore.Slot()
    def save_scene(self, path: Path | None = None) -> Path:
        target = path or self.current_scene_path
        if target is None:
            target = self.scene_documents.default_scene_path(self.project_service.root)
        self._store_selected_graph_history()
        saved = self.scene_documents.write(
            target,
            project_root=self.project_service.root,
            records=self.scene_model.records(),
        )
        self.current_scene_path = saved
        self._update_window_title()
        self.statusBar().showMessage(f"Scene saved: {saved}")
        return saved

    @QtCore.Slot()
    def save_scene_as_dialog(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Ghost Forge Scene",
            str(self.current_scene_path or self.project_service.root / "scenes" / "untitled.gforge"),
            "Ghost Forge Scenes (*.gforge);;All Files (*)",
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".gforge":
            target = target.with_suffix(".gforge")
        self.save_scene(target)

    def open_scene(self, path: Path) -> None:
        document = self.scene_documents.read(path)
        self._set_project_root(document.project_root)
        self.scene_model.set_records(document.records)
        self.mesh_selection.clear()
        self.operation_history.clear()
        self.current_scene_path = Path(path)
        self.current_topology = None
        if document.records:
            first = document.records[0]
            self.mesh_selection.active_object_id = first.object_id
            self.mesh_selection.selected_object_ids = {first.object_id}
            self.scene_panel.view.selectRow(0)
            self._refresh_topology(first.path)
        self.viewport.set_scene_records(self.scene_model.records())
        self._refresh_mesh_status()
        self._update_window_title()
        self.statusBar().showMessage(f"Scene opened: {path}")

    def _set_project_root(self, root: Path):
        state = self.project_service.set_root(root)
        self.mesh_operations = MeshOperationService(state.root / "outputs")
        self._refresh_editor_status_strip()
        return state

    def _write_manifest_for_record(
        self,
        record: SceneObjectRecord,
        *,
        mesh_path: Path,
        operation: str,
        operation_parameters: dict[str, object] | None = None,
    ) -> SceneObjectRecord:
        try:
            asset_dir = self._manifest_asset_dir(record, mesh_path)
            builder = ManifestBuilder.for_dir(asset_dir, asset_id=f"{record.object_id}_{asset_dir.name}")
            builder.with_name(record.name)
            builder.with_geometry_from_mesh(mesh_path)
            builder.with_validation_from_mesh(mesh_path)
            builder.add_artifact_from_path(mesh_path, role="mesh.primary")
            builder.add_provenance(
                ProvenanceStep(
                    kind=operation,
                    parameters={
                        "scene_object_id": record.object_id,
                        "mesh_path": str(mesh_path),
                        **(operation_parameters or {}),
                    },
                )
            )
            builder.with_custom("ghostforge.scene_object_id", record.object_id)
            builder.with_custom("ghostforge.scene_mesh_path", str(mesh_path))
            _manifest, manifest_file = builder.write()
        except Exception as exc:
            self.statusBar().showMessage(f"Manifest update skipped for {record.name}: {exc}")
            return record
        updated = self.scene_model.update_record(
            record.object_id,
            asset_dir=asset_dir,
            manifest_path=manifest_file,
        )
        return updated or record

    def _manifest_asset_dir(self, record: SceneObjectRecord, mesh_path: Path) -> Path:
        stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in mesh_path.stem).strip("_")
        return self.project_service.root / "assets" / record.object_id / (stem or "mesh")

    def _update_window_title(self) -> None:
        suffix = "" if self.current_scene_path is None else f" - {self.current_scene_path.name}"
        self.setWindowTitle(f"Ghost Forge{suffix}")

    @QtCore.Slot()
    def not_implemented_yet(self) -> None:
        self.statusBar().showMessage("This command is registered; workflow wiring is next.")

    @QtCore.Slot()
    def show_testing_guide(self) -> None:
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Testing Ghost Forge")
        dialog.resize(720, 560)
        layout = QtWidgets.QVBoxLayout(dialog)
        header = QtWidgets.QLabel("Testing Ghost Forge today")
        header.setObjectName("GhostForgePanelSectionLabel")
        body = QtWidgets.QPlainTextEdit(TESTING_GUIDE_TEXT)
        body.setReadOnly(True)
        body.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        close_button = QtWidgets.QPushButton("Close")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(header)
        layout.addWidget(body, 1)
        layout.addWidget(close_button, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        dialog.exec()

    @QtCore.Slot()
    def create_test_cube(self) -> Path | None:
        try:
            import trimesh

            sample_dir = self.project_service.root / "samples"
            sample_dir.mkdir(parents=True, exist_ok=True)
            target = sample_dir / "ghostforge_test_cube.glb"
            trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(target)
            self.import_mesh(target)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Create Test Cube", f"Could not create test cube: {exc}")
            return None
        self.statusBar().showMessage(f"Test cube imported: {target}")
        return target

    @QtCore.Slot()
    def about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "About Ghost Forge",
            "Ghost Forge Qt\nAI-native 3D asset foundry and modeling suite foundation.",
        )

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._save_window_layout()
        self.job_controller.stop()
        self.bridge.context.runner.shutdown(wait=False)
        super().closeEvent(event)


def _settings_bool(settings: QtCore.QSettings, key: str, default: bool) -> bool:
    raw = settings.value(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)


def _settings_int(settings: QtCore.QSettings, key: str, default: int) -> int:
    raw = settings.value(key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return int(default)
