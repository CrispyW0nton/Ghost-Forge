from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .renderer_interface import ViewportObject


class NullRenderer(QtCore.QObject):
    """Placeholder renderer that makes the Qt shell useful before GPU work."""

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._label = QtWidgets.QLabel()
        self._label.setObjectName("ghostforgeViewportNullRenderer")
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(420, 320)
        self._label.setText("Ghost Forge Viewport\nImport a mesh to begin")
        self._label.setStyleSheet(
            """
            QLabel#ghostforgeViewportNullRenderer {
                background: #0b0f12;
                color: #9bdc9b;
                border: 1px solid #1f3d2a;
                font-size: 18px;
            }
            """
        )

    def widget(self) -> QtWidgets.QWidget:
        return self._label

    def set_objects(self, objects: list[ViewportObject]) -> None:
        if not objects:
            self._label.setText("Ghost Forge Viewport\nImport a mesh to begin")
            return
        lines = ["Ghost Forge Viewport", "", "Scene Objects:"]
        lines.extend(f"- {obj.name}" for obj in objects[:12])
        if len(objects) > 12:
            lines.append(f"... {len(objects) - 12} more")
        self._label.setText("\n".join(lines))

    def frame_all(self) -> None:
        # Real renderers will update the camera; the null renderer is static.
        return None
