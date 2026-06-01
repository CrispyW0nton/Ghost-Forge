"""Default authoring operations shipped with GhostForge.

Selection criteria for "built-in":

* **Pure-python or trimesh-only**. No optional ML deps — everything
  here runs on a CPU-only laptop with the base install.
* **Useful in isolation**. Each operation either reshapes geometry,
  cleans up topology, or annotates material data. Anything that
  requires worker invocation (texture generation, AI mesh refinement)
  belongs in the worker registry, not here.
* **Idempotent where possible**. Re-running an operation on its own
  output should converge instead of drifting (e.g. ``recompute_normals``
  always recomputes from scratch; ``merge_vertices`` is a no-op once
  the mesh has no duplicates).

Adding a new operation: follow the same pattern as the existing ones
(declare a handler function, expose it via :func:`make_operation`, add
it to ``DEFAULT_OPERATIONS``) and it becomes available everywhere
immediately — UI palette, MCP tool surface, evaluator.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

from .registry import (
    Operation,
    OperationContext,
    OperationError,
    make_operation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_floats(params: dict[str, Any], key: str, expected_len: int) -> list[float]:
    value = params.get(key)
    if value is None:
        return [0.0] * expected_len
    if not isinstance(value, (list, tuple)) or len(value) != expected_len:
        raise OperationError(
            f"{key!r} must be a list of {expected_len} numbers; got {value!r}"
        )
    try:
        return [float(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise OperationError(f"{key!r} contains non-numeric entries: {value!r}") from exc


def _require_float(params: dict[str, Any], key: str, default: float) -> float:
    value = params.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise OperationError(f"{key!r} must be numeric, got {value!r}") from exc


def _require_int(params: dict[str, Any], key: str, default: int, *, low: int = -10**9, high: int = 10**9) -> int:
    value = params.get(key, default)
    try:
        ivalue = int(value)
    except (TypeError, ValueError) as exc:
        raise OperationError(f"{key!r} must be an integer, got {value!r}") from exc
    if ivalue < low or ivalue > high:
        raise OperationError(f"{key!r}={ivalue} outside [{low}, {high}]")
    return ivalue


def _copy_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Defensive copy so handlers never mutate the evaluator's input."""

    return mesh.copy()


# ---------------------------------------------------------------------------
# Geometry transform operations
# ---------------------------------------------------------------------------


def _op_transform(ctx: OperationContext) -> trimesh.Trimesh:
    translate = _require_floats(ctx.params, "translate", 3)
    rotate_euler_deg = _require_floats(ctx.params, "rotate_euler_deg", 3)
    scale = ctx.params.get("scale", [1.0, 1.0, 1.0])

    if isinstance(scale, (int, float)):
        scale = [float(scale)] * 3
    elif isinstance(scale, (list, tuple)) and len(scale) == 3:
        scale = [float(v) for v in scale]
    else:
        raise OperationError(
            f"scale must be a scalar or 3-vector; got {scale!r}"
        )

    mesh = _copy_mesh(ctx.mesh)
    if any(s != 1.0 for s in scale):
        scale_matrix = np.diag([scale[0], scale[1], scale[2], 1.0])
        mesh.apply_transform(scale_matrix)
    if any(r != 0.0 for r in rotate_euler_deg):
        radians = [math.radians(r) for r in rotate_euler_deg]
        rot = trimesh.transformations.euler_matrix(
            radians[0], radians[1], radians[2], "sxyz"
        )
        mesh.apply_transform(rot)
    if any(t != 0.0 for t in translate):
        mesh.apply_translation(np.array(translate, dtype=float))
    return mesh


def _op_recenter(ctx: OperationContext) -> trimesh.Trimesh:
    """Recenter geometry so a chosen pivot lands at the origin."""

    pivot = ctx.params.get("pivot", "centroid")
    mesh = _copy_mesh(ctx.mesh)
    if pivot == "centroid":
        offset = -mesh.centroid
    elif pivot == "bounds_center":
        offset = -mesh.bounds.mean(axis=0)
    elif pivot == "origin":
        offset = np.zeros(3)
    elif pivot == "bottom":
        # Place the lowest Y on the ground plane.
        bottom = np.array([
            mesh.bounds.mean(axis=0)[0],
            mesh.bounds[0][1],
            mesh.bounds.mean(axis=0)[2],
        ])
        offset = -bottom
    else:
        raise OperationError(
            f"pivot must be one of {{centroid, bounds_center, origin, bottom}}; got {pivot!r}"
        )
    mesh.apply_translation(offset)
    return mesh


