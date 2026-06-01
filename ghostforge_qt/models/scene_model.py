from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6 import QtCore

from ghostforge_core.types import MeshInfo


@dataclass(frozen=True)
class TransformState:
    translate: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotate_euler_deg: tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class SceneObjectRecord:
    object_id: str
    name: str
    path: Path
    vertices: int | None = None
    faces: int | None = None
    watertight: bool | None = None
    visible: bool = True
    transform: TransformState = TransformState()
    asset_dir: Path | None = None
    manifest_path: Path | None = None
    operations: tuple[str, ...] = ()


class SceneTableModel(QtCore.QAbstractTableModel):
    """Small document model for the first Qt scene outliner."""

    COLUMNS = ("Name", "Vertices", "Faces", "Watertight", "Position", "Path")
    ObjectIdRole = QtCore.Qt.ItemDataRole.UserRole + 1
    PathRole = QtCore.Qt.ItemDataRole.UserRole + 2
    TransformRole = QtCore.Qt.ItemDataRole.UserRole + 3

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: list[SceneObjectRecord] = []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == self.ObjectIdRole:
            return row.object_id
        if role == self.PathRole:
            return str(row.path)
        if role == self.TransformRole:
            return row.transform
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        pos = ", ".join(f"{v:.2f}" for v in row.transform.translate)
        values = (
            row.name,
            "" if row.vertices is None else row.vertices,
            "" if row.faces is None else row.faces,
            "" if row.watertight is None else ("yes" if row.watertight else "no"),
            pos,
            str(row.path),
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

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        base = super().flags(index)
        if index.isValid():
            return base | QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled
        return base

    def add_mesh(self, path: Path, info: MeshInfo | None = None) -> SceneObjectRecord:
        record = SceneObjectRecord(
            object_id=f"obj_{uuid.uuid4().hex}",
            name=path.stem,
            path=path,
            vertices=info.vertices if info else None,
            faces=info.faces if info else None,
            watertight=info.watertight if info else None,
        )
        self.beginInsertRows(QtCore.QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(record)
        self.endInsertRows()
        return record

    def add_record(self, record: SceneObjectRecord) -> SceneObjectRecord:
        self.beginInsertRows(QtCore.QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(record)
        self.endInsertRows()
        return record

    def set_records(self, records: list[SceneObjectRecord]) -> None:
        self.beginResetModel()
        self._rows = list(records)
        self.endResetModel()

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginRemoveRows(QtCore.QModelIndex(), 0, len(self._rows) - 1)
        self._rows.clear()
        self.endRemoveRows()

    def remove_row(self, row: int) -> SceneObjectRecord | None:
        if row < 0 or row >= len(self._rows):
            return None
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        record = self._rows.pop(row)
        self.endRemoveRows()
        return record

    def record_at(self, row: int) -> SceneObjectRecord | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def update_record(self, object_id: str, **changes) -> SceneObjectRecord | None:
        for row_index, row in enumerate(self._rows):
            if row.object_id != object_id:
                continue
            updated = replace(row, **changes)
            self._rows[row_index] = updated
            top_left = self.index(row_index, 0)
            bottom_right = self.index(row_index, self.columnCount() - 1)
            self.dataChanged.emit(top_left, bottom_right, [])
            return updated
        return None

    def update_transform(self, object_id: str, transform: TransformState) -> SceneObjectRecord | None:
        return self.update_record(object_id, transform=transform)

    def append_operation(self, object_id: str, label: str, *, path: Path | None = None, vertices: int | None = None, faces: int | None = None, watertight: bool | None = None, asset_dir: Path | None = None, manifest_path: Path | None = None) -> SceneObjectRecord | None:
        for row in self._rows:
            if row.object_id == object_id:
                ops = (*row.operations, label)
                return self.update_record(
                    object_id,
                    operations=ops,
                    path=path or row.path,
                    vertices=row.vertices if vertices is None else vertices,
                    faces=row.faces if faces is None else faces,
                    watertight=row.watertight if watertight is None else watertight,
                    asset_dir=row.asset_dir if asset_dir is None else asset_dir,
                    manifest_path=row.manifest_path if manifest_path is None else manifest_path,
                )
        return None

    def records(self) -> list[SceneObjectRecord]:
        return list(self._rows)
