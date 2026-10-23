from __future__ import annotations

from PySide6 import QtCore

from ghostforge_qt.layouts import WorkspaceLayout
from ghostforge_qt.workspaces import WorkspaceModule


class WorkspaceModuleModel(QtCore.QAbstractTableModel):
    """Model-backed list of Ghost Forge production workspaces."""

    HEADERS = ("Workspace", "Status", "Primary Panels", "Viewport", "Layout")

    def __init__(
        self,
        modules: tuple[WorkspaceModule, ...],
        layouts: dict[str, WorkspaceLayout] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._modules = tuple(modules)
        self._layouts = dict(layouts or {})

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._modules)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):  # noqa: ANN001, N802
        if not index.isValid() or not (0 <= index.row() < len(self._modules)):
            return None
        module = self._modules[index.row()]
        if role in {QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole}:
            if index.column() == 0:
                return module.label
            if index.column() == 1:
                return module.status
            if index.column() == 2:
                return ", ".join(module.primary_dock_ids)
            if index.column() == 3:
                return module.viewport_defaults.summary()
            if index.column() == 4:
                layout = self.layout_for(module.module_id)
                return layout.summary() if layout is not None else "Default layout"
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return module.summary
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return module.module_id
        if role == QtCore.Qt.ItemDataRole.UserRole + 1:
            return module
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def module_at(self, row: int) -> WorkspaceModule | None:
        if 0 <= row < len(self._modules):
            return self._modules[row]
        return None

    def module_by_id(self, module_id: str) -> WorkspaceModule | None:
        for module in self._modules:
            if module.module_id == module_id:
                return module
        return None

    def modules(self) -> tuple[WorkspaceModule, ...]:
        return self._modules

    def set_modules(
        self,
        modules: tuple[WorkspaceModule, ...],
        layouts: dict[str, WorkspaceLayout] | None = None,
    ) -> None:
        self.beginResetModel()
        self._modules = tuple(modules)
        if layouts is not None:
            self._layouts = dict(layouts)
        self.endResetModel()

    def layout_for(self, module_id: str) -> WorkspaceLayout | None:
        return self._layouts.get(module_id)

    def set_layouts(self, layouts: dict[str, WorkspaceLayout] | None) -> None:
        self._layouts = dict(layouts or {})
        if self.rowCount() > 0:
            top_left = self.index(0, 4)
            bottom_right = self.index(self.rowCount() - 1, 4)
            self.dataChanged.emit(top_left, bottom_right, [QtCore.Qt.ItemDataRole.DisplayRole])
