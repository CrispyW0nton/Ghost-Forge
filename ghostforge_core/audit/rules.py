"""Concrete audit rules.

Each rule is a small, sync function ``check_<name>(ctx) -> AuditRuleResult``.
They share a uniform shape so the runner can iterate them without
special-casing. Rules are intentionally cheap and side-effect-free so
they can be re-run many times — for example, before every engine
handoff, or as part of a CI gate.

Rule philosophy:

* **Errors block.** Engine handoff refuses to ship assets with errors
  unless the agent passes ``force=True``.
* **Warnings inform.** Engine handoff still ships warnings but the
  manifest's audit history records them so downstream tools can flag
  unfinished assets.
* **Skipping is honest.** A rule that can't run (missing optional
  dep, mesh file gone, etc.) records ``skipped=True`` instead of
  silently passing.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..manifest import AssetManifest, EngineTarget, TextureRole
from .presets import AuditPreset
from .report import (
    AuditIssue,
    AuditRuleResult,
    AuditSeverity,
    rule_status,
)

NAME_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_\-./ ]+$")
ENGINE_PATH_PATTERN = re.compile(r"^[A-Za-z0-9_\-./ ]+$")


@dataclass
class AuditContext:
    """Read-only context passed to every rule."""

    manifest: AssetManifest
    asset_dir: Path
    preset: AuditPreset


@dataclass(frozen=True)
class AuditRule:
    """Static rule descriptor + check callable."""

    id: str
    title: str
    description: str
    check: Callable[[AuditContext], list[AuditIssue]]


# ---------------------------------------------------------------------------
# Manifest rules
# ---------------------------------------------------------------------------


def _check_manifest_completeness(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    m = ctx.manifest
    if not m.asset_id:
        issues.append(
            AuditIssue(
                rule="manifest.completeness",
                severity=AuditSeverity.error,
                code="missing_asset_id",
                message="Manifest does not declare an asset_id",
                suggestion="Operations should always seed an asset_id; check the source pipeline.",
            )
        )
    if not m.artifacts:
        issues.append(
            AuditIssue(
                rule="manifest.completeness",
                severity=AuditSeverity.error,
                code="no_artifacts",
                message="Manifest has no artifacts; nothing to ship.",
            )
        )
    primary = next((a for a in m.artifacts if a.role == "mesh.primary"), None)
    if primary is None:
        issues.append(
            AuditIssue(
                rule="manifest.completeness",
                severity=AuditSeverity.error,
                code="no_primary_mesh",
                message="No artifact with role 'mesh.primary'",
                suggestion="Run image_to_3d with a reference image, or unwrap an existing mesh to seed a primary mesh.",
            )
        )
    if not m.provenance:
        issues.append(
            AuditIssue(
                rule="manifest.completeness",
                severity=AuditSeverity.warning,
                code="no_provenance",
                message="Manifest has no provenance steps",
                suggestion="Provenance helps downstream auditing; ensure operations record their steps.",
            )
        )
    return issues


def _check_manifest_license(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.require_license:
        return issues
    spec = ctx.manifest.license
    if not spec.spdx and not spec.name:
        issues.append(
            AuditIssue(
                rule="manifest.license",
                severity=AuditSeverity.error,
                code="missing_license",
                message="Manifest license has neither SPDX id nor a free-form name",
                suggestion=(
                    "Set license.spdx (e.g. 'CC0-1.0', 'MIT', 'CC-BY-4.0') or "
                    "license.name. Use 'project-internal' for in-house assets."
                ),
            )
        )
    allowed = ctx.preset.allowed_license_spdx
    if allowed is not None and spec.spdx and spec.spdx not in allowed:
        issues.append(
            AuditIssue(
                rule="manifest.license",
                severity=AuditSeverity.error,
                code="disallowed_license",
                message=f"License '{spec.spdx}' is not in the preset's allowlist",
                target=spec.spdx,
                details={"allowed": list(allowed)},
            )
        )
    return issues


def _check_manifest_engine_targets(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    required = ctx.preset.require_engine_target
    if required is None:
        return issues
    declared = {spec.engine for spec in ctx.manifest.engine_targets}
    if required not in declared and EngineTarget.any not in declared:
        issues.append(
            AuditIssue(
                rule="manifest.engine_targets",
                severity=AuditSeverity.error,
                code="missing_engine_target",
                message=(
                    f"Preset '{ctx.preset.name}' expects engine target "
                    f"'{required.value}' but the manifest declares "
                    f"{[e.value for e in declared] or '[]'}"
                ),
                suggestion=(
                    "Call update_asset_manifest with engine_targets=['"
                    f"{required.value}'] before running this audit."
                ),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Geometry rules
# ---------------------------------------------------------------------------


def _primary_mesh_path(ctx: AuditContext) -> Path | None:
    for artifact in ctx.manifest.artifacts:
        if artifact.role == "mesh.primary":
            candidate = Path(artifact.path)
            if not candidate.is_absolute():
                candidate = (ctx.asset_dir / candidate).resolve()
            return candidate
    return None


def _check_geometry_counts(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    geo = ctx.manifest.geometry
    if geo is None:
        issues.append(
            AuditIssue(
                rule="geometry.counts",
                severity=AuditSeverity.warning,
                code="no_geometry_summary",
                message="Manifest has no GeometrySummary; cannot audit triangle/vertex counts.",
                suggestion="Operations should populate manifest.geometry from build_geometry_summary().",
            )
        )
        return issues
    if geo.vertex_count == 0 or geo.triangle_count == 0:
        issues.append(
            AuditIssue(
                rule="geometry.counts",
                severity=AuditSeverity.error,
                code="empty_geometry",
                message=f"Mesh has {geo.vertex_count} verts / {geo.triangle_count} tris",
            )
        )
        return issues
    if ctx.preset.max_vertex_count and geo.vertex_count > ctx.preset.max_vertex_count:
        issues.append(
            AuditIssue(
                rule="geometry.counts",
                severity=AuditSeverity.error,
                code="too_many_vertices",
                message=(
                    f"{geo.vertex_count:,} vertices exceeds preset cap "
                    f"({ctx.preset.max_vertex_count:,})"
                ),
                suggestion=(
                    "Decimate or split the mesh; submit_refine_mesh with "
                    f"target_face_count<{ctx.preset.max_triangle_count or 'cap'}."
                ),
                details={"actual": geo.vertex_count, "max": ctx.preset.max_vertex_count},
            )
        )
    if ctx.preset.max_triangle_count and geo.triangle_count > ctx.preset.max_triangle_count:
        issues.append(
            AuditIssue(
                rule="geometry.counts",
                severity=AuditSeverity.error,
                code="too_many_triangles",
                message=(
                    f"{geo.triangle_count:,} triangles exceeds preset cap "
                    f"({ctx.preset.max_triangle_count:,})"
                ),
                details={"actual": geo.triangle_count, "max": ctx.preset.max_triangle_count},
            )
        )
    return issues


def _check_geometry_scale(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    geo = ctx.manifest.geometry
    if geo is None or geo.size is None:
        return issues
    largest = max(geo.size)
    smallest = min(geo.size)
    if ctx.preset.max_dimension_meters and largest > ctx.preset.max_dimension_meters:
        issues.append(
            AuditIssue(
                rule="geometry.scale",
                severity=AuditSeverity.warning,
                code="asset_too_large",
                message=(
                    f"Largest dimension {largest:.2f}{geo.units.value} exceeds preset "
                    f"max ({ctx.preset.max_dimension_meters})."
                ),
                suggestion="Re-export with the correct scene units or scale before handoff.",
                details={"size": list(geo.size), "units": geo.units.value},
            )
        )
    if ctx.preset.min_dimension_meters and smallest < ctx.preset.min_dimension_meters:
        issues.append(
            AuditIssue(
                rule="geometry.scale",
                severity=AuditSeverity.warning,
                code="asset_too_small",
                message=(
                    f"Smallest dimension {smallest:.4f}{geo.units.value} below preset "
                    f"min ({ctx.preset.min_dimension_meters})."
                ),
                details={"size": list(geo.size), "units": geo.units.value},
            )
        )
    return issues


def _check_geometry_normals(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.require_normals:
        return issues
    geo = ctx.manifest.geometry
    if geo is None:
        return issues
    if not geo.has_normals:
        issues.append(
            AuditIssue(
                rule="geometry.normals",
                severity=AuditSeverity.error,
                code="missing_normals",
                message="Mesh has no vertex normals; engine importers will recompute them with smoothing artefacts.",
                suggestion="Bake or generate normals before export; trimesh.smoothing or DCC tooling.",
            )
        )
    return issues


def _check_geometry_watertight(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.warn_if_not_watertight:
        return issues
    geo = ctx.manifest.geometry
    if geo is None or geo.watertight:
        return issues
    issues.append(
        AuditIssue(
            rule="geometry.watertight",
            severity=AuditSeverity.warning,
            code="not_watertight",
            message="Mesh is not watertight; collision, baking, and SDF generation may behave unexpectedly.",
        )
    )
    return issues


# ---------------------------------------------------------------------------
# UV rules
# ---------------------------------------------------------------------------


def _check_uv_channels(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.require_uvs:
        return issues
    geo = ctx.manifest.geometry
    if geo is None:
        return issues
    if geo.uv_channels < 1:
        issues.append(
            AuditIssue(
                rule="uvs.channels",
                severity=AuditSeverity.error,
                code="missing_uvs",
                message="Mesh has no UV channels; engine importers cannot apply textures.",
                suggestion="Run submit_unwrap to generate UVs (xatlas).",
            )
        )
    return issues


def _check_lightmap_uvs(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    required = ctx.preset.require_lightmap_uv_channel
    if required is None:
        return issues
    geo = ctx.manifest.geometry
    if geo is None:
        return issues
    if geo.lightmap_uv_channel != required:
        issues.append(
            AuditIssue(
                rule="uvs.lightmap",
                severity=AuditSeverity.warning,
                code="missing_lightmap_uv",
                message=(
                    f"Preset expects lightmap UVs on channel {required}; "
                    f"manifest declares channel {geo.lightmap_uv_channel}."
                ),
                suggestion="Generate a non-overlapping lightmap UV channel before shipping to the engine.",
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Material / texture rules
# ---------------------------------------------------------------------------


def _is_power_of_two(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _check_textures_exist(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    for material in ctx.manifest.materials:
        for slot in material.texture_slots:
            path = Path(slot.path)
            if not path.is_absolute():
                path = (ctx.asset_dir / path).resolve()
            if not path.exists():
                issues.append(
                    AuditIssue(
                        rule="materials.textures_exist",
                        severity=AuditSeverity.error,
                        code="texture_file_missing",
                        message=f"Texture '{path}' is referenced by material '{material.name}' but missing on disk.",
                        target=str(path),
                    )
                )
    return issues


def _check_texture_resolutions(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    cap = ctx.preset.max_texture_dimension
    for material in ctx.manifest.materials:
        for slot in material.texture_slots:
            res = slot.resolution
            if res is None:
                continue
            w, h = res
            if cap is not None and (w > cap or h > cap):
                issues.append(
                    AuditIssue(
                        rule="materials.texture_resolution",
                        severity=AuditSeverity.warning,
                        code="texture_too_large",
                        message=(
                            f"Texture '{slot.path}' is {w}x{h}; preset cap is {cap}."
                        ),
                        target=str(slot.path),
                        suggestion="Downscale the texture or relax the preset.",
                    )
                )
            if ctx.preset.require_power_of_two_textures and not (
                _is_power_of_two(w) and _is_power_of_two(h)
            ):
                issues.append(
                    AuditIssue(
                        rule="materials.texture_resolution",
                        severity=AuditSeverity.warning,
                        code="texture_not_power_of_two",
                        message=f"Texture '{slot.path}' is {w}x{h}; engine importers prefer power-of-two.",
                        target=str(slot.path),
                    )
                )
    return issues


def _check_color_space(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.enforce_color_space:
        return issues

    expected: dict[TextureRole, str] = {
        TextureRole.base_color: "sRGB",
        TextureRole.emissive: "sRGB",
        TextureRole.normal: "linear",
        TextureRole.metallic: "linear",
        TextureRole.roughness: "linear",
        TextureRole.metallic_roughness: "linear",
        TextureRole.orm: "linear",
        TextureRole.occlusion: "linear",
        TextureRole.height: "linear",
    }
    for material in ctx.manifest.materials:
        for slot in material.texture_slots:
            want = expected.get(slot.role)
            if want is None:
                continue
            if slot.color_space != want:
                issues.append(
                    AuditIssue(
                        rule="materials.color_space",
                        severity=AuditSeverity.warning,
                        code="color_space_mismatch",
                        message=(
                            f"Texture '{slot.path}' role '{slot.role.value}' is "
                            f"'{slot.color_space}'; expected '{want}'."
                        ),
                        target=str(slot.path),
                        suggestion=f"Re-tag the texture slot color_space='{want}'.",
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# LOD rules
# ---------------------------------------------------------------------------


def _check_lod_presence(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.require_lods:
        return issues
    if len(ctx.manifest.lods) < ctx.preset.min_lod_count:
        issues.append(
            AuditIssue(
                rule="lods.presence",
                severity=AuditSeverity.warning,
                code="missing_lods",
                message=(
                    f"Manifest declares {len(ctx.manifest.lods)} LODs; preset "
                    f"requires at least {ctx.preset.min_lod_count}."
                ),
            )
        )
    return issues


def _check_lod_ordering(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    lods = ctx.manifest.lods
    if not lods:
        return issues
    sorted_by_level = sorted(lods, key=lambda l: l.level)
    last = None
    for entry in sorted_by_level:
        if last is not None and entry.triangle_count > last.triangle_count:
            issues.append(
                AuditIssue(
                    rule="lods.ordering",
                    severity=AuditSeverity.error,
                    code="lod_triangle_count_increased",
                    message=(
                        f"LOD{entry.level} has {entry.triangle_count} triangles, "
                        f"more than LOD{last.level}'s {last.triangle_count}."
                    ),
                    target=str(entry.mesh_path),
                )
            )
        last = entry
    if len(lods) > ctx.preset.max_lod_count:
        issues.append(
            AuditIssue(
                rule="lods.ordering",
                severity=AuditSeverity.warning,
                code="too_many_lods",
                message=(
                    f"Manifest has {len(lods)} LOD entries; preset cap is {ctx.preset.max_lod_count}."
                ),
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Collision rules
# ---------------------------------------------------------------------------


def _check_collision_intent(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    if not ctx.preset.require_collision_intent:
        return issues
    intent = ctx.manifest.collision.intent.value
    if intent == "none":
        issues.append(
            AuditIssue(
                rule="collision.intent",
                severity=AuditSeverity.warning,
                code="missing_collision_intent",
                message="Collision intent is 'none'; the engine will skip collider generation.",
                suggestion="Set CollisionSpec.intent to 'auto', 'box', 'capsule', 'convex', or 'trimesh'.",
            )
        )
    return issues


def _check_collision_mesh(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    intent = ctx.manifest.collision.intent.value
    if intent in {"convex", "trimesh"}:
        mesh_path = ctx.manifest.collision.mesh_path
        if mesh_path is None:
            issues.append(
                AuditIssue(
                    rule="collision.mesh",
                    severity=AuditSeverity.warning,
                    code="missing_collision_mesh",
                    message=(
                        f"Collision intent is '{intent}' but no mesh_path is set; "
                        "engines may default to the visual mesh, which can be expensive."
                    ),
                )
            )
        else:
            candidate = Path(mesh_path)
            if not candidate.is_absolute():
                candidate = (ctx.asset_dir / candidate).resolve()
            if not candidate.exists():
                issues.append(
                    AuditIssue(
                        rule="collision.mesh",
                        severity=AuditSeverity.error,
                        code="collision_mesh_missing",
                        message=f"Collision mesh '{candidate}' is missing on disk.",
                        target=str(candidate),
                    )
                )
    return issues


# ---------------------------------------------------------------------------
# Naming rules
# ---------------------------------------------------------------------------


def _check_naming_safe_chars(ctx: AuditContext) -> list[AuditIssue]:
    issues: list[AuditIssue] = []
    bad = ctx.preset.disallowed_chars

    def _has_bad_char(value: str) -> str | None:
        for ch in bad:
            if ch in value:
                return ch
        return None

    targets: list[tuple[str, str]] = [("asset_id", ctx.manifest.asset_id)]
    if ctx.manifest.name:
        targets.append(("name", ctx.manifest.name))
    for material in ctx.manifest.materials:
        targets.append((f"material:{material.name}", material.name))

    for label, value in targets:
        bad_char = _has_bad_char(value)
        if bad_char:
            issues.append(
                AuditIssue(
                    rule="naming.safe_chars",
                    severity=AuditSeverity.error,
                    code="unsafe_character",
                    message=f"{label} contains disallowed char '{bad_char}'",
                    target=value,
                )
            )
        if len(value) > ctx.preset.max_name_length:
            issues.append(
                AuditIssue(
                    rule="naming.length",
                    severity=AuditSeverity.warning,
                    code="name_too_long",
                    message=(
                        f"{label} length {len(value)} exceeds preset max "
                        f"({ctx.preset.max_name_length})"
                    ),
                    target=value,
                )
            )

    if ctx.preset.require_safe_asset_id and not NAME_SAFE_PATTERN.match(ctx.manifest.asset_id):
        issues.append(
            AuditIssue(
                rule="naming.asset_id",
                severity=AuditSeverity.error,
                code="unsafe_asset_id",
                message=(
                    f"asset_id '{ctx.manifest.asset_id}' contains characters that "
                    "may break engine import paths"
                ),
                suggestion="Use only [A-Za-z0-9_-./] in asset ids.",
            )
        )
    return issues


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------


def _wrap(check: Callable[[AuditContext], list[AuditIssue]]) -> Callable[[AuditContext], list[AuditIssue]]:
    return check


DEFAULT_RULES: list[AuditRule] = [
    AuditRule(
        id="manifest.completeness",
        title="Manifest is complete",
        description="Asset id, primary mesh artifact, and provenance are present.",
        check=_wrap(_check_manifest_completeness),
    ),
    AuditRule(
        id="manifest.license",
        title="License is declared",
        description="Asset has an SPDX or named license; allowlist enforced if set.",
        check=_wrap(_check_manifest_license),
    ),
    AuditRule(
        id="manifest.engine_targets",
        title="Engine targets match preset",
        description="Manifest declares the engine the preset is auditing against.",
        check=_wrap(_check_manifest_engine_targets),
    ),
    AuditRule(
        id="geometry.counts",
        title="Geometry counts within preset",
        description="Vertex and triangle counts within preset bounds; no empty geometry.",
        check=_wrap(_check_geometry_counts),
    ),
    AuditRule(
        id="geometry.scale",
        title="Geometry scale within preset",
        description="Bounding-box dimensions are sane for the target engine.",
        check=_wrap(_check_geometry_scale),
    ),
    AuditRule(
        id="geometry.normals",
        title="Geometry has normals",
        description="Vertex normals are present so engines don't recompute with artefacts.",
        check=_wrap(_check_geometry_normals),
    ),
    AuditRule(
        id="geometry.watertight",
        title="Geometry watertightness",
        description="Optional check; matters for collision and SDF baking.",
        check=_wrap(_check_geometry_watertight),
    ),
    AuditRule(
        id="uvs.channels",
        title="UV channels present",
        description="Mesh has at least one UV channel for texturing.",
        check=_wrap(_check_uv_channels),
    ),
    AuditRule(
        id="uvs.lightmap",
        title="Lightmap UV channel present",
        description="Engine-specific second UV channel for static lightmaps.",
        check=_wrap(_check_lightmap_uvs),
    ),
    AuditRule(
        id="materials.textures_exist",
        title="Texture files exist",
        description="Every texture slot path resolves to a file on disk.",
        check=_wrap(_check_textures_exist),
    ),
    AuditRule(
        id="materials.texture_resolution",
        title="Texture resolutions within preset",
        description="Texture dimensions within preset cap; optionally power-of-two.",
        check=_wrap(_check_texture_resolutions),
    ),
    AuditRule(
        id="materials.color_space",
        title="Texture color spaces match role",
        description="Base color/emissive textures sRGB; data textures linear.",
        check=_wrap(_check_color_space),
    ),
    AuditRule(
        id="lods.presence",
        title="LOD count within preset",
        description="Asset declares enough LODs for the preset.",
        check=_wrap(_check_lod_presence),
    ),
    AuditRule(
        id="lods.ordering",
        title="LODs ordered by triangle count",
        description="Higher LOD index has fewer triangles; total LODs within cap.",
        check=_wrap(_check_lod_ordering),
    ),
    AuditRule(
        id="collision.intent",
        title="Collision intent declared",
        description="Asset declares an explicit collision intent.",
        check=_wrap(_check_collision_intent),
    ),
    AuditRule(
        id="collision.mesh",
        title="Collision mesh resolves",
        description="When intent is convex/trimesh, the mesh file exists.",
        check=_wrap(_check_collision_mesh),
    ),
    AuditRule(
        id="naming.safe_chars",
        title="Names use safe characters",
        description="Asset id, name, and material names avoid filesystem-unsafe chars.",
        check=_wrap(_check_naming_safe_chars),
    ),
]


def run_rule(rule: AuditRule, ctx: AuditContext) -> AuditRuleResult:
    """Execute a single rule, capturing exceptions as a skip."""

    started = time.monotonic()
    try:
        issues = rule.check(ctx)
    except Exception as exc:  # rules should be sturdy; surface bugs as skips
        return AuditRuleResult(
            rule=rule.id,
            title=rule.title,
            description=rule.description,
            status="skipped",
            skipped=True,
            skip_reason=f"{type(exc).__name__}: {exc}",
            duration_seconds=time.monotonic() - started,
        )
    duration = time.monotonic() - started
    return AuditRuleResult(
        rule=rule.id,
        title=rule.title,
        description=rule.description,
        status=rule_status(issues),
        skipped=False,
        issues=issues,
        duration_seconds=duration,
    )


__all__ = [
    "AuditContext",
    "AuditRule",
    "DEFAULT_RULES",
    "run_rule",
]
