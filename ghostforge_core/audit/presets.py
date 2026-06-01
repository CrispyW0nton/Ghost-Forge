"""Audit presets — engine-aware rule thresholds.

Presets capture the differences between "is this a sane glTF?" and
"will this drop into Unity HDRP / Unreal 5 with Nanite cleanly?". A
preset is just a frozen Pydantic model; rule functions read its fields
to decide what to enforce, what to warn about, and what to ignore.

Three presets ship by default:

* ``default`` — engine-agnostic floor. Demands a license, UVs, normals,
  and safe names; everything else is informational.
* ``unity`` — adds Unity's lightmap UV channel expectation, mesh-vertex
  ceiling, and PBR texture conventions.
* ``unreal`` — adds Unreal's content-path naming hints and slightly
  larger ceilings to match Nanite/Lumen-friendly assets.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from ..manifest import EngineTarget
from ..types import FrozenModel


class AuditPreset(FrozenModel):
    """Thresholds + toggles consulted by audit rules."""

    name: Literal["default", "unity", "unreal"] = "default"
    description: str = ""

    # Engine targeting
    require_engine_target: EngineTarget | None = None
    target_engines: list[EngineTarget] = Field(default_factory=list)

    # Geometry thresholds (apply per primary mesh)
    max_triangle_count: int | None = None
    max_vertex_count: int | None = None
    min_dimension_meters: float | None = 0.001
    max_dimension_meters: float | None = 500.0
    require_normals: bool = True
    warn_if_not_watertight: bool = False

    # UVs
    require_uvs: bool = True
    require_lightmap_uv_channel: int | None = None
    warn_overlapping_uvs: bool = True

    # Materials / textures
    max_texture_dimension: int | None = 4096
    require_power_of_two_textures: bool = False
    enforce_color_space: bool = True

    # LODs
    require_lods: bool = False
    min_lod_count: int = 1
    max_lod_count: int = 8

    # Collision
    require_collision_intent: bool = False

    # License
    require_license: bool = True
    allowed_license_spdx: list[str] | None = None

    # Naming
    disallowed_chars: str = '<>:"/\\|?*'
    max_name_length: int = 64
    require_safe_asset_id: bool = True


def default_preset() -> AuditPreset:
    return AuditPreset(
        name="default",
        description=(
            "Engine-agnostic readiness floor: license + safe names + sane "
            "geometry counts. Permissive on UVs and normals so abstract or "
            "in-progress assets don't fail; switch to 'unity' or 'unreal' "
            "before handoff to enforce the engine-specific rules."
        ),
        require_engine_target=None,
        target_engines=[EngineTarget.any],
        max_triangle_count=2_000_000,
        max_vertex_count=2_000_000,
        require_uvs=False,
        require_normals=False,
        require_lightmap_uv_channel=None,
        require_lods=False,
        require_collision_intent=False,
    )


def unity_preset() -> AuditPreset:
    return AuditPreset(
        name="unity",
        description=(
            "Unity HDRP/URP-ready preset. Enforces lightmap UV channel 1, "
            "65k-vert ceiling per submesh (16-bit index buffer default), and "
            "filesystem-safe Asset paths."
        ),
        require_engine_target=EngineTarget.unity,
        target_engines=[EngineTarget.unity],
        max_triangle_count=300_000,
        max_vertex_count=65_000,
        require_lightmap_uv_channel=1,
        require_lods=False,
        min_lod_count=1,
        require_collision_intent=False,
        max_texture_dimension=4096,
        require_power_of_two_textures=True,
        max_name_length=128,
    )


def unreal_preset() -> AuditPreset:
    return AuditPreset(
        name="unreal",
        description=(
            "Unreal Engine 5 preset (Nanite-friendly). Allows higher poly "
            "ceilings, expects /Game-style content paths, recommends LODs "
            "for non-Nanite static meshes."
        ),
        require_engine_target=EngineTarget.unreal,
        target_engines=[EngineTarget.unreal],
        max_triangle_count=2_000_000,
        max_vertex_count=2_000_000,
        require_lightmap_uv_channel=1,
        require_lods=False,
        min_lod_count=1,
        require_collision_intent=False,
        max_texture_dimension=8192,
        require_power_of_two_textures=False,
        max_name_length=128,
    )


PRESET_FACTORIES = {
    "default": default_preset,
    "unity": unity_preset,
    "unreal": unreal_preset,
}


def list_presets() -> list[AuditPreset]:
    return [factory() for factory in PRESET_FACTORIES.values()]


def get_preset(name: str) -> AuditPreset:
    try:
        return PRESET_FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(
            f"Unknown audit preset '{name}'. Known: {sorted(PRESET_FACTORIES)}"
        ) from exc


__all__ = [
    "AuditPreset",
    "PRESET_FACTORIES",
    "default_preset",
    "get_preset",
    "list_presets",
    "unity_preset",
    "unreal_preset",
]
