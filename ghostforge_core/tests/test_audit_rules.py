"""Per-rule audit checks.

Each test constructs a minimal :class:`AssetManifest` (or a mutated
copy) and runs a single rule's check function. This keeps the tests
fast and pinpoints which rule a future change would break.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.audit import AuditSeverity, default_preset, unity_preset
from ghostforge_core.audit.rules import (
    AuditContext,
    _check_collision_intent,
    _check_collision_mesh,
    _check_color_space,
    _check_geometry_counts,
    _check_geometry_normals,
    _check_geometry_scale,
    _check_lightmap_uvs,
    _check_lod_ordering,
    _check_lod_presence,
    _check_manifest_completeness,
    _check_manifest_engine_targets,
    _check_manifest_license,
    _check_naming_safe_chars,
    _check_texture_resolutions,
    _check_textures_exist,
    _check_uv_channels,
)
from ghostforge_core.manifest import (
    AssetManifest,
    CollisionIntent,
    CollisionSpec,
    EngineTarget,
    EngineTargetSpec,
    GeometrySummary,
    LODEntry,
    LicenseSpec,
    MaterialSpec,
    TextureRole,
    TextureSlot,
    Units,
)
from ghostforge_core.types import Artifact


def _ctx(manifest: AssetManifest, asset_dir: Path, preset=None) -> AuditContext:
    return AuditContext(
        manifest=manifest,
        asset_dir=asset_dir,
        preset=preset or default_preset(),
    )


def _basic_manifest(asset_dir: Path, **overrides) -> AssetManifest:
    fields = dict(
        asset_id="asset_test",
        license=LicenseSpec(spdx="CC0-1.0"),
        artifacts=[
            Artifact(
                path=asset_dir / "mesh.glb",
                sha256="0" * 64,
                bytes=1024,
                mime="model/gltf-binary",
                role="mesh.primary",
            )
        ],
        provenance=[],
    )
    fields.update(overrides)
    return AssetManifest(**fields)


# ---------------------------------------------------------------------------
# Manifest rules
# ---------------------------------------------------------------------------


def test_completeness_passes_for_basic(tmp_path):
    m = _basic_manifest(tmp_path)
    issues = _check_manifest_completeness(_ctx(m, tmp_path))
    # Provenance is empty -> warning; that's the only one
    assert all(i.severity != AuditSeverity.error for i in issues)


def test_completeness_no_artifacts_errors(tmp_path):
    m = _basic_manifest(tmp_path, artifacts=[])
    issues = _check_manifest_completeness(_ctx(m, tmp_path))
    codes = {i.code for i in issues}
    assert "no_artifacts" in codes
    assert "no_primary_mesh" in codes


def test_completeness_no_primary_mesh_errors(tmp_path):
    m = _basic_manifest(
        tmp_path,
        artifacts=[
            Artifact(
                path=tmp_path / "tex.png",
                sha256="0" * 64,
                bytes=1,
                mime="image/png",
                role="texture.base_color",
            )
        ],
    )
    issues = _check_manifest_completeness(_ctx(m, tmp_path))
    assert any(i.code == "no_primary_mesh" for i in issues)


def test_license_missing_errors(tmp_path):
    m = _basic_manifest(tmp_path, license=LicenseSpec())
    issues = _check_manifest_license(_ctx(m, tmp_path))
    assert any(i.code == "missing_license" for i in issues)


def test_license_allowlist(tmp_path):
    preset = default_preset().model_copy(update={"allowed_license_spdx": ["MIT"]})
    m = _basic_manifest(tmp_path, license=LicenseSpec(spdx="GPL-3.0"))
    issues = _check_manifest_license(_ctx(m, tmp_path, preset))
    assert any(i.code == "disallowed_license" for i in issues)


def test_engine_target_required(tmp_path):
    m = _basic_manifest(tmp_path)
    issues = _check_manifest_engine_targets(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "missing_engine_target" for i in issues)


def test_engine_target_satisfied_by_any(tmp_path):
    m = _basic_manifest(
        tmp_path, engine_targets=[EngineTargetSpec(engine=EngineTarget.any)]
    )
    issues = _check_manifest_engine_targets(_ctx(m, tmp_path, unity_preset()))
    assert issues == []


# ---------------------------------------------------------------------------
# Geometry rules
# ---------------------------------------------------------------------------


def _geo(**kwargs) -> GeometrySummary:
    base = dict(
        vertex_count=1000,
        triangle_count=1500,
        uv_channels=1,
        has_normals=True,
        size=(1.0, 1.0, 1.0),
    )
    base.update(kwargs)
    return GeometrySummary(**base)


def test_geometry_counts_within_preset(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo())
    issues = _check_geometry_counts(_ctx(m, tmp_path, unity_preset()))
    assert issues == []


def test_geometry_counts_too_many_triangles(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(triangle_count=1_000_000))
    issues = _check_geometry_counts(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "too_many_triangles" for i in issues)


def test_geometry_counts_too_many_vertices(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(vertex_count=200_000))
    issues = _check_geometry_counts(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "too_many_vertices" for i in issues)


def test_geometry_counts_empty_geometry_errors(tmp_path):
    m = _basic_manifest(
        tmp_path, geometry=_geo(vertex_count=0, triangle_count=0)
    )
    issues = _check_geometry_counts(_ctx(m, tmp_path))
    assert any(i.severity == AuditSeverity.error for i in issues)


def test_geometry_scale_too_large_warns(tmp_path):
    m = _basic_manifest(
        tmp_path, geometry=_geo(size=(2000.0, 2000.0, 2000.0), units=Units.meters)
    )
    issues = _check_geometry_scale(_ctx(m, tmp_path))
    assert any(i.code == "asset_too_large" for i in issues)


def test_geometry_normals_required(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(has_normals=False))
    issues = _check_geometry_normals(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "missing_normals" for i in issues)


def test_geometry_normals_skipped_when_preset_disables(tmp_path):
    preset = default_preset().model_copy(update={"require_normals": False})
    m = _basic_manifest(tmp_path, geometry=_geo(has_normals=False))
    assert _check_geometry_normals(_ctx(m, tmp_path, preset)) == []


# ---------------------------------------------------------------------------
# UV rules
# ---------------------------------------------------------------------------


def test_uv_channels_missing_errors(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(uv_channels=0))
    issues = _check_uv_channels(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "missing_uvs" for i in issues)


def test_uv_channels_satisfied(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(uv_channels=2))
    assert _check_uv_channels(_ctx(m, tmp_path, unity_preset())) == []


def test_lightmap_uv_required_by_unity(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(lightmap_uv_channel=None))
    issues = _check_lightmap_uvs(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "missing_lightmap_uv" for i in issues)


def test_lightmap_uv_present(tmp_path):
    m = _basic_manifest(tmp_path, geometry=_geo(lightmap_uv_channel=1))
    issues = _check_lightmap_uvs(_ctx(m, tmp_path, unity_preset()))
    assert issues == []


# ---------------------------------------------------------------------------
# Material / texture rules
# ---------------------------------------------------------------------------


def test_textures_exist_missing_file_errors(tmp_path):
    material = MaterialSpec(
        name="mat",
        texture_slots=[
            TextureSlot(role=TextureRole.base_color, path=tmp_path / "missing.png")
        ],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    issues = _check_textures_exist(_ctx(m, tmp_path))
    assert any(i.code == "texture_file_missing" for i in issues)


def test_textures_exist_passes_when_file_present(tmp_path):
    tex = tmp_path / "tex.png"
    tex.write_bytes(b"\x00")
    material = MaterialSpec(
        name="mat",
        texture_slots=[TextureSlot(role=TextureRole.base_color, path=tex)],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    assert _check_textures_exist(_ctx(m, tmp_path)) == []


def test_texture_too_large_warns(tmp_path):
    tex = tmp_path / "tex.png"
    tex.write_bytes(b"\x00")
    material = MaterialSpec(
        name="mat",
        texture_slots=[
            TextureSlot(
                role=TextureRole.base_color,
                path=tex,
                resolution=(8192, 8192),
            )
        ],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    issues = _check_texture_resolutions(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "texture_too_large" for i in issues)


def test_texture_not_power_of_two_warns(tmp_path):
    material = MaterialSpec(
        name="mat",
        texture_slots=[
            TextureSlot(
                role=TextureRole.base_color,
                path=tmp_path / "tex.png",
                resolution=(1500, 1500),
            )
        ],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    issues = _check_texture_resolutions(_ctx(m, tmp_path, unity_preset()))
    assert any(i.code == "texture_not_power_of_two" for i in issues)


def test_color_space_mismatch_for_normal_in_srgb(tmp_path):
    material = MaterialSpec(
        name="mat",
        texture_slots=[
            TextureSlot(
                role=TextureRole.normal,
                path=tmp_path / "n.png",
                color_space="sRGB",  # wrong; should be linear
            )
        ],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    issues = _check_color_space(_ctx(m, tmp_path))
    assert any(i.code == "color_space_mismatch" for i in issues)


def test_color_space_correct_when_base_color_srgb(tmp_path):
    material = MaterialSpec(
        name="mat",
        texture_slots=[
            TextureSlot(
                role=TextureRole.base_color,
                path=tmp_path / "bc.png",
                color_space="sRGB",
            )
        ],
    )
    m = _basic_manifest(tmp_path, materials=[material])
    assert _check_color_space(_ctx(m, tmp_path)) == []


# ---------------------------------------------------------------------------
# LOD rules
# ---------------------------------------------------------------------------


def test_lod_presence_required_warns(tmp_path):
    preset = default_preset().model_copy(update={"require_lods": True, "min_lod_count": 2})
    m = _basic_manifest(tmp_path)
    issues = _check_lod_presence(_ctx(m, tmp_path, preset))
    assert any(i.code == "missing_lods" for i in issues)


def test_lod_ordering_increasing_triangles_errors(tmp_path):
    lods = [
        LODEntry(level=0, triangle_count=100, mesh_path=tmp_path / "lod0.glb"),
        LODEntry(level=1, triangle_count=500, mesh_path=tmp_path / "lod1.glb"),
    ]
    m = _basic_manifest(tmp_path, lods=lods)
    issues = _check_lod_ordering(_ctx(m, tmp_path))
    assert any(i.code == "lod_triangle_count_increased" for i in issues)


def test_lod_ordering_descending_passes(tmp_path):
    lods = [
        LODEntry(level=0, triangle_count=1000, mesh_path=tmp_path / "lod0.glb"),
        LODEntry(level=1, triangle_count=500, mesh_path=tmp_path / "lod1.glb"),
        LODEntry(level=2, triangle_count=100, mesh_path=tmp_path / "lod2.glb"),
    ]
    m = _basic_manifest(tmp_path, lods=lods)
    assert _check_lod_ordering(_ctx(m, tmp_path)) == []


# ---------------------------------------------------------------------------
# Collision rules
# ---------------------------------------------------------------------------


def test_collision_intent_required_warns_when_none(tmp_path):
    preset = default_preset().model_copy(update={"require_collision_intent": True})
    m = _basic_manifest(tmp_path)
    issues = _check_collision_intent(_ctx(m, tmp_path, preset))
    assert any(i.code == "missing_collision_intent" for i in issues)


def test_collision_mesh_missing_when_intent_trimesh(tmp_path):
    spec = CollisionSpec(intent=CollisionIntent.trimesh, mesh_path=tmp_path / "cm.glb")
    m = _basic_manifest(tmp_path, collision=spec)
    issues = _check_collision_mesh(_ctx(m, tmp_path))
    assert any(i.code == "collision_mesh_missing" for i in issues)


def test_collision_mesh_passes_when_intent_box(tmp_path):
    spec = CollisionSpec(intent=CollisionIntent.box)
    m = _basic_manifest(tmp_path, collision=spec)
    assert _check_collision_mesh(_ctx(m, tmp_path)) == []


# ---------------------------------------------------------------------------
# Naming rules
# ---------------------------------------------------------------------------


def test_naming_unsafe_char_in_asset_id(tmp_path):
    m = _basic_manifest(tmp_path, asset_id="bad?id")
    issues = _check_naming_safe_chars(_ctx(m, tmp_path))
    assert any(i.code in {"unsafe_character", "unsafe_asset_id"} for i in issues)


def test_naming_safe_id_passes(tmp_path):
    m = _basic_manifest(tmp_path, asset_id="asset_001")
    issues = _check_naming_safe_chars(_ctx(m, tmp_path))
    assert all(i.severity != AuditSeverity.error for i in issues)
