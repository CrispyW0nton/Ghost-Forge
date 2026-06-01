from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.models.scene_model import TransformState


class ModelingToolsPanel(QtWidgets.QWidget):
    selectionModeRequested = QtCore.Signal(str)
    selectionToolRequested = QtCore.Signal(str)
    transformModeRequested = QtCore.Signal(str)
    toolRequested = QtCore.Signal(str)
    transformEdited = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._selection_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._transform_buttons: dict[str, QtWidgets.QToolButton] = {}
        self._translate: dict[str, QtWidgets.QDoubleSpinBox] = {}
        self._rotate: dict[str, QtWidgets.QDoubleSpinBox] = {}
        self._scale: dict[str, QtWidgets.QDoubleSpinBox] = {}
        self._status_labels: dict[str, QtWidgets.QLabel] = {}
        self.status = QtWidgets.QLabel("Ready")
        self.status.setWordWrap(True)
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self._selection_group())
        root.addWidget(self._selection_tools_group())
        root.addWidget(self._transform_group())
        root.addWidget(self._transform_typein_group())
        root.addWidget(self._options_group())
        root.addWidget(self._geometry_group())
        root.addWidget(self._cleanup_group())
        root.addWidget(self._status_group())
        root.addWidget(self.status)
        root.addStretch(1)

    def _selection_group(self) -> QtWidgets.QGroupBox:
        return self._button_group(
            "Selection",
            ["object", "vertex", "edge", "border", "face", "element"],
            self._selection_buttons,
            self.selectionModeRequested,
        )

    def _selection_tools_group(self) -> QtWidgets.QGroupBox:
        return self._selection_command_group(
            "Selection Tools",
            ["select_all", "clear_selection", "invert_selection"],
        )

    def _transform_group(self) -> QtWidgets.QGroupBox:
        return self._button_group(
            "Transform",
            ["move", "rotate", "scale", "pivot"],
            self._transform_buttons,
            self.transformModeRequested,
        )

    def _geometry_group(self) -> QtWidgets.QGroupBox:
        return self._command_group(
            "Modeling",
            [
                "extrude",
                "bevel",
                "inset",
                "bridge",
                "weld",
                "smooth_laplacian",
                "subdivide",
                "knife",
                "loop_cut",
                "delete",
                "recenter",
                "apply_material",
            ],
        )

    def _cleanup_group(self) -> QtWidgets.QGroupBox:
        return self._command_group(
            "Cleanup",
            ["recalculate_normals", "flip_normals", "remove_isolated", "decimate", "normalize_scale", "unwrap_uvs"],
        )

    def _options_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Operation Options")
        form = QtWidgets.QFormLayout(box)
        self.weld_tolerance = self._spin(0.000001, 1.0, 0.001, 0.001)
        self.decimate_ratio = self._spin(0.01, 1.0, 0.5, 0.05)
        self.smooth_iterations = QtWidgets.QSpinBox()
        self.smooth_iterations.setRange(1, 200)
        self.smooth_iterations.setValue(3)
        self.subdivide_iterations = QtWidgets.QSpinBox()
        self.subdivide_iterations.setRange(1, 4)
        self.subdivide_iterations.setValue(1)
        self.recenter_pivot = QtWidgets.QComboBox()
        self.recenter_pivot.addItems(["bounds_center", "centroid", "bottom", "origin"])
        form.addRow("Weld tolerance", self.weld_tolerance)
        form.addRow("Decimate ratio", self.decimate_ratio)
        form.addRow("Smooth iterations", self.smooth_iterations)
        form.addRow("Subdivide iterations", self.subdivide_iterations)
        form.addRow("Recenter pivot", self.recenter_pivot)
        return box

    def _transform_typein_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Transform Type-In")
        grid = QtWidgets.QGridLayout(box)
        grid.addWidget(QtWidgets.QLabel("Axis"), 0, 0)
        grid.addWidget(QtWidgets.QLabel("Move"), 0, 1)
        grid.addWidget(QtWidgets.QLabel("Rotate"), 0, 2)
        grid.addWidget(QtWidgets.QLabel("Scale"), 0, 3)
        for row, axis in enumerate(("X", "Y", "Z"), start=1):
            grid.addWidget(QtWidgets.QLabel(axis), row, 0)
            move = self._spin(-100000.0, 100000.0, 0.0, 0.1)
            rotate = self._spin(-3600.0, 3600.0, 0.0, 1.0)
            scale = self._spin(0.001, 100000.0, 1.0, 0.1)
            self._translate[axis] = move
            self._rotate[axis] = rotate
            self._scale[axis] = scale
            for col, spin in enumerate((move, rotate, scale), start=1):
                spin.valueChanged.connect(lambda _value=0.0: self._emit_transform())
                grid.addWidget(spin, row, col)
        reset = QtWidgets.QPushButton("Reset Transform")
        reset.clicked.connect(lambda: self.set_transform(TransformState()))
        grid.addWidget(reset, 4, 0, 1, 4)
        return box

    def _spin(self, low: float, high: float, value: float, step: float) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(low, high)
        spin.setDecimals(3)
        spin.setSingleStep(step)
        spin.setValue(value)
        return spin

    def _button_group(
        self,
        title: str,
        names: list[str],
        registry: dict[str, QtWidgets.QToolButton],
        signal: QtCore.Signal,
    ) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        for i, name in enumerate(names):
            button = QtWidgets.QToolButton()
            button.setText(name.replace("_", " ").title())
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, value=name: signal.emit(value))
            registry[name] = button
            grid.addWidget(button, i // 2, i % 2)
        if names:
            registry[names[0]].setChecked(True)
        return box

    def _command_group(self, title: str, names: list[str]) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        for i, name in enumerate(names):
            button = QtWidgets.QPushButton(name.replace("_", " ").title())
            button.clicked.connect(lambda _checked=False, value=name: self._request_tool(value))
            grid.addWidget(button, i // 2, i % 2)
        return box

    def _selection_command_group(self, title: str, names: list[str]) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        grid = QtWidgets.QGridLayout(box)
        for i, name in enumerate(names):
            button = QtWidgets.QPushButton(name.replace("_", " ").title())
            button.clicked.connect(lambda _checked=False, value=name: self.selectionToolRequested.emit(value))
            grid.addWidget(button, i // 2, i % 2)
        return box

    def _status_group(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Mesh Status")
        form = QtWidgets.QFormLayout(box)
        for label, key in (
            ("Active Object", "active"),
            ("Selection Mode", "mode"),
            ("Selected", "selected"),
            ("Topology", "topology"),
            ("Warnings", "warnings"),
        ):
            value = QtWidgets.QLabel("-")
            value.setWordWrap(True)
            self._status_labels[key] = value
            form.addRow(label, value)
        return box

    def _request_tool(self, tool_name: str) -> None:
        self.status.setText(f"{tool_name.replace('_', ' ').title()} requested. Operation graph wiring is next.")
        self.toolRequested.emit(tool_name)

    def _emit_transform(self) -> None:
        self.transformEdited.emit(self.transform())

    def transform(self) -> TransformState:
        return TransformState(
            translate=tuple(self._translate[a].value() for a in ("X", "Y", "Z")),
            rotate_euler_deg=tuple(self._rotate[a].value() for a in ("X", "Y", "Z")),
            scale=tuple(self._scale[a].value() for a in ("X", "Y", "Z")),
        )

    def set_transform(self, transform: TransformState) -> None:
        for axis, value in zip(("X", "Y", "Z"), transform.translate):
            self._translate[axis].blockSignals(True)
            self._translate[axis].setValue(float(value))
            self._translate[axis].blockSignals(False)
        for axis, value in zip(("X", "Y", "Z"), transform.rotate_euler_deg):
            self._rotate[axis].blockSignals(True)
            self._rotate[axis].setValue(float(value))
            self._rotate[axis].blockSignals(False)
        for axis, value in zip(("X", "Y", "Z"), transform.scale):
            self._scale[axis].blockSignals(True)
            self._scale[axis].setValue(float(value))
            self._scale[axis].blockSignals(False)
        self._emit_transform()

    @QtCore.Slot(str)
    def set_selection_mode(self, mode: str) -> None:
        for name, button in self._selection_buttons.items():
            button.setChecked(name == mode)

    @QtCore.Slot(str)
    def set_transform_mode(self, mode: str) -> None:
        for name, button in self._transform_buttons.items():
            button.setChecked(name == mode)

    def operation_options(self) -> dict[str, object]:
        return {
            "weld_tolerance": float(self.weld_tolerance.value()),
            "target_ratio": float(self.decimate_ratio.value()),
            "smooth_iterations": int(self.smooth_iterations.value()),
            "subdivide_iterations": int(self.subdivide_iterations.value()),
            "recenter_pivot": str(self.recenter_pivot.currentText()),
        }

    def set_mesh_status(self, *, active: str = "-", mode: str = "object", selected: dict[str, int] | None = None, topology=None) -> None:  # type: ignore[no-untyped-def]
        self._status_labels["active"].setText(active or "-")
        self._status_labels["mode"].setText(mode)
        selected = selected or {}
        self._status_labels["selected"].setText(
            ", ".join(f"{key}:{value}" for key, value in selected.items()) or "-"
        )
        if topology is None:
            self._status_labels["topology"].setText("-")
            self._status_labels["warnings"].setText("-")
            return
        self._status_labels["topology"].setText(
            f"v:{topology.vertices} e:{topology.edges} f:{topology.faces} elements:{topology.connected_elements}"
        )
        self._status_labels["warnings"].setText(topology.warning_text)
