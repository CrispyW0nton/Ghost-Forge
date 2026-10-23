from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.models.viewport_model import ViewportDiagnosticsModel
from ghostforge_qt.viewports.navigation import VIEWPORT_CAMERA_PRESETS, VIEWPORT_NAVIGATION_PROFILES
from ghostforge_qt.viewports.transform_gizmo import (
    GIZMO_ORIENTATIONS,
    GIZMO_PIVOTS,
    normalize_gizmo_orientation,
    normalize_gizmo_pivot,
)
from ghostforge_qt.viewports.viewport_host import ViewportHost


class ViewportPanel(QtWidgets.QWidget):
    """Ghost Rigger-inspired viewport tools and diagnostics dock."""

    def __init__(self, viewport: ViewportHost, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ViewportPanel")
        self.viewport = viewport
        self.model = ViewportDiagnosticsModel(self)
        self._updating = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        self.summary = QtWidgets.QLabel()
        self.summary.setObjectName("ViewportToolsSummary")
        self.summary.setWordWrap(True)
        self.summary.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.summary)

        controls = QtWidgets.QGroupBox("Controls")
        form = QtWidgets.QFormLayout(controls)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(6)

        self.display_combo = QtWidgets.QComboBox()
        self.display_combo.addItems(["shaded", "wireframe", "solid", "uv", "xray"])
        self.display_combo.currentTextChanged.connect(self.viewport.set_display_mode)
        form.addRow("Display", self.display_combo)

        self.selection_combo = QtWidgets.QComboBox()
        self.selection_combo.addItems(["object", "vertex", "edge", "border", "face", "element"])
        self.selection_combo.currentTextChanged.connect(self.viewport.set_selection_mode)
        form.addRow("Selection", self.selection_combo)

        self.transform_combo = QtWidgets.QComboBox()
        self.transform_combo.addItems(["move", "rotate", "scale", "pivot"])
        self.transform_combo.currentTextChanged.connect(self.viewport.set_transform_mode)
        form.addRow("Transform", self.transform_combo)

        self.gizmo_orientation_combo = QtWidgets.QComboBox()
        for key, label in GIZMO_ORIENTATIONS.items():
            self.gizmo_orientation_combo.addItem(label, key)
        self.gizmo_orientation_combo.currentIndexChanged.connect(self._gizmo_orientation_changed)
        form.addRow("Gizmo Orient", self.gizmo_orientation_combo)

        self.gizmo_pivot_combo = QtWidgets.QComboBox()
        for key, label in GIZMO_PIVOTS.items():
            self.gizmo_pivot_combo.addItem(label, key)
        self.gizmo_pivot_combo.currentIndexChanged.connect(self._gizmo_pivot_changed)
        form.addRow("Gizmo Pivot", self.gizmo_pivot_combo)

        self.navigation_combo = QtWidgets.QComboBox()
        for key, profile in VIEWPORT_NAVIGATION_PROFILES.items():
            self.navigation_combo.addItem(profile.label, key)
        self.navigation_combo.currentIndexChanged.connect(self._navigation_changed)
        form.addRow("Navigation", self.navigation_combo)

        self.camera_combo = QtWidgets.QComboBox()
        for label, preset, _short_label, tooltip in VIEWPORT_CAMERA_PRESETS:
            self.camera_combo.addItem(label, preset)
            index = self.camera_combo.count() - 1
            self.camera_combo.setItemData(index, tooltip, QtCore.Qt.ItemDataRole.ToolTipRole)
        self.camera_combo.currentIndexChanged.connect(self._camera_changed)
        form.addRow("Camera", self.camera_combo)

        snap_row = QtWidgets.QHBoxLayout()
        snap_row.setContentsMargins(0, 0, 0, 0)
        snap_row.setSpacing(4)
        self.snap_view_buttons: dict[str, QtWidgets.QToolButton] = {}
        for _label, preset, short_label, tooltip in VIEWPORT_CAMERA_PRESETS:
            button = QtWidgets.QToolButton()
            button.setText(short_label)
            button.setCheckable(True)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked=False, value=preset: self.viewport.set_camera_preset(value))
            self.snap_view_buttons[preset] = button
            snap_row.addWidget(button)
        form.addRow("Snap Views", snap_row)

        self.projection_button = QtWidgets.QToolButton()
        self.projection_button.setText("Persp")
        self.projection_button.setCheckable(True)
        self.projection_button.setToolTip("Toggle perspective / orthographic projection")
        self.projection_button.toggled.connect(self._projection_changed)
        form.addRow("Projection", self.projection_button)

        toggles = QtWidgets.QHBoxLayout()
        toggles.setContentsMargins(0, 0, 0, 0)
        toggles.setSpacing(6)
        self.grid_check = QtWidgets.QCheckBox("Grid")
        self.grid_check.toggled.connect(self.viewport.set_grid_visible)
        self.snap_check = QtWidgets.QCheckBox("Snap")
        self.snap_check.toggled.connect(self.viewport.set_snap_enabled)
        self.view_cube_check = QtWidgets.QCheckBox("ViewCube")
        self.view_cube_check.toggled.connect(self.viewport.set_view_cube_visible)
        for check in (self.grid_check, self.snap_check, self.view_cube_check):
            toggles.addWidget(check)
        form.addRow("Overlays", toggles)

        action_row = QtWidgets.QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(6)
        self.frame_button = QtWidgets.QPushButton("Frame All")
        self.frame_button.clicked.connect(self.viewport.frame_all)
        self.frame_selected_button = QtWidgets.QPushButton("Frame Selected")
        self.frame_selected_button.clicked.connect(self.viewport.frame_selected)
        self.reset_button = QtWidgets.QPushButton("Reset Camera")
        self.reset_button.clicked.connect(self.viewport.reset_camera)
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        action_row.addWidget(self.frame_button)
        action_row.addWidget(self.frame_selected_button)
        action_row.addWidget(self.reset_button)
        action_row.addWidget(self.refresh_button)
        form.addRow("Actions", action_row)
        layout.addWidget(controls)

        self.view = QtWidgets.QTableView()
        self.view.setObjectName("ViewportDiagnosticsTable")
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.view.setAlternatingRowColors(True)
        self.view.verticalHeader().hide()
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.view.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.view, 1)

        self._connect_viewport()
        self.refresh()

    def _connect_viewport(self) -> None:
        self.viewport.diagnosticsChanged.connect(self.set_diagnostics)
        self.viewport.displayModeChanged.connect(self._set_display_mode)
        self.viewport.selectionModeChanged.connect(self._set_selection_mode)
        self.viewport.transformModeChanged.connect(self._set_transform_mode)
        self.viewport.navigationProfileChanged.connect(self._set_navigation_profile)
        self.viewport.cameraPresetChanged.connect(self._set_camera_preset)
        self.viewport.projectionModeChanged.connect(self._set_projection_mode)
        self.viewport.gridVisibilityChanged.connect(self._set_grid_visible)
        self.viewport.snapChanged.connect(self._set_snap_enabled)
        self.viewport.viewCubeVisibilityChanged.connect(self._set_view_cube_visible)
        self.viewport.gizmoOrientationChanged.connect(self._set_gizmo_orientation)
        self.viewport.gizmoPivotChanged.connect(self._set_gizmo_pivot)

    @QtCore.Slot()
    def refresh(self) -> None:
        self.set_diagnostics(self.viewport.refresh_diagnostics())
        self._sync_from_navigation_state(self.viewport.navigation_state())

    @QtCore.Slot(object)
    def set_diagnostics(self, diagnostics: object) -> None:
        if not isinstance(diagnostics, dict):
            return
        self.model.set_diagnostics(diagnostics)
        renderer = str(diagnostics.get("renderer_name") or diagnostics.get("backend_id") or "Viewport")
        mode = str(diagnostics.get("display_mode") or "-")
        selection = str(diagnostics.get("selection_mode") or "-")
        transform = str(diagnostics.get("transform_mode") or "-")
        orientation = str(diagnostics.get("gizmo_orientation") or "world")
        pivot = str(diagnostics.get("gizmo_pivot") or "bounds_center")
        profile = str(diagnostics.get("navigation_profile_label") or diagnostics.get("navigation_profile") or "-")
        projection = str(diagnostics.get("projection_mode_label") or diagnostics.get("projection_mode") or "-")
        objects = int(diagnostics.get("object_count") or 0)
        faces = int(diagnostics.get("face_count") or 0)
        picking = "picking" if diagnostics.get("supports_object_picking") else "no picking"
        gizmo = "gizmo ready" if diagnostics.get("supports_gizmo_interaction") else "gizmo pending"
        self.summary.setText(
            f"{renderer}\n"
            f"{objects} objects, {faces} faces | {mode} / {selection} / {transform}\n"
            f"gizmo {orientation} / {pivot}\n"
            f"{projection} | {profile} navigation | {picking} | {gizmo}"
        )
        self._sync_from_diagnostics(diagnostics)

    def _sync_from_diagnostics(self, diagnostics: dict[str, object]) -> None:
        self._set_display_mode(str(diagnostics.get("display_mode") or "shaded"))
        self._set_selection_mode(str(diagnostics.get("selection_mode") or "object"))
        self._set_transform_mode(str(diagnostics.get("transform_mode") or "move"))
        self._set_gizmo_orientation(diagnostics.get("gizmo_orientation") or "world")
        self._set_gizmo_pivot(diagnostics.get("gizmo_pivot") or "bounds_center")
        self._set_navigation_profile(diagnostics.get("navigation_profile") or diagnostics.get("profile") or "maya")
        self._set_camera_preset(str(diagnostics.get("camera_preset") or "perspective"))
        self._set_projection_mode(str(diagnostics.get("projection_mode") or "perspective"))
        self._set_grid_visible(bool(diagnostics.get("grid_visible", True)))
        self._set_snap_enabled(bool(diagnostics.get("snap_enabled", False)))
        self._set_view_cube_visible(bool(diagnostics.get("view_cube_visible", True)))

    def _sync_from_navigation_state(self, state: dict[str, object]) -> None:
        self._sync_from_diagnostics(state)

    @QtCore.Slot(str)
    def _set_display_mode(self, mode: str) -> None:
        self._set_combo_text(self.display_combo, mode)

    @QtCore.Slot(str)
    def _set_selection_mode(self, mode: str) -> None:
        self._set_combo_text(self.selection_combo, mode)

    @QtCore.Slot(str)
    def _set_transform_mode(self, mode: str) -> None:
        self._set_combo_text(self.transform_combo, mode)

    @QtCore.Slot(object)
    def _set_gizmo_orientation(self, orientation: object) -> None:
        self._set_combo_data(self.gizmo_orientation_combo, normalize_gizmo_orientation(orientation))

    @QtCore.Slot(object)
    def _set_gizmo_pivot(self, pivot: object) -> None:
        self._set_combo_data(self.gizmo_pivot_combo, normalize_gizmo_pivot(pivot))

    @QtCore.Slot(object)
    def _set_navigation_profile(self, profile: object) -> None:
        self._set_combo_data(self.navigation_combo, str(profile or "maya"))

    @QtCore.Slot(str)
    def _set_camera_preset(self, preset: str) -> None:
        value = "right" if str(preset).strip().lower() == "side" else str(preset or "perspective").strip().lower()
        self._set_combo_data(self.camera_combo, value)
        self._set_snap_view_button_state(value)

    @QtCore.Slot(str)
    def _set_projection_mode(self, mode: object) -> None:
        value = str(mode or "perspective").strip().lower()
        checked = value in {"ortho", "orthographic", "orthogonal"}
        if self.projection_button.isChecked() == checked:
            self.projection_button.setText("Ortho" if checked else "Persp")
            return
        self._updating = True
        try:
            blocked = self.projection_button.blockSignals(True)
            self.projection_button.setChecked(checked)
            self.projection_button.setText("Ortho" if checked else "Persp")
            self.projection_button.blockSignals(blocked)
        finally:
            self._updating = False

    @QtCore.Slot(bool)
    def _set_grid_visible(self, visible: bool) -> None:
        self._set_checked(self.grid_check, visible)

    @QtCore.Slot(bool)
    def _set_snap_enabled(self, enabled: bool) -> None:
        self._set_checked(self.snap_check, enabled)

    @QtCore.Slot(bool)
    def _set_view_cube_visible(self, visible: bool) -> None:
        self._set_checked(self.view_cube_check, visible)

    @QtCore.Slot(int)
    def _navigation_changed(self, _index: int = -1) -> None:
        if not self._updating:
            self.viewport.set_navigation_profile(str(self.navigation_combo.currentData()))

    @QtCore.Slot(int)
    def _gizmo_orientation_changed(self, _index: int = -1) -> None:
        if not self._updating:
            self.viewport.set_gizmo_orientation(self.gizmo_orientation_combo.currentData())

    @QtCore.Slot(int)
    def _gizmo_pivot_changed(self, _index: int = -1) -> None:
        if not self._updating:
            self.viewport.set_gizmo_pivot(self.gizmo_pivot_combo.currentData())

    @QtCore.Slot(int)
    def _camera_changed(self, _index: int = -1) -> None:
        if not self._updating:
            self.viewport.set_camera_preset(str(self.camera_combo.currentData()))

    @QtCore.Slot(bool)
    def _projection_changed(self, checked: bool) -> None:
        if not self._updating:
            self.viewport.set_projection_mode("orthographic" if checked else "perspective")

    def _set_snap_view_button_state(self, preset: object) -> None:
        value = "right" if str(preset).strip().lower() == "side" else str(preset or "perspective").strip().lower()
        for key, button in self.snap_view_buttons.items():
            checked = key == value
            if button.isChecked() == checked:
                continue
            self._updating = True
            try:
                blocked = button.blockSignals(True)
                button.setChecked(checked)
                button.blockSignals(blocked)
            finally:
                self._updating = False

    def _set_combo_text(self, combo: QtWidgets.QComboBox, value: str) -> None:
        index = combo.findText(str(value))
        if index < 0 or combo.currentIndex() == index:
            return
        self._updating = True
        try:
            blocked = combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(blocked)
        finally:
            self._updating = False

    def _set_combo_data(self, combo: QtWidgets.QComboBox, value: str) -> None:
        index = combo.findData(str(value))
        if index < 0 or combo.currentIndex() == index:
            return
        self._updating = True
        try:
            blocked = combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(blocked)
        finally:
            self._updating = False

    def _set_checked(self, checkbox: QtWidgets.QCheckBox, checked: bool) -> None:
        if checkbox.isChecked() == bool(checked):
            return
        self._updating = True
        try:
            blocked = checkbox.blockSignals(True)
            checkbox.setChecked(bool(checked))
            checkbox.blockSignals(blocked)
        finally:
            self._updating = False
