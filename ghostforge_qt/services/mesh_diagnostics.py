from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class MeshTopologySummary:
    vertices: int = 0
    faces: int = 0
    edges: int = 0
    border_edges: int = 0
    non_manifold_edges: int = 0
    isolated_vertices: int = 0
    degenerate_faces: int = 0
    duplicate_vertices: int = 0
    connected_elements: int = 0
    watertight: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def warning_text(self) -> str:
        parts = []
        if self.non_manifold_edges:
            parts.append(f"{self.non_manifold_edges} non-manifold edge(s)")
        if self.border_edges:
            parts.append(f"{self.border_edges} border edge(s)")
        if self.isolated_vertices:
            parts.append(f"{self.isolated_vertices} isolated vertex/vertices")
        if self.degenerate_faces:
            parts.append(f"{self.degenerate_faces} degenerate face(s)")
        if self.duplicate_vertices:
            parts.append(f"{self.duplicate_vertices} duplicate vertex/vertices")
        return "; ".join(parts or ["None"])


def analyze_mesh(path: Path) -> MeshTopologySummary:
    import trimesh

    loaded = trimesh.load(str(path), force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = [mesh for mesh in loaded.geometry.values() if isinstance(mesh, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("scene has no mesh geometry")
        mesh = trimesh.util.concatenate(meshes)
    else:
        mesh = loaded
    if not isinstance(mesh, trimesh.Trimesh):
        raise ValueError(f"unsupported mesh type {type(mesh).__name__}")
    vertices = np.asarray(mesh.vertices)
    faces = np.asarray(mesh.faces)
    edge_to_faces: dict[tuple[int, int], list[int]] = defaultdict(list)
    degenerate = 0
    for fi, face in enumerate(faces):
        face_tuple = tuple(int(v) for v in face[:3])
        if len(set(face_tuple)) < 3:
            degenerate += 1
            continue
        for edge in (
            _edge(face_tuple[0], face_tuple[1]),
            _edge(face_tuple[1], face_tuple[2]),
            _edge(face_tuple[2], face_tuple[0]),
        ):
            edge_to_faces[edge].append(fi)
    used = {int(v) for face in faces for v in face[:3]}
    duplicate_vertices = _duplicate_vertex_count(vertices)
    return MeshTopologySummary(
        vertices=len(vertices),
        faces=len(faces),
        edges=len(edge_to_faces),
        border_edges=sum(1 for faces_for_edge in edge_to_faces.values() if len(faces_for_edge) == 1),
        non_manifold_edges=sum(1 for faces_for_edge in edge_to_faces.values() if len(faces_for_edge) > 2),
        isolated_vertices=len([i for i in range(len(vertices)) if i not in used]),
        degenerate_faces=degenerate,
        duplicate_vertices=duplicate_vertices,
        connected_elements=_connected_element_count(len(faces), edge_to_faces),
        watertight=bool(mesh.is_watertight),
        notes=(),
    )


def _edge(a: int, b: int) -> tuple[int, int]:
    return (a, b) if a <= b else (b, a)


def _duplicate_vertex_count(vertices: np.ndarray) -> int:
    seen: set[tuple[int, int, int]] = set()
    duplicates = 0
    for vertex in vertices:
        key = tuple(int(round(float(v) * 1_000_000.0)) for v in vertex[:3])
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)
    return duplicates


def _connected_element_count(face_count: int, edge_to_faces: dict[tuple[int, int], list[int]]) -> int:
    adjacency: dict[int, set[int]] = {i: set() for i in range(face_count)}
    for linked in edge_to_faces.values():
        for face_index in linked:
            adjacency.setdefault(face_index, set()).update(other for other in linked if other != face_index)
    remaining = set(range(face_count))
    count = 0
    while remaining:
        count += 1
        start = remaining.pop()
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            for other in adjacency.get(current, set()):
                if other in remaining:
                    remaining.remove(other)
                    queue.append(other)
    return count
