"""GhostForge `AssetManifest` v1.

Every asset GhostForge produces is described by a single ``asset_manifest.json``
file at the asset's output directory. The manifest is the contract that crosses
every boundary in the system: desktop UI, MCP agents, Unity-MCP-Ghost,
Unreal-MCP-Ghost, and offline tooling all consume the same structure.

Design rules:

* Schema is versioned via :data:`MANIFEST_VERSION`. Future, breaking schema
  changes must bump this string and ship a new ``AssetManifest`` model.
* All fields use :class:`FrozenModel` (``frozen=True``, ``extra="forbid"``)
  so a manifest read on a newer reader fails loudly instead of silently
  dropping unknown fields.
* The manifest is purely declarative. Heavy lifting (hashing, geometry
  inspection, validation) is performed by helpers in this module so the
  asset operations don't grow boilerplate.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .kb.schema import ConceptCitation
from .types import Artifact, FrozenModel, utc_now
from .validation import ValidationReport, validate_mesh

MANIFEST_VERSION: Literal["1.0"] = "1.0"
MANIFEST_FILENAME = "asset_manifest.json"


class Units(str, Enum):
    meters = "meters"
    centimeters = "centimeters"
    millimeters = "millimeters"
    inches = "inches"
    feet = "feet"
    unknown = "unknown"


class CollisionIntent(str, Enum):
    """Authoring hint for downstream engine importers.

    The asset author declares *intent*; the engine adapter (Unity-MCP-Ghost or
    Unreal-MCP-Ghost) is responsible for turning intent into the engine's
    specific collider type.
    """

    none = "none"
    auto = "auto"
    box = "box"
    sphere = "sphere"
    capsule = "capsule"
    convex = "convex"
    trimesh = "trimesh"


class EngineTarget(str, Enum):
    any = "any"
    unity = "unity"
    unreal = "unreal"
    godot = "godot"
    blender = "blender"
    web = "web"


class TextureRole(str, Enum):
    base_color = "base_color"
    metallic = "metallic"
    roughness = "roughness"
    metallic_roughness = "metallic_roughness"
    orm = "orm"
    normal = "normal"
    occlusion = "occlusion"
    emissive = "emissive"
    height = "height"
    other = "other"


class GeometrySummary(FrozenModel):
    vertex_count: int = Field(ge=0)
    triangle_count: int = Field(ge=0)
    edge_count: int | None = None
    bounds_min: tuple[float, float, float] | None = None
    bounds_max: tuple[float, float, float] | None = None
    size: tuple[float, float, float] | None = None
    units: Units = Units.meters
    watertight: bool = False
    uv_channels: int = Field(default=0, ge=0, le=8)
    uv_chart_count: int | None = None
    lightmap_uv_channel: int | None = Field(default=None, ge=0, le=7)
    has_normals: bool = False
    has_tangents: bool = False
    has_vertex_colors: bool = False


class TextureSlot(FrozenModel):
    role: TextureRole = TextureRole.base_color
    path: Path
    color_space: Literal["sRGB", "linear"] = "sRGB"
    resolution: tuple[int, int] | None = None
    sha256: str | None = None
    notes: str | None = None


class MaterialSpec(FrozenModel):
    name: str
    type: Literal["pbr_metallic_roughness", "specular_glossiness", "unlit", "custom"] = (
        "pbr_metallic_roughness"
    )
    base_color_factor: tuple[float, float, float, float] | None = None
    metallic_factor: float | None = Field(default=None, ge=0.0, le=1.0)
    roughness_factor: float | None = Field(default=None, ge=0.0, le=1.0)
    emissive_factor: tuple[float, float, float] | None = None
    double_sided: bool = False
    alpha_mode: Literal["OPAQUE", "MASK", "BLEND"] = "OPAQUE"
    alpha_cutoff: float | None = Field(default=None, ge=0.0, le=1.0)
    texture_slots: list[TextureSlot] = Field(default_factory=list)


class LODEntry(FrozenModel):
    level: int = Field(ge=0)
    triangle_count: int = Field(ge=0)
    mesh_path: Path
    screen_size_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class CollisionSpec(FrozenModel):
    intent: CollisionIntent = CollisionIntent.none
    mesh_path: Path | None = None
    notes: str | None = None


class LicenseSpec(FrozenModel):
    spdx: str | None = None
    name: str | None = None
    holder: str | None = None
    attribution: str | None = None
    source_url: str | None = None
    notes: str | None = None


class EngineTargetSpec(FrozenModel):
    engine: EngineTarget
    notes: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)


class ProvenanceStep(FrozenModel):
    kind: str
    job_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class ValidationSummary(FrozenModel):
    status: Literal["passed", "warnings", "failed", "skipped"] = "skipped"
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    report: ValidationReport = Field(default_factory=ValidationReport)


class AssetManifest(FrozenModel):
    """v1 GhostForge asset manifest.

    Every field is optional except ``manifest_version`` and ``asset_id`` so
    early-stage operations (e.g. an unwrap that hasn't produced materials)
    can still emit a useful manifest. Downstream consumers (engine importers,
    validators) check for the fields they care about.
    """

    manifest_version: Literal["1.0"] = MANIFEST_VERSION
    asset_id: str
    name: str | None = None
    description: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    asset_dir: Path | None = None
    source_prompt: str | None = None
    source_reference_image: Path | None = None

    geometry: GeometrySummary | None = None
    materials: list[MaterialSpec] = Field(default_factory=list)
    lods: list[LODEntry] = Field(default_factory=list)
    collision: CollisionSpec = Field(default_factory=CollisionSpec)
    license: LicenseSpec = Field(default_factory=LicenseSpec)
    engine_targets: list[EngineTargetSpec] = Field(default_factory=list)

    artifacts: list[Artifact] = Field(default_factory=list)
    provenance: list[ProvenanceStep] = Field(default_factory=list)
    parents: list[str] = Field(default_factory=list)
    concept_citations: list[ConceptCitation] = Field(default_factory=list)

    validation: ValidationSummary = Field(default_factory=ValidationSummary)
    tags: list[str] = Field(default_factory=list)
    custom: dict[str, Any] = Field(default_factory=dict)


def build_geometry_summary(
    mesh_path: Path | str,
    units: Units = Units.meters,
) -> GeometrySummary:
    """Inspect a mesh file with trimesh and return a :class:`GeometrySummary`.

    Defensive about loader quirks: scenes are concatenated, missing UVs are
    reported as ``uv_channels=0``, and any failure surfaces as a friendly
    :class:`ValueError` rather than a trimesh-internal exception.
    """
    import trimesh

    loaded = trimesh.load(str(mesh_path), force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError(f"No geometry found in {mesh_path}")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Expected a trimesh.Trimesh, got {type(loaded).__name__}")

    bounds_min: tuple[float, float, float] | None = None
    bounds_max: tuple[float, float, float] | None = None
    size: tuple[float, float, float] | None = None
    if loaded.bounds is not None:
        bmin = [float(v) for v in loaded.bounds[0]]
        bmax = [float(v) for v in loaded.bounds[1]]
        bounds_min = (bmin[0], bmin[1], bmin[2])
        bounds_max = (bmax[0], bmax[1], bmax[2])
        size = (bmax[0] - bmin[0], bmax[1] - bmin[1], bmax[2] - bmin[2])

    def _non_empty(value: Any) -> bool:
        # `value` may be a numpy ndarray (where `bool(arr)` raises for >1 elem)
        # or a list/tuple. Probe `.size` first, then fall back to len().
        if value is None:
            return False
        size_attr = getattr(value, "size", None)
        if size_attr is not None:
            try:
                return int(size_attr) > 0
            except (TypeError, ValueError):
                pass
        try:
            return len(value) > 0
        except TypeError:
            return False

    visual = getattr(loaded, "visual", None)
    has_uv = _non_empty(getattr(visual, "uv", None))
    has_normals = _non_empty(getattr(loaded, "vertex_normals", None))
    has_vertex_colors = _non_empty(getattr(visual, "vertex_colors", None))

    return GeometrySummary(
        vertex_count=int(len(loaded.vertices)),
        triangle_count=int(len(loaded.faces)),
        edge_count=int(len(loaded.edges)) if hasattr(loaded, "edges") else None,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        size=size,
        units=units,
        watertight=bool(loaded.is_watertight),
        uv_channels=1 if has_uv else 0,
        uv_chart_count=None,
        has_normals=has_normals,
        has_tangents=False,
        has_vertex_colors=has_vertex_colors,
    )


def summarize_validation(report: ValidationReport) -> ValidationSummary:
    error_count = len(report.errors)
    warning_count = len(report.warnings)
    if error_count:
        status: Literal["passed", "warnings", "failed", "skipped"] = "failed"
    elif warning_count:
        status = "warnings"
    else:
        status = "passed"
    return ValidationSummary(
        status=status,
        error_count=error_count,
        warning_count=warning_count,
        info_count=len(report.info),
        report=report,
    )


def manifest_path(asset_dir: Path | str) -> Path:
    return Path(asset_dir) / MANIFEST_FILENAME


def write_manifest(asset_dir: Path | str, manifest: AssetManifest) -> Path:
    """Atomically persist a manifest under ``asset_dir``.

    Atomicity matters because partial reads of the manifest by an engine
    importer or another tool would silently lose data; ``os.replace`` on the
    same filesystem is the durable rename primitive.
    """
    import os

    target = manifest_path(asset_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, target)
    return target


def read_manifest(asset_dir: Path | str) -> AssetManifest:
    target = manifest_path(asset_dir)
    return AssetManifest.model_validate_json(target.read_text(encoding="utf-8"))


def manifest_exists(asset_dir: Path | str) -> bool:
    return manifest_path(asset_dir).exists()


class ManifestBuilder:
    """Mutable accumulator for assembling an :class:`AssetManifest`.

    Operations call ``ManifestBuilder.for_dir(asset_dir)`` (which loads any
    existing manifest at that location), chain field updates, then call
    :meth:`write` to atomically persist the result. Each ``with_*`` /
    ``add_*`` returns ``self`` for fluency.
    """

    def __init__(self, asset_id: str, asset_dir: Path) -> None:
        self.asset_dir = asset_dir
        self._fields: dict[str, Any] = {
            "manifest_version": MANIFEST_VERSION,
            "asset_id": asset_id,
            "asset_dir": asset_dir,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "geometry": None,
            "materials": [],
            "lods": [],
            "collision": CollisionSpec(),
            "license": LicenseSpec(),
            "engine_targets": [],
            "artifacts": [],
            "provenance": [],
            "parents": [],
            "concept_citations": [],
            "validation": ValidationSummary(),
            "tags": [],
            "custom": {},
        }

    @classmethod
    def for_dir(
        cls,
        asset_dir: Path | str,
        asset_id: str | None = None,
    ) -> "ManifestBuilder":
        """Return a builder seeded with any existing manifest at ``asset_dir``.

        The resolved ``asset_id`` precedence is: explicit argument, existing
        manifest's id, then the directory name. This lets repeated job runs
        update the same manifest in place rather than overwriting it.
        """
        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)

        if manifest_exists(path):
            existing = read_manifest(path)
            builder = cls(asset_id=asset_id or existing.asset_id, asset_dir=path)
            for field_name in AssetManifest.model_fields:
                builder._fields[field_name] = getattr(existing, field_name)
            builder._fields["asset_dir"] = path
            if asset_id:
                builder._fields["asset_id"] = asset_id
            return builder

        return cls(asset_id=asset_id or path.name, asset_dir=path)

    def with_name(self, name: str | None) -> "ManifestBuilder":
        if name is not None:
            self._fields["name"] = name
        return self

    def with_description(self, description: str | None) -> "ManifestBuilder":
        if description is not None:
            self._fields["description"] = description
        return self

    def with_source_prompt(self, prompt: str | None) -> "ManifestBuilder":
        if prompt is not None:
            self._fields["source_prompt"] = prompt
        return self

    def with_reference_image(self, path: Path | str | None) -> "ManifestBuilder":
        if path is not None:
            self._fields["source_reference_image"] = Path(path)
        return self

    def with_geometry(self, geometry: GeometrySummary | None) -> "ManifestBuilder":
        self._fields["geometry"] = geometry
        return self

    def with_geometry_from_mesh(
        self,
        mesh_path: Path | str,
        units: Units = Units.meters,
    ) -> "ManifestBuilder":
        self._fields["geometry"] = build_geometry_summary(mesh_path, units=units)
        return self

    def with_collision(self, collision: CollisionSpec) -> "ManifestBuilder":
        self._fields["collision"] = collision
        return self

    def with_license(self, license_spec: LicenseSpec) -> "ManifestBuilder":
        self._fields["license"] = license_spec
        return self

    def add_engine_target(self, target: EngineTargetSpec) -> "ManifestBuilder":
        self._fields["engine_targets"] = list(self._fields["engine_targets"]) + [target]
        return self

    def has_engine_target(self, engine: EngineTarget) -> bool:
        return any(spec.engine == engine for spec in self._fields["engine_targets"])

    def get_custom(self, key: str, default: Any = None) -> Any:
        return self._fields["custom"].get(key, default)

    def add_material(self, material: MaterialSpec) -> "ManifestBuilder":
        self._fields["materials"] = list(self._fields["materials"]) + [material]
        return self

    def add_lod(self, lod: LODEntry) -> "ManifestBuilder":
        self._fields["lods"] = list(self._fields["lods"]) + [lod]
        return self

    def add_provenance(self, step: ProvenanceStep) -> "ManifestBuilder":
        self._fields["provenance"] = list(self._fields["provenance"]) + [step]
        return self

    def add_parent(self, parent_asset_id: str) -> "ManifestBuilder":
        if parent_asset_id not in self._fields["parents"]:
            self._fields["parents"] = list(self._fields["parents"]) + [parent_asset_id]
        return self

    def add_tag(self, tag: str) -> "ManifestBuilder":
        if tag not in self._fields["tags"]:
            self._fields["tags"] = list(self._fields["tags"]) + [tag]
        return self

    def add_artifact(self, artifact: Artifact) -> "ManifestBuilder":
        # Replace by (path, role) so repeated calls don't accumulate stale entries.
        existing = [
            a for a in self._fields["artifacts"]
            if not (Path(a.path) == Path(artifact.path) and a.role == artifact.role)
        ]
        existing.append(artifact)
        self._fields["artifacts"] = existing
        return self

    def add_artifact_from_path(
        self,
        path: Path | str | None,
        role: str = "artifact",
    ) -> "ManifestBuilder":
        if path is None:
            return self
        target = Path(path)
        if not target.exists():
            return self
        from .storage import compute_artifact

        return self.add_artifact(compute_artifact(target, role=role))

    def add_concept_citation(self, citation: ConceptCitation) -> "ManifestBuilder":
        # Deduplicate by concept_id so re-citing the same source is idempotent.
        existing = [
            c for c in self._fields["concept_citations"] if c.concept_id != citation.concept_id
        ]
        existing.append(citation)
        self._fields["concept_citations"] = existing
        return self

    def with_validation(self, summary: ValidationSummary) -> "ManifestBuilder":
        self._fields["validation"] = summary
        return self

    def with_validation_from_mesh(self, mesh_path: Path | str) -> "ManifestBuilder":
        report = validate_mesh(mesh_path)
        self._fields["validation"] = summarize_validation(report)
        return self

    def with_custom(self, key: str, value: Any) -> "ManifestBuilder":
        custom = dict(self._fields["custom"])
        custom[key] = value
        self._fields["custom"] = custom
        return self

    def build(self) -> AssetManifest:
        self._fields["updated_at"] = utc_now()
        return AssetManifest(**self._fields)

    def write(self) -> tuple[AssetManifest, Path]:
        manifest = self.build()
        path = write_manifest(self.asset_dir, manifest)
        return manifest, path


def apply_side_effects_to_manifest(
    asset_dir: Path | str,
    side_effects: list[dict[str, Any]],
    *,
    asset_id: str | None = None,
) -> AssetManifest | None:
    """Wire bake-operation side-effect dicts into a manifest at ``asset_dir``.

    Each entry shaped like ``{"kind": "convex_collision", "mesh_path": ...,
    "intent": "convex"}`` becomes a :class:`CollisionSpec`; ``lightmap_uv``
    entries are recorded under ``custom['lightmap_uv']`` so external tools
    can find them. No-op if ``side_effects`` is empty or no manifest can
    be produced (e.g. directory does not exist and no asset_id given).
    """

    if not side_effects:
        return None

    target = Path(asset_dir)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)

    builder = ManifestBuilder.for_dir(target, asset_id=asset_id)
    touched = False

    for entry in side_effects:
        kind = (entry or {}).get("kind")
        if kind == "convex_collision":
            mesh_path = entry.get("mesh_path")
            if not mesh_path:
                continue
            intent_name = entry.get("intent", "convex")
            try:
                intent = CollisionIntent(intent_name)
            except ValueError:
                intent = CollisionIntent.convex
            spec = CollisionSpec(
                intent=intent,
                mesh_path=Path(mesh_path),
                notes=(
                    f"baked from convex hull "
                    f"({entry.get('vertex_count')} verts, {entry.get('face_count')} faces)"
                ),
            )
            builder.with_collision(spec)
            builder.add_artifact_from_path(mesh_path, role="collision")
            touched = True
        elif kind == "lightmap_uv":
            existing = builder.get_custom("lightmap_uv", {})
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(
                {
                    "channel": entry.get("channel", 1),
                    "chart_count": entry.get("chart_count"),
                    "resolution": entry.get("resolution"),
                    "padding": entry.get("padding"),
                    "engine": entry.get("engine"),
                }
            )
            builder.with_custom("lightmap_uv", merged)
            touched = True

    if not touched:
        return None
    manifest, _ = builder.write()
    return manifest


__all__ = [
    "MANIFEST_FILENAME",
    "MANIFEST_VERSION",
    "AssetManifest",
    "CollisionIntent",
    "CollisionSpec",
    "ConceptCitation",
    "EngineTarget",
    "EngineTargetSpec",
    "GeometrySummary",
    "LODEntry",
    "LicenseSpec",
    "ManifestBuilder",
    "MaterialSpec",
    "ProvenanceStep",
    "TextureRole",
    "TextureSlot",
    "Units",
    "ValidationSummary",
    "apply_side_effects_to_manifest",
    "build_geometry_summary",
    "manifest_exists",
    "manifest_path",
    "read_manifest",
    "summarize_validation",
    "write_manifest",
]
