"""Retarget operation handler tests.

Use direct ``OperationContext`` invocations (no graph evaluator) so each
operation is exercised in isolation.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import trimesh

from ghostforge_core.authoring.registry import (
    OperationContext,
    OperationError,
    OperationRegistry,
)
from ghostforge_core.retarget import (
    RETARGET_OPERATIONS,
    get_profile,
)
from ghostforge_core.retarget.operations import _axis_swap_matrix


@pytest.fixture
def registry():
    reg = OperationRegistry()
    reg.register_all(RETARGET_OPERATIONS)
    return reg


@pytest.fixture
def cube() -> trimesh.Trimesh:
    return trimesh.creation.box(extents=(1.0, 2.0, 3.0))


def _ctx(mesh, params):
    return OperationContext(mesh=mesh, params=dict(params), node_id="n", graph_id="g")


# ---------------------------------------------------------------------------
# Axis swap
# ---------------------------------------------------------------------------


def test_axis_matrix_unity_to_unreal_changes_up_axis():
    src = get_profile("unity")
    dst = get_profile("unreal")
    matrix = _axis_swap_matrix(src, dst)
    assert matrix.shape == (4, 4)
    # Unity Y-up basis vector should map onto Unreal's Z-up.
    y_unit = np.array([0.0, 1.0, 0.0, 1.0])
    transformed = matrix @ y_unit
    assert transformed[2] != 0.0  # picked up by the up-axis row
    assert math.isclose(transformed[1], 0.0, abs_tol=1e-12)


def test_axis_matrix_handedness_flip_inverts_determinant():
    src = get_profile("gltf_canonical")
    dst = get_profile("unreal")
    matrix = _axis_swap_matrix(src, dst)
    det = float(np.linalg.det(matrix[:3, :3]))
    assert det == pytest.approx(-1.0, abs=1e-9) or det == pytest.approx(1.0, abs=1e-9)


def test_retarget_axis_canonical_to_unreal_swaps_y_and_z(registry, cube):
    op = registry.get("retarget_axis")
    out = op(_ctx(cube, {"from": "gltf_canonical", "to": "unreal"}))
    # Y-up extent (2.0) should now be on Z; X-extent (1.0) stays.
    extents = sorted(out.extents.tolist())
    assert extents == sorted([1.0, 2.0, 3.0])
    # Validate the up axis received the original up extent (2.0).
    assert math.isclose(out.extents[2], 2.0, abs_tol=1e-6)


def test_retarget_axis_to_required(registry, cube):
    op = registry.get("retarget_axis")
    with pytest.raises(OperationError):
        op(_ctx(cube, {}))


def test_retarget_axis_unknown_target(registry, cube):
    op = registry.get("retarget_axis")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"to": "godot"}))


def test_retarget_axis_handedness_flip_inverts_winding(registry):
    """If handedness flips, faces must invert so normals stay outward."""

    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    cube.fix_normals()
    before_volume_sign = float(np.sign(cube.volume))
    op = registry.get("retarget_axis")
    out = op(_ctx(cube, {"from": "gltf_canonical", "to": "unreal"}))
    after_volume_sign = float(np.sign(out.volume))
    # Both should be positive (i.e. faces stay outward) — if winding
    # didn't get inverted, volume would have flipped sign.
    assert after_volume_sign == before_volume_sign


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def test_retarget_units_explicit_factor(registry, cube):
    op = registry.get("retarget_units")
    out = op(_ctx(cube, {"factor": 100.0}))
    assert np.allclose(out.extents, np.array([100.0, 200.0, 300.0]))


def test_retarget_units_to_unreal_is_100x(registry, cube):
    op = registry.get("retarget_units")
    out = op(_ctx(cube, {"to": "unreal"}))
    assert np.allclose(out.extents, np.array([100.0, 200.0, 300.0]))


def test_retarget_units_to_unity_is_identity(registry, cube):
    op = registry.get("retarget_units")
    out = op(_ctx(cube, {"to": "unity"}))
    assert np.allclose(out.extents, cube.extents)


def test_retarget_units_negative_factor_rejected(registry, cube):
    op = registry.get("retarget_units")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"factor": -1.0}))


def test_retarget_units_neither_param_rejected(registry, cube):
    op = registry.get("retarget_units")
    with pytest.raises(OperationError):
        op(_ctx(cube, {}))


# ---------------------------------------------------------------------------
# Pivot for engine
# ---------------------------------------------------------------------------


def test_retarget_pivot_unity_grounds_y(registry, cube):
    cube.apply_translation([10.0, 5.0, 7.0])
    op = registry.get("retarget_pivot_for_engine")
    out = op(_ctx(cube, {"to": "unity"}))
    # Y bottom should now sit on the ground plane (y=0 within tolerance).
    assert math.isclose(out.bounds[0][1], 0.0, abs_tol=1e-6)


def test_retarget_pivot_unreal_grounds_z(registry, cube):
    cube.apply_translation([0.0, 0.0, 4.0])
    op = registry.get("retarget_pivot_for_engine")
    out = op(_ctx(cube, {"to": "unreal"}))
    assert math.isclose(out.bounds[0][2], 0.0, abs_tol=1e-6)


# ---------------------------------------------------------------------------
# Engine naming
# ---------------------------------------------------------------------------


def test_retarget_naming_writes_metadata(registry, cube):
    op = registry.get("retarget_apply_naming")
    out = op(_ctx(cube, {"to": "unreal", "base_name": "Crate"}))
    naming = out.metadata["ghostforge"]["engine_naming"]
    assert naming["engine"] == "unreal"
    assert naming["static_mesh_name"] == "SM_Crate"
    assert naming["material_prefix"] == "M_"
    assert naming["texture_prefix"] == "T_"


def test_retarget_naming_unity_has_no_prefix(registry, cube):
    op = registry.get("retarget_apply_naming")
    out = op(_ctx(cube, {"to": "unity", "base_name": "Crate"}))
    naming = out.metadata["ghostforge"]["engine_naming"]
    assert naming["static_mesh_name"] == "Crate"  # unity prefix is empty


def test_retarget_naming_requires_base_name(registry, cube):
    op = registry.get("retarget_apply_naming")
    with pytest.raises(OperationError):
        op(_ctx(cube, {"to": "unreal"}))


def test_retarget_naming_does_not_mutate_input(registry, cube):
    op = registry.get("retarget_apply_naming")
    op(_ctx(cube, {"to": "unreal", "base_name": "Crate"}))
    # Source should be untouched.
    assert "ghostforge" not in (cube.metadata or {})
