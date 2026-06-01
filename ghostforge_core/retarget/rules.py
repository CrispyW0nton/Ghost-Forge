"""Cross-engine retarget audit rules.

These rules answer one specific question: *given the engine target on
the audit preset, what would I need to fix before this asset imports
cleanly?* They are deliberately scoped to issues a normal game-readiness
audit doesn't catch — axis convention, units, naming patterns, lightmap
UVs, collision proxies, pivot location.

Each function follows the same shape as the existing ``ghostforge_core.
audit.rules`` checks (``check_*(ctx) -> list[AuditIssue]``) so they slot
into the same ``AuditRule`` registry without bespoke wiring.

Why a separate module:

* Keeps the cross-engine concerns reviewable in isolation — the output
  of these rules drives the auto-retarget planner.
* Lets the existing presets stay focused on geometry / texture sanity
  while the new ``unity_retarget`` / ``unreal_retarget`` presets add
  these rules on top.
"""

from __future__ import annotations

import math
from typing import Iterable

from ..audit.report import AuditIssue, AuditSeverity
from ..audit.rules import AuditContext, AuditRule
from ..manifest import EngineTarget
from .profiles import EngineConventions, get_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _target_engine(ctx: AuditContext) -> EngineTarget | None:
    """Pick the engine the preset is targeting, if any."""

    if ctx.preset.require_engine_target is not None:
        return ctx.preset.require_engine_target
    targets = [
        t for t in ctx.preset.target_engines if t != EngineTarget.any
    ]
    return targets[0] if targets else None


def _profile_for_target(target: EngineTarget | None) -> EngineConventions | None:
    if target is None:
        return None
    if target == EngineTarget.unity:
        return get_profile("unity")
    if target == EngineTarget.unreal:
        return get_profile("unreal")
    return None


def _largest_extent(ctx: AuditContext) -> float | None:
    geom = ctx.manifest.geometry
    if geom is None or geom.size is None:
        return None
    try:
        return float(max(geom.size))
    except (TypeError, ValueError):
        return None


def _centroid_estimate(ctx: AuditContext) -> tuple[float, float, float] | None:
    """Approximate centroid from manifest bounds (we don't load the mesh)."""

    geom = ctx.manifest.geometry
    if geom is None or geom.bounds_min is None or geom.bounds_max is None:
        return None
    return (
        0.5 * (geom.bounds_min[0] + geom.bounds_max[0]),
        0.5 * (geom.bounds_min[1] + geom.bounds_max[1]),
        0.5 * (geom.bounds_min[2] + geom.bounds_max[2]),
    )


def _is_pow2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _check_axis_convention(ctx: AuditContext) -> list[AuditIssue]:
    """We can't introspect axis convention from manifest alone; emit an info-level
    note so the planner knows to insert an axis swap regardless of detection."""

    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None:
        return []
    canonical = get_profile("gltf_canonical")
    if profile.axis_up == canonical.axis_up and profile.handedness == canonical.handedness:
        return []
    return [
        AuditIssue(
            rule="retarget.axis",
            severity=AuditSeverity.info,
            code="axis_mismatch_assumed",
            message=(
                f"Source assumed glTF canonical (right-handed, "
                f"{canonical.axis_up.upper()}-up); target {profile.label} expects "
                f"{profile.handedness}-handed, {profile.axis_up.upper()}-up. An "
                f"axis swap is required."
            ),
            suggestion=f"Insert a `retarget_axis` op targeting '{profile.name}'.",
            details={
                "from": canonical.model_dump(mode="json"),
                "to": profile.model_dump(mode="json"),
            },
        )
    ]


def _check_unit_scale(ctx: AuditContext) -> list[AuditIssue]:
    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None:
        return []
    if math.isclose(profile.units_to_meters, 1.0):
        return []
    factor = 1.0 / profile.units_to_meters
    extent = _largest_extent(ctx)
    extent_msg = (
        f" Largest mesh extent currently {extent:.4f} m → would become "
        f"{extent * factor:.2f} engine units."
        if extent is not None
        else ""
    )
    return [
        AuditIssue(
            rule="retarget.units",
            severity=AuditSeverity.warning,
            code="units_scale_required",
            message=(
                f"Target {profile.label} uses {profile.units_to_meters} m/unit; "
                f"asset is in metres. Apply scale factor {factor:g} to match.{extent_msg}"
            ),
            suggestion=f"Insert a `retarget_units` op with factor={factor:g}.",
            details={"factor": factor, "engine_units_to_meters": profile.units_to_meters},
        )
    ]


