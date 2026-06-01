from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


VertexId = str
EdgeId = str
FaceId = str


@dataclass(frozen=True)
class EditableVertex:
    id: VertexId
    index: int
    position: tuple[float, float, float]
    edge_ids: tuple[EdgeId, ...] = ()
    face_ids: tuple[FaceId, ...] = ()


@dataclass(frozen=True)
class EditableEdge:
    id: EdgeId
    index: int
    vertex_ids: tuple[VertexId, VertexId]
    face_ids: tuple[FaceId, ...] = ()

    @property
    def is_boundary(self) -> bool:
        return len(self.face_ids) == 1

    @property
    def is_non_manifold(self) -> bool:
        return len(self.face_ids) > 2


@dataclass(frozen=True)
class EditableFace:
    id: FaceId
    index: int
    vertex_ids: tuple[VertexId, VertexId, VertexId]
    edge_ids: tuple[EdgeId, EdgeId, EdgeId]
    normal: tuple[float, float, float]


@dataclass(frozen=True)
class EditableMeshValidation:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        if self.warnings:
            return "warnings"
        return "passed"


@dataclass(frozen=True)
class EditableMeshSnapshot:
    vertices: dict[VertexId, EditableVertex]
    edges: dict[EdgeId, EditableEdge]
    faces: dict[FaceId, EditableFace]
    vertex_order: tuple[VertexId, ...]
    edge_order: tuple[EdgeId, ...]
    face_order: tuple[FaceId, ...]
    source_path: Path | None = None

    @classmethod
    def from_path(cls, path: Path) -> "EditableMeshSnapshot":
        import trimesh

        loaded = trimesh.load(str(path), force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            meshes = [mesh for mesh in loaded.geometry.values() if isinstance(mesh, trimesh.Trimesh)]
            if not meshes:
                raise ValueError("scene has no mesh geometry")
            loaded = trimesh.util.concatenate(meshes)
        if not isinstance(loaded, trimesh.Trimesh):
            raise ValueError(f"unsupported mesh type {type(loaded).__name__}")
        return cls.from_arrays(np.asarray(loaded.vertices), np.asarray(loaded.faces), source_path=path)

    @classmethod
    def from_arrays(
        cls,
        vertices: np.ndarray,
        faces: np.ndarray,
        *,
        source_path: Path | None = None,
    ) -> "EditableMeshSnapshot":
        vertex_order = tuple(_vertex_id(index) for index in range(len(vertices)))
        face_specs = [
            (_face_id(index), tuple(_vertex_id(int(v)) for v in face))
            for index, face in enumerate(np.asarray(faces, dtype=np.int64))
        ]
        positions = {
            vertex_id: _triple(vertices[index])
            for index, vertex_id in enumerate(vertex_order)
        }
        return _build_snapshot(
            positions=positions,
            face_specs=face_specs,
            source_path=source_path,
            previous_edges={},
        )

    @property
    def vertex_count(self) -> int:
        return len(self.vertex_order)

    @property
    def edge_count(self) -> int:
        return len(self.edge_order)

    @property
    def face_count(self) -> int:
        return len(self.face_order)

    def validate(self) -> EditableMeshValidation:
        errors: list[str] = []
        warnings: list[str] = []
        if not self.vertices:
            errors.append("mesh has no vertices")
        if not self.faces:
            errors.append("mesh has no faces")
        for face in self.faces.values():
            if len(set(face.vertex_ids)) != 3:
                errors.append(f"{face.id} has duplicate vertices")
            if any(vertex_id not in self.vertices for vertex_id in face.vertex_ids):
                errors.append(f"{face.id} references a missing vertex")
            if _normal_length(face.normal) <= 1e-9:
                warnings.append(f"{face.id} has zero area")
        boundary_edges = sum(1 for edge in self.edges.values() if edge.is_boundary)
        non_manifold_edges = sum(1 for edge in self.edges.values() if edge.is_non_manifold)
        isolated_vertices = sum(1 for vertex in self.vertices.values() if not vertex.face_ids)
        if boundary_edges:
            warnings.append(f"{boundary_edges} boundary edges")
        if non_manifold_edges:
            warnings.append(f"{non_manifold_edges} non-manifold edges")
        if isolated_vertices:
            warnings.append(f"{isolated_vertices} isolated vertices")
        return EditableMeshValidation(errors=tuple(errors), warnings=tuple(warnings))

    def face_neighbors(self, face_id: FaceId) -> set[FaceId]:
        face = self.faces[face_id]
        neighbors: set[FaceId] = set()
        for edge_id in face.edge_ids:
            edge = self.edges[edge_id]
            neighbors.update(item for item in edge.face_ids if item != face_id)
        return neighbors

    def connected_face_component(self, seed_face_id: FaceId) -> set[FaceId]:
        if seed_face_id not in self.faces:
            return set()
        visited = {seed_face_id}
        stack = [seed_face_id]
        while stack:
            face_id = stack.pop()
            for neighbor in self.face_neighbors(face_id):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
        return visited

    def face_ids_from_indices(self, indices: set[int]) -> set[FaceId]:
        return {
            self.face_order[index]
            for index in indices
            if 0 <= index < len(self.face_order)
        }

    def vertex_ids_from_indices(self, indices: set[int]) -> set[VertexId]:
        return {
            self.vertex_order[index]
            for index in indices
            if 0 <= index < len(self.vertex_order)
        }

    def delete_faces(self, face_ids: set[FaceId]) -> "MeshEditDelta":
        targets = {face_id for face_id in face_ids if face_id in self.faces}
        if not targets:
            raise ValueError("delete_faces requires at least one existing face id")
        if len(targets) == len(self.faces):
            raise ValueError("delete_faces would remove every face")
        previous_edges = {
            tuple(sorted(edge.vertex_ids)): edge.id
            for edge in self.edges.values()
        }
        remaining_specs = [
            (face_id, self.faces[face_id].vertex_ids)
            for face_id in self.face_order
            if face_id not in targets
        ]
        used_vertices = {vertex_id for _face_id, verts in remaining_specs for vertex_id in verts}
        positions = {
            vertex_id: self.vertices[vertex_id].position
            for vertex_id in self.vertex_order
            if vertex_id in used_vertices
        }
        after = _build_snapshot(
            positions=positions,
            face_specs=remaining_specs,
            source_path=self.source_path,
            previous_edges=previous_edges,
        )
        return MeshEditDelta(
            operation="delete_faces",
            before=self,
            after=after,
            removed_face_ids=tuple(sorted(targets)),
        )

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        vertex_index = {vertex_id: index for index, vertex_id in enumerate(self.vertex_order)}
        vertices = np.asarray([self.vertices[vertex_id].position for vertex_id in self.vertex_order], dtype=float)
        faces = np.asarray(
            [
                [vertex_index[vertex_id] for vertex_id in self.faces[face_id].vertex_ids]
                for face_id in self.face_order
            ],
            dtype=np.int64,
        )
        return vertices, faces

    def to_trimesh(self):  # type: ignore[no-untyped-def]
        import trimesh

        vertices, faces = self.to_arrays()
        return trimesh.Trimesh(vertices=vertices, faces=faces, process=False)


@dataclass(frozen=True)
class MeshEditDelta:
    operation: str
    before: EditableMeshSnapshot
    after: EditableMeshSnapshot
    removed_face_ids: tuple[FaceId, ...] = ()

    def undo(self) -> EditableMeshSnapshot:
        return self.before

    def redo(self) -> EditableMeshSnapshot:
        return self.after


@dataclass
class EditableMeshHistory:
    current: EditableMeshSnapshot
    undo_stack: list[MeshEditDelta] = field(default_factory=list)
    redo_stack: list[MeshEditDelta] = field(default_factory=list)

    def record(self, delta: MeshEditDelta) -> None:
        self.current = delta.after
        self.undo_stack.append(delta)
        self.redo_stack.clear()

    def delete_faces(self, face_ids: set[FaceId]) -> MeshEditDelta:
        delta = self.current.delete_faces(face_ids)
        self.record(delta)
        return delta

    def undo(self) -> MeshEditDelta | None:
        if not self.undo_stack:
            return None
        delta = self.undo_stack.pop()
        self.current = delta.undo()
        self.redo_stack.append(delta)
        return delta

    def redo(self) -> MeshEditDelta | None:
        if not self.redo_stack:
            return None
        delta = self.redo_stack.pop()
        self.current = delta.redo()
        self.undo_stack.append(delta)
        return delta


def _build_snapshot(
    *,
    positions: dict[VertexId, tuple[float, float, float]],
    face_specs: list[tuple[FaceId, tuple[VertexId, VertexId, VertexId]]],
    source_path: Path | None,
    previous_edges: dict[tuple[VertexId, VertexId], EdgeId],
) -> EditableMeshSnapshot:
    edge_ids_by_pair: dict[tuple[VertexId, VertexId], EdgeId] = {}
    edge_faces: dict[EdgeId, list[FaceId]] = {}
    face_edges: dict[FaceId, tuple[EdgeId, EdgeId, EdgeId]] = {}
    edge_order: list[EdgeId] = []
    next_edge_index = 0

    for face_id, vertex_ids in face_specs:
        edges_for_face: list[EdgeId] = []
        for pair in (
            (vertex_ids[0], vertex_ids[1]),
            (vertex_ids[1], vertex_ids[2]),
            (vertex_ids[2], vertex_ids[0]),
        ):
            key = tuple(sorted(pair))
            edge_id = edge_ids_by_pair.get(key)
            if edge_id is None:
                edge_id = previous_edges.get(key) or _edge_id(next_edge_index)
                while edge_id in edge_order:
                    next_edge_index += 1
                    edge_id = _edge_id(next_edge_index)
                edge_ids_by_pair[key] = edge_id
                edge_order.append(edge_id)
                next_edge_index += 1
            edge_faces.setdefault(edge_id, []).append(face_id)
            edges_for_face.append(edge_id)
        face_edges[face_id] = (edges_for_face[0], edges_for_face[1], edges_for_face[2])

    vertex_edges: dict[VertexId, set[EdgeId]] = {vertex_id: set() for vertex_id in positions}
    vertex_faces: dict[VertexId, set[FaceId]] = {vertex_id: set() for vertex_id in positions}
    for pair, edge_id in edge_ids_by_pair.items():
        for vertex_id in pair:
            vertex_edges.setdefault(vertex_id, set()).add(edge_id)
    for face_id, vertex_ids in face_specs:
        for vertex_id in vertex_ids:
            vertex_faces.setdefault(vertex_id, set()).add(face_id)

    vertex_order = tuple(positions.keys())
    vertices = {
        vertex_id: EditableVertex(
            id=vertex_id,
            index=index,
            position=positions[vertex_id],
            edge_ids=tuple(sorted(vertex_edges.get(vertex_id, set()))),
            face_ids=tuple(sorted(vertex_faces.get(vertex_id, set()))),
        )
        for index, vertex_id in enumerate(vertex_order)
    }
    edges = {
        edge_id: EditableEdge(
            id=edge_id,
            index=index,
            vertex_ids=_edge_pair_for_id(edge_ids_by_pair, edge_id),
            face_ids=tuple(edge_faces.get(edge_id, ())),
        )
        for index, edge_id in enumerate(edge_order)
    }
    faces = {
        face_id: EditableFace(
            id=face_id,
            index=index,
            vertex_ids=vertex_ids,
            edge_ids=face_edges[face_id],
            normal=_face_normal(positions, vertex_ids),
        )
        for index, (face_id, vertex_ids) in enumerate(face_specs)
    }
    return EditableMeshSnapshot(
        vertices=vertices,
        edges=edges,
        faces=faces,
        vertex_order=vertex_order,
        edge_order=tuple(edge_order),
        face_order=tuple(face_id for face_id, _vertices in face_specs),
        source_path=source_path,
    )


def _edge_pair_for_id(edge_ids_by_pair: dict[tuple[VertexId, VertexId], EdgeId], edge_id: EdgeId) -> tuple[VertexId, VertexId]:
    for pair, candidate in edge_ids_by_pair.items():
        if candidate == edge_id:
            return pair
    raise KeyError(edge_id)


def _face_normal(
    positions: dict[VertexId, tuple[float, float, float]],
    vertex_ids: tuple[VertexId, VertexId, VertexId],
) -> tuple[float, float, float]:
    a, b, c = (np.asarray(positions[vertex_id], dtype=float) for vertex_id in vertex_ids)
    normal = np.cross(b - a, c - a)
    length = float(np.linalg.norm(normal))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0)
    normal = normal / length
    return _triple(normal)


def _normal_length(normal: tuple[float, float, float]) -> float:
    return float(np.linalg.norm(np.asarray(normal, dtype=float)))


def _triple(values) -> tuple[float, float, float]:  # type: ignore[no-untyped-def]
    return (float(values[0]), float(values[1]), float(values[2]))


def _vertex_id(index: int) -> VertexId:
    return f"v_{index:06d}"


def _edge_id(index: int) -> EdgeId:
    return f"e_{index:06d}"


def _face_id(index: int) -> FaceId:
    return f"f_{index:06d}"
