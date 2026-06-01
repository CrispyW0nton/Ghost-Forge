from __future__ import annotations

from dataclasses import dataclass, field


def normalize_edge(a: int, b: int) -> tuple[int, int]:
    return (int(a), int(b)) if int(a) <= int(b) else (int(b), int(a))


@dataclass
class MeshSelectionState:
    active_object_id: str | None = None
    mode: str = "object"
    selected_object_ids: set[str] = field(default_factory=set)
    selected_vertices: set[int] = field(default_factory=set)
    selected_edges: set[tuple[int, int]] = field(default_factory=set)
    selected_faces: set[int] = field(default_factory=set)
    selected_borders: set[int] = field(default_factory=set)
    selected_elements: set[int] = field(default_factory=set)
    status_message: str = ""

    def set_mode(self, mode: str) -> None:
        if mode != self.mode:
            self.mode = mode
            self.clear_subobjects()

    def clear_subobjects(self) -> None:
        self.selected_vertices.clear()
        self.selected_edges.clear()
        self.selected_faces.clear()
        self.selected_borders.clear()
        self.selected_elements.clear()

    def clear(self) -> None:
        self.selected_object_ids.clear()
        self.clear_subobjects()

    def counts(self) -> dict[str, int]:
        return {
            "objects": len(self.selected_object_ids),
            "vertices": len(self.selected_vertices),
            "edges": len(self.selected_edges),
            "borders": len(self.selected_borders),
            "faces": len(self.selected_faces),
            "elements": len(self.selected_elements),
        }
