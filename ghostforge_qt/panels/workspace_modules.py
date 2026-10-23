from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.layouts import WorkspaceLayout
from ghostforge_qt.models.workspace_model import WorkspaceModuleModel
from ghostforge_qt.workspaces import WorkspaceModule


class WorkspaceModulePanel(QtWidgets.QWidget):
    """Switches between universal Ghost Forge production workspaces."""

    moduleSelected = QtCore.Signal(str)
    moduleActivated = QtCore.Signal(str)
    moduleReloadRequested = QtCore.Signal()
    layoutReloadRequested = QtCore.Signal()
    layoutSelected = QtCore.Signal(str, str)
    liveReloadToggled = QtCore.Signal(bool)

    def __init__(
        self,
        modules: tuple[WorkspaceModule, ...],
        layouts: dict[str, WorkspaceLayout] | None = None,
        available_layouts: dict[str, tuple[WorkspaceLayout, ...]] | None = None,
        module_diagnostics: tuple[str, ...] = (),
        layout_diagnostics: tuple[str, ...] = (),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("WorkspaceModulePanel")
        self.model = WorkspaceModuleModel(modules, layouts, self)
        self._available_layouts = self._normalize_available_layouts(layouts, available_layouts)
        self._module_diagnostics = tuple(module_diagnostics)
        self._layout_diagnostics = tuple(layout_diagnostics)
        self._watched_paths: tuple[str, ...] = ()
        self._updating_layout_combo = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.view = QtWidgets.QTableView()
        self.view.setObjectName("WorkspaceModuleTable")
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().hide()
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.view.doubleClicked.connect(self._activate_index)
        layout.addWidget(self.view, 1)

        self.summary = QtWidgets.QLabel()
        self.summary.setObjectName("WorkspaceModuleSummary")
        self.summary.setWordWrap(True)
        self.summary.setMinimumHeight(66)
        self.summary.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.summary)

        layout_preset_row = QtWidgets.QHBoxLayout()
        layout_preset_row.setContentsMargins(0, 0, 0, 0)
        layout_preset_row.setSpacing(6)
        layout_preset_label = QtWidgets.QLabel("Layout Preset")
        self.layout_combo = QtWidgets.QComboBox()
        self.layout_combo.setObjectName("WorkspaceLayoutPresetCombo")
        self.layout_combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.layout_combo.currentIndexChanged.connect(self._layout_combo_changed)
        layout_preset_row.addWidget(layout_preset_label)
        layout_preset_row.addWidget(self.layout_combo, 1)
        layout.addLayout(layout_preset_row)

        self.layout_diagnostics = QtWidgets.QLabel()
        self.layout_diagnostics.setObjectName("WorkspaceLayoutDiagnostics")
        self.layout_diagnostics.setWordWrap(True)
        self.layout_diagnostics.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.layout_diagnostics)

        self.module_diagnostics = QtWidgets.QLabel()
        self.module_diagnostics.setObjectName("WorkspaceModuleDiagnostics")
        self.module_diagnostics.setWordWrap(True)
        self.module_diagnostics.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.module_diagnostics)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(6)
        self.activate_button = QtWidgets.QPushButton("Activate Workspace")
        self.activate_button.clicked.connect(self.activate_current)
        button_row.addWidget(self.activate_button, 1)
        self.reload_modules_button = QtWidgets.QPushButton("Reload Modules")
        self.reload_modules_button.clicked.connect(lambda _checked=False: self.moduleReloadRequested.emit())
        button_row.addWidget(self.reload_modules_button)
        self.reload_layouts_button = QtWidgets.QPushButton("Reload Layouts")
        self.reload_layouts_button.clicked.connect(lambda _checked=False: self.layoutReloadRequested.emit())
        button_row.addWidget(self.reload_layouts_button)
        layout.addLayout(button_row)

        watch_row = QtWidgets.QHBoxLayout()
        watch_row.setContentsMargins(0, 0, 0, 0)
        watch_row.setSpacing(6)
        self.live_reload_check = QtWidgets.QCheckBox("Live Reload")
        self.live_reload_check.toggled.connect(self.liveReloadToggled.emit)
        self.resource_watch_label = QtWidgets.QLabel()
        self.resource_watch_label.setObjectName("WorkspaceResourceWatch")
        self.resource_watch_label.setWordWrap(True)
        watch_row.addWidget(self.live_reload_check)
        watch_row.addWidget(self.resource_watch_label, 1)
        layout.addLayout(watch_row)

        selection = self.view.selectionModel()
        if selection is not None:
            selection.selectionChanged.connect(lambda *_: self._selection_changed())
        if self.model.rowCount() > 0:
            self.view.selectRow(0)
            self._selection_changed(emit=False)
        self._refresh_layout_diagnostics()
        self._refresh_module_diagnostics()
        self.set_resource_watch_state(False, ())

    def current_module(self) -> WorkspaceModule | None:
        selection = self.view.selectionModel()
        if selection is None or not selection.hasSelection():
            return None
        row = selection.selectedRows()[0].row()
        return self.model.module_at(row)

    def current_module_id(self) -> str:
        module = self.current_module()
        return module.module_id if module is not None else ""

    def select_module(self, module_id: str, *, emit: bool = True) -> bool:
        for row, module in enumerate(self.model.modules()):
            if module.module_id != module_id:
                continue
            blocked = self.view.selectionModel().blockSignals(True) if self.view.selectionModel() else False
            self.view.selectRow(row)
            if self.view.selectionModel() is not None:
                self.view.selectionModel().blockSignals(blocked)
            self._selection_changed(emit=emit)
            return True
        return False

    def set_layouts(
        self,
        layouts: dict[str, WorkspaceLayout],
        *,
        available_layouts: dict[str, tuple[WorkspaceLayout, ...]] | None = None,
        layout_diagnostics: tuple[str, ...] | list[str] = (),
    ) -> None:
        current = self.current_module_id()
        self.model.set_layouts(layouts)
        self._available_layouts = self._normalize_available_layouts(layouts, available_layouts)
        self._layout_diagnostics = tuple(str(item) for item in layout_diagnostics)
        if current:
            self.select_module(current, emit=False)
        else:
            self._selection_changed(emit=False)
        self._refresh_layout_diagnostics()

    def set_modules(
        self,
        modules: tuple[WorkspaceModule, ...],
        *,
        layouts: dict[str, WorkspaceLayout] | None = None,
        available_layouts: dict[str, tuple[WorkspaceLayout, ...]] | None = None,
        module_diagnostics: tuple[str, ...] | list[str] = (),
        layout_diagnostics: tuple[str, ...] | list[str] | None = None,
    ) -> None:
        current = self.current_module_id()
        self.model.set_modules(tuple(modules), layouts)
        self._available_layouts = self._normalize_available_layouts(layouts, available_layouts)
        self._module_diagnostics = tuple(str(item) for item in module_diagnostics)
        if layout_diagnostics is not None:
            self._layout_diagnostics = tuple(str(item) for item in layout_diagnostics)
        if current and self.select_module(current, emit=False):
            pass
        elif self.model.rowCount() > 0:
            self.view.selectRow(0)
            self._selection_changed(emit=False)
        else:
            self._selection_changed(emit=False)
        self._refresh_module_diagnostics()
        self._refresh_layout_diagnostics()

    def set_resource_watch_state(self, enabled: bool, watched_paths: tuple[object, ...] | list[object]) -> None:
        blocked = self.live_reload_check.blockSignals(True)
        self.live_reload_check.setChecked(bool(enabled))
        self.live_reload_check.blockSignals(blocked)
        self._watched_paths = tuple(str(path) for path in watched_paths)
        self._refresh_resource_watch_label()

    @QtCore.Slot()
    def activate_current(self) -> None:
        module = self.current_module()
        if module is not None:
            self.moduleActivated.emit(module.module_id)

    @QtCore.Slot(QtCore.QModelIndex)
    def _activate_index(self, index: QtCore.QModelIndex) -> None:
        module = self.model.module_at(index.row())
        if module is not None:
            self.moduleActivated.emit(module.module_id)

    def _selection_changed(self, *, emit: bool = True) -> None:
        module = self.current_module()
        if module is None:
            self.summary.setText("No workspace selected.")
            self.activate_button.setEnabled(False)
            return
        self.activate_button.setEnabled(True)
        panels = ", ".join(module.dock_ids)
        workspace_layout = self.model.layout_for(module.module_id)
        layout_text = workspace_layout.summary() if workspace_layout is not None else "Default layout"
        self._refresh_layout_combo(module.module_id)
        self.summary.setText(
            f"{module.label} [{module.status}]\n"
            f"{module.summary}\n"
            f"Panels: {panels}\n"
            f"Viewport: {module.viewport_defaults.summary()}\n"
            f"Layout: {layout_text}"
        )
        if emit:
            self.moduleSelected.emit(module.module_id)

    @QtCore.Slot(int)
    def _layout_combo_changed(self, index: int) -> None:
        if self._updating_layout_combo or index < 0:
            return
        module_id = self.current_module_id()
        layout_id = self.layout_combo.itemData(index)
        if module_id and layout_id:
            self.layoutSelected.emit(module_id, str(layout_id))

    def _refresh_layout_combo(self, module_id: str) -> None:
        selected = self.model.layout_for(module_id)
        selected_layout_id = selected.layout_id if selected is not None else ""
        layouts = self._available_layouts.get(module_id, ())
        self._updating_layout_combo = True
        try:
            self.layout_combo.clear()
            for layout in layouts:
                label = layout.name
                if layout.source_path:
                    label = f"{label} (file)"
                self.layout_combo.addItem(label, layout.layout_id)
                row = self.layout_combo.count() - 1
                self.layout_combo.setItemData(row, layout.summary(), QtCore.Qt.ItemDataRole.ToolTipRole)
            if not layouts:
                self.layout_combo.addItem("Default layout", "")
            index = self.layout_combo.findData(selected_layout_id)
            self.layout_combo.setCurrentIndex(index if index >= 0 else 0)
            self.layout_combo.setEnabled(bool(layouts))
        finally:
            self._updating_layout_combo = False

    def _refresh_layout_diagnostics(self) -> None:
        if not self._layout_diagnostics:
            self.layout_diagnostics.setText("Layout diagnostics: clean.")
            return
        visible = "\n".join(self._layout_diagnostics[:4])
        suffix = "" if len(self._layout_diagnostics) <= 4 else f"\n... {len(self._layout_diagnostics) - 4} more"
        self.layout_diagnostics.setText(f"Layout diagnostics:\n{visible}{suffix}")

    def _refresh_module_diagnostics(self) -> None:
        if not self._module_diagnostics:
            self.module_diagnostics.setText("Module diagnostics: clean.")
            return
        visible = "\n".join(self._module_diagnostics[:4])
        suffix = "" if len(self._module_diagnostics) <= 4 else f"\n... {len(self._module_diagnostics) - 4} more"
        self.module_diagnostics.setText(f"Module diagnostics:\n{visible}{suffix}")

    def _refresh_resource_watch_label(self) -> None:
        if not self.live_reload_check.isChecked():
            self.resource_watch_label.setText("Workspace resources: live reload off.")
            return
        self.resource_watch_label.setText(f"Workspace resources: watching {len(self._watched_paths)} paths.")

    def _normalize_available_layouts(
        self,
        layouts: dict[str, WorkspaceLayout] | None,
        available_layouts: dict[str, tuple[WorkspaceLayout, ...]] | None,
    ) -> dict[str, tuple[WorkspaceLayout, ...]]:
        if available_layouts is not None:
            return {module_id: tuple(items) for module_id, items in available_layouts.items()}
        return {module_id: (layout,) for module_id, layout in (layouts or {}).items()}
