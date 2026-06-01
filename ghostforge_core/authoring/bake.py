"""Bake operations for game-ready asset preparation.

Two operations live here, both produced as auto-fixes by P12's
cross-engine retarget audit:

* ``bake_lightmap_uv`` — generate a non-overlapping UV chart in
  channel 1 (xatlas) suitable for engine lightmappers, with engine-
  specific padding defaults.
* ``bake_convex_collision`` — emit a sibling convex hull mesh and
  record its path in :class:`~ghostforge_core.authoring.registry.OperationContext.side_effects`
  so the manifest layer can wire it into :class:`CollisionSpec`.

Both ops are deliberately thin: they validate their parameters, do
the smallest reasonable amount of work, and surface clear errors when
optional deps are missing. Heavy lifting (file I/O for collision,
xatlas process bookkeeping) is the operation's job; manifest
mutation is downstream so a single graph evaluation can produce
many side-effect artifacts and the manifest builder consumes them in
one pass.
"""

from __future__ import annotations

from pathlib import Path
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
# Lightmap UV bake
# ---------------------------------------------------------------------------


def _engine_padding_default(engine: str) -> int:
    """Engine-recommended texel padding between charts for lightmapping."""

    return {
        "unity": 4,
        "unreal": 8,
        "gltf_canonical": 4,
        "default": 4,
    }.get(engine.lower(), 4)


def _op_bake_lightmap_uv(ctx: OperationContext) -> trimesh.Trimesh:
    try:
        import xatlas  # type: ignore
    except ImportError as exc:
        raise OperationError(
            "bake_lightmap_uv requires the `xatlas` package "
            "(install with `pip install xatlas`)"
        ) from exc

    engine = str(ctx.params.get("engine", "default"))
    resolution = int(ctx.params.get("resolution", 1024))
    padding = int(ctx.params.get("padding", _engine_padding_default(engine)))
    if resolution < 64 or resolution > 8192:
        raise OperationError("resolution must be in [64, 8192]")
    if padding < 0 or padding > 64:
        raise OperationError("padding must be in [0, 64]")

    src = ctx.mesh
    if src is None or len(src.faces) == 0:
        raise OperationError("input mesh has no geometry to unwrap")

    atlas = xatlas.Atlas()
    # xatlas wants float32 verts and uint32 faces.
    atlas.add_mesh(
        np.asarray(src.vertices, dtype=np.float32),
        np.asarray(src.faces, dtype=np.uint32),
        np.asarray(src.vertex_normals, dtype=np.float32) if src.vertex_normals is not None else None,
    )
    chart_options = xatlas.ChartOptions()
    pack_options = xatlas.PackOptions()
    pack_options.padding = padding
    pack_options.resolution = resolution
    atlas.generate(chart_options=chart_options, pack_options=pack_options)

    vmapping, indices, uvs = atlas[0]

    new_mesh = trimesh.Trimesh(
        vertices=np.asarray(src.vertices, dtype=np.float64)[vmapping],
        faces=np.asarray(indices, dtype=np.int64),
        process=False,
    )
    if src.vertex_normals is not None:
        new_mesh.vertex_normals = np.asarray(src.vertex_normals)[vmapping]

    # Preserve the channel-0 UV (if any) and stash channel-1 in metadata
    # so downstream consumers (manifest, gltf exporter) can promote it.
    existing_uv = None
    if hasattr(src.visual, "uv") and getattr(src.visual, "uv", None) is not None:
        existing_uv = np.asarray(src.visual.uv)[vmapping]

    md = dict(new_mesh.metadata) if new_mesh.metadata is not None else {}
    md["lightmap_uv_channel"] = 1
    md["lightmap_uv"] = np.asarray(uvs, dtype=np.float64).tolist()
    md["lightmap_chart_count"] = int(atlas.chart_count) if hasattr(atlas, "chart_count") else None
    md["lightmap_resolution"] = resolution
    md["lightmap_padding"] = padding
    md["lightmap_engine"] = engine
    new_mesh.metadata = md

    if existing_uv is not None:
        # Re-attach the original channel-0 UV alongside the visual.
        try:
            new_mesh.visual = trimesh.visual.TextureVisuals(
                uv=existing_uv,
                material=getattr(src.visual, "material", None),
            )
        except Exception:
            # Fallback: skip channel-0 reattach but keep channel-1 metadata.
            pass

    if ctx.side_effects is not None:
        ctx.side_effects.append(
            {
                "kind": "lightmap_uv",
                "channel": 1,
                "chart_count": md.get("lightmap_chart_count"),
                "resolution": resolution,
                "padding": padding,
                "engine": engine,
            }
        )

    return new_mesh


