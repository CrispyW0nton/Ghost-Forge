from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.models.scene_model import SceneObjectRecord
from ghostforge_qt.theme.theme_model import Theme

from .editor_viewport import EditorViewportRenderer
from .renderer_interface import RendererInterface, ViewportObject


class ViewportHost(QtWidgets.QWidget):
    """Owns the active renderer widget and exposes scene update hooks."""

    selectionModeChanged = QtCore.Signal(str)
    transformModeChanged = QtCore.Signal(str)
    displayModeChanged = QtCore.Signal(str)
    itemPicked = QtCore.Signal(object)

    def __init__(self, renderer: RendererInterface | None = None, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.renderer = renderer or EditorViewportRenderer(self)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self.renderer.widget())
        picked = getattr(self.renderer, "itemPicked", None)
        if picked is not None:
            picked.connect(self.itemPicked.emit)

    def _build_toolbar(self) -> QtWidgets.QWidget:
        bar = QtWidgets.QFrame()
        row = QtWidgets.QHBoxLayout(bar)
        row.setContentsMargins(6, 4, 6, 4)
        row.setSpacing(4)

        self.selection_combo = QtWidgets.QComboBox()
        self.selection_combo.addItems(["object", "vertex", "edge", "border", "face", "element"])
        self.selection_combo.currentTextChanged.connect(self.set_selection_mode)
        row.addWidget(QtWidgets.QLabel("Select"))
        row.addWidget(self.selection_combo)

        self.transform_combo = QtWidgets.QComboBox()
        self.transform_combo.addItems(["move", "rotate", "scale", "pivot"])
        self.transform_combo.currentTextChanged.connect(self.set_transform_mode)
        row.addWidget(QtWidgets.QLabel("Transform"))
        row.addWidget(self.transform_combo)

        self.display_combo = QtWidgets.QComboBox()
        self.display_combo.addItems(["shaded", "wireframe", "solid", "uv", "xray"])
        self.display_combo.currentTextChanged.connect(self.set_display_mode)
        row.addWidget(QtWidgets.QLabel("Display"))
        row.addWidget(self.display_combo)

        for label, preset in (("Persp", "perspective"), ("Front", "front"), ("Side", "side"), ("Top", "top")):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=preset: self.set_camera_preset(value))
            row.addWidget(button)
        frame_button = QtWidgets.QPushButton("Frame")
        frame_button.clicked.connect(self.frame_all)
        row.addWidget(frame_button)
        row.addStretch(1)
        return bar

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

    @QtCore.Slot(str)
    def set_selection_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_selection_mode", None)
        if callable(setter):
            setter(mode)
        idx = self.selection_combo.findText(mode)
        if idx >= 0 and self.selection_combo.currentIndex() != idx:
            self.selection_combo.setCurrentIndex(idx)
        self.selectionModeChanged.emit(mode)

    @QtCore.Slot(str)
    def set_transform_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_transform_mode", None)
        if callable(setter):
            setter(mode)
        idx = self.transform_combo.findText(mode)
        if idx >= 0 and self.transform_combo.currentIndex() != idx:
            self.transform_combo.setCurrentIndex(idx)
        self.transformModeChanged.emit(mode)

    @QtCore.Slot(str)
    def set_display_mode(self, mode: str) -> None:
        setter = getattr(self.renderer, "set_display_mode", None)
        if callable(setter):
            setter(mode)
        idx = self.display_combo.findText(mode)
        if idx >= 0 and self.display_combo.currentIndex() != idx:
            self.display_combo.setCurrentIndex(idx)
        self.displayModeChanged.emit(mode)

    @QtCore.Slot(str)
    def set_camera_preset(self, preset: str) -> None:
        setter = getattr(self.renderer, "set_camera_preset", None)
        if callable(setter):
            setter(preset)

    def apply_theme(self, theme: Theme) -> None:
        setter = getattr(self.renderer, "set_theme", None)
        if callable(setter):
            setter(theme)

    def frame_all(self) -> None:
        self.renderer.frame_all()
