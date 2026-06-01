from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6 import QtCore


PROJECT_DIRS = ("assets", "imports", "outputs", "references", "scenes")


@dataclass(frozen=True)
class ProjectState:
    root: Path
    dirs: dict[str, Path]


class ProjectService(QtCore.QObject):
    projectChanged = QtCore.Signal(object)

    def __init__(self, root: Path, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._root = Path(root).resolve()
        self.ensure_structure()

    @property
    def root(self) -> Path:
        return self._root

    def state(self) -> ProjectState:
        return ProjectState(
            root=self._root,
            dirs={name: self._root / name for name in PROJECT_DIRS},
        )

    def set_root(self, root: Path) -> ProjectState:
        self._root = Path(root).resolve()
        self.ensure_structure()
        state = self.state()
        self.projectChanged.emit(state)
        return state

    def ensure_structure(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        for name in PROJECT_DIRS:
            (self._root / name).mkdir(parents=True, exist_ok=True)
