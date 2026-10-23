"""Native CAD import/export contracts for Ghost Forge.

Plasticity recon shows a serious translator footprint, but translator DLL names
are evidence rather than product behavior.  Ghost Forge owns the actual interop
contract here: supported directions, option schemas, file safety, topology
effects, tolerances, diagnostics, fixtures, and verification gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schema import FailureMode, FormatOption, TolerancePolicy


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


InteropDirection = Literal["import", "export"]


class InteropOptionSpec(FrozenModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    default: Any = None
    values: tuple[Any, ...] = ()
    unit: str | None = None
    applies_to: tuple[InteropDirection, ...] = ("import", "export")
    required: bool = False
    description: str = ""
    safety_note: str = ""


class InteropFormatDescriptor(FrozenModel):
    format_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    family: Literal["brep", "drawing", "mesh"] = "brep"
    extensions: tuple[str, ...] = ()
    directions: tuple[InteropDirection, ...] = ()
    confidence: str = "inferred_needs_fixture_verification"
    plasticity_evidence: tuple[str, ...] = ()
    backend_candidates: tuple[str, ...] = ()
    option_schema: tuple[InteropOptionSpec, ...] = ()
    format_options_from_recon: tuple[FormatOption, ...] = ()
    topology_policy: tuple[str, ...] = ()
    tolerance_policy: TolerancePolicy = Field(default_factory=TolerancePolicy)
    failure_modes: tuple[FailureMode, ...] = ()
    fixture_tests: tuple[str, ...] = ()
    automation_requirements: tuple[str, ...] = ()
    ghostforge_application: tuple[str, ...] = ()
    verification_gates: tuple[str, ...] = ()

    @property
    def can_import(self) -> bool:
        return "import" in self.directions

    @property
    def can_export(self) -> bool:
        return "export" in self.directions

    def options_for_direction(self, direction: InteropDirection) -> tuple[InteropOptionSpec, ...]:
        return tuple(option for option in self.option_schema if direction in option.applies_to)


def _option(
    name: str,
    type_: str,
    *,
    default: Any = None,
    values: tuple[Any, ...] = (),
    unit: str | None = None,
    applies_to: tuple[InteropDirection, ...] = ("import", "export"),
    required: bool = False,
    description: str = "",
    safety_note: str = "",
) -> InteropOptionSpec:
    return InteropOptionSpec(
        name=name,
        type=type_,
        default=default,
        values=values,
        unit=unit,
        applies_to=applies_to,
        required=required,
        description=description,
        safety_note=safety_note,
    )


def _format_option(
    name: str,
    type_: str,
    *,
    default: Any = None,
    description: str = "",
) -> FormatOption:
    return FormatOption(
        name=name,
        type=type_,
        default=default,
        applies_to=("mesh_export",),
        description=description,
    )


def _failure(code: str, message: str, recovery: str) -> FailureMode:
    return FailureMode(code=code, message=message, recovery=recovery)


COMMON_FILE_FAILURES = (
    _failure("path.missing", "No source or target path was provided.", "Provide a workspace-controlled path before running the translator."),
    _failure("path.permission_denied", "The translator cannot read or write the requested path.", "Choose a writable workspace path or fix file permissions."),
    _failure("format.unsupported", "The selected file extension or translator backend is unavailable.", "Choose a supported format or install the required translator backend."),
    _failure("translator.failed", "The translator returned an error before producing a complete artifact.", "Inspect translator diagnostics and retry with simpler geometry or safer options."),
)


COMMON_BREP_OPTIONS = (
    _option("units", "enum", default="scene", values=("scene", "mm", "cm", "m", "inch", "foot"), description="Unit interpretation or conversion policy."),
    _option("heal_geometry", "bool", default=True, description="Allow translator/kernel healing for stitched or slightly invalid B-rep topology."),
    _option("preserve_names", "bool", default=True, description="Preserve body, face, layer, and material names where the format supports them."),
    _option("body_split_policy", "enum", default="preserve_bodies", values=("preserve_bodies", "merge_by_layer", "single_body"), description="How imported/exported bodies are grouped."),
    _option("linear_tolerance", "float", default=1e-5, unit="scene_units", description="Translation, healing, or stitching linear tolerance."),
    _option("angular_tolerance_deg", "float", default=0.1, unit="degrees", description="Angular tolerance for surface/edge healing and validation."),
)


DEFAULT_INTEROP_FORMATS: tuple[InteropFormatDescriptor, ...] = (
    InteropFormatDescriptor(
        format_id="step_stp",
        label="STEP / STP",
        family="brep",
        extensions=(".step", ".stp"),
        directions=("import", "export"),
        confidence="high_install_evidence_needs_fixture_verification",
        plasticity_evidence=("dwgstep30.dll", "igestep30.dll", "rdmstep30.dll", "satstep31.dll", "stepstep30.dll", "xtstep30.dll"),
        backend_candidates=("opencascade_step", "future_commercial_translator", "assimp_metadata_bridge"),
        option_schema=COMMON_BREP_OPTIONS
        + (
            _option("step_schema", "enum", default="AP242", values=("AP203", "AP214", "AP242"), applies_to=("export",), description="STEP application protocol for exported assemblies and metadata."),
            _option("export_assembly_structure", "bool", default=True, applies_to=("export",), description="Preserve object hierarchy where the backend supports it."),
        ),
        topology_policy=(
            "Import creates B-rep body/sheet/curve entities with source-name provenance.",
            "Export must not mutate source topology.",
            "Healing changes are reported as translator diagnostics and topology deltas on import.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="Neutral B-rep translation and healing tolerance."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("step.schema_unsupported", "Requested STEP schema is not supported by the selected backend.", "Choose AP242/AP214/AP203 based on backend support."),
            _failure("brep.healing_failed", "Imported B-rep topology could not be healed within tolerance.", "Increase tolerance or import without healing for inspection."),
        ),
        fixture_tests=("fixture_cube_solid", "fixture_sheet_patch"),
        automation_requirements=("workspace_controlled_path", "translator_diagnostics_record", "round_trip_topology_summary", "undoable_import_transaction"),
        ghostforge_application=("Prioritize as the first neutral CAD B-rep interop path for Ghost Forge.",),
        verification_gates=("tiny_solid_import", "tiny_solid_export", "round_trip_names_units", "diagnostics_serialized"),
    ),
    InteropFormatDescriptor(
        format_id="iges_igs",
        label="IGES / IGS",
        family="brep",
        extensions=(".iges", ".igs"),
        directions=("import", "export"),
        confidence="high_install_evidence_needs_fixture_verification",
        plasticity_evidence=("igestep30.dll", "wiges.dll"),
        backend_candidates=("opencascade_iges", "future_commercial_translator"),
        option_schema=COMMON_BREP_OPTIONS
        + (
            _option("surface_trim_policy", "enum", default="preserve_trimmed_surfaces", values=("preserve_trimmed_surfaces", "untrim_surfaces", "curves_only"), description="How IGES trimmed surfaces and curves are represented."),
            _option("import_curves", "bool", default=True, applies_to=("import",), description="Import free curves and curve-on-surface entities."),
        ),
        topology_policy=(
            "Import may create sheets, trimmed surfaces, and curve entities rather than closed solids.",
            "Surface trim and curve identity must be recorded because IGES is often less assembly-aware than STEP.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="Surface/curve import and trim reconstruction tolerance."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("iges.trim_reconstruction_failed", "Trim curves could not be reconstructed onto imported surfaces.", "Import surfaces untrimmed or increase trim tolerance."),
            _failure("iges.unsupported_entity", "The file contains IGES entity types the backend cannot translate.", "Record unsupported entities and continue partial import only when safe."),
        ),
        fixture_tests=("fixture_sheet_patch", "fixture_curve_profile"),
        automation_requirements=("workspace_controlled_path", "surface_trim_diagnostics", "round_trip_curve_summary"),
        ghostforge_application=("Keep IGES as a surface/curve-heavy interop path, separate from mesh export.",),
        verification_gates=("sheet_import", "curve_import", "trim_policy_asserted", "diagnostics_serialized"),
    ),
    InteropFormatDescriptor(
        format_id="parasolid_x_t_x_b",
        label="Parasolid X_T / X_B",
        family="brep",
        extensions=(".x_t", ".x_b"),
        directions=("import", "export"),
        confidence="high_install_evidence_needs_fixture_verification",
        plasticity_evidence=("pk.node", "pskernel.dll", "101 Parasolid schema text files"),
        backend_candidates=("future_parasolid_or_bridge",),
        option_schema=COMMON_BREP_OPTIONS
        + (
            _option("parasolid_encoding", "enum", default="text", values=("text", "binary"), description="Choose text or binary Parasolid flavor."),
            _option("kernel_version", "string", default="backend_default", applies_to=("export",), description="Requested Parasolid schema/kernel version when supported."),
        ),
        topology_policy=(
            "Treat as a future premium-kernel interchange target.",
            "Preserve body identity and topology names as closely as backend licensing allows.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-6, angular_degrees=0.05, description="Kernel-native B-rep translation tolerance target."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("parasolid.backend_unavailable", "No Parasolid-capable backend is configured.", "Use STEP/SAT fallback or install a licensed backend."),
        ),
        fixture_tests=("fixture_cube_solid",),
        automation_requirements=("backend_capability_check", "workspace_controlled_path", "round_trip_topology_summary"),
        ghostforge_application=("Represent explicitly now so architecture does not collapse premium kernel interchange into generic file IO.",),
        verification_gates=("backend_gate_blocks_when_missing", "solid_round_trip_when_backend_exists"),
    ),
    InteropFormatDescriptor(
        format_id="sat_sab",
        label="ACIS SAT / SAB",
        family="brep",
        extensions=(".sat", ".sab"),
        directions=("import", "export"),
        confidence="high_install_evidence_needs_fixture_verification",
        plasticity_evidence=("satstep31.dll", "TD_AcisBuilder_26.8_16.dll", "wsat.dll"),
        backend_candidates=("future_acis_or_bridge", "opencascade_sat_bridge_if_available"),
        option_schema=COMMON_BREP_OPTIONS
        + (
            _option("acis_encoding", "enum", default="sat", values=("sat", "sab"), description="Choose text SAT or binary SAB flavor."),
            _option("acis_version", "string", default="backend_default", applies_to=("export",), description="Requested ACIS version when supported."),
        ),
        topology_policy=(
            "Import creates B-rep entities with healing diagnostics.",
            "Export preserves body/layer names and records backend version.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="ACIS translation and healing tolerance target."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("acis.backend_unavailable", "No ACIS-capable backend is configured.", "Use STEP fallback or install a supported backend."),
        ),
        fixture_tests=("fixture_cube_solid",),
        automation_requirements=("backend_capability_check", "workspace_controlled_path", "translator_diagnostics_record"),
        ghostforge_application=("Keep ACIS import/export separate from STEP and Parasolid because diagnostics and licensing differ.",),
        verification_gates=("backend_gate_blocks_when_missing", "solid_import_or_export_when_backend_exists"),
    ),
    InteropFormatDescriptor(
        format_id="dwg_dxf",
        label="DWG / DXF",
        family="drawing",
        extensions=(".dwg", ".dxf"),
        directions=("import", "export"),
        confidence="high_install_evidence_needs_fixture_verification",
        plasticity_evidence=("dwgstep30.dll", "TD_DbIO_26.8_16.tx", "TD_DbEntities_26.8_16.tx", "TD_AcisBuilder_26.8_16.dll"),
        backend_candidates=("oda_file_converter", "ezdxf_for_dxf", "future_commercial_dwg_backend"),
        option_schema=(
            _option("units", "enum", default="scene", values=("scene", "mm", "cm", "m", "inch", "foot"), description="Drawing unit conversion policy."),
            _option("drawing_version", "enum", default="R2018", values=("R12", "R2000", "R2007", "R2013", "R2018", "R2024"), applies_to=("export",), description="Target DWG/DXF version."),
            _option("preserve_layers", "bool", default=True, description="Preserve layer membership and names."),
            _option("lineweight_policy", "enum", default="preserve", values=("preserve", "ignore", "material_from_lineweight"), description="How lineweights map into Ghost Forge attributes."),
            _option("model_space_only", "bool", default=True, applies_to=("import",), description="Import model-space entities and ignore paper-space layouts unless explicitly enabled."),
            _option("include_hidden_lines", "bool", default=False, applies_to=("export",), description="Export hidden-line/vector edges when generated by the viewport or kernel."),
        ),
        topology_policy=(
            "Import creates curves, layers, optional B-rep bodies, and drawing metadata.",
            "Export can emit curve/vector views without mutating scene topology.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="Curve tessellation and drawing entity conversion tolerance."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("drawing.unsupported_entity", "Drawing contains entities the backend cannot translate.", "Record unsupported entity counts and import supported layers only when safe."),
            _failure("drawing.version_unsupported", "Requested drawing version is not supported.", "Choose a supported DWG/DXF target version."),
        ),
        fixture_tests=("fixture_curve_profile",),
        automation_requirements=("workspace_controlled_path", "layer_name_report", "unsupported_entity_report"),
        ghostforge_application=("Use layer/name preservation as a contract for CAD drawing interchange and hidden-line export.",),
        verification_gates=("curve_profile_import", "dxf_export_layers", "unsupported_entities_diagnostic"),
    ),
    InteropFormatDescriptor(
        format_id="mesh_export",
        label="Mesh Export",
        family="mesh",
        extensions=(".glb", ".obj", ".stl", ".fbx", ".ply", ".3mf"),
        directions=("export",),
        confidence="high_static_asset_evidence_needs_file_dialog_probe",
        plasticity_evidence=("export-mesh-angle-tolerance.png", "export-mesh-inflect.png", "export-mesh-max-width.png"),
        backend_candidates=("trimesh_export", "assimp_export", "future_engine_presets"),
        option_schema=(
            _option("format", "enum", default="glb", values=("glb", "obj", "stl", "fbx", "ply", "3mf"), applies_to=("export",), required=True, description="Target mesh format."),
            _option("target_path", "path", applies_to=("export",), required=True, description="Workspace-controlled output path.", safety_note="Automated export must write only to approved temporary/workspace locations."),
            _option("scope", "enum", default="selection", values=("selection", "visible_scene", "whole_scene", "named_set"), applies_to=("export",), description="Geometry included in the export."),
            _option("axis_preset", "enum", default="ghostforge", values=("ghostforge", "unity", "unreal", "blender"), applies_to=("export",), description="Axis/up/unit preset for game-engine targets."),
            _option("include_normals", "bool", default=True, applies_to=("export",), description="Export vertex/face normals where supported."),
            _option("include_materials", "bool", default=True, applies_to=("export",), description="Export material references where supported."),
            _option("include_uvs", "bool", default=True, applies_to=("export",), description="Export UV coordinates where supported."),
            _option("angle_tolerance", "float", default=1.0, unit="degrees", applies_to=("export",), description="Plasticity static asset suggests an angular tessellation control."),
            _option("max_width", "float", default=None, unit="scene_units", applies_to=("export",), description="Plasticity static asset suggests maximum triangle/edge width control."),
            _option("inflect", "bool", default=False, applies_to=("export",), description="Plasticity static asset suggests extra tessellation at inflection changes."),
            _option("overwrite_policy", "enum", default="fail_if_exists", values=("fail_if_exists", "overwrite", "versioned_name"), applies_to=("export",), description="File overwrite behavior."),
        ),
        format_options_from_recon=(
            _format_option("angle_tolerance", "float", default=1.0, description="Observed as Plasticity static export-mesh asset."),
            _format_option("max_width", "float", default=None, description="Observed as Plasticity static export-mesh asset."),
            _format_option("inflect", "bool", default=False, description="Observed as Plasticity static export-mesh asset."),
        ),
        topology_policy=(
            "Export preserves source scene topology.",
            "Tessellated output is an artifact with its own mesh summary, not a mutation of source B-rep entities.",
            "Exported node names and material slot names must be recorded for downstream engine use.",
        ),
        tolerance_policy=TolerancePolicy(linear=1e-5, angular_degrees=1.0, description="Mesh tessellation/export tolerance."),
        failure_modes=COMMON_FILE_FAILURES
        + (
            _failure("export.empty_scope", "The selected export scope contains no geometry.", "Select objects or choose visible/whole-scene export."),
            _failure("export.overwrite_blocked", "Target file exists and overwrite policy blocks replacement.", "Choose overwrite or versioned-name policy."),
        ),
        fixture_tests=("fixture_cube_mesh", "fixture_cube_solid"),
        automation_requirements=("workspace_controlled_path", "artifact_manifest_record", "source_topology_preserved", "export_summary_record"),
        ghostforge_application=("Make game-ready mesh export reproducible from Qt, MCP, tests, and operation graph nodes.",),
        verification_gates=("fixture_cube_exports", "source_topology_unchanged", "artifact_manifest_record", "tessellation_options_serialized"),
    ),
)


@dataclass(frozen=True)
class CadInteropRegistry:
    formats: dict[str, InteropFormatDescriptor]

    @classmethod
    def from_defaults(cls) -> "CadInteropRegistry":
        return cls({descriptor.format_id: descriptor for descriptor in DEFAULT_INTEROP_FORMATS})

    def get(self, format_id: str) -> InteropFormatDescriptor:
        return self.formats[format_id]

    def all(self) -> list[InteropFormatDescriptor]:
        return [self.formats[key] for key in sorted(self.formats)]

    def by_direction(self, direction: InteropDirection) -> list[InteropFormatDescriptor]:
        return [descriptor for descriptor in self.all() if direction in descriptor.directions]

    def by_family(self, family: str) -> list[InteropFormatDescriptor]:
        return [descriptor for descriptor in self.all() if descriptor.family == family]

    def summary(self) -> dict[str, Any]:
        family_counts: dict[str, int] = {}
        direction_counts: dict[str, int] = {"import": 0, "export": 0}
        for descriptor in self.formats.values():
            family_counts[descriptor.family] = family_counts.get(descriptor.family, 0) + 1
            for direction in descriptor.directions:
                direction_counts[direction] += 1
        return {
            "format_count": len(self.formats),
            "family_counts": dict(sorted(family_counts.items())),
            "direction_counts": direction_counts,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_default_interop_registry() -> CadInteropRegistry:
    return CadInteropRegistry.from_defaults()


__all__ = [
    "CadInteropRegistry",
    "COMMON_FILE_FAILURES",
    "DEFAULT_INTEROP_FORMATS",
    "InteropDirection",
    "InteropFormatDescriptor",
    "InteropOptionSpec",
    "build_default_interop_registry",
]
