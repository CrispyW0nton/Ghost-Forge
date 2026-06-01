from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScenePathCommand:
    label: str
    object_id: str
    before_path: Path
    after_path: Path
    before_vertices: int | None = None
    before_faces: int | None = None
    before_watertight: bool | None = None
    after_vertices: int | None = None
    after_faces: int | None = None
    after_watertight: bool | None = None


@dataclass
class OperationHistory:
    limit: int = 100
    undo_stack: list[ScenePathCommand] = field(default_factory=list)
    redo_stack: list[ScenePathCommand] = field(default_factory=list)

    def record(self, command: ScenePathCommand) -> None:
        self.undo_stack.append(command)
        if len(self.undo_stack) > self.limit:
            del self.undo_stack[: len(self.undo_stack) - self.limit]
        self.redo_stack.clear()

    def clear(self) -> None:
        self.undo_stack.clear()
        self.redo_stack.clear()

    def undo(self) -> ScenePathCommand | None:
        if not self.undo_stack:
            return None
        command = self.undo_stack.pop()
        self.redo_stack.append(command)
        return command

    def redo(self) -> ScenePathCommand | None:
        if not self.redo_stack:
            return None
        command = self.redo_stack.pop()
        self.undo_stack.append(command)
        return command
