"""Direct unit tests for each built-in authoring operation."""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from ghostforge_core.authoring import (
    OperationContext,
    OperationError,
    default_operation_registry,
)


@pytest.fixture
def cube() -> trimesh.Trimesh:
    return trimesh.creation.box(extents=(1.0, 1.0, 1.0))


@pytest.fixture
def registry():
    return default_operation_registry()


def _ctx(mesh, params):
    return OperationContext(
        mesh=mesh,
        params=dict(params),
        node_id="n",
        graph_id="g",
    )


# ---------------------------------------------------------------------------
# Transform / placement
# ---------------------------------------------------------------------------


def test_transform_translates_centroid(cube, registry):
    op = registry.get("transform")
    out = op(_ctx(cube, {"translate": [1.0, 2.0, 3.0]}))
    assert np.allclose(out.centroid, np.array([1.0, 2.0, 3.0]), atol=1e-6)


def test_transform_scalar_scale(cube, registry):
    op = registry.get("transform")
    out = op(_ctx(cube, {"scale": 2.0}))
    assert np.allclose(out.extents, np.array([2.0, 2.0, 2.0]))


def test_transform_rotate_90_about_z(cube, registry):
    mesh = trimesh.creation.box(extents=(2.0, 1.0, 1.0))
    op = registry.get("transform")
    out = op(_ctx(mesh, {"rotate_euler_deg": [0.0, 0.0, 90.0]}))
    # x extent and y extent swap.
    assert math.isclose(out.extents[0], 1.0, abs_tol=1e-6)
    assert math.isclose(out.extents[1], 2.0, abs_tol=1e-6)


def test_transform_rejects_bad_translate(cube, registry):
    op = registry.get("transform")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"translate": [1.0, 2.0]}))


def test_recenter_centroid_default(registry):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.apply_translation([5.0, 5.0, 5.0])
    op = registry.get("recenter")
    out = op(_ctx(mesh, {}))
    assert np.allclose(out.centroid, np.zeros(3), atol=1e-6)


def test_recenter_bottom_pivot(registry):
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.apply_translation([0.0, -2.0, 0.0])
    op = registry.get("recenter")
    out = op(_ctx(mesh, {"pivot": "bottom"}))
    # Lowest Y should now be at 0.
    assert math.isclose(out.bounds[0][1], 0.0, abs_tol=1e-6)


def test_recenter_unknown_pivot_raises(registry, cube):
    op = registry.get("recenter")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"pivot": "moon"}))


def test_normalize_scale_to_unit(registry):
    mesh = trimesh.creation.box(extents=(4.0, 2.0, 1.0))
    op = registry.get("normalize_scale")
    out = op(_ctx(mesh, {"target_extent": 1.0}))
    assert math.isclose(float(out.extents.max()), 1.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Topology / cleanup
# ---------------------------------------------------------------------------


def test_recompute_normals_returns_valid_mesh(cube, registry):
    op = registry.get("recompute_normals")
    out = op(_ctx(cube, {}))
    assert out.face_normals.shape == cube.face_normals.shape


def test_merge_vertices_idempotent(cube, registry):
    op = registry.get("merge_vertices")
    out1 = op(_ctx(cube, {}))
    out2 = op(_ctx(out1, {}))
    assert len(out1.vertices) == len(out2.vertices)


def test_smooth_laplacian_shrinks_extents(registry):
    mesh = trimesh.creation.icosphere(subdivisions=2)
    op = registry.get("smooth_laplacian")
    out = op(_ctx(mesh, {"iterations": 5, "lambda": 0.5}))
    # Laplacian smoothing pulls vertices inward; extents should decrease.
    assert float(out.extents.max()) <= float(mesh.extents.max())


def test_smooth_laplacian_rejects_bad_lambda(cube, registry):
    op = registry.get("smooth_laplacian")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"lambda": 1.5}))


def test_subdivide_increases_face_count(cube, registry):
    op = registry.get("subdivide")
    out = op(_ctx(cube, {"iterations": 1}))
    assert len(out.faces) > len(cube.faces)


def test_subdivide_rejects_excessive_iterations(cube, registry):
    op = registry.get("subdivide")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"iterations": 10}))


def test_decimate_reduces_or_explains(registry):
    mesh = trimesh.creation.icosphere(subdivisions=4)
    op = registry.get("decimate")
    try:
        out = op(_ctx(mesh, {"target_ratio": 0.25}))
    except OperationError as exc:
        # Acceptable on machines without an open3d / fast-simplification
        # backend; the error message must explain how to enable it.
        assert "decimation backend" in str(exc).lower()
        return
    assert len(out.faces) < len(mesh.faces)


# ---------------------------------------------------------------------------
# Material
# ---------------------------------------------------------------------------


def test_apply_material_sets_pbr_factors(cube, registry):
    op = registry.get("apply_material")
    out = op(
        _ctx(
            cube,
            {
                "name": "iron",
                "base_color_rgba": [0.5, 0.5, 0.5, 1.0],
                "metallic": 1.0,
                "roughness": 0.2,
            },
        )
    )
    material = getattr(out.visual, "material", None)
    assert material is not None
    assert material.name == "iron"
    assert math.isclose(float(material.metallicFactor), 1.0, abs_tol=1e-6)
    assert math.isclose(float(material.roughnessFactor), 0.2, abs_tol=1e-6)


def test_apply_material_rejects_oob_color(cube, registry):
    op = registry.get("apply_material")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"base_color_rgba": [1.5, 0.0, 0.0, 1.0]}))


def test_apply_material_rejects_empty_name(cube, registry):
    op = registry.get("apply_material")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"name": ""}))


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_unknown_kind_raises(registry):
    with pytest.raises(KeyError):
        registry.get("does_not_exist")


def test_registry_descriptors_sorted_by_category_kind(registry):
    descriptors = registry.descriptors()
    keys = [(d.category, d.kind) for d in descriptors]
    assert keys == sorted(keys)
    kinds = {d.kind for d in descriptors}
    expected = {
        "transform",
        "recenter",
        "normalize_scale",
        "recompute_normals",
        "merge_vertices",
        "smooth_laplacian",
        "subdivide",
        "decimate",
        "apply_material",
    }
    assert expected.issubset(kinds)
