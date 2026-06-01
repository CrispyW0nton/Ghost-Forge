from __future__ import annotations

from PySide6 import QtWidgets

from ghostforge_qt.models.job_model import JobTableModel
from ghostforge_qt.services.job_controller import JobController


class JobPanel(QtWidgets.QWidget):
    def __init__(self, controller: JobController, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.controller = controller
        self.model = JobTableModel()
        self.view = QtWidgets.QTableView()
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.verticalHeader().hide()

        self.refresh_button = QtWidgets.QPushButton("Refresh Jobs")
        self.refresh_button.clicked.connect(self.controller.refresh)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.view)

        self.controller.jobsChanged.connect(self.model.set_jobs)
