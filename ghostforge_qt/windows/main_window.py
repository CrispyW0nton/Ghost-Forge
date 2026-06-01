from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ghostforge_core.manifest import ManifestBuilder, ProvenanceStep
from ghostforge_qt.actions import DEFAULT_ACTIONS, ActionRegistry
from ghostforge_qt.models.scene_model import SceneObjectRecord, SceneTableModel
from ghostforge_qt.panels import (
    ContentBrowserPanel,
    JobPanel,
    ModelingToolsPanel,
    PlaceholderPanel,
    SceneOutlinerPanel,
    ThemePanel,
    WorkerPanel,
)
from ghostforge_qt.services.core_bridge import CoreBridge
from ghostforge_qt.services.job_controller import JobController
from ghostforge_qt.services.mesh_diagnostics import MeshTopologySummary, analyze_mesh
from ghostforge_qt.services.mesh_operation_service import MeshOperationSelection, MeshOperationService
from ghostforge_qt.services.mesh_selection import MeshSelectionState, normalize_edge
from ghostforge_qt.services.operation_history import OperationHistory, ScenePathCommand
from ghostforge_qt.services.project_service import ProjectService
from ghostforge_qt.services.scene_document import SceneDocumentService
from ghostforge_qt.theme import ThemeManager
from ghostforge_qt.viewports.viewport_host import ViewportHost


