"""AuditPreset factories and the get_preset/list_presets helpers."""

from __future__ import annotations

import pytest

from ghostforge_core.audit import (
    AuditPreset,
    default_preset,
    get_preset,
    list_presets,
    unity_preset,
    unreal_preset,
)
from ghostforge_core.manifest import EngineTarget


def test_default_preset_is_engine_agnostic():
    preset = default_preset()
    assert preset.name == "default"
    assert preset.require_engine_target is None
    assert preset.require_lightmap_uv_channel is None
    assert preset.require_lods is False


def test_unity_preset_enforces_unity_specifics():
    preset = unity_preset()
    assert preset.name == "unity"
    assert preset.require_engine_target == EngineTarget.unity
    assert preset.require_lightmap_uv_channel == 1
    assert preset.max_vertex_count == 65_000


def test_unreal_preset_uses_higher_caps():
    preset = unreal_preset()
    assert preset.name == "unreal"
    assert preset.require_engine_target == EngineTarget.unreal
    assert preset.max_triangle_count and preset.max_triangle_count >= 1_000_000


def test_get_preset_known_names():
    assert get_preset("default").name == "default"
    assert get_preset("unity").name == "unity"
    assert get_preset("unreal").name == "unreal"


def test_get_preset_unknown_raises():
    with pytest.raises(ValueError):
        get_preset("godot")


def test_list_presets_returns_all_three():
    presets = list_presets()
    names = {p.name for p in presets}
    assert names == {"default", "unity", "unreal"}
    assert all(isinstance(p, AuditPreset) for p in presets)


def test_preset_is_frozen():
    preset = default_preset()
    with pytest.raises(Exception):
        preset.name = "not-default"  # type: ignore[misc]
