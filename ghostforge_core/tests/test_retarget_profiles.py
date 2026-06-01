"""Engine profile registry tests."""

from __future__ import annotations

import pytest

from ghostforge_core.retarget import (
    EngineConventions,
    NamingConventions,
    PROFILE_FACTORIES,
    get_profile,
    gltf_canonical_profile,
    list_profiles,
    unity_profile,
    unreal_profile,
)


def test_list_profiles_returns_three_known_profiles():
    profiles = list_profiles()
    names = {p.name for p in profiles}
    assert names == {"gltf_canonical", "unity", "unreal"}
    assert all(isinstance(p, EngineConventions) for p in profiles)


def test_get_profile_returns_fresh_copies():
    a = get_profile("unity")
    b = get_profile("unity")
    assert a == b
    assert a is not b


def test_get_profile_unknown_raises():
    with pytest.raises(ValueError) as info:
        get_profile("godot")
    assert "godot" in str(info.value)


def test_canonical_profile_is_metric_right_handed_y_up():
    p = gltf_canonical_profile()
    assert p.handedness == "right"
    assert p.axis_up == "y"
    assert p.units_to_meters == 1.0
    assert p.naming.static_mesh_prefix == ""


def test_unity_profile_is_left_handed_y_up_metric():
    p = unity_profile()
    assert p.handedness == "left"
    assert p.axis_up == "y"
    assert p.axis_forward == "z"
    assert p.units_to_meters == 1.0
    assert p.require_lightmap_uv_channel == 1
    assert p.require_pow2_textures is True
    assert p.max_texture_dimension == 4096


def test_unreal_profile_is_left_handed_z_up_centimetric():
    p = unreal_profile()
    assert p.handedness == "left"
    assert p.axis_up == "z"
    assert p.axis_forward == "x"
    assert p.units_to_meters == 0.01
    assert p.require_lightmap_uv_channel == 1
    assert p.require_collision is True
    assert p.naming.static_mesh_prefix == "SM_"
    assert p.naming.material_prefix == "M_"
    assert p.naming.texture_prefix == "T_"
    assert p.naming.collision_prefix == "UCX_"


def test_profile_is_frozen():
    p = unity_profile()
    with pytest.raises(Exception):
        p.units_to_meters = 0.1  # type: ignore[misc]


def test_profile_factories_keys_match_get_profile():
    for name in PROFILE_FACTORIES:
        assert get_profile(name).name == name


def test_naming_conventions_default_empty():
    n = NamingConventions()
    assert n.static_mesh_prefix == ""
    assert n.material_prefix == ""
    assert n.collision_prefix == ""
