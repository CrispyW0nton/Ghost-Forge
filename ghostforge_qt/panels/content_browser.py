from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.services.project_service import ProjectService


class ContentBrowserPanel(QtWidgets.QWidget):
    fileActivated = QtCore.Signal(str)

    def __init__(self, project: ProjectService, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.model = QtWidgets.QFileSystemModel(self)
        self.model.setFilter(
            QtCore.QDir.Filter.AllDirs
            | QtCore.QDir.Filter.Files
            | QtCore.QDir.Filter.NoDotAndDotDot
        )
        self.model.setNameFilters(["*.glb", "*.gltf", "*.obj", "*.stl", "*.ply", "*.fbx", "*.png", "*.jpg", "*.jpeg", "*.json", "*.ghostscene"])
        self.model.setNameFilterDisables(False)

        self.root_label = QtWidgets.QLabel()
        self.root_label.setWordWrap(True)
        self.open_button = QtWidgets.QPushButton("Open Project Folder")
        self.open_button.clicked.connect(self.open_project_dialog)

        self.tree = QtWidgets.QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIsDecorated(True)
        self.tree.setSortingEnabled(True)
        self.tree.doubleClicked.connect(self._activate_index)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.root_label)
        layout.addWidget(self.open_button)
        layout.addWidget(self.tree)

        self.project.projectChanged.connect(self._set_project_state)
        self._set_project_root(self.project.root)

    def _set_project_state(self, state) -> None:  # type: ignore[no-untyped-def]
        self._set_project_root(state.root)

    def _set_project_root(self, root: Path) -> None:
        root = Path(root).resolve()
        idx = self.model.setRootPath(str(root))
        self.tree.setRootIndex(idx)
        self.root_label.setText(f"Project: {root}")
        for col in (1, 2, 3):
            self.tree.hideColumn(col)

    @QtCore.Slot()
    def open_project_dialog(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Ghost Forge Project", str(self.project.root))
        if path:
            self.project.set_root(Path(path))

    @QtCore.Slot(QtCore.QModelIndex)
    def _activate_index(self, index: QtCore.QModelIndex) -> None:
        path = self.model.filePath(index)
        if path and Path(path).is_file():
            self.fileActivated.emit(path)