# ---------------------------------------------------------------------------
# Convex collision bake
# ---------------------------------------------------------------------------


def _op_bake_convex_collision(ctx: OperationContext) -> trimesh.Trimesh:
    """Emit a sibling convex collision mesh next to the evaluator output.

    Returns the original mesh unchanged — collision is *additional*
    geometry, not a replacement. The path of the emitted file is
    appended to ``ctx.side_effects`` and the manifest builder layer
    is responsible for promoting it to a ``CollisionSpec``.
    """

    target_faces = int(ctx.params.get("target_faces", 0))
    output_name = str(ctx.params.get("output_name", "collision.glb"))
    output_format = str(ctx.params.get("output_format", "glb"))

    if not output_name:
        raise OperationError("output_name must be a non-empty string")
    if output_format not in {"glb", "gltf", "obj", "stl", "ply"}:
        raise OperationError(f"unsupported collision output format: {output_format!r}")
    if target_faces < 0 or target_faces > 100_000:
        raise OperationError("target_faces must be in [0, 100000]")

    if ctx.output_dir is None:
        raise OperationError(
            "bake_convex_collision requires the evaluator to know an output_dir; "
            "set EditGraph.output_path before running."
        )

    src = ctx.mesh
    if src is None or len(src.faces) == 0:
        raise OperationError("input mesh has no geometry to bake collision from")

    try:
        hull = src.convex_hull
    except Exception as exc:
        raise OperationError(f"convex hull computation failed: {exc}") from exc

    if not isinstance(hull, trimesh.Trimesh) or len(hull.faces) == 0:
        raise OperationError("convex hull is empty; mesh may be degenerate")

    if target_faces and len(hull.faces) > target_faces and hasattr(hull, "simplify_quadric_decimation"):
        try:
            simplified = hull.simplify_quadric_decimation(target_faces)
            if isinstance(simplified, trimesh.Trimesh) and len(simplified.faces) > 0:
                hull = simplified
        except Exception:
            # Decimation is optional — keep the full hull if simplification fails.
            pass

    out_dir = Path(ctx.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_name = output_name
    if not out_name.lower().endswith(f".{output_format.lower()}"):
        out_name = f"{Path(out_name).stem}.{output_format}"
    out_path = out_dir / out_name

    hull.export(str(out_path))

    if ctx.side_effects is not None:
        ctx.side_effects.append(
            {
                "kind": "convex_collision",
                "intent": "convex",
                "mesh_path": str(out_path),
                "vertex_count": int(len(hull.vertices)),
                "face_count": int(len(hull.faces)),
            }
        )

    return src.copy()


# ---------------------------------------------------------------------------
# Public registration list
# ---------------------------------------------------------------------------


BAKE_OPERATIONS: tuple[Operation, ...] = (
    make_operation(
        kind="bake_lightmap_uv",
        label="Bake Lightmap UV",
        summary=(
            "Generate a non-overlapping UV chart on channel 1 with engine-"
            "specific padding (xatlas)."
        ),
        category="bake",
        params_schema={
            "engine": {
                "type": "enum",
                "values": ["unity", "unreal", "gltf_canonical", "default"],
                "default": "default",
            },
            "resolution": {"type": "int", "default": 1024, "min": 64, "max": 8192},
            "padding": {"type": "int", "default": 4, "min": 0, "max": 64},
        },
        requires_modules=("xatlas",),
        handler=_op_bake_lightmap_uv,
    ),
    make_operation(
        kind="bake_convex_collision",
        label="Bake Convex Collision",
        summary="Compute a convex hull and emit it as a sibling collision mesh.",
        category="bake",
        params_schema={
            "output_name": {"type": "string", "default": "collision.glb"},
            "output_format": {
                "type": "enum",
                "values": ["glb", "gltf", "obj", "stl", "ply"],
                "default": "glb",
            },
            "target_faces": {"type": "int", "default": 0, "min": 0, "max": 100000},
        },
        handler=_op_bake_convex_collision,
    ),
)


__all__ = ["BAKE_OPERATIONS"]
