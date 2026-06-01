"""Cross-engine audit rule tests.

Each rule is exercised via its check function with a hand-built
``AuditContext`` so we don't pay the cost of writing a manifest to disk
for every assertion.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.audit.report import AuditSeverity
from ghostforge_core.audit.rules import AuditContext
from ghostforge_core.manifest import (
    AssetManifest,
    EngineTarget,
    EngineTargetSpec,
    GeometrySummary,
    LicenseSpec,
    MaterialSpec,
    TextureRole,
    TextureSlot,
)
from ghostforge_core.retarget import (
    unity_retarget_preset,
    unreal_retarget_preset,
)
from ghostforge_core.retarget.rules import (
    _check_axis_convention,
    _check_collision_present,
    _check_lightmap_uv_channel,
    _check_naming_convention,
    _check_pivot_at_base,
    _check_texture_pow2_strict,
    _check_unit_scale,
)


def _manifest(
    *,
    asset_id: str = "asset",
    name: str | None = None,
    geometry: GeometrySummary | None = None,
    materials: tuple[MaterialSpec, ...] = (),
) -> AssetManifest:
    return AssetManifest(
        asset_id=asset_id,
        name=name or asset_id,
        license=LicenseSpec(spdx="CC0-1.0"),
        geometry=geometry,
        materials=list(materials),
        engine_targets=[EngineTargetSpec(engine=EngineTarget.unity)],
    )


def _ctx(manifest: AssetManifest, preset, asset_dir: Path | None = None) -> AuditContext:
    return AuditContext(
        manifest=manifest,
        asset_dir=asset_dir or Path("/tmp/asset"),
        preset=preset,
    )


# ---------------------------------------------------------------------------
# Axis
# ---------------------------------------------------------------------------


def test_axis_rule_flags_unity_handedness_flip():
    """Unity is left-handed — canonical glTF is right-handed, so a flip is needed."""

    issues = _check_axis_convention(_ctx(_manifest(), unity_retarget_preset()))
    assert len(issues) == 1
    assert issues[0].code == "axis_mismatch_assumed"


def test_axis_rule_flags_unreal_axis_mismatch():
    issues = _check_axis_convention(_ctx(_manifest(), unreal_retarget_preset()))
    assert len(issues) == 1
    assert issues[0].severity == AuditSeverity.info
    assert issues[0].code == "axis_mismatch_assumed"
    assert "retarget_axis" in issues[0].suggestion.lower()


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------


def test_units_rule_silent_for_unity():
    issues = _check_unit_scale(_ctx(_manifest(), unity_retarget_preset()))
    assert issues == []


def test_units_rule_flags_unreal_scale():
    geom = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        bounds_min=(0, 0, 0),
        bounds_max=(1, 2, 3),
        size=(1, 2, 3),
    )
    issues = _check_unit_scale(_ctx(_manifest(geometry=geom), unreal_retarget_preset()))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == AuditSeverity.warning
    assert issue.code == "units_scale_required"
    assert "100" in issue.message  # factor 100x
    assert issue.details["factor"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------


def test_naming_rule_unity_silent_when_prefixes_empty():
    """Unity has empty naming prefixes, so nothing should fire."""

    m = _manifest(asset_id="hero", name="hero")
    issues = _check_naming_convention(_ctx(m, unity_retarget_preset()))
    assert issues == []


def test_naming_rule_flags_missing_unreal_prefixes():
    materials = (MaterialSpec(name="HeroMat", texture_slots=[]),)
    m = _manifest(asset_id="hero", name="hero", materials=materials)
    issues = _check_naming_convention(_ctx(m, unreal_retarget_preset()))
    codes = {i.code for i in issues}
    assert "static_mesh_prefix_missing" in codes
    assert "material_prefix_missing" in codes


def test_naming_rule_silent_when_prefixes_present():
    materials = (MaterialSpec(name="M_Hero", texture_slots=[]),)
    m = _manifest(asset_id="hero", name="SM_Hero", materials=materials)
    issues = _check_naming_convention(_ctx(m, unreal_retarget_preset()))
    assert issues == []


# ---------------------------------------------------------------------------
# Lightmap UV
# ---------------------------------------------------------------------------


def test_lightmap_rule_silent_when_channel_matches():
    geom = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        uv_channels=2,
        lightmap_uv_channel=1,
    )
    issues = _check_lightmap_uv_channel(_ctx(_manifest(geometry=geom), unity_retarget_preset()))
    assert issues == []


def test_lightmap_rule_warns_when_missing():
    geom = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        uv_channels=1,
        lightmap_uv_channel=None,
    )
    issues = _check_lightmap_uv_channel(_ctx(_manifest(geometry=geom), unity_retarget_preset()))
    assert len(issues) == 1
    assert issues[0].severity == AuditSeverity.warning
    assert issues[0].code == "lightmap_uv_channel_missing"


# ---------------------------------------------------------------------------
# Pivot
# ---------------------------------------------------------------------------


def test_pivot_rule_silent_when_centroid_at_base():
    geom = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        bounds_min=(-1.0, 0.0, -1.0),
        bounds_max=(1.0, 2.0, 1.0),
        size=(2.0, 2.0, 2.0),
    )
    issues = _check_pivot_at_base(_ctx(_manifest(geometry=geom), unity_retarget_preset()))
    # Centroid at y=1.0 — that's halfway up; rule should fire.
    assert len(issues) == 1


def test_pivot_rule_silent_when_centroid_in_lower_quartile():
    geom = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        bounds_min=(-1.0, 0.0, -1.0),
        bounds_max=(1.0, 8.0, 1.0),  # centroid_y = 4.0, base_y = 0.0
        size=(2.0, 8.0, 2.0),
    )
    # 4 / 8 = 0.5 → not in lower quartile, so rule fires.
    issues = _check_pivot_at_base(_ctx(_manifest(geometry=geom), unity_retarget_preset()))
    assert len(issues) == 1
    geom2 = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        bounds_min=(-1.0, 0.0, -1.0),
        bounds_max=(1.0, 16.0, 1.0),  # centroid 8 / 16 = 0.5 still
        size=(2.0, 16.0, 2.0),
    )
    issues2 = _check_pivot_at_base(_ctx(_manifest(geometry=geom2), unity_retarget_preset()))
    assert len(issues2) == 1
    geom3 = GeometrySummary(
        vertex_count=8,
        triangle_count=12,
        bounds_min=(0.0, 0.0, 0.0),
        bounds_max=(2.0, 8.0, 2.0),
        size=(2.0, 8.0, 2.0),
    )
    # centroid_y = 4.0; base = 0.0; ratio = 4/8 = 0.5 → fires.
    issues3 = _check_pivot_at_base(_ctx(_manifest(geometry=geom3), unity_retarget_preset()))
    assert len(issues3) == 1


# ---------------------------------------------------------------------------
# Collision
# ---------------------------------------------------------------------------


def test_collision_rule_silent_for_unity():
    """Unity preset doesn't require collision."""

    issues = _check_collision_present(_ctx(_manifest(), unity_retarget_preset()))
    assert issues == []


