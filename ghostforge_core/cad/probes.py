"""Plasticity probe planning contracts for Ghost Forge CAD parity.

The command registry says what Ghost Forge intends to support.  The fixture
catalog says how behavior should be verified.  This module records the missing
evidence that must be collected from Plasticity before parity claims become
credible: option panels, fixture behavior, failures, tolerances, topology
naming, import/export settings, static-asset classification, and automation
routes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AutomationStep(FrozenModel):
    tool: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    purpose: str = ""
    mutates_document: bool = False
    requires_disposable_fixture: bool = False


class CommandProbePlan(FrozenModel):
    command_id: str = Field(min_length=1)
    priority: str = "medium"
    plasticity_stage: str
    readiness_bucket: str
    evidence_sources: tuple[str, ...] = ()
    fixture_ids: tuple[str, ...] = ()
    parameter_panel_targets: tuple[str, ...] = ()
    option_panel_targets: tuple[str, ...] = ()
    selection_rule_targets: tuple[str, ...] = ()
    topology_naming_targets: tuple[str, ...] = ()
    failure_mode_targets: tuple[str, ...] = ()
    tolerance_targets: tuple[str, ...] = ()
    import_export_targets: tuple[str, ...] = ()
    static_asset_resolution: str | None = None
    automation_route: tuple[AutomationStep, ...] = ()
    ghostforge_application: tuple[str, ...] = ()
    acceptance_evidence: tuple[str, ...] = (
        "before_screenshot",
        "after_screenshot",
        "observed_parameter_schema",
        "fixture_topology_delta",
        "undo_reset_result",
    )

    @property
    def needs_live_plasticity_probe(self) -> bool:
        return self.plasticity_stage not in {
            "ghostforge_internal_contract_only",
            "relationship_recorded_until_live_probe",
        }


class FormatProbePlan(FrozenModel):
    format_id: str = Field(min_length=1)
    direction: str
    confidence: str
    evidence_sources: tuple[str, ...] = ()
    option_targets: tuple[str, ...] = ()
    fixture_ids: tuple[str, ...] = ()
    automation_route: tuple[AutomationStep, ...] = ()
    ghostforge_application: tuple[str, ...] = ()


class StaticAssetProbePlan(FrozenModel):
    asset_key: str = Field(min_length=1)
    mapping_status: str
    inferred_options: tuple[str, ...] = ()
    evidence_assets: tuple[str, ...] = ()
    candidate_owner_commands: tuple[str, ...] = ()
    negative_palette_evidence: tuple[str, ...] = ()
    next_action: str
    ghostforge_mapping: str


def _route(
    command_id: str,
    *,
    query: str | None = None,
    fixture_required: bool = False,
    file_touching: bool = False,
) -> tuple[AutomationStep, ...]:
    steps: list[AutomationStep] = []
    if query:
        steps.append(
            AutomationStep(
                tool="plasticity_palette_search_probe",
                arguments={"query": query},
                purpose="Confirm command or option wording in the live command palette.",
            )
        )
    steps.extend(
        [
            AutomationStep(
                tool="plasticity_command_invocation_probe",
                arguments={"command_id": command_id, "mode": "plan"},
                purpose="Verify route safety and expected UI state before mutation.",
                mutates_document=file_touching,
                requires_disposable_fixture=fixture_required,
            ),
            AutomationStep(
                tool="parameter_probe_session",
                arguments={"command_id": command_id, "mode": "plan"},
                purpose="Capture command panel and option-panel schema without committing unsafe edits.",
                mutates_document=file_touching,
                requires_disposable_fixture=fixture_required,
            ),
            AutomationStep(
                tool="parameter_schema_observation_record",
                arguments={"command_id": command_id},
                purpose="Record observed fields, defaults, ranges, validation, screenshots, and reset behavior.",
            ),
            AutomationStep(
                tool="refresh_observation_artifacts",
                arguments={},
                purpose="Regenerate readiness ledgers after observation.",
            ),
        ]
    )
    return tuple(steps)


DEFAULT_COMMAND_PROBE_PLANS: tuple[CommandProbePlan, ...] = (
    CommandProbePlan(
        command_id="transform",
        priority="critical",
        plasticity_stage="static_inferred_needs_palette_confirmation",
        readiness_bucket="palette_confirmation",
        evidence_sources=("transform-face-step.png", "static_command_mapping_review.json"),
        fixture_ids=("fixture_cube_mesh",),
        parameter_panel_targets=("translate", "rotate", "scale", "pivot", "coordinate_space"),
        option_panel_targets=("face_step",),
        selection_rule_targets=("object", "face", "edge", "active_plane"),
        topology_naming_targets=("face_ids_preserved", "edge_ids_preserved", "object_transform_or_baked_vertices"),
        failure_mode_targets=("empty_selection", "locked_object", "invalid_pivot", "zero_scale"),
        tolerance_targets=("linear_snap_increment", "angular_snap_increment"),
        static_asset_resolution="Controlled probe must decide whether face step is a transform option or belongs to a face-edit command.",
        automation_route=_route("transform", query="Transform", fixture_required=True, file_touching=True),
        ghostforge_application=(
            "Drive descriptor-based transform panel instead of hard-coded Qt controls.",
            "Keep object-transform and baked-vertex behavior explicit in topology deltas.",
        ),
    ),
    CommandProbePlan(
        command_id="export_mesh",
        priority="critical",
        plasticity_stage="static_inferred_needs_palette_confirmation",
        readiness_bucket="palette_confirmation",
        evidence_sources=(
            "export-mesh-angle-tolerance.png",
            "export-mesh-inflect.png",
            "export-mesh-max-width.png",
            "plasticity_file_format_map.json",
        ),
        fixture_ids=("fixture_cube_mesh",),
        parameter_panel_targets=("format", "target_path", "scope", "units", "axis_preset"),
        option_panel_targets=("angle_tolerance", "inflect", "max_width", "normal_export", "material_export"),
        selection_rule_targets=("selected_objects", "whole_scene", "hidden_or_locked_objects"),
        topology_naming_targets=("source_geometry_not_mutated", "exported_node_names", "material_slot_names"),
        failure_mode_targets=("missing_target_path", "unsupported_format", "permission_denied", "empty_scene"),
        tolerance_targets=("linear_tessellation_tolerance", "angular_tessellation_tolerance", "max_edge_width"),
        import_export_targets=("obj", "stl", "3mf", "svg", "hidden_line", "mesh_export"),
        static_asset_resolution="Controlled file-dialog probe must decide whether Export Mesh is standalone or an option panel under format-specific exports.",
        automation_route=_route("export_mesh", query="Export Mesh", fixture_required=True, file_touching=True),
        ghostforge_application=(
            "Separate mesh export descriptor from generic file export.",
            "Make tessellation options first-class and test them against deterministic fixtures.",
        ),
    ),
    CommandProbePlan(
        command_id="extrude",
        priority="high",
        plasticity_stage="palette_reachable_needs_parameter_probe",
        readiness_bucket="fixture_required",
        evidence_sources=("parameter_observation_readiness.json", "plasticity_command_schema.json"),
        fixture_ids=("fixture_cube_solid", "fixture_curve_profile"),
        parameter_panel_targets=("distance", "direction", "operation", "draft_angle", "symmetric", "extent_type"),
        option_panel_targets=("new_body", "join", "cut", "intersect", "thin_extrude"),
        selection_rule_targets=("closed_profile", "planar_face", "multiple_profiles", "selection_order"),
        topology_naming_targets=("source_profile_lineage", "cap_face_ids", "side_face_ids", "body_id"),
        failure_mode_targets=("open_profile", "self_intersection", "zero_distance", "non_planar_profile"),
        tolerance_targets=("profile_closure_tolerance", "side_face_stitching_tolerance"),
        automation_route=_route("extrude", fixture_required=True, file_touching=True),
        ghostforge_application=(
            "Use command fixtures to define B-rep lineage before a kernel exists.",
            "Render operation/direction choices from schema in Qt and MCP.",
        ),
    ),
    CommandProbePlan(
        command_id="fillet",
        priority="high",
        plasticity_stage="palette_reachable_needs_parameter_probe",
        readiness_bucket="fixture_required",
        evidence_sources=("parameter_observation_readiness.json", "plasticity_command_schema.json"),
        fixture_ids=("fixture_cube_solid",),
        parameter_panel_targets=("radius", "continuity", "setback", "variable_radius", "chain_selection"),
        option_panel_targets=("g1", "g2", "constant_radius", "variable_radius"),
        selection_rule_targets=("edge", "edge_chain", "tangent_chain", "multi_body"),
        topology_naming_targets=("blend_face_ids", "adjacent_face_lineage", "removed_sharp_edge_id"),
        failure_mode_targets=("radius_too_large", "non_manifold_edge", "self_intersection", "zero_radius"),
        tolerance_targets=("blend_tolerance", "angular_continuity_tolerance"),
        automation_route=_route("fillet", fixture_required=True, file_touching=True),
        ghostforge_application=(
            "Require structured failure reports for bad radii instead of silent no-ops.",
            "Track created blend faces separately from modified adjacent faces.",
        ),
    ),
    CommandProbePlan(
        command_id="project",
        priority="high",
        plasticity_stage="palette_confirmed_needs_parameter_probe",
        readiness_bucket="safe_parameter_session",
        evidence_sources=("palette_probe_confirmations.json", "parameter_observation_readiness.json"),
        fixture_ids=("fixture_sheet_patch", "fixture_curve_profile"),
        parameter_panel_targets=("projection_mode", "direction", "imprint_result", "trim_to_target"),
        option_panel_targets=("normal", "camera", "direction", "imprint", "trim"),
        selection_rule_targets=("source_curve_then_target_surface", "ordered_selection", "active_view"),
        topology_naming_targets=("curve_on_surface_id", "target_surface_preserved", "imprint_edge_ids"),
        failure_mode_targets=("missing_target_surface", "projection_miss", "ambiguous_direction"),
        tolerance_targets=("curve_projection_tolerance",),
        automation_route=_route("project", fixture_required=True, file_touching=True),
        ghostforge_application=(
            "Make ordered selection explicit in the descriptor and picking layer.",
            "Keep projected curve creation separate from destructive imprint/trim options.",
        ),
    ),
    CommandProbePlan(
        command_id="delete_selection",
        priority="medium",
        plasticity_stage="palette_reachable_needs_parameter_probe",
        readiness_bucket="fixture_required",
        evidence_sources=("parameter_observation_readiness.json",),
        fixture_ids=("fixture_cube_mesh", "fixture_degenerate_mesh"),
        parameter_panel_targets=("delete_scope", "delete_children", "heal_openings"),
        selection_rule_targets=("object", "face", "edge", "vertex", "all_geometry"),
        topology_naming_targets=("unselected_face_ids_preserved", "unreferenced_vertices_removed"),
        failure_mode_targets=("empty_selection", "would_delete_all_geometry", "locked_object"),
        automation_route=_route("delete", fixture_required=True, file_touching=True),
        ghostforge_application=("Keep destructive edits fixture-gated and undoable through structured deltas.",),
    ),
    CommandProbePlan(
        command_id="weld",
        priority="medium",
        plasticity_stage="ghostforge_internal_contract_only",
        readiness_bucket="implemented_mesh_contract",
        evidence_sources=("ghostforge_core.cad.fixtures",),
        fixture_ids=("fixture_degenerate_mesh",),
        parameter_panel_targets=("tolerance",),
        selection_rule_targets=("vertex", "edge", "object"),
        topology_naming_targets=("duplicate_vertices_deleted", "collapsed_faces_reported"),
        failure_mode_targets=("collapsed_all_faces", "non_finite_geometry"),
        tolerance_targets=("linear_weld_tolerance",),
        ghostforge_application=("Use Plasticity tolerance probing to tune Ghost Forge weld defaults later.",),
    ),
    CommandProbePlan(
        command_id="recompute_normals",
        priority="medium",
        plasticity_stage="ghostforge_internal_contract_only",
        readiness_bucket="implemented_mesh_contract",
        evidence_sources=("ghostforge_core.cad.fixtures",),
        fixture_ids=("fixture_cube_mesh",),
        parameter_panel_targets=("normal_mode", "angle_weighting", "preserve_sharp_edges"),
        topology_naming_targets=("geometry_ids_preserved", "normals_modified"),
        failure_mode_targets=("empty_geometry", "non_finite_geometry"),
        ghostforge_application=("Treat normal edits as non-topology-mutating operations in manifests.",),
    ),
    CommandProbePlan(
        command_id="normalize_scale",
        priority="medium",
        plasticity_stage="ghostforge_internal_contract_only",
        readiness_bucket="implemented_mesh_contract",
        evidence_sources=("ghostforge_core.cad.fixtures",),
        fixture_ids=("fixture_cube_mesh",),
        parameter_panel_targets=("target_extent", "axis_scope", "apply_transform"),
        topology_naming_targets=("face_ids_preserved", "bounds_modified"),
        failure_mode_targets=("zero_volume", "empty_selection"),
        ghostforge_application=("Keep scale normalization as a descriptor-backed cleanup command.",),
    ),
    CommandProbePlan(
        command_id="face_change_grow",
        priority="critical",
        plasticity_stage="relationship_recorded_until_live_probe",
        readiness_bucket="review_as_option_or_alias",
        evidence_sources=("face-change-grow.png", "palette_probe_negative_reviews.json"),
        fixture_ids=("fixture_command_option_mapping", "fixture_cube_solid"),
        option_panel_targets=("grow",),
        selection_rule_targets=("face_selection", "adjacent_face_growth"),
        topology_naming_targets=("source_geometry_not_mutated_until_owner_command_commits",),
        failure_mode_targets=("no_face_selection", "owner_command_unavailable"),
        static_asset_resolution="Negative palette evidence shows no visible Face Change command; probe Match Face, Draft Face, Push Face, and Bridge Surface as likely owners.",
        automation_route=_route("match_face", query="Face Change", fixture_required=True, file_touching=False),
        ghostforge_application=(
            "Represent as option_of/contextual relationship, not a top-level command.",
            "Require owner command evidence before adding Qt action.",
        ),
    ),
    CommandProbePlan(
        command_id="xnurbs_boundary",
        priority="critical",
        plasticity_stage="relationship_recorded_until_live_probe",
        readiness_bucket="review_as_option_or_alias",
        evidence_sources=("xnurbs-boundary.png", "xnurbs-quad-sided.png", "palette_probe_negative_reviews.json"),
        fixture_ids=("fixture_command_option_mapping", "fixture_sheet_patch"),
        option_panel_targets=("boundary", "quad_sided", "continuity"),
        selection_rule_targets=("closed_boundary", "four_sided_boundary", "surface_patch"),
        topology_naming_targets=("surface_patch_id", "boundary_curve_lineage"),
        failure_mode_targets=("open_boundary", "wrong_side_count", "continuity_unsatisfied"),
        tolerance_targets=("surface_fitting_tolerance", "continuity_tolerance"),
        static_asset_resolution="Negative palette evidence shows no visible Xnurbs command; probe Sweep, Trim, Extend, and future Surface Patch ownership.",
        automation_route=_route("surface_patch", query="Xnurbs", fixture_required=True, file_touching=False),
        ghostforge_application=(
            "Keep XNURBS-like behavior as contextual surface-patch mode until live evidence proves command ownership.",
            "Design Ghost Forge surface tools around boundary constraints and continuity contracts.",
        ),
    ),
)


DEFAULT_FORMAT_PROBE_PLANS: tuple[FormatProbePlan, ...] = (
    FormatProbePlan(
        format_id="step_stp",
        direction="read_write_likely",
        confidence="high",
        evidence_sources=("dwgstep30.dll", "igestep30.dll", "rdmstep30.dll", "satstep31.dll", "stepstep30.dll", "xtstep30.dll"),
        option_targets=("units", "schema", "healing", "body_split_policy", "metadata_names"),
        fixture_ids=("fixture_cube_solid", "fixture_sheet_patch"),
        automation_route=_route("file_import", fixture_required=True, file_touching=True)
        + _route("file_export", fixture_required=True, file_touching=True),
        ghostforge_application=("Plan neutral B-rep import/export descriptors before kernel integration.",),
    ),
    FormatProbePlan(
        format_id="iges_igs",
        direction="read_write_likely",
        confidence="high",
        evidence_sources=("igestep30.dll", "wiges.dll"),
        option_targets=("surface_trim_policy", "units", "curve_import", "healing"),
        fixture_ids=("fixture_sheet_patch", "fixture_curve_profile"),
        automation_route=_route("file_import", fixture_required=True, file_touching=True)
        + _route("file_export", fixture_required=True, file_touching=True),
        ghostforge_application=("Keep surface and curve translation separate from mesh export.",),
    ),
    FormatProbePlan(
        format_id="parasolid_x_t_x_b",
        direction="read_write_likely",
        confidence="high",
        evidence_sources=("pk.node", "pskernel.dll", "101 Parasolid schema files"),
        option_targets=("binary_or_text", "schema_version", "units", "body_names"),
        fixture_ids=("fixture_cube_solid",),
        automation_route=_route("file_import", fixture_required=True, file_touching=True)
        + _route("file_export", fixture_required=True, file_touching=True),
        ghostforge_application=("Treat Parasolid as a future premium-kernel interoperability target.",),
    ),
    FormatProbePlan(
        format_id="sat_sab",
        direction="read_write_likely",
        confidence="high",
        evidence_sources=("satstep31.dll", "TD_AcisBuilder_26.8_16.dll", "wsat.dll"),
        option_targets=("binary_or_text", "units", "healing", "body_names"),
        fixture_ids=("fixture_cube_solid",),
        automation_route=_route("file_import", fixture_required=True, file_touching=True)
        + _route("file_export", fixture_required=True, file_touching=True),
        ghostforge_application=("Represent ACIS import/export separately from generic file IO.",),
    ),
    FormatProbePlan(
        format_id="dwg_dxf",
        direction="read_write_likely",
        confidence="high",
        evidence_sources=("dwgstep30.dll", "TD_DbIO_26.8_16.tx", "TD_DbEntities_26.8_16.tx"),
        option_targets=("version", "layers", "units", "2d_3d_policy", "lineweights"),
        fixture_ids=("fixture_curve_profile",),
        automation_route=_route("file_import", fixture_required=True, file_touching=True)
        + _route("file_export", fixture_required=True, file_touching=True),
        ghostforge_application=("Use layer/name preservation as a contract for CAD drawing interchange.",),
    ),
    FormatProbePlan(
        format_id="mesh_export",
        direction="export_likely",
        confidence="high",
        evidence_sources=("export-mesh-angle-tolerance.png", "export-mesh-inflect.png", "export-mesh-max-width.png"),
        option_targets=("angle_tolerance", "inflect", "max_width", "normals", "materials", "axis_preset"),
        fixture_ids=("fixture_cube_mesh",),
        automation_route=_route("export_mesh", query="Export Mesh", fixture_required=True, file_touching=True),
        ghostforge_application=("Make tessellation controls visible in both Qt and MCP.",),
    ),
)


DEFAULT_STATIC_ASSET_PROBE_PLANS: tuple[StaticAssetProbePlan, ...] = (
    StaticAssetProbePlan(
        asset_key="face_change",
        mapping_status="likely_option_or_alias",
        inferred_options=("grow",),
        evidence_assets=("face-change-grow.png",),
        candidate_owner_commands=("match_face", "draft_face", "push_face", "bridge_surface"),
        negative_palette_evidence=("evidence\\probe_palette_face_change_search_after.png",),
        next_action="Probe likely owner commands on face-selection fixtures and record option-panel ownership.",
        ghostforge_mapping="option_of:match_face until owner command evidence changes it",
    ),
    StaticAssetProbePlan(
        asset_key="xnurbs",
        mapping_status="likely_option_or_alias",
        inferred_options=("boundary", "quad_sided"),
        evidence_assets=("xnurbs-boundary.png", "xnurbs-quad-sided.png"),
        candidate_owner_commands=("extend", "sweep", "sweep_tool", "trim", "surface_patch"),
        negative_palette_evidence=("evidence\\probe_palette_xnurbs_search_after.png",),
        next_action="Probe surface owner commands on boundary fixtures and record contextual mode ownership.",
        ghostforge_mapping="contextual_mode_of:surface_patch until owner command evidence changes it",
    ),
    StaticAssetProbePlan(
        asset_key="export_mesh",
        mapping_status="controlled_probe_needed",
        inferred_options=("angle_tolerance", "inflect", "max_width"),
        evidence_assets=("export-mesh-angle-tolerance.png", "export-mesh-inflect.png", "export-mesh-max-width.png"),
        candidate_owner_commands=("file_export", "export_obj", "export_stl", "export_3mf", "export_svg"),
        next_action="Probe export dialog/options with disposable output paths before assigning final command ownership.",
        ghostforge_mapping="controlled_probe_needed export_pipeline command",
    ),
    StaticAssetProbePlan(
        asset_key="transform",
        mapping_status="controlled_probe_needed",
        inferred_options=("face_step",),
        evidence_assets=("transform-face-step.png",),
        candidate_owner_commands=("transform", "draft", "match_face", "draft_face", "push_face"),
        next_action="Probe transform and face-edit commands to classify Face Step as transform option or face-edit option.",
        ghostforge_mapping="controlled_probe_needed transform command with unresolved face_step option",
    ),
)


@dataclass(frozen=True)
class CadProbeMatrix:
    command_plans: dict[str, CommandProbePlan]
    format_plans: dict[str, FormatProbePlan]
    static_asset_plans: dict[str, StaticAssetProbePlan]

    @classmethod
    def from_defaults(cls) -> "CadProbeMatrix":
        return cls(
            command_plans={plan.command_id: plan for plan in DEFAULT_COMMAND_PROBE_PLANS},
            format_plans={plan.format_id: plan for plan in DEFAULT_FORMAT_PROBE_PLANS},
            static_asset_plans={plan.asset_key: plan for plan in DEFAULT_STATIC_ASSET_PROBE_PLANS},
        )

    def get_command_plan(self, command_id: str) -> CommandProbePlan:
        return self.command_plans[command_id]

    def all_command_plans(self) -> list[CommandProbePlan]:
        return [self.command_plans[key] for key in sorted(self.command_plans)]

    def all_format_plans(self) -> list[FormatProbePlan]:
        return [self.format_plans[key] for key in sorted(self.format_plans)]

    def all_static_asset_plans(self) -> list[StaticAssetProbePlan]:
        return [self.static_asset_plans[key] for key in sorted(self.static_asset_plans)]

    def summary(self) -> dict[str, Any]:
        bucket_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        live_probe_count = 0
        for plan in self.command_plans.values():
            bucket_counts[plan.readiness_bucket] = bucket_counts.get(plan.readiness_bucket, 0) + 1
            priority_counts[plan.priority] = priority_counts.get(plan.priority, 0) + 1
            if plan.needs_live_plasticity_probe:
                live_probe_count += 1
        return {
            "command_plan_count": len(self.command_plans),
            "format_plan_count": len(self.format_plans),
            "static_asset_plan_count": len(self.static_asset_plans),
            "command_readiness_bucket_counts": dict(sorted(bucket_counts.items())),
            "command_priority_counts": dict(sorted(priority_counts.items())),
            "commands_needing_live_plasticity_probe": live_probe_count,
        }


def build_default_probe_matrix() -> CadProbeMatrix:
    return CadProbeMatrix.from_defaults()


__all__ = [
    "AutomationStep",
    "CadProbeMatrix",
    "CommandProbePlan",
    "DEFAULT_COMMAND_PROBE_PLANS",
    "DEFAULT_FORMAT_PROBE_PLANS",
    "DEFAULT_STATIC_ASSET_PROBE_PLANS",
    "FormatProbePlan",
    "StaticAssetProbePlan",
    "build_default_probe_matrix",
]
