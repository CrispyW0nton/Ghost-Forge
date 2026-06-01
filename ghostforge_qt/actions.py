from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable

from PySide6 import QtGui, QtWidgets


@dataclass(frozen=True)
class ActionSpec:
    action_id: str
    text: str
    shortcut: str | None = None
    status_tip: str = ""
    checkable: bool = False


DEFAULT_ACTIONS: tuple[ActionSpec, ...] = (
    ActionSpec("file.new_scene", "New Scene", "Ctrl+N", "Clear the current scene document."),
    ActionSpec("file.open_project", "Open Project...", "Ctrl+O", "Open a Ghost Forge project folder."),
    ActionSpec("file.open_scene", "Open Scene...", "Ctrl+Shift+O", "Open a Ghost Forge scene document."),
    ActionSpec("file.import_mesh", "Import Mesh...", "Ctrl+I", "Import a mesh into the scene."),
    ActionSpec("file.save_scene", "Save Scene", "Ctrl+S", "Save the active Ghost Forge scene."),
    ActionSpec("file.save_scene_as", "Save Scene As...", "Ctrl+Shift+S", "Save the active scene to a new file."),
    ActionSpec("file.quit", "Quit", "Ctrl+Q", "Close Ghost Forge."),
    ActionSpec("edit.undo", "Undo", "Ctrl+Z", "Undo the last mesh operation."),
    ActionSpec("edit.redo", "Redo", "Ctrl+Y", "Redo the last undone mesh operation."),
    ActionSpec("view.refresh_runtime", "Refresh Runtime", "F5", "Refresh workers, jobs, engines, and runtime probes."),
    ActionSpec("view.frame_all", "Frame All", "F", "Frame all scene objects in the viewport."),
    ActionSpec("asset.unwrap", "Unwrap UVs", "Ctrl+U", "Submit a UV unwrap job for the selected asset."),
    ActionSpec("asset.texture", "Generate Texture", "Ctrl+T", "Submit a texture generation job for the selected asset."),
    ActionSpec("asset.audit", "Audit Asset", "Ctrl+Shift+A", "Run the game-readiness audit."),
    ActionSpec("asset.export_bridge", "Create Engine Bridge", "Ctrl+E", "Create a Unity or Unreal export bridge package."),
    ActionSpec("tools.worker_models", "Worker Models", None, "Show worker and model runtime status."),
    ActionSpec("help.about", "About Ghost Forge", None, "Show Ghost Forge version information."),
)


class ActionRegistry:
    """Ghost Rigger-style QAction registry for command routing."""

    def __init__(self, owner: QtWidgets.QWidget) -> None:
        self.owner = owner
        self._actions: OrderedDict[str, QtGui.QAction] = OrderedDict()

    def register(
        self,
        spec: ActionSpec,
        callback: Callable[[], None] | None = None,
    ) -> QtGui.QAction:
        action = QtGui.QAction(spec.text, self.owner)
        action.setObjectName(spec.action_id)
        if spec.shortcut:
            action.setShortcut(QtGui.QKeySequence(spec.shortcut))
        if spec.status_tip:
            action.setStatusTip(spec.status_tip)
        action.setCheckable(spec.checkable)
        if callback is not None:
            action.triggered.connect(callback)
        self._actions[spec.action_id] = action
        return action

    def get(self, action_id: str) -> QtGui.QAction:
        return self._actions[action_id]

    def all(self) -> list[QtGui.QAction]:
        return list(self._actions.values())

    def ids(self) -> list[str]:
        return list(self._actions.keys())
