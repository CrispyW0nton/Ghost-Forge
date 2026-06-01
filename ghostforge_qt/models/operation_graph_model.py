from __future__ import annotations

import json
import uuid

from PySide6 import QtCore, QtGui

from ghostforge_core.authoring import EditGraph, EvaluationResult, OperationNode
from ghostforge_qt.services.core_bridge import OperationRow


class OperationPaletteModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Kind", "Type", "Status", "Workers", "Summary")
    OperationRole = QtCore.Qt.ItemDataRole.UserRole + 1
    KindRole = QtCore.Qt.ItemDataRole.UserRole + 2
    StatusRole = QtCore.Qt.ItemDataRole.UserRole + 3

    def __init__(self, rows: list[OperationRow] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = rows or []

    def set_rows(self, rows: list[OperationRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == self.OperationRole:
            return row
        if role == self.KindRole:
            return row.kind
        if role == self.StatusRole:
            return row.status
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            return QtGui.QBrush(_status_color(row.status))
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            row.kind,
            row.operation_type,
            row.status,
            ", ".join(row.workers) or "-",
            row.summary,
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def row_at(self, row: int) -> OperationRow | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def rows(self) -> list[OperationRow]:
        return list(self._rows)


class OperationGraphModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Enabled", "Kind", "Label", "Status", "Params")
    NodeRole = QtCore.Qt.ItemDataRole.UserRole + 1
    NodeIdRole = QtCore.Qt.ItemDataRole.UserRole + 2
    StatusRole = QtCore.Qt.ItemDataRole.UserRole + 3

    def __init__(self, graph: EditGraph | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._graph = graph or EditGraph(graph_id=f"qt_{uuid.uuid4().hex[:10]}", name="Qt Operation Graph")
        self._step_status: dict[str, str] = {}
        self._step_errors: dict[str, str] = {}

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._graph.nodes)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._graph.nodes[index.row()]
        status = self._step_status.get(node.id, "pending")
        if role == self.NodeRole:
            return node
        if role == self.NodeIdRole:
            return node.id
        if role == self.StatusRole:
            return status
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() == 3:
            return QtGui.QBrush(_status_color(status))
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return self._step_errors.get(node.id) or node.notes or ""
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            "yes" if node.enabled else "no",
            node.kind,
            node.label or node.kind,
            status,
            _params_text(node.params),
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def graph(self) -> EditGraph:
        return self._graph

    def set_graph(self, graph: EditGraph) -> None:
        self.beginResetModel()
        self._graph = graph
        self._step_status.clear()
        self._step_errors.clear()
        self.endResetModel()

    def append_operation(self, operation: OperationRow, params: dict[str, object] | None = None) -> OperationNode:
        node_id = _node_id(operation.kind, len(self._graph.nodes) + 1)
        node = OperationNode(
            id=node_id,
            kind=operation.kind,
            label=operation.label,
            params=params or {},
        )
        self.beginInsertRows(QtCore.QModelIndex(), len(self._graph.nodes), len(self._graph.nodes))
        self._graph = self._graph.with_nodes([*self._graph.nodes, node])
        self.endInsertRows()
        return node

    def remove_row(self, row: int) -> OperationNode | None:
        if row < 0 or row >= len(self._graph.nodes):
            return None
        nodes = list(self._graph.nodes)
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        removed = nodes.pop(row)
        self._graph = self._graph.with_nodes(nodes)
        self._step_status.pop(removed.id, None)
        self._step_errors.pop(removed.id, None)
        self.endRemoveRows()
        return removed

    def clear(self) -> None:
        if not self._graph.nodes:
            return
        self.beginResetModel()
        self._graph = self._graph.model_copy(update={"nodes": ()})
        self._step_status.clear()
        self._step_errors.clear()
        self.endResetModel()

    def set_evaluation_result(self, result: EvaluationResult) -> None:
        self._step_status = {step.node_id: step.status for step in result.steps}
        self._step_errors = {step.node_id: step.error or "" for step in result.steps if step.error}
        if self.rowCount():
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1), [])

    def node_at(self, row: int) -> OperationNode | None:
        if row < 0 or row >= len(self._graph.nodes):
            return None
        return self._graph.nodes[row]


def _node_id(kind: str, index: int) -> str:
    safe_kind = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in kind)
    return f"n{index}_{safe_kind[:40]}"


def _params_text(params: dict[str, object]) -> str:
    if not params:
        return "-"
    return json.dumps(params, sort_keys=True)


def _status_color(status: str) -> QtGui.QColor:
    if status in {"available", "runnable", "succeeded"}:
        return QtGui.QColor("#1F8F3A")
    if status in {"stub", "pending", "skipped"}:
        return QtGui.QColor("#B9822B")
    return QtGui.QColor("#B34848")


__all__ = ["OperationGraphModel", "OperationPaletteModel"]
