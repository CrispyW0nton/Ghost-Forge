from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.models.scene_model import SceneObjectRecord
from ghostforge_qt.theme.theme_model import Theme
from ghostforge_qt.viewports.navigation import (
    VIEWPORT_CAMERA_PRESETS,
    VIEWPORT_NAVIGATION_HELP,
    VIEWPORT_NAVIGATION_PROFILES,
    normalize_viewport_navigation_profile,
    normalize_viewport_projection_mode,
    viewport_projection_label,
)
from ghostforge_qt.viewports.transform_gizmo import (
    GIZMO_ORIENTATIONS,
    GIZMO_PIVOTS,
    normalize_gizmo_orientation,
    normalize_gizmo_pivot,
)

from .editor_viewport import EditorViewportRenderer
from .renderer_interface import RendererInterface, ViewportObject


class ViewportHost(QtWidgets.QWidget):
    """Owns the active renderer widget and exposes scene update hooks."""

    selectionModeChanged = QtCore.Signal(str)
    transformModeChanged = QtCore.Signal(str)
    displayModeChanged = QtCore.Signal(str)
    cameraPresetChanged = QtCore.Signal(str)
    navigationProfileChanged = QtCore.Signal(str)
    projectionModeChanged = QtCore.Signal(str)
    gridVisibilityChanged = QtCore.Signal(bool)
    snapChanged = QtCore.Signal(bool)
    viewCubeVisibilityChanged = QtCore.Signal(bool)
    gizmoOrientationChanged = QtCore.Signal(str)
    gizmoPivotChanged = QtCore.Signal(str)
    navigationStateChanged = QtCore.Signal(object)
    diagnosticsChanged = QtCore.Signal(object)
    itemPicked = QtCore.Signal(object)
    transformEdited = QtCore.Signal(object)

    def __init__(self, renderer: RendererInterface | None = None, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.renderer = renderer or EditorViewportRenderer(self)
        self._syncing_renderer = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.renderer.widget().setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self._build_toolbar(), 0)
        layout.addWidget(self.renderer.widget(), 1)
        layout.addWidget(self._build_status_strip(), 0)
        picked = getattr(self.renderer, "itemPicked", None)
        if picked is not None:
            picked.connect(self.itemPicked.emit)
        transformed = getattr(self.renderer, "transformEdited", None)
        if transformed is not None:
            transformed.connect(self._renderer_transform_edited)
        self._connect_renderer_navigation_signals()
        self.refresh_diagnostics()

    def _build_toolbar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        bar.setObjectName("GhostForgeViewportToolbar")
        bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        bar.setMinimumHeight(34)
        bar.setMaximumHeight(40)
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(4)

        self.selection_combo = QtWidgets.QComboBox()
        self.selection_combo.addItems(["object", "vertex", "edge", "border", "face", "element"])
        _compact_combo(self.selection_combo, width=88, tooltip="Selection component mode")
        self.selection_combo.currentTextChanged.connect(self.set_selection_mode)
        row.addWidget(_toolbar_label("Sel"))
        row.addWidget(self.selection_combo)

        self.transform_combo = QtWidgets.QComboBox()
        self.transform_combo.addItems(["move", "rotate", "scale", "pivot"])
        _compact_combo(self.transform_combo, width=82, tooltip="Transform tool")
        self.transform_combo.currentTextChanged.connect(self.set_transform_mode)
        row.addWidget(_toolbar_label("Xform"))
        row.addWidget(self.transform_combo)

        self.gizmo_orientation_combo = QtWidgets.QComboBox()
        for key, label in GIZMO_ORIENTATIONS.items():
            self.gizmo_orientation_combo.addItem(label, key)
        _compact_combo(self.gizmo_orientation_combo, width=86, tooltip="Transform gizmo axis orientation")
        self.gizmo_orientation_combo.currentIndexChanged.connect(self._gizmo_orientation_combo_changed)
        row.addWidget(_toolbar_label("Orient"))
        row.addWidget(self.gizmo_orientation_combo)

        self.gizmo_pivot_combo = QtWidgets.QComboBox()
        for key, label in GIZMO_PIVOTS.items():
            self.gizmo_pivot_combo.addItem(label, key)
        _compact_combo(self.gizmo_pivot_combo, width=108, tooltip="Transform gizmo pivot anchor")
        self.gizmo_pivot_combo.currentIndexChanged.connect(self._gizmo_pivot_combo_changed)
        row.addWidget(_toolbar_label("Pivot"))
        row.addWidget(self.gizmo_pivot_combo)

        self.display_combo = QtWidgets.QComboBox()
        self.display_combo.addItems(["shaded", "wireframe", "solid", "uv", "xray"])
        _compact_combo(self.display_combo, width=88, tooltip="Viewport display mode")
        self.display_combo.currentTextChanged.connect(self.set_display_mode)
        row.addWidget(_toolbar_label("Display"))
        row.addWidget(self.display_combo)

        self.navigation_combo = QtWidgets.QComboBox()
        for key, profile in VIEWPORT_NAVIGATION_PROFILES.items():
            self.navigation_combo.addItem(profile.label, key)
            index = self.navigation_combo.count() - 1
            self.navigation_combo.setItemData(index, profile.summary, QtCore.Qt.ItemDataRole.ToolTipRole)
        _compact_combo(self.navigation_combo, width=86, tooltip=VIEWPORT_NAVIGATION_HELP)
        self.navigation_combo.currentIndexChanged.connect(self._navigation_combo_changed)
        row.addWidget(_toolbar_label("Nav"))
        row.addWidget(self.navigation_combo)

        self.camera_combo = QtWidgets.QComboBox()
        for label, preset, _short_label, tooltip in VIEWPORT_CAMERA_PRESETS:
            self.camera_combo.addItem(label, preset)
            index = self.camera_combo.count() - 1
            self.camera_combo.setItemData(index, tooltip, QtCore.Qt.ItemDataRole.ToolTipRole)
        _compact_combo(self.camera_combo, width=104, tooltip="Camera view preset")
        self.camera_combo.currentIndexChanged.connect(self._camera_combo_changed)
        row.addWidget(_toolbar_label("Cam"))
        row.addWidget(self.camera_combo)

        row.addWidget(_toolbar_label("Views"))
        self.snap_view_buttons: dict[str, QtWidgets.QToolButton] = {}
        for _label, preset, short_label, tooltip in VIEWPORT_CAMERA_PRESETS:
            button = QtWidgets.QToolButton()
            button.setText(short_label)
            button.setCheckable(True)
            button.setFixedSize(28, 26)
            button.setToolTip(tooltip)
            button.clicked.connect(lambda _checked=False, value=preset: self.set_camera_preset(value))
            self.snap_view_buttons[preset] = button
            row.addWidget(button)
        self.snap_view_buttons["perspective"].setChecked(True)

        self.projection_button = QtWidgets.QToolButton()
        self.projection_button.setText("Persp")
        self.projection_button.setCheckable(True)
        self.projection_button.setMinimumWidth(58)
        self.projection_button.setToolTip("Toggle perspective / orthographic projection")
        self.projection_button.toggled.connect(self._projection_button_toggled)
        row.addWidget(self.projection_button)

        self.grid_button = QtWidgets.QToolButton()
        self.grid_button.setText("Grid")
        self.grid_button.setCheckable(True)
        self.grid_button.setChecked(True)
        self.grid_button.setMinimumWidth(46)
        self.grid_button.setToolTip("Toggle viewport grid")
        self.grid_button.toggled.connect(self.set_grid_visible)
        row.addWidget(self.grid_button)

        self.snap_button = QtWidgets.QToolButton()
        self.snap_button.setText("Snap")
        self.snap_button.setCheckable(True)
        self.snap_button.setMinimumWidth(50)
        self.snap_button.setToolTip("Toggle snap state for future gizmo tools")
        self.snap_button.toggled.connect(self.set_snap_enabled)
        row.addWidget(self.snap_button)

        self.view_cube_button = QtWidgets.QToolButton()
        self.view_cube_button.setText("Cube")
        self.view_cube_button.setCheckable(True)
        self.view_cube_button.setChecked(True)
        self.view_cube_button.setMinimumWidth(50)
        self.view_cube_button.setToolTip("Toggle viewport orientation cube")
        self.view_cube_button.toggled.connect(self.set_view_cube_visible)
        row.addWidget(self.view_cube_button)

        self.status_strip_button = QtWidgets.QToolButton()
        self.status_strip_button.setText("Stats")
        self.status_strip_button.setCheckable(True)
        self.status_strip_button.setChecked(True)
        self.status_strip_button.setMinimumWidth(52)
        self.status_strip_button.setToolTip("Toggle viewport diagnostics strip")
        self.status_strip_button.toggled.connect(self._set_status_strip_visible)
        row.addWidget(self.status_strip_button)

        frame_button = QtWidgets.QPushButton("Frame")
        frame_button.setMinimumWidth(58)
        frame_button.clicked.connect(self.frame_all)
        row.addWidget(frame_button)
        frame_selected_button = QtWidgets.QPushButton("Frame Sel")
        frame_selected_button.setMinimumWidth(74)
        frame_selected_button.setToolTip("Frame the active object or selected sub-object elements")
        frame_selected_button.clicked.connect(self.frame_selected)
        row.addWidget(frame_selected_button)
        reset_button = QtWidgets.QPushButton("Reset")
        reset_button.setMinimumWidth(58)
        reset_button.clicked.connect(self.reset_camera)
        row.addWidget(reset_button)
        row.addStretch(1)
        self.viewport_toolbar = bar
        return bar

    def _build_status_strip(self) -> QtWidgets.QWidget:
        strip = QtWidgets.QFrame()
        strip.setObjectName("GhostForgeViewportStatusStrip")
        strip.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        strip.setMinimumHeight(24)
        strip.setMaximumHeight(28)
        row = QtWidgets.QHBoxLayout(strip)
        row.setContentsMargins(6, 2, 6, 2)
        row.setSpacing(10)

        self.renderer_status_label = QtWidgets.QLabel("CPU Projected")
        self.renderer_status_label.setObjectName("ViewportRendererStatus")
        self.scene_stats_label = QtWidgets.QLabel("0 objects | 0 verts | 0 faces")
        self.scene_stats_label.setObjectName("ViewportSceneStats")
        self.mode_status_label = QtWidgets.QLabel("shaded | object | move")
        self.mode_status_label.setObjectName("ViewportModeStatus")
        self.camera_status_label = QtWidgets.QLabel("Perspective | Maya | 1.00x")
        self.camera_status_label.setObjectName("ViewportCameraStatus")
        self.selection_status_label = QtWidgets.QLabel("Selection: 0 objects")
        self.selection_status_label.setObjectName("ViewportSelectionStatus")

        for label in (
            self.renderer_status_label,
            self.scene_stats_label,
            self.mode_status_label,
            self.camera_status_label,
            self.selection_status_label,
        ):
            label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum, QtWidgets.QSizePolicy.Policy.Fixed)
            row.addWidget(label)
        row.addStretch(1)
        self.status_strip = strip
        return strip

    def _connect_renderer_navigation_signals(self) -> None:
        connections = (
            ("displayModeChanged", self._renderer_display_mode_changed),
            ("cameraPresetChanged", self._renderer_camera_preset_changed),
            ("navigationProfileChanged", self._renderer_navigation_profile_changed),
            ("projectionModeChanged", self._renderer_projection_mode_changed),
            ("gridVisibilityChanged", self._renderer_grid_visibility_changed),
            ("snapChanged", self._renderer_snap_changed),
            ("viewCubeVisibilityChanged", self._renderer_view_cube_visibility_changed),
            ("gizmoOrientationChanged", self._renderer_gizmo_orientation_changed),
            ("gizmoPivotChanged", self._renderer_gizmo_pivot_changed),
            ("navigationStateChanged", self._renderer_navigation_state_changed),
        )
        for signal_name, slot in connections:
            signal = getattr(self.renderer, signal_name, None)
            if signal is not None:
                signal.connect(slot)

    def set_scene_records(self, records: list[SceneObjectRecord]) -> None:
        self.renderer.set_objects(
            [
                ViewportObject(
                    object_id=record.object_id,
                    name=record.name,
                    path=record.path,
                    transform=record.transform,
                )
                for record in records
            ]
        )
        self.refresh_diagnostics()

    def set_selection_state(self, state) -> None:  # type: ignore[no-untyped-def]
        setter = getattr(self.renderer, "set_selection_state", None)
        if callable(setter):
            setter(
                active_object_id=getattr(state, "active_object_id", None),
                object_ids=set(getattr(state, "selected_object_ids", set())),
                vertices=set(getattr(state, "selected_vertices", set())),
                edges=set(getattr(state, "selected_edges", set())),
                faces=set(getattr(state, "selected_faces", set())),
                borders=set(getattr(state, "selected_borders", set())),
                elements=set(getattr(state, "selected_elements", set())),
            )
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def set_selection_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_selection_mode", None)
        if callable(setter):
            setter(mode)
        idx = self.selection_combo.findText(mode)
        if idx >= 0 and self.selection_combo.currentIndex() != idx:
            self.selection_combo.setCurrentIndex(idx)
        self.selectionModeChanged.emit(mode)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def set_transform_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_transform_mode", None)
        if callable(setter):
            setter(mode)
        idx = self.transform_combo.findText(mode)
        if idx >= 0 and self.transform_combo.currentIndex() != idx:
            self.transform_combo.setCurrentIndex(idx)
        self.transformModeChanged.emit(mode)
        self.refresh_diagnostics()

    @QtCore.Slot(object)
    def set_gizmo_orientation(self, orientation: object) -> None:
        key = normalize_gizmo_orientation(orientation)
        setter = getattr(self.renderer, "set_gizmo_orientation", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(key)
            finally:
                self._syncing_renderer = False
        self._set_gizmo_orientation_combo_state(key)
        self.gizmoOrientationChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(object)
    def set_gizmo_pivot(self, pivot: object) -> None:
        key = normalize_gizmo_pivot(pivot)
        setter = getattr(self.renderer, "set_gizmo_pivot", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(key)
            finally:
                self._syncing_renderer = False
        self._set_gizmo_pivot_combo_state(key)
        self.gizmoPivotChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def set_display_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_display_mode", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(mode)
            finally:
                self._syncing_renderer = False
        idx = self.display_combo.findText(mode)
        if idx >= 0 and self.display_combo.currentIndex() != idx:
            self.display_combo.setCurrentIndex(idx)
        self.displayModeChanged.emit(mode)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def set_camera_preset(self, preset: str) -> None:
        setter = getattr(self.renderer, "set_camera_preset", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(preset)
            finally:
                self._syncing_renderer = False
        value = "right" if str(preset).strip().lower() == "side" else str(preset or "perspective").strip().lower()
        idx = self.camera_combo.findData(value)
        if idx >= 0 and self.camera_combo.currentIndex() != idx:
            self.camera_combo.setCurrentIndex(idx)
        self._set_snap_view_button_state(value)
        self.cameraPresetChanged.emit(value)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def set_navigation_profile(self, profile: object) -> None:
        key = normalize_viewport_navigation_profile(profile)
        setter = getattr(self.renderer, "set_navigation_profile", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(key)
            finally:
                self._syncing_renderer = False
        idx = self.navigation_combo.findData(key)
        if idx >= 0 and self.navigation_combo.currentIndex() != idx:
            self.navigation_combo.setCurrentIndex(idx)
        self.navigation_combo.setToolTip(f"{VIEWPORT_NAVIGATION_PROFILES[key].summary}\n\n{VIEWPORT_NAVIGATION_HELP}")
        self.navigationProfileChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(object)
    def set_projection_mode(self, mode: object) -> None:
        key = normalize_viewport_projection_mode(mode)
        setter = getattr(self.renderer, "set_projection_mode", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(key)
            finally:
                self._syncing_renderer = False
        self._set_projection_button_state(key)
        self.projectionModeChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def set_grid_visible(self, visible: bool) -> None:
        setter = getattr(self.renderer, "set_grid_visible", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(bool(visible))
            finally:
                self._syncing_renderer = False
        if self.grid_button.isChecked() != bool(visible):
            self.grid_button.setChecked(bool(visible))
        self.gridVisibilityChanged.emit(bool(visible))
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def set_snap_enabled(self, enabled: bool) -> None:
        setter = getattr(self.renderer, "set_snap_enabled", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(bool(enabled))
            finally:
                self._syncing_renderer = False
        if self.snap_button.isChecked() != bool(enabled):
            self.snap_button.setChecked(bool(enabled))
        self.snapChanged.emit(bool(enabled))
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def set_view_cube_visible(self, visible: bool) -> None:
        setter = getattr(self.renderer, "set_view_cube_visible", None)
        if callable(setter):
            self._syncing_renderer = True
            try:
                setter(bool(visible))
            finally:
                self._syncing_renderer = False
        if self.view_cube_button.isChecked() != bool(visible):
            self.view_cube_button.setChecked(bool(visible))
        self.viewCubeVisibilityChanged.emit(bool(visible))
        self.refresh_diagnostics()

    @QtCore.Slot()
    def reset_camera(self) -> None:
        setter = getattr(self.renderer, "reset_camera", None)
        if callable(setter):
            setter()
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def _set_status_strip_visible(self, visible: bool) -> None:
        self.status_strip.setVisible(bool(visible))

    @QtCore.Slot(int)
    def _camera_combo_changed(self, _index: int = -1) -> None:
        self.set_camera_preset(str(self.camera_combo.currentData()))

    @QtCore.Slot(int)
    def _navigation_combo_changed(self, _index: int = -1) -> None:
        self.set_navigation_profile(str(self.navigation_combo.currentData()))

    @QtCore.Slot(int)
    def _gizmo_orientation_combo_changed(self, _index: int = -1) -> None:
        if not self._syncing_renderer:
            self.set_gizmo_orientation(self.gizmo_orientation_combo.currentData())

    @QtCore.Slot(int)
    def _gizmo_pivot_combo_changed(self, _index: int = -1) -> None:
        if not self._syncing_renderer:
            self.set_gizmo_pivot(self.gizmo_pivot_combo.currentData())

    @QtCore.Slot(bool)
    def _projection_button_toggled(self, checked: bool) -> None:
        if self._syncing_renderer:
            return
        self.set_projection_mode("orthographic" if checked else "perspective")

    def _set_snap_view_button_state(self, preset: object) -> None:
        value = "right" if str(preset).strip().lower() == "side" else str(preset or "perspective").strip().lower()
        for key, button in getattr(self, "snap_view_buttons", {}).items():
            checked = key == value
            if button.isChecked() == checked:
                continue
            blocked = button.blockSignals(True)
            button.setChecked(checked)
            button.blockSignals(blocked)

    def _set_gizmo_orientation_combo_state(self, orientation: object) -> None:
        key = normalize_gizmo_orientation(orientation)
        idx = self.gizmo_orientation_combo.findData(key)
        if idx >= 0 and self.gizmo_orientation_combo.currentIndex() != idx:
            blocked = self.gizmo_orientation_combo.blockSignals(True)
            self.gizmo_orientation_combo.setCurrentIndex(idx)
            self.gizmo_orientation_combo.blockSignals(blocked)

    def _set_gizmo_pivot_combo_state(self, pivot: object) -> None:
        key = normalize_gizmo_pivot(pivot)
        idx = self.gizmo_pivot_combo.findData(key)
        if idx >= 0 and self.gizmo_pivot_combo.currentIndex() != idx:
            blocked = self.gizmo_pivot_combo.blockSignals(True)
            self.gizmo_pivot_combo.setCurrentIndex(idx)
            self.gizmo_pivot_combo.blockSignals(blocked)

    def _set_projection_button_state(self, mode: object) -> None:
        key = normalize_viewport_projection_mode(mode)
        checked = key == "orthographic"
        blocked = self.projection_button.blockSignals(True)
        try:
            self.projection_button.setChecked(checked)
            self.projection_button.setText("Ortho" if checked else "Persp")
            self.projection_button.setToolTip(f"{viewport_projection_label(key)} projection")
        finally:
            self.projection_button.blockSignals(blocked)

    def navigation_state(self) -> dict[str, object]:
        getter = getattr(self.renderer, "navigation_state", None)
        if callable(getter):
            return dict(getter())
        return {
            "display_mode": self.display_combo.currentText(),
            "navigation_profile": self.navigation_combo.currentData(),
            "camera_preset": self.camera_combo.currentData(),
            "projection_mode": "orthographic" if self.projection_button.isChecked() else "perspective",
            "grid_visible": self.grid_button.isChecked(),
            "snap_enabled": self.snap_button.isChecked(),
            "view_cube_visible": self.view_cube_button.isChecked(),
            "gizmo_orientation": self.gizmo_orientation_combo.currentData(),
            "gizmo_pivot": self.gizmo_pivot_combo.currentData(),
        }

    def restore_navigation_state(self, payload: dict[str, object] | None) -> None:
        restorer = getattr(self.renderer, "restore_navigation_state", None)
        if callable(restorer):
            self._syncing_renderer = True
            try:
                restorer(payload)
            finally:
                self._syncing_renderer = False
        data = self.navigation_state() if not payload else dict(payload)
        self._renderer_display_mode_changed(str(data.get("display_mode") or "shaded"))
        self._renderer_camera_preset_changed(str(data.get("camera_preset") or "perspective"))
        self._renderer_navigation_profile_changed(data.get("profile") or data.get("navigation_profile") or "maya")
        self._renderer_projection_mode_changed(data.get("projection_mode") or "perspective")
        self._renderer_grid_visibility_changed(bool(data.get("grid_visible", True)))
        self._renderer_snap_changed(bool(data.get("snap_enabled", False)))
        self._renderer_view_cube_visibility_changed(bool(data.get("view_cube_visible", True)))
        self._renderer_gizmo_orientation_changed(data.get("gizmo_orientation") or "world")
        self._renderer_gizmo_pivot_changed(data.get("gizmo_pivot") or "bounds_center")
        self.navigationStateChanged.emit(self.navigation_state())
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_display_mode_changed(self, mode: str) -> None:
        idx = self.display_combo.findText(str(mode))
        if idx >= 0 and self.display_combo.currentIndex() != idx:
            blocked = self.display_combo.blockSignals(True)
            self.display_combo.setCurrentIndex(idx)
            self.display_combo.blockSignals(blocked)
        if not self._syncing_renderer:
            self.displayModeChanged.emit(str(mode))
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_camera_preset_changed(self, preset: str) -> None:
        value = "right" if str(preset).strip().lower() == "side" else str(preset or "perspective").strip().lower()
        idx = self.camera_combo.findData(value)
        if idx >= 0 and self.camera_combo.currentIndex() != idx:
            blocked = self.camera_combo.blockSignals(True)
            self.camera_combo.setCurrentIndex(idx)
            self.camera_combo.blockSignals(blocked)
        self._set_snap_view_button_state(value)
        if not self._syncing_renderer:
            self.cameraPresetChanged.emit(value)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_navigation_profile_changed(self, profile: object) -> None:
        key = normalize_viewport_navigation_profile(profile)
        idx = self.navigation_combo.findData(key)
        if idx >= 0 and self.navigation_combo.currentIndex() != idx:
            blocked = self.navigation_combo.blockSignals(True)
            self.navigation_combo.setCurrentIndex(idx)
            self.navigation_combo.blockSignals(blocked)
        self.navigation_combo.setToolTip(f"{VIEWPORT_NAVIGATION_PROFILES[key].summary}\n\n{VIEWPORT_NAVIGATION_HELP}")
        if not self._syncing_renderer:
            self.navigationProfileChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_projection_mode_changed(self, mode: object) -> None:
        key = normalize_viewport_projection_mode(mode)
        self._set_projection_button_state(key)
        if not self._syncing_renderer:
            self.projectionModeChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def _renderer_grid_visibility_changed(self, visible: bool) -> None:
        if self.grid_button.isChecked() != bool(visible):
            blocked = self.grid_button.blockSignals(True)
            self.grid_button.setChecked(bool(visible))
            self.grid_button.blockSignals(blocked)
        if not self._syncing_renderer:
            self.gridVisibilityChanged.emit(bool(visible))
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def _renderer_snap_changed(self, enabled: bool) -> None:
        if self.snap_button.isChecked() != bool(enabled):
            blocked = self.snap_button.blockSignals(True)
            self.snap_button.setChecked(bool(enabled))
            self.snap_button.blockSignals(blocked)
        if not self._syncing_renderer:
            self.snapChanged.emit(bool(enabled))
        self.refresh_diagnostics()

    @QtCore.Slot(bool)
    def _renderer_view_cube_visibility_changed(self, visible: bool) -> None:
        if self.view_cube_button.isChecked() != bool(visible):
            blocked = self.view_cube_button.blockSignals(True)
            self.view_cube_button.setChecked(bool(visible))
            self.view_cube_button.blockSignals(blocked)
        if not self._syncing_renderer:
            self.viewCubeVisibilityChanged.emit(bool(visible))
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_gizmo_orientation_changed(self, orientation: object) -> None:
        key = normalize_gizmo_orientation(orientation)
        self._set_gizmo_orientation_combo_state(key)
        if not self._syncing_renderer:
            self.gizmoOrientationChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(str)
    def _renderer_gizmo_pivot_changed(self, pivot: object) -> None:
        key = normalize_gizmo_pivot(pivot)
        self._set_gizmo_pivot_combo_state(key)
        if not self._syncing_renderer:
            self.gizmoPivotChanged.emit(key)
        self.refresh_diagnostics()

    @QtCore.Slot(object)
    def _renderer_navigation_state_changed(self, state: object) -> None:
        if not self._syncing_renderer:
            self.navigationStateChanged.emit(state)
        self.refresh_diagnostics()

    @QtCore.Slot(object)
    def _renderer_transform_edited(self, edit: object) -> None:
        self.transformEdited.emit(edit)
        self.refresh_diagnostics()

    def apply_theme(self, theme: Theme) -> None:
        setter = getattr(self.renderer, "set_theme", None)
        if callable(setter):
            setter(theme)

    def apply_ghost_layout(self, layout) -> None:  # noqa: ANN001 - shared layout hook
        host_layout = self.layout()
        if host_layout is not None:
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(0)
            host_layout.setStretch(0, 0)
            host_layout.setStretch(1, 1)
            host_layout.setStretch(2, 0)
        input_height = max(24, int(layout.spacing_value("inputHeight", 26)))
        toolbar_height = max(34, min(44, input_height + 10))
        self.viewport_toolbar.setMinimumHeight(toolbar_height)
        self.viewport_toolbar.setMaximumHeight(toolbar_height)
        toolbar_layout = self.viewport_toolbar.layout()
        if toolbar_layout is not None:
            toolbar_layout.setContentsMargins(6, 4, 6, 4)
            toolbar_layout.setSpacing(max(3, int(layout.spacing_value("toolbarSpacing", 4))))
        self.status_strip.setMinimumHeight(24)
        self.status_strip.setMaximumHeight(max(26, min(32, input_height + 2)))
        strip_layout = self.status_strip.layout()
        if strip_layout is not None:
            strip_layout.setContentsMargins(6, 2, 6, 2)
            strip_layout.setSpacing(10)

    def frame_all(self) -> None:
        self.renderer.frame_all()
        self.refresh_diagnostics()

    def frame_selected(self) -> bool:
        framing = getattr(self.renderer, "frame_selected", None)
        framed = bool(framing()) if callable(framing) else False
        self.refresh_diagnostics()
        return framed

    def viewport_diagnostics(self) -> dict[str, object]:
        getter = getattr(self.renderer, "diagnostics", None)
        if callable(getter):
            return dict(getter())
        return {
            "backend_id": type(self.renderer).__name__,
            "renderer_name": type(self.renderer).__name__,
            "available": True,
            "object_count": 0,
            "vertex_count": 0,
            "edge_count": 0,
            "face_count": 0,
            "supports_gizmo_drawing": False,
            "supports_gizmo_interaction": False,
            "supports_gizmo_plane_handles": False,
            "supports_frame_selected": False,
            "display_mode": self.display_combo.currentText(),
            "selection_mode": self.selection_combo.currentText(),
            "transform_mode": self.transform_combo.currentText(),
            "gizmo_orientation": self.gizmo_orientation_combo.currentData(),
            "gizmo_pivot": self.gizmo_pivot_combo.currentData(),
            "camera_preset": self.camera_combo.currentData(),
            "projection_mode": "orthographic" if self.projection_button.isChecked() else "perspective",
            "projection_mode_label": viewport_projection_label(
                "orthographic" if self.projection_button.isChecked() else "perspective"
            ),
            "navigation_profile": self.navigation_combo.currentData(),
            "transform_gizmo_visible": False,
            "selection_counts": {},
        }

    def refresh_diagnostics(self) -> dict[str, object]:
        diagnostics = self.viewport_diagnostics()
        self._apply_diagnostics_to_strip(diagnostics)
        self.diagnosticsChanged.emit(diagnostics)
        return diagnostics

    def _apply_diagnostics_to_strip(self, diagnostics: dict[str, object]) -> None:
        renderer = str(diagnostics.get("renderer_name") or diagnostics.get("backend_id") or "Viewport")
        availability = "ready" if diagnostics.get("available", True) else "unavailable"
        if diagnostics.get("diagnostic_only"):
            availability = "diagnostic"
        self.renderer_status_label.setText(f"{renderer} | {availability}")
        self.scene_stats_label.setText(
            f"{int(diagnostics.get('object_count') or 0)} objects | "
            f"{int(diagnostics.get('vertex_count') or 0)} verts | "
            f"{int(diagnostics.get('edge_count') or 0)} edges | "
            f"{int(diagnostics.get('face_count') or 0)} faces"
        )
        self.mode_status_label.setText(
            f"{diagnostics.get('display_mode', 'shaded')} | "
            f"{diagnostics.get('selection_mode', 'object')} | "
            f"{diagnostics.get('transform_mode', 'move')} | "
            f"{diagnostics.get('gizmo_orientation', 'world')} | "
            f"{diagnostics.get('gizmo_pivot', 'bounds_center')}"
        )
        preset = str(diagnostics.get("camera_preset") or "perspective").replace("_", " ").title()
        projection = str(
            diagnostics.get("projection_mode_label")
            or viewport_projection_label(diagnostics.get("projection_mode") or "perspective")
        )
        profile = str(diagnostics.get("navigation_profile_label") or diagnostics.get("navigation_profile") or "Maya")
        zoom = float(diagnostics.get("zoom") or 1.0)
        toggles = []
        toggles.append("grid" if diagnostics.get("grid_visible", True) else "grid off")
        toggles.append("snap" if diagnostics.get("snap_enabled", False) else "snap off")
        toggles.append("cube" if diagnostics.get("view_cube_visible", True) else "cube off")
        self.camera_status_label.setText(f"{preset} | {projection} | {profile} | {zoom:.2f}x | {', '.join(toggles)}")
        counts = dict(diagnostics.get("selection_counts") or {})
        active = str(diagnostics.get("active_object_id") or "")
        selection_parts = [f"{key}:{int(value)}" for key, value in sorted(counts.items()) if int(value or 0)]
        selection = ", ".join(selection_parts) if selection_parts else "none"
        suffix = f" | active {active}" if active else ""
        self.selection_status_label.setText(f"Selection: {selection}{suffix}")


def _compact_combo(combo: QtWidgets.QComboBox, *, width: int, tooltip: str) -> None:
    combo.setMinimumWidth(width)
    combo.setMaximumWidth(width + 28)
    combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setToolTip(tooltip)


def _toolbar_label(text: str) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName("GhostForgeViewportToolbarLabel")
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight)
    label.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Fixed)
    return label
