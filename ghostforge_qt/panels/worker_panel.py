from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.models.worker_model import WorkerTableModel
from ghostforge_qt.services.core_bridge import CoreBridge


class WorkerPanel(QtWidgets.QWidget):
    refreshed = QtCore.Signal()

    def __init__(self, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.model = WorkerTableModel()
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().hide()

        self.refresh_button = QtWidgets.QPushButton("Refresh Workers")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.view)
        self.refresh()

    @QtCore.Slot()
    def refresh(self) -> None:
        self.model.set_rows(self.bridge.list_workers())
        self.refreshed.emit()
