"""Worker-backed authoring graph operations.

These operations make AI generation and worker processing native graph nodes
instead of side-channel jobs. They still route through the same worker dispatch
layer, so manifests, provenance, audit inputs, worker probes, and secret
redaction remain centralized in ``ghostforge_core.operations.workers``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import trimesh

from ..manifest import manifest_path
from ..workers.schemas import (
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from .registry import Operation, OperationContext, OperationError, make_operation

SOURCE_OPERATION_KINDS = frozenset({"generate_text_to_3d", "generate_image_to_3d"})


def _node_dir(ctx: OperationContext, kind: str) -> Path:
    if ctx.output_dir is None:
        raise OperationError(
            f"{kind} requires an evaluator output_path so worker artifacts "
            "can be written into a stable graph-node directory"
        )
    safe_node = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in ctx.node_id)
    return Path(ctx.output_dir) / "_graph_nodes" / safe_node


def _load_mesh(path: str | Path) -> trimesh.Trimesh:
    loaded = trimesh.load(str(path), process=False, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise OperationError(f"worker output has no Trimesh geometry: {path}")
        return trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise OperationError(f"worker output is {type(loaded).__name__}, not Trimesh")
    return loaded


def _require_mesh(ctx: OperationContext, kind: str) -> trimesh.Trimesh:
    if ctx.mesh is None:
        raise OperationError(f"{kind} requires an input mesh or an earlier source node")
    return ctx.mesh


def _str_param(params: dict[str, Any], key: str, default: str | None = None) -> str | None:
    value = params.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise OperationError(f"{key!r} must be a string")
    return value


def _int_param(params: dict[str, Any], key: str) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise OperationError(f"{key!r} must be an integer") from exc


def _dict_param(params: dict[str, Any], key: str) -> dict[str, Any]:
    value = params.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise OperationError(f"{key!r} must be an object")
    return dict(value)


def _record_side_effect(
    ctx: OperationContext,
    *,
    kind: str,
    asset_dir: Path,
    result: dict[str, Any],
) -> None:
    if ctx.side_effects is None:
        return
    effect: dict[str, Any] = {
        "kind": "worker_operation",
        "operation": kind,
        "node_id": ctx.node_id,
        "asset_dir": str(asset_dir),
        "output_mesh": str(result.get("output_mesh") or ""),
        "worker": result.get("worker"),
        "metadata": dict(result.get("metadata") or {}),
    }
    tex = result.get("texture_map")
    if tex:
        effect["texture_map"] = str(tex)
    mp = manifest_path(asset_dir)
    if mp.exists():
        effect["manifest_path"] = str(mp)
    ctx.side_effects.append(effect)


def _op_generate_text_to_3d(ctx: OperationContext) -> trimesh.Trimesh:
    from ..operations import workers as worker_ops

    prompt = _str_param(ctx.params, "prompt")
    if not prompt:
        raise OperationError("prompt is required")
    asset_dir = _node_dir(ctx, "generate_text_to_3d")
    spec = TextTo3DRequest(
        prompt=prompt,
        negative_prompt=_str_param(ctx.params, "negative_prompt"),
        output_dir=asset_dir,
        worker=_str_param(ctx.params, "worker"),
        seed=_int_param(ctx.params, "seed"),
        output_format=_str_param(ctx.params, "output_format", "glb") or "glb",
        extras=_dict_param(ctx.params, "extras"),
    )
    result = worker_ops.run_text_to_3d(spec, reporter=ctx.reporter, cancel=ctx.cancel)
    _record_side_effect(ctx, kind="generate_text_to_3d", asset_dir=asset_dir, result=result)
    return _load_mesh(result["output_mesh"])


def _op_generate_image_to_3d(ctx: OperationContext) -> trimesh.Trimesh:
    from ..operations import workers as worker_ops

    image_path = _str_param(ctx.params, "input_image_path")
    if not image_path:
        raise OperationError("input_image_path is required")
    asset_dir = _node_dir(ctx, "generate_image_to_3d")
    spec = ImageTo3DRequest(
        input_image_path=Path(image_path),
        prompt=_str_param(ctx.params, "prompt"),
        output_dir=asset_dir,
        worker=_str_param(ctx.params, "worker"),
        seed=_int_param(ctx.params, "seed"),
        output_format=_str_param(ctx.params, "output_format", "glb") or "glb",
        extras=_dict_param(ctx.params, "extras"),
    )
    result = worker_ops.run_image_to_3d(spec, reporter=ctx.reporter, cancel=ctx.cancel)
    _record_side_effect(ctx, kind="generate_image_to_3d", asset_dir=asset_dir, result=result)
    return _load_mesh(result["output_mesh"])


def _op_worker_refine_mesh(ctx: OperationContext) -> trimesh.Trimesh:
    from ..operations import workers as worker_ops

    mesh = _require_mesh(ctx, "worker_refine_mesh")
    asset_dir = _node_dir(ctx, "worker_refine_mesh")
    asset_dir.mkdir(parents=True, exist_ok=True)
    input_mesh = asset_dir / "input.glb"
    mesh.export(str(input_mesh))
    spec = RefineMeshRequest(
        input_mesh_path=input_mesh,
        output_dir=asset_dir,
        worker=_str_param(ctx.params, "worker"),
        seed=_int_param(ctx.params, "seed"),
        output_format=_str_param(ctx.params, "output_format", "glb") or "glb",
        target_face_count=_int_param(ctx.params, "target_face_count"),
        preserve_uvs=bool(ctx.params.get("preserve_uvs", True)),
        extras=_dict_param(ctx.params, "extras"),
    )
    result = worker_ops.run_refine_mesh(spec, reporter=ctx.reporter, cancel=ctx.cancel)
    _record_side_effect(ctx, kind="worker_refine_mesh", asset_dir=asset_dir, result=result)
    return _load_mesh(result["output_mesh"])


def _op_worker_texture_mesh(ctx: OperationContext) -> trimesh.Trimesh:
    from ..operations import workers as worker_ops

    mesh = _require_mesh(ctx, "worker_texture_mesh")
    prompt = _str_param(ctx.params, "prompt")
    if not prompt:
        raise OperationError("prompt is required")
    asset_dir = _node_dir(ctx, "worker_texture_mesh")
    asset_dir.mkdir(parents=True, exist_ok=True)
    input_mesh = asset_dir / "input.glb"
    mesh.export(str(input_mesh))
    ref_image = _str_param(ctx.params, "reference_image_path")
    spec = TextureMeshRequest(
        input_mesh_path=input_mesh,
        prompt=prompt,
        output_dir=asset_dir,
        worker=_str_param(ctx.params, "worker"),
        seed=_int_param(ctx.params, "seed"),
        reference_image_path=Path(ref_image) if ref_image else None,
        texture_size=int(ctx.params.get("texture_size", 1024)),
        output_format=_str_param(ctx.params, "output_format", "glb") or "glb",
        extras=_dict_param(ctx.params, "extras"),
    )
    result = worker_ops.run_texture_mesh(spec, reporter=ctx.reporter, cancel=ctx.cancel)
    _record_side_effect(ctx, kind="worker_texture_mesh", asset_dir=asset_dir, result=result)
    return _load_mesh(result["output_mesh"])


WORKER_OPERATIONS: tuple[Operation, ...] = (
    make_operation(
        kind="generate_text_to_3d",
        label="Generate Text To 3D",
        summary="Source node: run a text-to-3D worker and use its mesh as graph input.",
        category="ai.source",
        params_schema={
            "prompt": {"type": "string", "required": True},
            "negative_prompt": {"type": "string", "default": None},
            "worker": {"type": "string", "default": None},
            "seed": {"type": "int", "default": None},
            "output_format": {"type": "string", "default": "glb"},
            "extras": {"type": "object", "default": {}},
        },
        handler=_op_generate_text_to_3d,
    ),
    make_operation(
        kind="generate_image_to_3d",
        label="Generate Image To 3D",
        summary="Source node: run an image-to-3D worker and use its mesh as graph input.",
        category="ai.source",
        params_schema={
            "input_image_path": {"type": "path", "required": True},
            "prompt": {"type": "string", "default": None},
            "worker": {"type": "string", "default": None},
            "seed": {"type": "int", "default": None},
            "output_format": {"type": "string", "default": "glb"},
            "extras": {"type": "object", "default": {}},
        },
        handler=_op_generate_image_to_3d,
    ),
    make_operation(
        kind="worker_refine_mesh",
        label="Worker Refine Mesh",
        summary="Run a refine/retopo worker as a graph operation.",
        category="ai.process",
        params_schema={
            "worker": {"type": "string", "default": None},
            "target_face_count": {"type": "int", "default": None},
            "preserve_uvs": {"type": "bool", "default": True},
            "seed": {"type": "int", "default": None},
            "output_format": {"type": "string", "default": "glb"},
            "extras": {"type": "object", "default": {}},
        },
        handler=_op_worker_refine_mesh,
    ),
    make_operation(
        kind="worker_texture_mesh",
        label="Worker Texture Mesh",
        summary="Run a texture worker as a graph operation and record texture artifacts.",
        category="ai.process",
        params_schema={
            "prompt": {"type": "string", "required": True},
            "worker": {"type": "string", "default": None},
            "reference_image_path": {"type": "path", "default": None},
            "texture_size": {"type": "int", "default": 1024, "min": 256, "max": 4096},
            "seed": {"type": "int", "default": None},
            "output_format": {"type": "string", "default": "glb"},
            "extras": {"type": "object", "default": {}},
        },
        handler=_op_worker_texture_mesh,
    ),
)


__all__ = ["SOURCE_OPERATION_KINDS", "WORKER_OPERATIONS"]