class MainWindow(QtWidgets.QMainWindow):
    """First Qt desktop shell for Ghost Forge."""

    def __init__(self, *, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.setObjectName("GhostForgeMainWindow")
        self.setWindowTitle("Ghost Forge")

        self.actions = ActionRegistry(self)
        self.scene_model = SceneTableModel(self)
        self.job_controller = JobController(bridge, interval_ms=1000)
        self.project_service = ProjectService(self.bridge.data_root / "project", self)
        self.mesh_operations = MeshOperationService(self.project_service.root / "outputs")
        self.scene_documents = SceneDocumentService()
        self.current_scene_path: Path | None = None
        self.mesh_selection = MeshSelectionState()
        self.operation_history = OperationHistory()
        self.current_topology: MeshTopologySummary | None = None
        self.theme_manager = ThemeManager(self)
        self.viewport = ViewportHost(parent=self)
        self.setCentralWidget(self.viewport)

        self._build_actions()
        self._build_menu_bar()
        self._build_toolbar()
        self._build_docks()
        self._connect_models()
        self._connect_tools()
        self.theme_manager.apply()
        self.viewport.apply_theme(self.theme_manager.current_theme())
        self.statusBar().showMessage(f"Ghost Forge Qt ready - data root: {self.bridge.data_root}")
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
            "view.refresh_runtime": self.refresh_runtime,
            "view.frame_all": self.viewport.frame_all,
            "asset.unwrap": self.not_implemented_yet,
            "asset.texture": self.not_implemented_yet,
            "asset.audit": self.not_implemented_yet,
            "asset.export_bridge": self.not_implemented_yet,
            "tools.worker_models": self.refresh_runtime,
            "help.about": self.about,
        }
        for spec in DEFAULT_ACTIONS:
            self.actions.register(spec, callbacks.get(spec.action_id))

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

        edit_menu = self.menuBar().addMenu("&Edit")
        edit_menu.addAction(self.actions.get("edit.undo"))
        edit_menu.addAction(self.actions.get("edit.redo"))

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self.actions.get("view.refresh_runtime"))
        view_menu.addAction(self.actions.get("view.frame_all"))
        view_menu.addAction(self.actions.get("tools.worker_models"))

        help_menu = self.menuBar().addMenu("&Help")
        help_menu.addAction(self.actions.get("help.about"))

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setObjectName("GhostForgeMainToolbar")
        for action_id in (
            "file.new_scene",
            "file.open_project",
            "file.open_scene",
            "file.import_mesh",
            "file.save_scene",
            "edit.undo",
            "edit.redo",
            "view.frame_all",
            "view.refresh_runtime",
            "asset.unwrap",
            "asset.texture",
            "asset.audit",
            "asset.export_bridge",
        ):
            toolbar.addAction(self.actions.get(action_id))

    def _build_docks(self) -> None:
        self.scene_panel = SceneOutlinerPanel(self.scene_model, self)
        self.content_panel = ContentBrowserPanel(self.project_service, self)
        self.modeling_panel = ModelingToolsPanel(self)
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

        self._add_dock("Scene", self.scene_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Content", self.content_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Modeling", self.modeling_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Workers", self.worker_panel, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self._add_dock("Jobs", self.job_panel, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self._add_dock("Properties", self.properties_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Audit", self.audit_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self._add_dock("Theme", self.theme_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)

    def _add_dock(self, title: str, widget: QtWidgets.QWidget, area: QtCore.Qt.DockWidgetArea) -> None:
        dock = QtWidgets.QDockWidget(title, self)
        dock.setObjectName(f"GhostForge{title.replace(' ', '')}Dock")
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def _connect_models(self) -> None:
        self.scene_model.rowsInserted.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_model.rowsRemoved.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_model.modelReset.connect(lambda *_: self.viewport.set_scene_records(self.scene_model.records()))
        self.scene_panel.view.selectionModel().selectionChanged.connect(lambda *_: self._sync_selected_context())

    def _connect_tools(self) -> None:
        self.modeling_panel.selectionModeRequested.connect(self.viewport.set_selection_mode)
        self.modeling_panel.selectionModeRequested.connect(self._set_mesh_selection_mode)
        self.modeling_panel.selectionToolRequested.connect(self._selection_tool_requested)
        self.modeling_panel.transformModeRequested.connect(self.viewport.set_transform_mode)
        self.viewport.selectionModeChanged.connect(self.modeling_panel.set_selection_mode)
        self.viewport.transformModeChanged.connect(self.modeling_panel.set_transform_mode)
        self.viewport.itemPicked.connect(self._viewport_pick_requested)
        self.modeling_panel.toolRequested.connect(self._modeling_tool_requested)
        self.modeling_panel.transformEdited.connect(self._apply_transform_to_selection)
        self.content_panel.fileActivated.connect(lambda path: self.import_mesh(Path(path)))
        self.theme_manager.themeChanged.connect(self.viewport.apply_theme)

    @QtCore.Slot()
    def new_scene(self) -> None:
        self.scene_model.clear()
        self.mesh_selection.clear()
        self.mesh_selection.active_object_id = None
        self.operation_history.clear()
        self.current_scene_path = None
        self.current_topology = None
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

    @QtCore.Slot(object)
    def _apply_transform_to_selection(self, transform) -> None:  # type: ignore[no-untyped-def]
        selected = self._selected_record()
        if selected is None:
            return
        self.scene_model.update_transform(selected.object_id, transform)
        self.viewport.set_scene_records(self.scene_model.records())

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
            self.modeling_panel.set_transform(selected.transform)
            self._refresh_topology(selected.path)
        self._refresh_mesh_status()

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

    @QtCore.Slot()
    def undo_operation(self) -> None:
        command = self.operation_history.undo()
        if command is None:
            self.statusBar().showMessage("Nothing to undo.")
            return
        self._apply_history_path(command, undo=True)
        self.statusBar().showMessage(f"Undid {command.label}.")

    @QtCore.Slot()
    def redo_operation(self) -> None:
        command = self.operation_history.redo()
        if command is None:
            self.statusBar().showMessage("Nothing to redo.")
            return
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

    @QtCore.Slot()
    def save_scene(self, path: Path | None = None) -> Path:
        target = path or self.current_scene_path
        if target is None:
            target = self.scene_documents.default_scene_path(self.project_service.root)
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
    def about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            "About Ghost Forge",
            "Ghost Forge Qt\nAI-native 3D asset foundry and modeling suite foundation.",
        )

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.job_controller.stop()
        self.bridge.context.runner.shutdown(wait=False)
        super().closeEvent(event)
