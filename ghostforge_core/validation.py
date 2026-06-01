from __future__ import annotations

from pathlib import Path

from pydantic import Field

from .types import FrozenModel


class Issue(FrozenModel):
    code: str
    message: str
    location: str | None = None


class ValidationReport(FrozenModel):
    errors: list[Issue] = Field(default_factory=list)
    warnings: list[Issue] = Field(default_factory=list)
    info: list[Issue] = Field(default_factory=list)


def validate_mesh(path: Path | str) -> ValidationReport:
    errors: list[Issue] = []
    warnings: list[Issue] = []
    info: list[Issue] = []

    try:
        import trimesh

        mesh = trimesh.load(str(path), force="mesh", process=False)
        if isinstance(mesh, trimesh.Scene):
            meshes = [g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                return ValidationReport(errors=[Issue(code="mesh.empty", message="No geometry found")])
            mesh = trimesh.util.concatenate(meshes)

        vertex_count = len(mesh.vertices)
        face_count = len(mesh.faces)
        info.append(Issue(code="mesh.vertices", message=str(vertex_count)))
        info.append(Issue(code="mesh.triangles", message=str(face_count)))

        if vertex_count == 0 or face_count == 0:
            errors.append(Issue(code="mesh.empty", message="Mesh has no vertices or faces"))
        if not bool(mesh.is_watertight):
            warnings.append(Issue(code="mesh.not_watertight", message="Mesh is not watertight"))

        visual = getattr(mesh, "visual", None)
        has_uvs = bool(getattr(visual, "uv", None) is not None and len(visual.uv) > 0)
        if has_uvs:
            info.append(Issue(code="mesh.has_uvs", message="Mesh has UV coordinates"))
        else:
            warnings.append(Issue(code="mesh.missing_uvs", message="Mesh has no UV coordinates"))
    except Exception as exc:
        errors.append(Issue(code="mesh.unloadable", message=str(exc)))

    return ValidationReport(errors=errors, warnings=warnings, info=info)


def validate_glb(path: Path | str) -> ValidationReport:
    return validate_mesh(path)
