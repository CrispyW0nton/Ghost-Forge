from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class PlaceholderPanel(QtWidgets.QWidget):
    """Named landing panel for upcoming editor surfaces."""

    def __init__(self, title: str, body: str, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        label = QtWidgets.QLabel(f"{title}\n\n{body}")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft)
        label.setWordWrap(True)
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(label)
