"""Declarative engine profiles for cross-engine retargeting.

Every supported game engine has its own coordinate system, units, and
naming conventions. Retargeting works by treating GhostForge's *internal*
representation as the canonical glTF orientation (right-handed, Y-up,
-Z forward, units in meters) and per-engine profiles describe the
delta to apply when shipping there.

A profile is a frozen Pydantic model so it can be JSON-serialised over
the v2 API and the MCP surface; the canonical instances are defined as
factory functions in this module so callers get a fresh copy that can
be tweaked per asset (e.g. forcing a metric Unreal pipeline) without
mutating the global default.
"""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field

from ..types import FrozenModel


Axis = Literal["x", "y", "z"]
Handedness = Literal["left", "right"]


class NamingConventions(FrozenModel):
    """Per-engine asset naming hints.

    Empty strings mean "no constraint". The auto-retarget planner uses
    these to apply non-destructive name patches; the audit linter uses
    them to surface ``info``-level warnings when names disagree.
    """

    static_mesh_prefix: str = ""
    skeletal_mesh_prefix: str = ""
    material_prefix: str = ""
    material_instance_prefix: str = ""
    texture_prefix: str = ""
    collision_prefix: str = ""
    asset_path_pattern: str | None = None  # e.g. "/Game/<category>/<name>" for Unreal


class EngineConventions(FrozenModel):
    """A single engine target's coordinate / unit / naming spec."""

    name: str  # stable id, e.g. "unity", "unreal"
    label: str  # human-readable, e.g. "Unity (HDRP/URP)"
    axis_up: Axis = "y"
    axis_forward: Axis = "z"
    handedness: Handedness = "right"
    units_to_meters: float = Field(
        default=1.0,
        gt=0.0,
        description="How many meters one unit in this engine equals. Unity=1, Unreal=0.01.",
    )
    require_lightmap_uv_channel: int | None = None
    lightmap_padding_pixels: int = 4
    require_collision: bool = False
    require_pivot_at_base: bool = False
    require_pow2_textures: bool = False
    max_texture_dimension: int | None = None
    naming: NamingConventions = NamingConventions()


# ---------------------------------------------------------------------------
# Canonical profiles
# ---------------------------------------------------------------------------


def gltf_canonical_profile() -> EngineConventions:
    """The reference profile.

    Equal to the glTF 2.0 default frame: right-handed, Y-up, -Z forward,
    units in meters. The retarget planner uses this as the assumed input
    when no other profile is declared on the manifest.
    """

    return EngineConventions(
        name="gltf_canonical",
        label="glTF 2.0 (canonical)",
        axis_up="y",
        axis_forward="z",  # +Z is camera-back; "forward" stays z to keep ops simple
        handedness="right",
        units_to_meters=1.0,
    )


def unity_profile() -> EngineConventions:
    """Unity 6 / HDRP-friendly defaults.

    Unity is left-handed, Y-up, +Z forward, units in meters.
    """

    return EngineConventions(
        name="unity",
        label="Unity 6 (HDRP/URP)",
        axis_up="y",
        axis_forward="z",
        handedness="left",
        units_to_meters=1.0,
        require_lightmap_uv_channel=1,
        lightmap_padding_pixels=4,
        require_collision=False,
        require_pivot_at_base=True,
        require_pow2_textures=True,
        max_texture_dimension=4096,
        naming=NamingConventions(),  # Unity is permissive on names
    )


def unreal_profile() -> EngineConventions:
    """Unreal Engine 5 defaults.

    Unreal is left-handed, Z-up, +X forward, units in centimetres
    (1 unit = 1 cm = 0.01 m). Naming conventions are strict by default
    so the retargeter will rename meshes and materials to match.
    """

    return EngineConventions(
        name="unreal",
        label="Unreal Engine 5",
        axis_up="z",
        axis_forward="x",
        handedness="left",
        units_to_meters=0.01,
        require_lightmap_uv_channel=1,
        lightmap_padding_pixels=4,
        require_collision=True,
        require_pivot_at_base=True,
        require_pow2_textures=False,
        max_texture_dimension=8192,
        naming=NamingConventions(
            static_mesh_prefix="SM_",
            skeletal_mesh_prefix="SK_",
            material_prefix="M_",
            material_instance_prefix="MI_",
            texture_prefix="T_",
            collision_prefix="UCX_",
            asset_path_pattern="/Game/<category>/<name>",
        ),
    )


PROFILE_FACTORIES = {
    "gltf_canonical": gltf_canonical_profile,
    "unity": unity_profile,
    "unreal": unreal_profile,
}


def get_profile(name: str) -> EngineConventions:
    try:
        return PROFILE_FACTORIES[name]()
    except KeyError as exc:
        raise ValueError(
            f"Unknown engine profile {name!r}. Known: {sorted(PROFILE_FACTORIES)}"
        ) from exc


def list_profiles() -> list[EngineConventions]:
    return [factory() for factory in PROFILE_FACTORIES.values()]


__all__ = [
    "EngineConventions",
    "NamingConventions",
    "PROFILE_FACTORIES",
    "get_profile",
    "gltf_canonical_profile",
    "list_profiles",
    "unity_profile",
    "unreal_profile",
]
