from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class MeshPreview:
    vertices: np.ndarray
    faces: np.ndarray
    edges: np.ndarray
    bounds_min: np.ndarray
    bounds_max: np.ndarray

    @property
    def extent(self) -> float:
        size = self.bounds_max - self.bounds_min
        return float(np.max(size)) if size.size else 1.0

    @property
    def center(self) -> np.ndarray:
        return (self.bounds_min + self.bounds_max) * 0.5


def load_mesh_preview(path: Path, *, max_faces: int = 3500) -> MeshPreview:
    import trimesh

    loaded = trimesh.load(str(path), force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = [mesh for mesh in loaded.geometry.values() if isinstance(mesh, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("scene has no mesh geometry")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"unsupported mesh type {type(loaded).__name__}")
    mesh = loaded
    if len(mesh.faces) > max_faces:
        step = max(1, int(len(mesh.faces) / max_faces))
        faces = np.asarray(mesh.faces[::step], dtype=np.int64)
    else:
        faces = np.asarray(mesh.faces, dtype=np.int64)
    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    edges = _unique_edges(faces)
    if len(vertices):
        bounds_min = vertices.min(axis=0)
        bounds_max = vertices.max(axis=0)
    else:
        bounds_min = np.zeros(3)
        bounds_max = np.ones(3)
    return MeshPreview(
        vertices=vertices,
        faces=faces,
        edges=edges,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
    )


def _unique_edges(faces: np.ndarray) -> np.ndarray:
    if faces.size == 0:
        return np.zeros((0, 2), dtype=np.int64)
    pairs = np.vstack(
        [
            faces[:, [0, 1]],
            faces[:, [1, 2]],
            faces[:, [2, 0]],
        ]
    )
    pairs.sort(axis=1)
    return np.unique(pairs, axis=0)
