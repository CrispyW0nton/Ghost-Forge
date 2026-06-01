from __future__ import annotations

from PySide6 import QtCore, QtGui

from ghostforge_qt.services.core_bridge import WorkerRow


class WorkerTableModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Worker", "Capabilities", "Status", "Priority", "License", "Reason")
    WorkerNameRole = QtCore.Qt.ItemDataRole.UserRole + 1
    RunnableRole = QtCore.Qt.ItemDataRole.UserRole + 2

    def __init__(self, rows: list[WorkerRow] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = rows or []

    def set_rows(self, rows: list[WorkerRow]) -> None:
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
        if role == self.WorkerNameRole:
            return row.name
        if role == self.RunnableRole:
            return row.runnable
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            return QtGui.QBrush(QtGui.QColor("#1F8F3A" if row.runnable else "#B34848"))
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        status = "runnable"
        if row.is_stub:
            status = "stub"
        if not row.runnable:
            status = "missing"
        values = (
            row.name,
            ", ".join(row.capabilities),
            status,
            row.priority,
            row.license,
            row.reason,
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

    def rows(self) -> list[WorkerRow]:
        return list(self._rows)