def _check_naming_convention(ctx: AuditContext) -> list[AuditIssue]:
    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None or profile.naming.static_mesh_prefix == "":
        return []
    issues: list[AuditIssue] = []
    name = ctx.manifest.name or ctx.manifest.asset_id
    if name and not name.startswith(profile.naming.static_mesh_prefix):
        issues.append(
            AuditIssue(
                rule="retarget.naming",
                severity=AuditSeverity.info,
                code="static_mesh_prefix_missing",
                message=(
                    f"Asset name {name!r} does not start with "
                    f"{profile.naming.static_mesh_prefix!r} expected by {profile.label}."
                ),
                suggestion=(
                    f"Insert a `retarget_apply_naming` op with target='{profile.name}'."
                ),
                target=name,
            )
        )
    for material in ctx.manifest.materials or []:
        mname = material.name
        if mname and not mname.startswith(profile.naming.material_prefix):
            issues.append(
                AuditIssue(
                    rule="retarget.naming",
                    severity=AuditSeverity.info,
                    code="material_prefix_missing",
                    message=(
                        f"Material {mname!r} does not start with "
                        f"{profile.naming.material_prefix!r}."
                    ),
                    target=mname,
                )
            )
    return issues


def _check_lightmap_uv_channel(ctx: AuditContext) -> list[AuditIssue]:
    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None or profile.require_lightmap_uv_channel is None:
        return []
    geom = ctx.manifest.geometry
    if geom is None:
        return []
    declared = geom.lightmap_uv_channel
    expected = profile.require_lightmap_uv_channel
    if declared == expected:
        return []
    return [
        AuditIssue(
            rule="retarget.lightmap_uv",
            severity=AuditSeverity.warning,
            code="lightmap_uv_channel_missing",
            message=(
                f"{profile.label} expects a lightmap UV on channel {expected}; "
                f"manifest declares "
                f"{'none' if declared is None else f'channel {declared}'}."
            ),
            suggestion=(
                "Bake a non-overlapping UV chart with xatlas at "
                f"{profile.lightmap_padding_pixels}-pixel padding and store it "
                f"on UV channel {expected}."
            ),
            details={
                "expected_channel": expected,
                "declared_channel": declared,
                "padding_pixels": profile.lightmap_padding_pixels,
            },
        )
    ]


def _check_pivot_at_base(ctx: AuditContext) -> list[AuditIssue]:
    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None or not profile.require_pivot_at_base:
        return []
    geom = ctx.manifest.geometry
    if geom is None or geom.bounds_min is None:
        return []
    centroid = _centroid_estimate(ctx)
    if centroid is None:
        return []
    # "Base" = lowest along the engine's up axis. We approximate by
    # checking the centroid's offset from bounds_min along that axis.
    axis_index = {"x": 0, "y": 1, "z": 2}[profile.axis_up]
    base = geom.bounds_min[axis_index]
    centroid_axis = centroid[axis_index]
    extent_axis = (
        geom.bounds_max[axis_index] - geom.bounds_min[axis_index]
        if geom.bounds_max is not None
        else 0.0
    )
    if extent_axis <= 0.0:
        return []
    # Tolerance: pivot is "at base" if centroid sits within the bottom 25%.
    if (centroid_axis - base) / extent_axis <= 0.25:
        return []
    return [
        AuditIssue(
            rule="retarget.pivot",
            severity=AuditSeverity.warning,
            code="pivot_not_at_base",
            message=(
                f"{profile.label} expects pivot at the asset base on "
                f"{profile.axis_up.upper()}-up. Current centroid sits "
                f"{(centroid_axis - base):.3f} above base "
                f"(extent {extent_axis:.3f})."
            ),
            suggestion="Insert a `retarget_pivot_for_engine` op.",
            details={"axis_up": profile.axis_up},
        )
    ]


