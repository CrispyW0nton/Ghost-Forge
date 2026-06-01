from __future__ import annotations

from PySide6 import QtWidgets

from ghostforge_qt.models.scene_model import SceneTableModel


class SceneOutlinerPanel(QtWidgets.QWidget):
    def __init__(self, model: SceneTableModel, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self.view = QtWidgets.QTableView()
        self.view.setModel(model)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().hide()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.view)
