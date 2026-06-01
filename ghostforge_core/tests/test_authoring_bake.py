"""Tests for bake operations (lightmap UV + convex collision)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import trimesh

from ghostforge_core.authoring import (
    BAKE_OPERATIONS,
    EditGraph,
    OperationContext,
    OperationError,
    OperationNode,
    default_operation_registry,
    evaluate_graph,
)
from ghostforge_core.authoring.bake import _op_bake_convex_collision


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_default_registry_includes_bake_ops():
    reg = default_operation_registry()
    kinds = {op.descriptor.kind for op in reg.all()}
    assert "bake_lightmap_uv" in kinds
    assert "bake_convex_collision" in kinds


def test_bake_ops_have_proper_metadata():
    by_kind = {op.descriptor.kind: op.descriptor for op in BAKE_OPERATIONS}
    lm = by_kind["bake_lightmap_uv"]
    assert lm.category == "bake"
    assert "xatlas" in lm.requires_modules
    coll = by_kind["bake_convex_collision"]
    assert coll.category == "bake"
    assert "output_name" in coll.params_schema


# ---------------------------------------------------------------------------
# Convex collision
# ---------------------------------------------------------------------------


def _make_box(path: Path) -> Path:
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 0.5))
    mesh.export(str(path))
    return path


def _ctx_for(mesh: trimesh.Trimesh, output_dir: Path | None, params: dict | None = None):
    return OperationContext(
        mesh=mesh,
        params=params or {},
        node_id="n1",
        graph_id="g1",
        output_dir=output_dir,
        side_effects=[],
    )


def test_collision_bake_writes_sibling_file_and_records_side_effect(tmp_path):
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    ctx = _ctx_for(mesh, tmp_path)
    out = _op_bake_convex_collision(ctx)
    assert isinstance(out, trimesh.Trimesh)
    coll_path = tmp_path / "collision.glb"
    assert coll_path.exists()
    assert ctx.side_effects[0]["kind"] == "convex_collision"
    assert ctx.side_effects[0]["mesh_path"] == str(coll_path)
    assert ctx.side_effects[0]["face_count"] > 0


def test_collision_bake_respects_custom_output_name(tmp_path):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, tmp_path, {"output_name": "my_collider", "output_format": "glb"})
    _op_bake_convex_collision(ctx)
    assert (tmp_path / "my_collider.glb").exists()


def test_collision_bake_requires_output_dir():
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, None)
    with pytest.raises(OperationError):
        _op_bake_convex_collision(ctx)


def test_collision_bake_rejects_unknown_format(tmp_path):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, tmp_path, {"output_format": "fbx"})
    with pytest.raises(OperationError):
        _op_bake_convex_collision(ctx)


def test_collision_returns_unchanged_mesh(tmp_path):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, tmp_path)
    out = _op_bake_convex_collision(ctx)
    assert out.vertices.shape == mesh.vertices.shape
    assert out.faces.shape == mesh.faces.shape


# ---------------------------------------------------------------------------
# Lightmap UV bake (skipped when xatlas isn't installed)
# ---------------------------------------------------------------------------


def _xatlas_available() -> bool:
    try:
        import xatlas  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _xatlas_available(), reason="xatlas not installed")
def test_lightmap_uv_bake_records_channel_metadata(tmp_path):
    from ghostforge_core.authoring.bake import _op_bake_lightmap_uv

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, tmp_path)
    out = _op_bake_lightmap_uv(ctx)
    assert isinstance(out, trimesh.Trimesh)
    md = out.metadata
    assert md.get("lightmap_uv_channel") == 1
    assert isinstance(md.get("lightmap_uv"), list)
    assert len(md["lightmap_uv"]) == len(out.vertices)


@pytest.mark.skipif(_xatlas_available(), reason="want xatlas-missing path")
def test_lightmap_uv_bake_errors_when_xatlas_missing(tmp_path):
    from ghostforge_core.authoring.bake import _op_bake_lightmap_uv

    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    ctx = _ctx_for(mesh, tmp_path)
    with pytest.raises(OperationError):
        _op_bake_lightmap_uv(ctx)


# ---------------------------------------------------------------------------
# End-to-end through the evaluator
# ---------------------------------------------------------------------------


def test_evaluator_records_collision_side_effect(tmp_path):
    base = _make_box(tmp_path / "base.glb")
    out = tmp_path / "out.glb"
    graph = EditGraph(
        graph_id="g1",
        base_asset_path=str(base),
        output_path=str(out),
        nodes=(
            OperationNode(id="n1", kind="bake_convex_collision", params={}),
        ),
    )
    reg = default_operation_registry()
    result, _ = evaluate_graph(graph, registry=reg)
    assert result.status == "succeeded"
    side_effects = (result.metadata or {}).get("side_effects") or []
    kinds = [se.get("kind") for se in side_effects]
    assert "convex_collision" in kinds
    coll_path = next(se["mesh_path"] for se in side_effects if se["kind"] == "convex_collision")
    assert Path(coll_path).exists()


def test_apply_side_effects_to_manifest_writes_collision_spec(tmp_path):
    from ghostforge_core.manifest import (
        apply_side_effects_to_manifest,
        manifest_path,
        read_manifest,
    )

    coll = tmp_path / "collision.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(coll))
    manifest = apply_side_effects_to_manifest(
        tmp_path,
        [
            {
                "kind": "convex_collision",
                "intent": "convex",
                "mesh_path": str(coll),
                "vertex_count": 8,
                "face_count": 12,
            }
        ],
        asset_id="asset_x",
    )
    assert manifest is not None
    assert manifest_path(tmp_path).exists()
    reread = read_manifest(tmp_path)
    assert reread.collision.intent.value == "convex"
    assert Path(reread.collision.mesh_path) == coll
    assert any(a.role == "collision" for a in reread.artifacts)


def test_apply_side_effects_lightmap_only_writes_custom(tmp_path):
    from ghostforge_core.manifest import apply_side_effects_to_manifest, read_manifest

    manifest = apply_side_effects_to_manifest(
        tmp_path,
        [
            {
                "kind": "lightmap_uv",
                "channel": 1,
                "chart_count": 7,
                "resolution": 1024,
                "padding": 4,
                "engine": "unreal",
            }
        ],
        asset_id="asset_y",
    )
    assert manifest is not None
    reread = read_manifest(tmp_path)
    assert reread.custom["lightmap_uv"]["channel"] == 1
    assert reread.custom["lightmap_uv"]["engine"] == "unreal"


def test_apply_side_effects_noop_when_empty(tmp_path):
    from ghostforge_core.manifest import apply_side_effects_to_manifest

    assert apply_side_effects_to_manifest(tmp_path, []) is None
