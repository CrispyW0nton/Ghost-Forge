from __future__ import annotations

from PySide6 import QtCore

from ghostforge_core.types import JobHandle


class JobTableModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Job", "Kind", "Status", "Progress", "Updated")
    JobIdRole = QtCore.Qt.ItemDataRole.UserRole + 1

    def __init__(self, rows: list[JobHandle] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = rows or []

    def set_jobs(self, rows: list[JobHandle]) -> None:
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
        if role == self.JobIdRole:
            return row.id
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        progress = ""
        if row.progress is not None:
            progress = f"{row.progress.percent:.0f}% {row.progress.stage}"
        values = (
            row.id[:12],
            row.kind,
            row.status.value,
            progress,
            row.updated_at.astimezone().strftime("%H:%M:%S"),
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