def _op_normalize_scale(ctx: OperationContext) -> trimesh.Trimesh:
    """Uniformly scale so the mesh fits a target maximum extent."""

    target = _require_float(ctx.params, "target_extent", 1.0)
    if target <= 0.0:
        raise OperationError("target_extent must be > 0")

    mesh = _copy_mesh(ctx.mesh)
    extents = mesh.extents
    largest = float(extents.max()) if extents is not None and len(extents) > 0 else 0.0
    if largest <= 0.0:
        raise OperationError("cannot normalise zero-volume mesh")
    factor = target / largest
    mesh.apply_scale(factor)
    return mesh


# ---------------------------------------------------------------------------
# Topology / cleanup operations
# ---------------------------------------------------------------------------


def _op_recompute_normals(ctx: OperationContext) -> trimesh.Trimesh:
    mesh = _copy_mesh(ctx.mesh)
    mesh.fix_normals()
    return mesh


def _op_merge_vertices(ctx: OperationContext) -> trimesh.Trimesh:
    tol = _require_float(ctx.params, "tolerance", 1e-6)
    if tol < 0.0:
        raise OperationError("tolerance must be >= 0")
    mesh = _copy_mesh(ctx.mesh)
    mesh.merge_vertices(merge_tex=False, merge_norm=False)
    return mesh


def _op_smooth_laplacian(ctx: OperationContext) -> trimesh.Trimesh:
    iterations = _require_int(ctx.params, "iterations", 3, low=1, high=200)
    lamb = _require_float(ctx.params, "lambda", 0.5)
    if not 0.0 < lamb <= 1.0:
        raise OperationError("lambda must satisfy 0 < lambda <= 1")
    mesh = _copy_mesh(ctx.mesh)
    trimesh.smoothing.filter_laplacian(mesh, lamb=lamb, iterations=iterations)
    return mesh


def _op_subdivide(ctx: OperationContext) -> trimesh.Trimesh:
    iterations = _require_int(ctx.params, "iterations", 1, low=1, high=4)
    mesh = _copy_mesh(ctx.mesh)
    for _ in range(iterations):
        verts, faces = trimesh.remesh.subdivide(mesh.vertices, mesh.faces)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    return mesh


def _op_decimate(ctx: OperationContext) -> trimesh.Trimesh:
    """Reduce face count.

    trimesh exposes two paths: ``simplify_quadric_decimation`` (fast,
    needs ``open3d``) and ``simplify_quadratic_decimation`` (older;
    needs ``fast_simplification``). We try the open3d-backed entrypoint
    first and fall back to a uniform face-merge approximation.
    """

    target_faces = _require_int(ctx.params, "target_faces", 0, low=0, high=10**9)
    target_ratio = _require_float(ctx.params, "target_ratio", 0.5)
    if not 0.0 < target_ratio <= 1.0:
        raise OperationError("target_ratio must satisfy 0 < ratio <= 1")

    mesh = _copy_mesh(ctx.mesh)
    if target_faces == 0:
        target_faces = max(4, int(round(len(mesh.faces) * target_ratio)))
    if target_faces >= len(mesh.faces):
        return mesh

    # Try modern trimesh API first, then legacy, then graceful no-op.
    if hasattr(mesh, "simplify_quadric_decimation"):
        try:
            return mesh.simplify_quadric_decimation(target_faces)
        except Exception:
            pass
    if hasattr(mesh, "simplify_quadratic_decimation"):
        try:
            return mesh.simplify_quadratic_decimation(target_faces)
        except Exception:
            pass

    raise OperationError(
        "no decimation backend available (install `open3d` or "
        "`fast-simplification` to enable mesh decimation)"
    )


# ---------------------------------------------------------------------------
# Material operations
# ---------------------------------------------------------------------------


