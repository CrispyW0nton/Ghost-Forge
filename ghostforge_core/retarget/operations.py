"""Retarget operations registered into the P11 OperationRegistry.

These slot into the regular modifier stack — they're authored, evaluated,
reordered, and disabled exactly like any other authoring node. The
retarget planner emits sequences of these.

Why expose retarget as ops instead of a one-shot pipeline:

* **Visibility** — the user sees the exact transform chain in the
  modifier UI and can disable any individual step (e.g. keep Unreal's
  units but skip the axis swap because the source is already Z-up).
* **Composability** — retargeting fits inside larger graphs that include
  decimate, smooth, etc.
* **Idempotency** — applying ``retarget_units(factor=100)`` twice is
  obviously wrong, but the user (and any sanity rule) can spot it in
  the stack.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh

from ..authoring.registry import (
    Operation,
    OperationContext,
    OperationError,
    make_operation,
)
from .profiles import EngineConventions, get_profile, gltf_canonical_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def _axis_swap_matrix(
    src: EngineConventions, dst: EngineConventions
) -> np.ndarray:
    """Build a 4x4 transform that re-maps `src` axes onto `dst`.

    The matrix permutes columns so the destination's *up* and *forward*
    axes align with the source's, and applies a sign flip on the
    forward axis if handedness differs (which would otherwise mirror
    the geometry).
    """

    src_up = _AXIS_INDEX[src.axis_up]
    src_fwd = _AXIS_INDEX[src.axis_forward]
    src_right = ({0, 1, 2} - {src_up, src_fwd}).pop()

    dst_up = _AXIS_INDEX[dst.axis_up]
    dst_fwd = _AXIS_INDEX[dst.axis_forward]
    dst_right = ({0, 1, 2} - {dst_up, dst_fwd}).pop()

    # Rows of the 3x3 block correspond to the destination basis; columns
    # to the source basis.
    rotation = np.zeros((3, 3), dtype=float)
    rotation[dst_up, src_up] = 1.0
    rotation[dst_fwd, src_fwd] = 1.0
    rotation[dst_right, src_right] = 1.0

    # Handedness flip: if source and destination handedness disagree,
    # mirror along the destination's forward axis. Mirroring forward
    # (rather than up or right) preserves "facing direction" between
    # the two coordinate systems for typical character/prop assets.
    if src.handedness != dst.handedness:
        rotation[dst_fwd, :] *= -1.0

    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    return matrix


def _resolve_profile(value: Any, *, default: str = "gltf_canonical") -> EngineConventions:
    if value is None:
        return get_profile(default)
    if isinstance(value, EngineConventions):
        return value
    if not isinstance(value, str):
        raise OperationError(
            f"profile must be a name string or EngineConventions; got {type(value).__name__}"
        )
    try:
        return get_profile(value)
    except ValueError as exc:
        # Surface unknown profiles as OperationError so the evaluator
        # records the issue per-step rather than aborting the whole run.
        raise OperationError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Operation handlers
# ---------------------------------------------------------------------------


def _op_retarget_axis(ctx: OperationContext) -> trimesh.Trimesh:
    """Re-orient a mesh from one engine's axis convention to another."""

    src = _resolve_profile(ctx.params.get("from"), default="gltf_canonical")
    dst_value = ctx.params.get("to")
    if not dst_value:
        raise OperationError("'to' is required (engine profile name)")
    dst = _resolve_profile(dst_value)
    matrix = _axis_swap_matrix(src, dst)
    mesh = ctx.mesh.copy()
    # ``trimesh.apply_transform`` auto-inverts face winding when the
    # determinant is negative, so we don't need a second flip here —
    # see trimesh.base.Trimesh.apply_transform for the implementation.
    mesh.apply_transform(matrix)
    return mesh


def _op_retarget_units(ctx: OperationContext) -> trimesh.Trimesh:
    """Apply a uniform scale to convert metres into engine units (or back)."""

    factor_param = ctx.params.get("factor")
    target_param = ctx.params.get("to")
    if factor_param is None and target_param is None:
        raise OperationError("either 'factor' or 'to' must be supplied")

    if factor_param is not None:
        try:
            factor = float(factor_param)
        except (TypeError, ValueError) as exc:
            raise OperationError(f"factor must be numeric; got {factor_param!r}") from exc
    else:
        profile = _resolve_profile(target_param)
        factor = 1.0 / profile.units_to_meters

    if factor <= 0.0:
        raise OperationError("factor must be > 0")
    mesh = ctx.mesh.copy()
    mesh.apply_scale(factor)
    return mesh


