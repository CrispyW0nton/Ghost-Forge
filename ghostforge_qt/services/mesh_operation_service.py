from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ghostforge_core.operations import mesh_info as mesh_info_op
from ghostforge_core.types import MeshInfo


@dataclass(frozen=True)
class MeshOperationOutput:
    label: str
    path: Path
    info: MeshInfo


@dataclass(frozen=True)
class MeshOperationSelection:
    """Sub-object selection snapshot passed from the editor into CPU tools."""

    mode: str = "object"
    vertices: set[int] = field(default_factory=set)
    edges: set[tuple[int, int]] = field(default_factory=set)
    faces: set[int] = field(default_factory=set)
    borders: set[int] = field(default_factory=set)
    elements: set[int] = field(default_factory=set)

    @property
    def has_subobjects(self) -> bool:
        return bool(self.vertices or self.edges or self.faces or self.borders or self.elements)


class MeshOperationService:
    """Small CPU mesh operation bridge for early Qt modeling tools."""

    SUPPORTED = {
        "apply_material",
        "delete",
        "recalculate_normals",
        "flip_normals",
        "remove_isolated",
        "decimate",
        "normalize_scale",
        "recenter",
        "smooth_laplacian",
        "subdivide",
        "weld",
    }

    def __init__(self, output_root: Path) -> None:
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)

    def is_supported(self, name: str) -> bool:
        return name in self.SUPPORTED

    def apply(
        self,
        name: str,
        input_path: Path,
        *,
        target_ratio: float = 0.5,
        weld_tolerance: float = 1e-6,
        smooth_iterations: int = 3,
        subdivide_iterations: int = 1,
        recenter_pivot: str = "bounds_center",
        selection: MeshOperationSelection | None = None,
    ) -> MeshOperationOutput:
        import trimesh

        if not self.is_supported(name):
            raise ValueError(f"{name!r} is staged but not implemented yet")
        loaded = trimesh.load(str(input_path), force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            meshes = [mesh for mesh in loaded.geometry.values() if isinstance(mesh, trimesh.Trimesh)]
            if not meshes:
                raise ValueError("scene has no mesh geometry")
            mesh = trimesh.util.concatenate(meshes)
        else:
            mesh = loaded
        if not isinstance(mesh, trimesh.Trimesh):
            raise ValueError(f"unsupported mesh type {type(mesh).__name__}")

        selection = selection or MeshOperationSelection()

        if name == "recalculate_normals":
            mesh.fix_normals()
        elif name == "flip_normals":
            face_indices = _selected_face_indices(mesh, selection)
            if face_indices:
                faces = mesh.faces.copy()
                target = sorted(face_indices)
                faces[target] = faces[target][:, ::-1]
                mesh = trimesh.Trimesh(vertices=mesh.vertices.copy(), faces=faces, process=False)
            else:
                mesh.invert()
        elif name == "remove_isolated":
            mesh.remove_unreferenced_vertices()
            mesh.merge_vertices(merge_tex=False, merge_norm=False)
        elif name == "delete":
            face_indices = _selected_face_indices(mesh, selection)
            if not face_indices:
                raise ValueError("Select vertices, edges, faces, or elements before deleting sub-objects.")
            keep = [index not in face_indices for index in range(len(mesh.faces))]
            if not any(keep):
                raise ValueError("Delete would remove every face from the mesh.")
            mesh.update_faces(keep)
            mesh.remove_unreferenced_vertices()
            mesh.fix_normals()
        elif name == "normalize_scale":
            largest = float(mesh.extents.max()) if mesh.extents is not None and len(mesh.extents) else 0.0
            if largest <= 0.0:
                raise ValueError("cannot normalize a zero-volume mesh")
            mesh.apply_scale(1.0 / largest)
        elif name == "recenter":
            if recenter_pivot == "centroid":
                offset = -mesh.centroid
            elif recenter_pivot == "bottom":
                center = mesh.bounds.mean(axis=0)
                offset = -center
                offset[1] = -mesh.bounds[0][1]
            elif recenter_pivot == "origin":
                offset = (0.0, 0.0, 0.0)
            else:
                offset = -mesh.bounds.mean(axis=0)
            mesh.apply_translation(offset)
        elif name == "weld":
            vertices = _selected_vertices_for_weld(mesh, selection)
            if len(vertices) >= 2:
                mesh = _weld_selected_vertices(mesh, vertices)
            else:
                digits = max(0, min(12, int(abs(__import__("math").log10(max(weld_tolerance, 1e-12))))))
                mesh.merge_vertices(digits_vertex=digits, merge_tex=False, merge_norm=False)
        elif name == "smooth_laplacian":
            trimesh.smoothing.filter_laplacian(
                mesh,
                lamb=0.5,
                iterations=max(1, min(200, int(smooth_iterations))),
            )
        elif name == "subdivide":
            iterations = max(1, min(4, int(subdivide_iterations)))
            for _ in range(iterations):
                verts, faces = trimesh.remesh.subdivide(mesh.vertices, mesh.faces)
                mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        elif name == "apply_material":
            mesh.visual.face_colors = [95, 180, 120, 255]
        elif name == "decimate":
            target_faces = max(4, int(len(mesh.faces) * target_ratio))
            if target_faces < len(mesh.faces):
                if hasattr(mesh, "simplify_quadric_decimation"):
                    mesh = mesh.simplify_quadric_decimation(target_faces)
                elif hasattr(mesh, "simplify_quadratic_decimation"):
                    mesh = mesh.simplify_quadratic_decimation(target_faces)
                else:
                    raise ValueError("no decimation backend available")

        output_path = self._output_path(input_path, name)
        mesh.export(str(output_path))
        info = mesh_info_op.run(mesh_info_op.MeshInfoRequest(mesh_path=output_path))
        return MeshOperationOutput(label=name, path=output_path, info=info)

    def _output_path(self, input_path: Path, name: str) -> Path:
        stem = input_path.stem
        suffix = ".glb"
        base = self.output_root / f"{stem}_{name}{suffix}"
        if not base.exists():
            return base
        index = 2
        while True:
            candidate = self.output_root / f"{stem}_{name}_{index}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


def _selected_vertices_for_weld(mesh, selection: MeshOperationSelection) -> set[int]:  # type: ignore[no-untyped-def]
    vertices = {int(v) for v in selection.vertices if 0 <= int(v) < len(mesh.vertices)}
    for edge in selection.edges:
        a, b = _resolve_edge(mesh, edge)
        if a is not None and b is not None:
            vertices.update((a, b))
    return vertices


def _selected_face_indices(mesh, selection: MeshOperationSelection) -> set[int]:  # type: ignore[no-untyped-def]
    faces = {int(index) for index in selection.faces if 0 <= int(index) < len(mesh.faces)}
    for seed in selection.elements:
        seed_index = int(seed)
        if 0 <= seed_index < len(mesh.faces):
            faces.update(_face_component(mesh, seed_index))
    for edge in selection.edges:
        a, b = _resolve_edge(mesh, edge)
        if a is not None and b is not None:
            faces.update(_faces_using_edge(mesh, a, b))
    for edge_index in selection.borders:
        edge = _edge_by_index(mesh, int(edge_index))
        if edge is not None:
            faces.update(_faces_using_edge(mesh, edge[0], edge[1]))
    if selection.mode == "vertex" or selection.vertices:
        vertices = {int(v) for v in selection.vertices if 0 <= int(v) < len(mesh.vertices)}
        if vertices:
            face_array = mesh.faces
            for index, face in enumerate(face_array):
                if any(int(vertex) in vertices for vertex in face):
                    faces.add(index)
    return faces


def _resolve_edge(mesh, edge: tuple[int, int]) -> tuple[int | None, int | None]:  # type: ignore[no-untyped-def]
    a, b = int(edge[0]), int(edge[1])
    if a >= 0 and b >= 0 and a < len(mesh.vertices) and b < len(mesh.vertices):
        return min(a, b), max(a, b)
    if a < 0:
        resolved = _edge_by_index(mesh, b)
        if resolved is not None:
            return resolved
    return None, None


def _edge_by_index(mesh, edge_index: int) -> tuple[int, int] | None:  # type: ignore[no-untyped-def]
    edges = getattr(mesh, "edges_unique", None)
    if edges is None:
        edges = getattr(mesh, "edges", None)
    if edges is None or edge_index < 0 or edge_index >= len(edges):
        return None
    a, b = edges[edge_index]
    return min(int(a), int(b)), max(int(a), int(b))


def _faces_using_edge(mesh, a: int, b: int) -> set[int]:  # type: ignore[no-untyped-def]
    target = {int(a), int(b)}
    return {
        index
        for index, face in enumerate(mesh.faces)
        if target.issubset({int(face[0]), int(face[1]), int(face[2])})
    }


def _face_component(mesh, seed_face: int) -> set[int]:  # type: ignore[no-untyped-def]
    if seed_face < 0 or seed_face >= len(mesh.faces):
        return set()
    edge_to_faces: dict[tuple[int, int], list[int]] = {}
    for index, face in enumerate(mesh.faces):
        a, b, c = [int(value) for value in face]
        for edge in ((a, b), (b, c), (c, a)):
            edge_to_faces.setdefault(tuple(sorted(edge)), []).append(index)
    visited = {seed_face}
    stack = [seed_face]
    while stack:
        face_index = stack.pop()
        face = [int(value) for value in mesh.faces[face_index]]
        for edge in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            for neighbor in edge_to_faces.get(tuple(sorted(edge)), []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
    return visited


def _weld_selected_vertices(mesh, vertices: set[int]):  # type: ignore[no-untyped-def]
    import numpy as np
    import trimesh

    valid = sorted(v for v in vertices if 0 <= v < len(mesh.vertices))
    if len(valid) < 2:
        return mesh
    target = valid[0]
    vertices_array = np.asarray(mesh.vertices, dtype=float).copy()
    centroid = vertices_array[valid].mean(axis=0)
    vertices_array[target] = centroid
    remap = {vertex: target for vertex in valid[1:]}
    faces = np.asarray(mesh.faces, dtype=np.int64).copy()
    for source, destination in remap.items():
        faces[faces == source] = destination
    keep = np.array([len(set(int(v) for v in face)) == 3 for face in faces], dtype=bool)
    if not bool(keep.any()):
        raise ValueError("Weld collapsed every selected face.")
    welded = trimesh.Trimesh(vertices=vertices_array, faces=faces[keep], process=False)
    welded.remove_unreferenced_vertices()
    welded.fix_normals()
    return welded