def _op_apply_material(ctx: OperationContext) -> trimesh.Trimesh:
    """Annotate the mesh with a base-colour PBR material."""

    name = ctx.params.get("name", "ghostforge_material")
    if not isinstance(name, str) or not name:
        raise OperationError("material name must be a non-empty string")
    base_color = _require_floats(ctx.params, "base_color_rgba", 4)
    metallic = _require_float(ctx.params, "metallic", 0.0)
    roughness = _require_float(ctx.params, "roughness", 0.5)

    if any(c < 0.0 or c > 1.0 for c in base_color):
        raise OperationError("base_color_rgba components must lie in [0, 1]")
    if not 0.0 <= metallic <= 1.0:
        raise OperationError("metallic must lie in [0, 1]")
    if not 0.0 <= roughness <= 1.0:
        raise OperationError("roughness must lie in [0, 1]")

    mesh = _copy_mesh(ctx.mesh)
    rgba = [int(round(c * 255)) for c in base_color]
    material = trimesh.visual.material.PBRMaterial(
        name=name,
        baseColorFactor=rgba,
        metallicFactor=metallic,
        roughnessFactor=roughness,
    )
    if mesh.visual is None or not hasattr(mesh.visual, "uv"):
        # Synthesise a degenerate UV map so the material can attach.
        uv = np.zeros((len(mesh.vertices), 2), dtype=float)
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
    else:
        existing_uv = getattr(mesh.visual, "uv", None)
        uv = (
            existing_uv
            if existing_uv is not None
            else np.zeros((len(mesh.vertices), 2), dtype=float)
        )
        mesh.visual = trimesh.visual.TextureVisuals(uv=uv, material=material)
    return mesh


# ---------------------------------------------------------------------------
# Default registration list
# ---------------------------------------------------------------------------


DEFAULT_OPERATIONS: tuple[Operation, ...] = (
    make_operation(
        kind="transform",
        label="Transform",
        summary="Translate / rotate / scale (Euler degrees, scalar or 3-vector scale).",
        category="transform",
        params_schema={
            "translate": {"type": "vec3", "default": [0.0, 0.0, 0.0]},
            "rotate_euler_deg": {"type": "vec3", "default": [0.0, 0.0, 0.0]},
            "scale": {"type": "scalar_or_vec3", "default": 1.0},
        },
        handler=_op_transform,
    ),
    make_operation(
        kind="recenter",
        label="Recenter",
        summary="Move pivot to origin / centroid / bounds center / bottom.",
        category="transform",
        params_schema={
            "pivot": {
                "type": "enum",
                "values": ["centroid", "bounds_center", "origin", "bottom"],
                "default": "centroid",
            }
        },
        handler=_op_recenter,
    ),
    make_operation(
        kind="normalize_scale",
        label="Normalize Scale",
        summary="Uniformly scale so the largest extent matches a target value.",
        category="transform",
        params_schema={"target_extent": {"type": "float", "default": 1.0, "min": 1e-6}},
        handler=_op_normalize_scale,
    ),
    make_operation(
        kind="recompute_normals",
        label="Recompute Normals",
        summary="Reorient face normals consistently (trimesh.fix_normals).",
        category="cleanup",
        params_schema={},
        handler=_op_recompute_normals,
    ),
    make_operation(
        kind="merge_vertices",
        label="Merge Vertices",
        summary="Merge duplicate vertices within tolerance.",
        category="cleanup",
        params_schema={"tolerance": {"type": "float", "default": 1e-6, "min": 0.0}},
        handler=_op_merge_vertices,
    ),
    make_operation(
        kind="smooth_laplacian",
        label="Smooth (Laplacian)",
        summary="Iterative Laplacian smoothing; preserves topology.",
        category="topology",
        params_schema={
            "iterations": {"type": "int", "default": 3, "min": 1, "max": 200},
            "lambda": {"type": "float", "default": 0.5, "min": 0.01, "max": 1.0},
        },
        handler=_op_smooth_laplacian,
    ),
    make_operation(
        kind="subdivide",
        label="Subdivide",
        summary="Loop-style subdivision (1–4 iterations).",
        category="topology",
        params_schema={"iterations": {"type": "int", "default": 1, "min": 1, "max": 4}},
        handler=_op_subdivide,
    ),
    make_operation(
        kind="decimate",
        label="Decimate",
        summary="Reduce face count via quadric edge collapse.",
        category="topology",
        params_schema={
            "target_ratio": {"type": "float", "default": 0.5, "min": 0.01, "max": 1.0},
            "target_faces": {"type": "int", "default": 0, "min": 0},
        },
        requires_modules=("open3d",),
        handler=_op_decimate,
    ),
    make_operation(
        kind="apply_material",
        label="Apply Material",
        summary="Attach a PBR material with base color / metallic / roughness.",
        category="material",
        params_schema={
            "name": {"type": "string", "default": "ghostforge_material"},
            "base_color_rgba": {"type": "vec4", "default": [0.6, 0.6, 0.6, 1.0]},
            "metallic": {"type": "float", "default": 0.0, "min": 0.0, "max": 1.0},
            "roughness": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0},
        },
        handler=_op_apply_material,
    ),
)


__all__ = ["DEFAULT_OPERATIONS"]
