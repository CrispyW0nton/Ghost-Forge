from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Mapping, Sequence

from PySide6 import QtCore, QtWidgets


class EditorStatusStrip(QtWidgets.QFrame):
    """Compact production status strip below the central viewport."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GhostForgeEditorBottomStrip")
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        self.workspace_label = _strip_label("Workspace", min_width=150)
        self.project_label = _strip_label("Project", min_width=180)
        self.scene_label = _strip_label("Scene", min_width=150)
        self.selection_label = _strip_label("Selection", min_width=180)
        self.renderer_label = _strip_label("Renderer", min_width=180)
        self.jobs_label = _strip_label("Jobs", min_width=150)

        layout.addWidget(self.workspace_label)
        layout.addWidget(_separator())
        layout.addWidget(self.project_label, 1)
        layout.addWidget(_separator())
        layout.addWidget(self.scene_label)
        layout.addWidget(_separator())
        layout.addWidget(self.selection_label, 1)
        layout.addWidget(_separator())
        layout.addWidget(self.renderer_label)
        layout.addWidget(_separator())
        layout.addWidget(self.jobs_label)

        self.set_workspace("Modeling")
        self.set_project_root(None)
        self.set_scene_counts(0, 0, 0)
        self.set_selection_summary("")
        self.set_renderer_summary({})
        self.set_jobs(())

    def set_workspace(self, label: str, status: str = "") -> None:
        status_text = f" [{status}]" if status else ""
        self.workspace_label.setText(f"Workspace: {label or '-'}{status_text}")

    def set_project_root(self, root: Path | str | None) -> None:
        if root is None:
            self.project_label.setText("Project: -")
            self.project_label.setToolTip("")
            return
        path = Path(root)
        self.project_label.setText(f"Project: {path.name or str(path)}")
        self.project_label.setToolTip(str(path))

    def set_scene_counts(self, objects: int, vertices: int, faces: int) -> None:
        self.scene_label.setText(f"Scene: {objects} obj | {vertices} verts | {faces} faces")

    def set_selection_summary(self, summary: str) -> None:
        self.selection_label.setText(f"Selection: {summary or 'none'}")

    def set_renderer_summary(self, diagnostics: Mapping[str, object] | None) -> None:
        payload = diagnostics or {}
        backend = str(payload.get("backend_id") or "renderer")
        display = str(payload.get("display_mode") or "-")
        camera = str(payload.get("camera_preset") or "-").replace("_", " ").title()
        projection = str(payload.get("projection_mode") or "-").replace("_", " ").title()
        self.renderer_label.setText(f"{backend}: {display} | {camera} | {projection}")

    def set_jobs(self, jobs: Sequence[object]) -> None:
        counts: Counter[str] = Counter()
        for job in jobs:
            status = getattr(job, "status", "")
            value = getattr(status, "value", status)
            counts[str(value or "unknown")] += 1
        if not jobs:
            self.jobs_label.setText("Jobs: idle")
            return
        active = counts.get("running", 0) + counts.get("pending", 0)
        failures = counts.get("failed", 0) + counts.get("cancelled", 0)
        done = counts.get("succeeded", 0)
        self.jobs_label.setText(f"Jobs: {active} active | {done} done | {failures} blocked")

    def apply_ghost_layout(self, layout) -> None:  # noqa: ANN001 - shared layout hook
        height = max(24, int(layout.spacing_value("bottomStripHeight", 32)))
        spacing = max(2, int(layout.spacing_value("toolbarSpacing", 4)))
        margin = max(2, int(layout.spacing_value("margin", 6)) // 2)
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        strip_layout = self.layout()
        if strip_layout is not None:
            strip_layout.setSpacing(spacing)
            strip_layout.setContentsMargins(margin, 2, margin, 2)


def _strip_label(text: str, *, min_width: int) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setMinimumWidth(min_width)
    label.setAlignment(QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft)
    label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _separator() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setObjectName("GhostForgeEditorBottomStripSeparator")
    line.setFrameShape(QtWidgets.QFrame.Shape.VLine)
    line.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
    line.setFixedWidth(1)
    return line