def _op_retarget_pivot_for_engine(ctx: OperationContext) -> trimesh.Trimesh:
    """Move the pivot to the asset base along the target engine's up axis."""

    profile = _resolve_profile(ctx.params.get("to") or ctx.params.get("target"))
    mesh = ctx.mesh.copy()
    axis_index = _AXIS_INDEX[profile.axis_up]
    extents_min = mesh.bounds[0]
    centroid = mesh.centroid
    offset = -centroid.copy()
    # Keep the asset base on the up-axis grounding plane (e.g. y=0 for Unity,
    # z=0 for Unreal); leave the other axes centred on the centroid.
    offset[axis_index] = -extents_min[axis_index]
    mesh.apply_translation(offset)
    return mesh


def _op_retarget_apply_naming(ctx: OperationContext) -> trimesh.Trimesh:
    """Annotate the mesh with engine-specific name prefixes.

    trimesh meshes don't carry a stable "name" attribute the way
    glTF/USD do, so we stash the suggested names in ``mesh.metadata``
    where the manifest builder can pick them up at export time. This
    keeps the operation pure (returns a Trimesh, no side-effect on
    the manifest) while still being useful in a graph.
    """

    profile = _resolve_profile(ctx.params.get("to") or ctx.params.get("target"))
    base_name = ctx.params.get("base_name")
    if not base_name:
        raise OperationError("'base_name' is required")
    if not isinstance(base_name, str):
        raise OperationError("'base_name' must be a string")

    mesh = ctx.mesh.copy()
    metadata = dict(mesh.metadata or {})
    naming = profile.naming
    metadata.setdefault("ghostforge", {})
    gf_meta = dict(metadata["ghostforge"])
    gf_meta["engine_naming"] = {
        "engine": profile.name,
        "static_mesh_name": f"{naming.static_mesh_prefix}{base_name}",
        "material_prefix": naming.material_prefix,
        "texture_prefix": naming.texture_prefix,
        "collision_prefix": naming.collision_prefix,
    }
    metadata["ghostforge"] = gf_meta
    mesh.metadata = metadata
    return mesh


# ---------------------------------------------------------------------------
# Default operation list
# ---------------------------------------------------------------------------


RETARGET_OPERATIONS: tuple[Operation, ...] = (
    make_operation(
        kind="retarget_axis",
        label="Retarget Axis",
        summary=(
            "Re-orient mesh from one engine's coordinate system to another. "
            "Inverts face winding when handedness flips."
        ),
        category="retarget",
        params_schema={
            "from": {
                "type": "enum",
                "values": ["gltf_canonical", "unity", "unreal"],
                "default": "gltf_canonical",
            },
            "to": {
                "type": "enum",
                "values": ["gltf_canonical", "unity", "unreal"],
                "default": "unreal",
            },
        },
        handler=_op_retarget_axis,
    ),
    make_operation(
        kind="retarget_units",
        label="Retarget Units",
        summary="Uniformly scale to switch between metres and engine units (e.g. 100x for Unreal).",
        category="retarget",
        params_schema={
            "factor": {"type": "float", "default": 100.0, "min": 0.0001},
            "to": {
                "type": "enum",
                "values": ["unity", "unreal"],
                "default": None,
                "note": "If supplied, derives factor=1/engine.units_to_meters automatically.",
            },
        },
        handler=_op_retarget_units,
    ),
    make_operation(
        kind="retarget_pivot_for_engine",
        label="Retarget Pivot",
        summary="Move pivot to the asset base along the target engine's up axis.",
        category="retarget",
        params_schema={
            "to": {
                "type": "enum",
                "values": ["unity", "unreal"],
                "default": "unity",
            }
        },
        handler=_op_retarget_pivot_for_engine,
    ),
    make_operation(
        kind="retarget_apply_naming",
        label="Apply Engine Naming",
        summary=(
            "Annotate mesh.metadata with engine-conformant name prefixes "
            "(e.g. SM_<name>, M_<name>, T_<name> for Unreal). The manifest "
            "writer reads these annotations at export time."
        ),
        category="retarget",
        params_schema={
            "to": {
                "type": "enum",
                "values": ["unity", "unreal"],
                "default": "unreal",
            },
            "base_name": {"type": "string"},
        },
        handler=_op_retarget_apply_naming,
    ),
)


__all__ = ["RETARGET_OPERATIONS"]
