from __future__ import annotations

import json
from typing import Any

from PySide6 import QtWidgets

from ghostforge_qt.services.core_bridge import OperationRow


class OperationParameterForm(QtWidgets.QWidget):
    """Schema-driven editor for an authoring operation's node parameters."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._form = QtWidgets.QFormLayout(self)
        self._form.setContentsMargins(0, 0, 0, 0)
        self._operation: OperationRow | None = None
        self._widgets: dict[str, QtWidgets.QWidget] = {}
        self._schema: dict[str, dict[str, Any]] = {}

    @property
    def operation_kind(self) -> str | None:
        return None if self._operation is None else self._operation.kind

    def set_operation(
        self,
        operation: OperationRow | None,
        values: dict[str, object] | None = None,
    ) -> None:
        self._clear()
        self._operation = operation
        self._widgets = {}
        self._schema = {}
        if operation is None:
            self._form.addRow(QtWidgets.QLabel("Select an operation."))
            return

        schema = _normalise_schema(operation.params_schema)
        self._schema = schema
        if not schema:
            self._form.addRow(QtWidgets.QLabel("This operation has no parameters."))
            return

        current = values or {}
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

    def _clear(self) -> None:
        while self._form.count():
            item = self._form.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
    return {str(key): dict(value or {}) for key, value in schema.items()}


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


__all__ = ["OperationParameterForm"]