def test_collision_rule_flags_unreal_when_missing():
    issues = _check_collision_present(_ctx(_manifest(), unreal_retarget_preset()))
    assert len(issues) == 1
    assert issues[0].code == "collision_missing"


# ---------------------------------------------------------------------------
# Textures
# ---------------------------------------------------------------------------


def test_texture_rule_flags_non_pow2_for_unity():
    materials = (
        MaterialSpec(
            name="Mat",
            texture_slots=[
                TextureSlot(
                    role=TextureRole.base_color,
                    path=Path("a.png"),
                    resolution=(1023, 768),
                )
            ],
        ),
    )
    issues = _check_texture_pow2_strict(_ctx(_manifest(materials=materials), unity_retarget_preset()))
    assert any(i.code == "texture_not_power_of_two" for i in issues)


def test_texture_rule_flags_oversize_for_unity():
    materials = (
        MaterialSpec(
            name="Mat",
            texture_slots=[
                TextureSlot(
                    role=TextureRole.base_color,
                    path=Path("a.png"),
                    resolution=(8192, 8192),
                )
            ],
        ),
    )
    issues = _check_texture_pow2_strict(_ctx(_manifest(materials=materials), unity_retarget_preset()))
    assert any(i.code == "texture_exceeds_engine_cap" for i in issues)


def test_texture_rule_silent_for_compliant_textures():
    materials = (
        MaterialSpec(
            name="Mat",
            texture_slots=[
                TextureSlot(
                    role=TextureRole.base_color,
                    path=Path("a.png"),
                    resolution=(1024, 1024),
                )
            ],
        ),
    )
    issues = _check_texture_pow2_strict(_ctx(_manifest(materials=materials), unity_retarget_preset()))
    assert issues == []
