from __future__ import annotations

from pathlib import Path

from pydantic import Field

from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.types import FrozenModel, MeshInfo


class MeshInfoRequest(FrozenModel):
    mesh_path: Path


def run(
    spec: MeshInfoRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> MeshInfo:
    reporter and reporter("Loading mesh", 5)
    cancel and cancel.throw_if_cancelled()

    import trimesh

    loaded = trimesh.load(str(spec.mesh_path), force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = list(loaded.geometry.values())
        if not meshes:
            raise ValueError("No geometry in file")
        loaded = trimesh.util.concatenate(meshes)

    cancel and cancel.throw_if_cancelled()
    bounds = loaded.bounds.tolist() if loaded.bounds is not None else None
    size = None
    if bounds:
        size = [bounds[1][i] - bounds[0][i] for i in range(3)]

    reporter and reporter("Mesh info complete", 100)
    return MeshInfo(
        vertices=len(loaded.vertices),
        faces=len(loaded.faces),
        edges=len(loaded.edges) if hasattr(loaded, "edges") else None,
        watertight=bool(loaded.is_watertight),
        bounds=bounds,
        size=size,
        format=spec.mesh_path.suffix.lower(),
    )
