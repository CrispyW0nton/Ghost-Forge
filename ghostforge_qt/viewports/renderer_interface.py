from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PySide6 import QtWidgets

from ghostforge_qt.models.scene_model import TransformState


@dataclass(frozen=True)
class ViewportObject:
    object_id: str
    name: str
    path: Path
    transform: TransformState = TransformState()


class RendererInterface(Protocol):
    """Viewport renderer boundary.

    A null renderer ships first so the editor shell can mature while the real
    OpenGL/wgpu renderer is built behind this same contract.
    """

    def widget(self) -> QtWidgets.QWidget: ...
    def set_objects(self, objects: list[ViewportObject]) -> None: ...
    def set_selection_state(self, **state) -> None: ...  # type: ignore[no-untyped-def]
    def frame_all(self) -> None: ...
