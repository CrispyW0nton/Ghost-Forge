from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.services.core_bridge import OperationRow


@dataclass(frozen=True)
class ParameterPreset:
    label: str
    values: dict[str, object]
    default: bool = False
    description: str = ""


class PathParameterWidget(QtWidgets.QWidget):
    """Small editor for descriptor parameters that point at files or folders."""

    def __init__(
        self,
        *,
        mode: str = "file",
        file_filter: str = "All Files (*)",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.file_filter = file_filter
        self.line_edit = QtWidgets.QLineEdit()
        self.browse_button = QtWidgets.QPushButton("Browse")
        self.browse_button.clicked.connect(self.browse)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.line_edit, 1)
        layout.addWidget(self.browse_button)

    def value(self) -> str:
        return self.line_edit.text().strip()

    def set_value(self, value: object) -> None:
        self.line_edit.setText("" if value is None else str(value))

    def browse(self) -> None:
        start = self.value() or QtCore.QDir.homePath()
        if self.mode == "directory":
            chosen = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder", start)
        else:
            chosen, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "Select File",
                start,
                self.file_filter,
            )
        if chosen:
            self.set_value(chosen)


class OperationParameterForm(QtWidgets.QWidget):
    """Schema-driven editor for an authoring operation's node parameters."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QtWidgets.QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._operation: OperationRow | None = None
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._schema: dict[str, dict[str, Any]] = {}
        self._presets: list[ParameterPreset] = []
        self._preset_combo: QtWidgets.QComboBox | None = None

    @property
    def operation_kind(self) -> str | None:
        return None if self._operation is None else self._operation.kind

    @property
    def preset_labels(self) -> tuple[str, ...]:
        return tuple(preset.label for preset in self._presets)

    def set_operation(
        self,
        operation: OperationRow | None,
        values: dict[str, object] | None = None,
    ) -> None:
        self._clear()
        self._operation = operation
        self._widgets = {}
        self._schema = {}
        self._presets = []
        self._preset_combo = None
        if operation is None:
            self._form.addRow(QtWidgets.QLabel("Select an operation."))
            return

        schema = _normalise_schema(operation.params_schema)
        self._presets = _extract_presets(operation)
        current = dict(values or {})
        default_preset_index = None if current else _default_preset_index(self._presets)
        if default_preset_index is not None:
            current.update(self._presets[default_preset_index].values)
        self._schema = schema
        if not schema:
            self._form.addRow(QtWidgets.QLabel("This operation has no parameters."))
            return
        if self._presets:
            self._add_preset_row(default_preset_index)

        for key, spec in schema.items():
            widget = self._make_widget(key, spec, current.get(key, spec.get("default")), operation)
            self._widgets[key] = widget
            self._form.addRow(_label(key, bool(spec.get("required"))), widget)

    def values(self) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, widget in self._widgets.items():
            spec = self._schema[key]
            value = self._read_widget(key, widget, spec)
            if value is _MISSING:
                continue
            out[key] = value
        return out

    def set_value(self, key: str, value: object) -> None:
        if key not in self._widgets:
            raise KeyError(key)
        _write_widget(self._widgets[key], self._schema[key], value)

    def apply_preset(self, label: str) -> None:
        for index, preset in enumerate(self._presets):
            if preset.label == label:
                if self._preset_combo is not None:
                    self._preset_combo.setCurrentIndex(index + 1)
                else:
                    self._apply_preset(preset)
                return
        raise KeyError(label)

    def _clear(self) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _add_preset_row(self, default_preset_index: int | None) -> None:
        combo = QtWidgets.QComboBox()
        combo.addItem("Custom", None)
        for index, preset in enumerate(self._presets):
            combo.addItem(preset.label, index)
            if preset.description:
                combo.setItemData(index + 1, preset.description, QtCore.Qt.ItemDataRole.ToolTipRole)
        combo.blockSignals(True)
        if default_preset_index is not None:
            combo.setCurrentIndex(default_preset_index + 1)
        combo.blockSignals(False)
        combo.currentIndexChanged.connect(self._preset_index_changed)
        self._preset_combo = combo
        self._form.addRow("Preset", combo)

    @QtCore.Slot(int)
    def _preset_index_changed(self, index: int) -> None:
        if self._preset_combo is None or index <= 0:
            return
        preset_index = self._preset_combo.itemData(index)
        if not isinstance(preset_index, int) or preset_index < 0 or preset_index >= len(self._presets):
            return
        self._apply_preset(self._presets[preset_index])

    def _apply_preset(self, preset: ParameterPreset) -> None:
        for key, value in preset.values.items():
            widget = self._widgets.get(key)
            spec = self._schema.get(key)
            if widget is not None and spec is not None:
                _write_widget(widget, spec, value)

    def _make_widget(
        self,
        key: str,
        spec: dict[str, Any],
        value: object,
        operation: OperationRow,
    ) -> QtWidgets.QWidget:
        typ = str(spec.get("type") or "string")
        if key == "worker":
            combo = QtWidgets.QComboBox()
            combo.addItem("Auto", "")
            for name in operation.workers:
                combo.addItem(name, name)
            _write_widget(combo, spec, value)
            return combo
        if typ == "enum":
            combo = QtWidgets.QComboBox()
            for item in spec.get("values", ()):
                text = str(item)
                combo.addItem(text, text)
            _write_widget(combo, spec, value)
            return combo
        if typ == "bool":
            check = QtWidgets.QCheckBox()
            _write_widget(check, spec, value)
            return check
        if typ == "object":
            edit = QtWidgets.QPlainTextEdit()
            edit.setMaximumHeight(72)
            _write_widget(edit, spec, value)
            return edit
        path_mode = _path_mode(key, spec)
        if path_mode is not None:
            picker = PathParameterWidget(
                mode=path_mode,
                file_filter=str(spec.get("filter") or spec.get("file_filter") or "All Files (*)"),
            )
            picker.line_edit.setPlaceholderText(
                "Folder path" if path_mode == "directory" else "File path"
            )
            _write_widget(picker, spec, value)
            return picker

        edit = QtWidgets.QLineEdit()
        if typ in {"int", "float"}:
            edit.setPlaceholderText(_number_hint(spec))
        elif typ in {"vec3", "vec4"}:
            count = 3 if typ == "vec3" else 4
            edit.setPlaceholderText(", ".join(["0.0"] * count))
        elif typ == "scalar_or_vec3":
            edit.setPlaceholderText("1.0 or 1.0, 1.0, 1.0")
        elif typ == "path":
            edit.setPlaceholderText("Path")
        _write_widget(edit, spec, value)
        return edit

    def _read_widget(self, key: str, widget: QtWidgets.QWidget, spec: dict[str, Any]) -> object:
        typ = str(spec.get("type") or "string")
        required = bool(spec.get("required"))
        if isinstance(widget, QtWidgets.QComboBox):
            value = widget.currentData()
            if value in {None, ""} and required:
                raise ValueError(f"{key} is required")
            return _MISSING if value in {None, ""} else str(value)
        if isinstance(widget, QtWidgets.QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QtWidgets.QPlainTextEdit):
            text = widget.toPlainText().strip()
            if not text:
                if required:
                    raise ValueError(f"{key} is required")
                return {} if spec.get("default") == {} else _MISSING
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError(f"{key} must be a JSON object")
            return value
        if isinstance(widget, PathParameterWidget):
            text = widget.value()
            if not text:
                if required:
                    raise ValueError(f"{key} is required")
                return _MISSING
            return text
        if not isinstance(widget, QtWidgets.QLineEdit):
            return _MISSING
        text = widget.text().strip()
        if not text:
            if required:
                raise ValueError(f"{key} is required")
            return _MISSING
        if typ == "int":
            return _bounded(key, int(text), spec)
        if typ == "float":
            return _bounded(key, float(text), spec)
        if typ == "vec3":
            return _read_vector(key, text, 3)
        if typ == "vec4":
            return _read_vector(key, text, 4)
        if typ == "scalar_or_vec3":
            parts = _split_numbers(text)
            if len(parts) == 1:
                return parts[0]
            if len(parts) == 3:
                return parts
            raise ValueError(f"{key} must be a scalar or a 3-vector")
        return text


class _Missing:
    pass


_MISSING = _Missing()


def _normalise_schema(schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, value in schema.items():
        text = str(key)
        if _is_schema_metadata(text, value):
            continue
        out[text] = dict(value or {})
    return out


def _is_schema_metadata(key: str, value: Any) -> bool:
    if key.startswith("_"):
        return True
    return key == "presets" and isinstance(value, (list, tuple))


def _extract_presets(operation: OperationRow) -> list[ParameterPreset]:
    raw_presets: list[Any] = list(operation.parameter_presets)
    schema = operation.params_schema
    for key in ("_presets", "__presets"):
        raw = schema.get(key)
        if isinstance(raw, (list, tuple)):
            raw_presets.extend(raw)
    raw = schema.get("presets")
    if isinstance(raw, (list, tuple)):
        raw_presets.extend(raw)
    for key in ("_ui", "__ui__"):
        raw_ui = schema.get(key)
        if isinstance(raw_ui, dict) and isinstance(raw_ui.get("presets"), (list, tuple)):
            raw_presets.extend(raw_ui["presets"])

    presets: list[ParameterPreset] = []
    for index, raw in enumerate(raw_presets, start=1):
        preset = _coerce_preset(raw, fallback_label=f"Preset {index}")
        if preset is not None:
            presets.append(preset)
    return presets


def _coerce_preset(raw: Any, *, fallback_label: str) -> ParameterPreset | None:
    if not isinstance(raw, dict):
        return None
    values = raw.get("values", raw.get("params", raw.get("defaults")))
    if not isinstance(values, dict):
        return None
    label = str(raw.get("label") or raw.get("name") or raw.get("id") or fallback_label)
    return ParameterPreset(
        label=label,
        values=dict(values),
        default=bool(raw.get("default", False)),
        description=str(raw.get("description") or ""),
    )


def _default_preset_index(presets: list[ParameterPreset]) -> int | None:
    for index, preset in enumerate(presets):
        if preset.default:
            return index
    return None


def _label(key: str, required: bool) -> str:
    text = key.replace("_", " ").title()
    return f"{text} *" if required else text


def _number_hint(spec: dict[str, Any]) -> str:
    minimum = spec.get("min")
    maximum = spec.get("max")
    if minimum is not None and maximum is not None:
        return f"{minimum} to {maximum}"
    if minimum is not None:
        return f">= {minimum}"
    if maximum is not None:
        return f"<= {maximum}"
    return ""


def _path_mode(key: str, spec: dict[str, Any]) -> str | None:
    typ = str(spec.get("type") or "string").lower()
    fmt = str(spec.get("format") or "").lower()
    widget = str(spec.get("widget") or "").lower()
    path_kind = str(spec.get("path_kind") or spec.get("pathType") or "").lower()
    tokens = {typ, fmt, widget, path_kind}
    if tokens & {"directory", "dir", "folder"}:
        return "directory"
    if key.endswith(("_dir", "_directory", "_folder")) or key in {
        "asset_dir",
        "bridge_dir",
        "output_dir",
    }:
        return "directory"
    if tokens & {"path", "file", "open_file", "input_file"}:
        return "file"
    if key.endswith(("_path", "_file", "_filename")):
        return "file"
    return None


def _write_widget(widget: QtWidgets.QWidget, spec: dict[str, Any], value: object) -> None:
    if value is None:
        value = spec.get("default")
    if isinstance(widget, QtWidgets.QComboBox):
        index = widget.findData("" if value is None else str(value))
        if index >= 0:
            widget.setCurrentIndex(index)
        return
    if isinstance(widget, QtWidgets.QCheckBox):
        widget.setChecked(bool(value))
        return
    if isinstance(widget, QtWidgets.QPlainTextEdit):
        if value is None:
            widget.setPlainText("")
        else:
            widget.setPlainText(json.dumps(value, sort_keys=True))
        return
    if isinstance(widget, PathParameterWidget):
        widget.set_value(value)
        return
    if isinstance(widget, QtWidgets.QLineEdit):
        if value is None:
            widget.setText("")
        elif isinstance(value, (list, tuple)):
            widget.setText(", ".join(str(item) for item in value))
        else:
            widget.setText(str(value))


def _read_vector(key: str, text: str, expected: int) -> list[float]:
    values = _split_numbers(text)
    if len(values) != expected:
        raise ValueError(f"{key} must contain {expected} numbers")
    return values


def _split_numbers(text: str) -> list[float]:
    return [float(part.strip()) for part in text.replace(";", ",").split(",") if part.strip()]


def _bounded(key: str, value: int | float, spec: dict[str, Any]) -> int | float:
    minimum = spec.get("min")
    maximum = spec.get("max")
    if minimum is not None and value < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{key} must be <= {maximum}")
    return value


__all__ = ["OperationParameterForm", "PathParameterWidget"]