def _check_collision_present(ctx: AuditContext) -> list[AuditIssue]:
    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None or not profile.require_collision:
        return []
    collision = ctx.manifest.collision
    if collision is not None and collision.intent and collision.intent.value != "none":
        return []
    return [
        AuditIssue(
            rule="retarget.collision",
            severity=AuditSeverity.warning,
            code="collision_missing",
            message=(
                f"{profile.label} expects a collision proxy. Manifest "
                "declares no collision."
            ),
            suggestion=(
                "Bake a convex hull collision (Unreal naming "
                "`UCX_<name>_00`) and declare collision intent in the manifest."
            ),
        )
    ]


def _check_texture_pow2_strict(ctx: AuditContext) -> list[AuditIssue]:
    """Stricter version than the default audit's pow2 check.

    The default rule only flags textures when ``preset.require_power_of_two_textures``
    is true. The retarget rule additionally flags textures whose dimensions
    exceed the engine's hard cap, which matters for runtime VRAM budgets
    on console targets.
    """

    target = _target_engine(ctx)
    profile = _profile_for_target(target)
    if profile is None:
        return []
    issues: list[AuditIssue] = []
    cap = profile.max_texture_dimension
    for material in ctx.manifest.materials or []:
        for slot in material.texture_slots or []:
            if slot.resolution is None:
                continue
            w, h = slot.resolution
            if profile.require_pow2_textures and not (_is_pow2(w) and _is_pow2(h)):
                issues.append(
                    AuditIssue(
                        rule="retarget.textures",
                        severity=AuditSeverity.warning,
                        code="texture_not_power_of_two",
                        message=(
                            f"{profile.label} expects power-of-two textures; "
                            f"{slot.path.name} is {w}x{h}."
                        ),
                        target=str(slot.path),
                    )
                )
            if cap is not None and (w > cap or h > cap):
                issues.append(
                    AuditIssue(
                        rule="retarget.textures",
                        severity=AuditSeverity.warning,
                        code="texture_exceeds_engine_cap",
                        message=(
                            f"{slot.path.name} is {w}x{h}, exceeding {profile.label}'s "
                            f"{cap}px cap."
                        ),
                        target=str(slot.path),
                        details={"engine_cap": cap},
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------


CROSS_ENGINE_RULES: list[AuditRule] = [
    AuditRule(
        id="retarget.axis",
        title="Axis convention matches engine",
        description="Source glTF axes vs target engine axes; informational unless the planner needs to add a retarget op.",
        check=_check_axis_convention,
    ),
    AuditRule(
        id="retarget.units",
        title="Unit scale matches engine",
        description="Asset metres vs engine units (Unity=1m, Unreal=1cm).",
        check=_check_unit_scale,
    ),
    AuditRule(
        id="retarget.naming",
        title="Naming follows engine convention",
        description="Asset / material / texture prefixes match engine's expected pattern.",
        check=_check_naming_convention,
    ),
    AuditRule(
        id="retarget.lightmap_uv",
        title="Lightmap UV channel present",
        description="Engine-specific second UV channel for lightmap baking.",
        check=_check_lightmap_uv_channel,
    ),
    AuditRule(
        id="retarget.pivot",
        title="Pivot at engine-expected location",
        description="Centroid heuristic for whether the pivot sits at the asset base.",
        check=_check_pivot_at_base,
    ),
    AuditRule(
        id="retarget.collision",
        title="Collision proxy present when required",
        description="Engine-required collision intent declared on the manifest.",
        check=_check_collision_present,
    ),
    AuditRule(
        id="retarget.textures",
        title="Textures within engine constraints",
        description="Power-of-two and engine VRAM caps.",
        check=_check_texture_pow2_strict,
    ),
]


def cross_engine_rule_ids() -> list[str]:
    return [rule.id for rule in CROSS_ENGINE_RULES]


__all__ = [
    "CROSS_ENGINE_RULES",
    "cross_engine_rule_ids",
]
