"""Fixture-level CAD command behavior matrix for native Ghost Forge modeling.

Descriptors say what a command accepts.  Fixtures say what geometry exists.
This module connects the two into replayable behavior cases: selected topology,
parameters/options, preflight requirements, expected topology lineage, failure
probes, tolerances, and automation evidence.  Plasticity remains comparator
evidence only; these are Ghost Forge-owned implementation contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


BehaviorResultState = Literal[
    "commit_allowed",
    "preview_only_until_kernel_handler",
    "controlled_probe_required",
    "relationship_owner_required",
]


class BehaviorSelectionBinding(FrozenModel):
    selection_id: str | None = None
    required_selection_kinds: tuple[str, ...] = ()
    required_object_kinds: tuple[str, ...] = ()
    active_object_required: bool = True
    active_plane_required: bool = False
    ordered: bool = False
    topology_ids: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()


class BehaviorTopologyTransition(FrozenModel):
    source: str
    relation: Literal["preserved", "created", "deleted", "modified", "split", "merged", "replaced"]
    results: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


class BehaviorFailureProbe(FrozenModel):
    probe_id: str = Field(min_length=1)
    mutation: str
    expected_failure_code: str
    recovery: str
    tolerance_sensitive: bool = False


class BehaviorAutomationRoute(FrozenModel):
    route_id: str = Field(min_length=1)
    steps: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    file_touching: bool = False
    disposable_fixture_required: bool = False
    reset_verification: tuple[str, ...] = ()


class CommandBehaviorCase(FrozenModel):
    case_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    fixture_id: str = Field(min_length=1)
    label: str
    result_state: BehaviorResultState
    plasticity_evidence_status: str = "ghostforge_contract"
    selection: BehaviorSelectionBinding = Field(default_factory=BehaviorSelectionBinding)
    parameters: dict[str, Any] = Field(default_factory=dict)
    option_panel_state: dict[str, Any] = Field(default_factory=dict)
    preconditions: tuple[str, ...] = ()
    expected_preflight: tuple[str, ...] = ()
    expected_count_deltas: dict[str, str] = Field(default_factory=dict)
    topology_transitions: tuple[BehaviorTopologyTransition, ...] = ()
    topology_naming_assertions: tuple[str, ...] = ()
    tolerance_assertions: tuple[str, ...] = ()
    failure_probes: tuple[BehaviorFailureProbe, ...] = ()
    automation: BehaviorAutomationRoute = Field(default_factory=lambda: BehaviorAutomationRoute(route_id="manual_contract"))
    ghostforge_implementation_notes: tuple[str, ...] = ()

    @property
    def needs_live_plasticity_evidence(self) -> bool:
        return self.plasticity_evidence_status in {
            "needs_parameter_panel_probe",
            "needs_fixture_behavior_probe",
            "needs_static_asset_owner_probe",
            "needs_file_dialog_probe",
        }


def _transition(
    source: str,
    relation: str,
    *results: str,
    notes: tuple[str, ...] = (),
) -> BehaviorTopologyTransition:
    return BehaviorTopologyTransition(
        source=source,
        relation=relation,  # type: ignore[arg-type]
        results=results,
        notes=notes,
    )


def _failure(
    probe_id: str,
    mutation: str,
    expected_failure_code: str,
    recovery: str,
    *,
    tolerance_sensitive: bool = False,
) -> BehaviorFailureProbe:
    return BehaviorFailureProbe(
        probe_id=probe_id,
        mutation=mutation,
        expected_failure_code=expected_failure_code,
        recovery=recovery,
        tolerance_sensitive=tolerance_sensitive,
    )


def _automation(
    route_id: str,
    *,
    steps: tuple[str, ...],
    evidence: tuple[str, ...],
    file_touching: bool = False,
    disposable: bool = False,
    reset: tuple[str, ...] = ("undo_or_escape_restores_fixture", "after_state_matches_before_snapshot"),
) -> BehaviorAutomationRoute:
    return BehaviorAutomationRoute(
        route_id=route_id,
        steps=steps,
        required_evidence=evidence,
        file_touching=file_touching,
        disposable_fixture_required=disposable,
        reset_verification=reset,
    )


DEFAULT_COMMAND_BEHAVIOR_CASES: tuple[CommandBehaviorCase, ...] = (
    CommandBehaviorCase(
        case_id="transform_cube_translate_preserves_topology",
        command_id="transform",
        fixture_id="fixture_cube_mesh",
        label="Translate a selected cube without renumbering topology",
        result_state="commit_allowed",
        selection=BehaviorSelectionBinding(
            selection_id="object",
            required_selection_kinds=("object",),
            required_object_kinds=("mesh",),
            topology_ids=("mesh_cube",),
            rules=("One active mesh object is required.", "Subobject selections should be promoted or rejected according to transform mode."),
        ),
        parameters={"translate": [1.0, 0.0, 0.0], "rotate_euler_deg": [0.0, 0.0, 0.0], "scale": 1.0},
        preconditions=("mesh has finite bounds", "object is not locked"),
        expected_preflight=("selection.count >= 1", "active_object_id present", "scale != 0"),
        expected_count_deltas={"objects": "0", "vertices": "0", "edges": "0", "faces": "0"},
        topology_transitions=(
            _transition("mesh_cube", "modified", "mesh_cube", notes=("bounds and vertex positions change",)),
            _transition("F_top", "preserved", "F_top"),
            _transition("E_top_front", "preserved", "E_top_front"),
        ),
        topology_naming_assertions=("object id remains stable", "face and edge ids remain stable", "bounds delta is recorded"),
        tolerance_assertions=("linear snap increment may alter translate value only before commit",),
        failure_probes=(
            _failure("zero_scale", "set scale to 0", "parameter.scale.invalid", "Use non-zero scale."),
            _failure("locked_object", "mark object locked", "selection.locked_object", "Unlock object or duplicate it."),
        ),
        automation=_automation(
            "transform_fixture_probe",
            steps=("load fixture_cube_mesh", "select object", "apply translate", "capture before/after topology snapshots", "undo"),
            evidence=("before_topology_snapshot", "after_topology_snapshot", "undo_snapshot", "parameter_snapshot"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Transform may be represented as object transform or baked vertices, but topology ids must remain stable.",),
    ),
    CommandBehaviorCase(
        case_id="delete_top_face_leaves_open_mesh",
        command_id="delete_selection",
        fixture_id="fixture_cube_mesh",
        label="Delete the named top face while preserving unselected face ids",
        result_state="commit_allowed",
        selection=BehaviorSelectionBinding(
            selection_id="top_face",
            required_selection_kinds=("face",),
            required_object_kinds=("mesh",),
            topology_ids=("F_top",),
            rules=("Delete face mode removes selected faces and any unreferenced vertices.", "Deleting all faces is blocked as a distinct failure."),
        ),
        preconditions=("selection is a proper subset of mesh faces",),
        expected_preflight=("face selection accepted", "delete.all_geometry not triggered"),
        expected_count_deltas={"objects": "0", "faces": "-1", "vertices": "<=0", "components": ">=0"},
        topology_transitions=(
            _transition("F_top", "deleted"),
            _transition("F_bottom", "preserved", "F_bottom"),
            _transition("mesh_cube", "modified", "mesh_cube", notes=("connectivity and normals update",)),
        ),
        topology_naming_assertions=("unselected face ids remain stable", "deleted face id is absent after commit", "open boundary ids are generated or reported"),
        failure_probes=(
            _failure("delete_all_faces", "select all faces", "delete.all_geometry", "Use object delete or reduce face selection."),
            _failure("empty_selection", "clear selection", "selection.count_below_minimum", "Select faces, edges, vertices, or an object."),
        ),
        automation=_automation(
            "delete_face_fixture_probe",
            steps=("load fixture_cube_mesh", "select top_face", "run delete_selection", "capture topology delta", "undo"),
            evidence=("selected_face_id", "after_face_count", "unselected_id_map", "undo_snapshot"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("This is the first destructive subobject edit contract for the native command path.",),
    ),
    CommandBehaviorCase(
        case_id="weld_degenerate_mesh_collapses_duplicates",
        command_id="weld",
        fixture_id="fixture_degenerate_mesh",
        label="Weld duplicate vertices and report collapsed faces",
        result_state="commit_allowed",
        selection=BehaviorSelectionBinding(
            selection_id="object",
            required_selection_kinds=("object", "vertex", "edge"),
            required_object_kinds=("mesh",),
            topology_ids=("degenerate_mesh",),
            rules=("Tolerance controls which vertices collapse.", "Collapsed faces are deleted and reported."),
        ),
        parameters={"tolerance": 1e-6},
        expected_preflight=("tolerance >= 0", "geometry finite", "mesh contains duplicate vertices"),
        expected_count_deltas={"vertices": "<0", "faces": "<=0"},
        topology_transitions=(
            _transition("duplicate_vertices", "merged", "welded_vertex"),
            _transition("zero_area_faces", "deleted"),
        ),
        topology_naming_assertions=("merged vertices record source ids", "deleted collapsed faces are reported"),
        tolerance_assertions=("larger tolerance may collapse more vertices and must be previewed before commit",),
        failure_probes=(
            _failure("collapsed_all_faces", "raise tolerance until every face collapses", "weld.collapsed_all_faces", "Lower tolerance.", tolerance_sensitive=True),
        ),
        automation=_automation(
            "weld_degenerate_fixture_probe",
            steps=("load fixture_degenerate_mesh", "run weld tolerance 1e-6", "capture merged/deleted ids", "undo"),
            evidence=("before_duplicate_count", "after_vertex_count", "collapsed_face_report", "undo_snapshot"),
            disposable=True,
        ),
    ),
    CommandBehaviorCase(
        case_id="recompute_normals_preserves_geometry",
        command_id="recompute_normals",
        fixture_id="fixture_cube_mesh",
        label="Recompute normals without changing geometry topology",
        result_state="commit_allowed",
        selection=BehaviorSelectionBinding(
            selection_id="object",
            required_selection_kinds=("object",),
            required_object_kinds=("mesh",),
            topology_ids=("mesh_cube",),
        ),
        expected_count_deltas={"vertices": "0", "edges": "0", "faces": "0"},
        topology_transitions=(
            _transition("mesh_cube.normals", "modified", "mesh_cube.normals"),
            _transition("mesh_cube.vertices", "preserved", "mesh_cube.vertices"),
            _transition("mesh_cube.faces", "preserved", "mesh_cube.faces"),
        ),
        topology_naming_assertions=("all geometry ids remain stable", "only normal buffers change"),
        failure_probes=(
            _failure("empty_geometry", "run on mesh with zero faces", "geometry.empty", "Generate or import valid geometry."),
        ),
        automation=_automation(
            "recompute_normals_fixture_probe",
            steps=("load fixture_cube_mesh", "invalidate normals", "run recompute_normals", "compare topology counts"),
            evidence=("normal_delta", "topology_count_delta", "parameter_snapshot"),
            disposable=True,
        ),
    ),
    CommandBehaviorCase(
        case_id="normalize_scale_cube_preserves_ids",
        command_id="normalize_scale",
        fixture_id="fixture_cube_mesh",
        label="Normalize cube extent while preserving ids",
        result_state="commit_allowed",
        selection=BehaviorSelectionBinding(
            selection_id="object",
            required_selection_kinds=("object",),
            required_object_kinds=("mesh",),
            topology_ids=("mesh_cube",),
        ),
        parameters={"target_extent": 2.0},
        expected_preflight=("target_extent > 0", "bounds are non-zero"),
        expected_count_deltas={"vertices": "0", "edges": "0", "faces": "0"},
        topology_transitions=(
            _transition("mesh_cube", "modified", "mesh_cube", notes=("bounds and vertex positions change",)),
            _transition("mesh_cube.faces", "preserved", "mesh_cube.faces"),
        ),
        failure_probes=(
            _failure("zero_volume", "use zero-volume mesh", "scale.zero_volume", "Repair or replace the input geometry."),
            _failure("invalid_target_extent", "set target_extent <= 0", "parameter.target_extent.below_minimum", "Use a positive extent."),
        ),
        automation=_automation(
            "normalize_scale_fixture_probe",
            steps=("load fixture_cube_mesh", "run normalize_scale target_extent 2", "capture bounds delta", "undo"),
            evidence=("before_bounds", "after_bounds", "id_map", "undo_snapshot"),
            disposable=True,
        ),
    ),
    CommandBehaviorCase(
        case_id="extrude_top_face_new_body_lineage",
        command_id="extrude",
        fixture_id="fixture_cube_solid",
        label="Extrude the top face as a new body and record cap/side lineage",
        result_state="preview_only_until_kernel_handler",
        plasticity_evidence_status="needs_fixture_behavior_probe",
        selection=BehaviorSelectionBinding(
            selection_id="top_face",
            required_selection_kinds=("face",),
            required_object_kinds=("mesh", "solid"),
            topology_ids=("F_top",),
            rules=("Closed planar face/profile required.", "Operation mode controls whether source body is joined, cut, intersected, or a new body is created."),
        ),
        parameters={"distance": 1.0, "direction": "normal", "operation": "new_body", "draft_angle_deg": 0.0},
        option_panel_state={"extent_type": "distance", "symmetric": False, "thin_extrude": False},
        preconditions=("selected profile is closed", "profile is planar", "distance != 0"),
        expected_preflight=("required distance present", "face/profile selection accepted", "planned handler gate until kernel exists"),
        expected_count_deltas={"bodies": "+1", "faces": ">0", "edges": ">0"},
        topology_transitions=(
            _transition("F_top", "modified", "F_top_source_profile"),
            _transition("F_top", "created", "F_extrude_cap"),
            _transition("E_top_front", "created", "F_extrude_side_front"),
            _transition("solid_cube", "created", "solid_extrude_body"),
        ),
        topology_naming_assertions=("cap face id is distinct from source face id", "each profile edge creates one side-face lineage record", "operation mode is recorded in manifest"),
        tolerance_assertions=("profile closure tolerance gates open profiles", "side-face stitching tolerance is recorded"),
        failure_probes=(
            _failure("open_profile", "use open curve profile", "extrude.open_profile", "Close the profile or choose surface extrusion.", tolerance_sensitive=True),
            _failure("zero_distance", "set distance to 0", "extrude.zero_distance", "Use non-zero distance."),
            _failure("self_intersection", "extrude into self-intersecting direction", "operation.self_intersection", "Reduce distance or change operation mode.", tolerance_sensitive=True),
        ),
        automation=_automation(
            "extrude_parameter_and_fixture_probe",
            steps=("load fixture_cube_solid", "select top_face", "open extrude", "capture parameter panel", "execute in disposable document", "capture topology delta", "undo/reset"),
            evidence=("parameter_panel_screenshot", "observed_parameter_schema", "before_after_topology_snapshot", "lineage_map", "undo_snapshot"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Implement a mesh preview first if needed, but preserve this B-rep lineage contract for the future kernel.",),
    ),
    CommandBehaviorCase(
        case_id="fillet_top_front_edge_blend_lineage",
        command_id="fillet",
        fixture_id="fixture_cube_solid",
        label="Fillet one cube edge and record blend/adjacent-face lineage",
        result_state="preview_only_until_kernel_handler",
        plasticity_evidence_status="needs_fixture_behavior_probe",
        selection=BehaviorSelectionBinding(
            selection_id="top_front_edge",
            required_selection_kinds=("edge",),
            required_object_kinds=("mesh", "solid"),
            topology_ids=("E_top_front",),
            rules=("Edge selection required.", "Tangent-chain option may expand selection.", "Radius must fit local adjacent-face extents."),
        ),
        parameters={"radius": 0.05, "continuity": "g1", "setback": False},
        option_panel_state={"chain_selection": True, "variable_radius": False},
        preconditions=("edge has two adjacent faces", "radius > 0", "radius fits local geometry"),
        expected_preflight=("edge selection accepted", "required radius present", "planned handler gate until kernel exists"),
        expected_count_deltas={"faces": ">0", "edges": ">=0"},
        topology_transitions=(
            _transition("E_top_front", "deleted", notes=("sharp edge is replaced by blend topology",)),
            _transition("F_top", "modified", "F_top_trimmed"),
            _transition("F_front", "modified", "F_front_trimmed"),
            _transition("E_top_front", "created", "F_blend_top_front"),
        ),
        topology_naming_assertions=("blend face id is created", "adjacent face lineage records trim/replace relation", "removed sharp edge id is retained as deleted source"),
        tolerance_assertions=("blend tolerance and angular continuity tolerance are recorded",),
        failure_probes=(
            _failure("radius_too_large", "set radius larger than adjacent face can support", "fillet.radius_too_large", "Lower radius.", tolerance_sensitive=True),
            _failure("zero_radius", "set radius to 0", "parameter.radius.below_minimum", "Use positive radius."),
            _failure("non_manifold_edge", "select non-manifold edge", "fillet.non_manifold_edge", "Repair topology or select a valid solid edge."),
        ),
        automation=_automation(
            "fillet_fixture_behavior_probe",
            steps=("load fixture_cube_solid", "select top_front_edge", "open fillet", "capture panel", "execute small radius", "capture blend lineage", "undo/reset"),
            evidence=("parameter_panel_screenshot", "blend_face_ids", "adjacent_face_lineage", "failure_radius_too_large_probe", "undo_snapshot"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Fillet readiness depends more on robust failure diagnostics than on a single happy-path blend.",),
    ),
    CommandBehaviorCase(
        case_id="project_curve_to_sheet_without_imprint",
        command_id="project",
        fixture_id="fixture_sheet_patch",
        label="Project a curve onto a sheet without mutating the target surface",
        result_state="preview_only_until_kernel_handler",
        plasticity_evidence_status="needs_parameter_panel_probe",
        selection=BehaviorSelectionBinding(
            selection_id="surface",
            required_selection_kinds=("curve", "face", "surface"),
            required_object_kinds=("mesh", "surface"),
            ordered=True,
            topology_ids=("C_square", "S_patch"),
            rules=("Source curve/profile must be selected before target surface.", "Projection mode controls direction source.", "Imprint/trim options decide whether target topology mutates."),
        ),
        parameters={"projection_mode": "normal", "imprint_result": False, "trim_to_target": False},
        option_panel_state={"projection_space": "target_normal"},
        expected_preflight=("ordered selection contains source and target", "target surface present", "planned handler gate until kernel exists"),
        expected_count_deltas={"surfaces": "0", "curves": ">0"},
        topology_transitions=(
            _transition("S_patch", "preserved", "S_patch"),
            _transition("C_square", "created", "C_projected_on_S_patch"),
        ),
        topology_naming_assertions=("target surface id is preserved when imprint_result is false", "projected curve id links to source curve and target surface"),
        tolerance_assertions=("curve projection tolerance determines miss/trim diagnostics",),
        failure_probes=(
            _failure("projection_miss", "project curve away from target", "project.projection_miss", "Change direction or target.", tolerance_sensitive=True),
            _failure("missing_target_surface", "select only source curve", "selection.count_below_minimum", "Select source curve then target surface."),
        ),
        automation=_automation(
            "project_ordered_selection_probe",
            steps=("load fixture_sheet_patch and fixture_curve_profile", "select source then target", "open project", "capture panel", "preview/execute", "verify target preserved", "undo/reset"),
            evidence=("ordered_selection_record", "parameter_panel_screenshot", "projected_curve_id", "target_surface_id_preserved"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Ordered selection must be a first-class core object, not a Qt-only sequence.",),
    ),
    CommandBehaviorCase(
        case_id="export_mesh_cube_glb_preserves_source",
        command_id="export_mesh",
        fixture_id="fixture_cube_mesh",
        label="Export a cube mesh artifact without mutating source topology",
        result_state="controlled_probe_required",
        plasticity_evidence_status="needs_file_dialog_probe",
        selection=BehaviorSelectionBinding(
            selection_id="object",
            required_selection_kinds=("object",),
            required_object_kinds=("mesh", "scene"),
            active_object_required=False,
            topology_ids=("mesh_cube",),
            rules=("Export scope can be selection, visible scene, whole scene, or named set.", "File automation must use workspace-controlled paths."),
        ),
        parameters={"format": "glb", "target_path": "knowledge_base/fixtures/exports/cube.glb", "include_materials": True, "axis_preset": "unity"},
        option_panel_state={"angle_tolerance": 1.0, "max_width": None, "inflect": False, "overwrite_policy": "versioned_name"},
        preconditions=("target path is under approved workspace export folder", "export scope is non-empty"),
        expected_preflight=("target_path present", "format supported", "controlled probe warning until Plasticity dialog evidence is captured"),
        expected_count_deltas={"source_vertices": "0", "source_faces": "0", "artifact_files": "+1"},
        topology_transitions=(
            _transition("mesh_cube", "preserved", "mesh_cube"),
            _transition("mesh_cube", "created", "cube.glb_artifact", notes=("artifact provenance, not scene topology",)),
        ),
        topology_naming_assertions=("source topology ids are unchanged", "artifact records exported node names and material slot names"),
        tolerance_assertions=("angle_tolerance/max_width/inflect are serialized with artifact provenance",),
        failure_probes=(
            _failure("missing_target_path", "omit target_path", "parameter.target_path.required", "Choose an output path."),
            _failure("permission_denied", "target protected directory", "path.permission_denied", "Choose a writable workspace path."),
            _failure("empty_scope", "export empty scene", "export.empty_scope", "Select geometry or change scope."),
        ),
        automation=_automation(
            "export_mesh_file_dialog_probe",
            steps=("load fixture_cube_mesh", "select object", "invoke export mesh", "capture file/options dialog", "export to workspace temp path", "record artifact", "delete/reset only workspace export file"),
            evidence=("file_dialog_or_options_screenshot", "workspace_path_file_record", "artifact_manifest_record", "source_topology_preserved"),
            file_touching=True,
            disposable=True,
            reset=("remove_only_workspace_export_artifact", "source_scene_snapshot_unchanged"),
        ),
        ghostforge_implementation_notes=("This case bridges Plasticity static assets into Ghost Forge mesh export option schema while keeping file writes safety-gated.",),
    ),
    CommandBehaviorCase(
        case_id="face_change_grow_relationship_owner_probe",
        command_id="face_change_grow",
        fixture_id="fixture_command_option_mapping",
        label="Classify Face Change Grow as option/alias/contextual evidence before implementation",
        result_state="relationship_owner_required",
        plasticity_evidence_status="needs_static_asset_owner_probe",
        selection=BehaviorSelectionBinding(
            selection_id=None,
            required_selection_kinds=("face",),
            required_object_kinds=("mesh", "solid"),
            topology_ids=("F_top",),
            rules=("Negative palette evidence blocks top-level command exposure.", "Likely owner commands must be probed with face selection."),
        ),
        parameters={"grow": True},
        preconditions=("candidate owner command selected", "face selection fixture available"),
        expected_preflight=("relationship owner unresolved", "no standalone mutation allowed"),
        expected_count_deltas={"source_geometry": "0"},
        topology_transitions=(
            _transition("F_top", "preserved", "F_top", notes=("until owner command commits",)),
            _transition("face_change_grow.option_state", "modified", "candidate_owner.option_state"),
        ),
        topology_naming_assertions=("no topology effect is claimed until owner command evidence exists",),
        failure_probes=(
            _failure("owner_command_unavailable", "invoke as standalone", "relationship.owner_required", "Resolve owner command first."),
        ),
        automation=_automation(
            "face_change_owner_probe",
            steps=("search palette for Face Change", "record negative result", "probe Match Face/Draft Face/Push Face with face selection", "capture option panels"),
            evidence=("negative_palette_screenshot", "candidate_owner_panel_screenshots", "observed_option_owner"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Keep as option_of match_face until stronger evidence identifies a different owner.",),
    ),
    CommandBehaviorCase(
        case_id="xnurbs_boundary_contextual_surface_probe",
        command_id="xnurbs_boundary",
        fixture_id="fixture_command_option_mapping",
        label="Classify XNURBS Boundary as contextual surface-patch mode",
        result_state="relationship_owner_required",
        plasticity_evidence_status="needs_static_asset_owner_probe",
        selection=BehaviorSelectionBinding(
            selection_id=None,
            required_selection_kinds=("edge", "curve"),
            required_object_kinds=("surface", "mesh"),
            topology_ids=("B_outer",),
            rules=("Closed boundary or four-sided boundary is required for surface patch context.", "Negative palette evidence blocks top-level command exposure."),
        ),
        parameters={"boundary_mode": "boundary", "continuity": "g1"},
        option_panel_state={"quad_sided": False},
        expected_preflight=("relationship owner unresolved", "no standalone mutation allowed"),
        expected_count_deltas={"source_geometry": "0"},
        topology_transitions=(
            _transition("B_outer", "preserved", "B_outer", notes=("until surface patch owner commits",)),
            _transition("xnurbs_boundary.context_mode", "modified", "surface_patch.context_mode"),
        ),
        topology_naming_assertions=("boundary curve lineage belongs to eventual owner command",),
        tolerance_assertions=("surface fitting and continuity tolerances are inherited from owner command until verified",),
        failure_probes=(
            _failure("open_boundary", "use open boundary", "surface_patch.open_boundary", "Close boundary or choose a different surface command.", tolerance_sensitive=True),
            _failure("wrong_side_count", "use non-four-sided quad mode", "surface_patch.wrong_side_count", "Use boundary mode or select four sides."),
        ),
        automation=_automation(
            "xnurbs_context_owner_probe",
            steps=("search palette for Xnurbs", "record negative result", "probe Surface Patch/Sweep/Extend/Trim with boundary fixture", "capture contextual options"),
            evidence=("negative_palette_screenshot", "candidate_owner_panel_screenshots", "contextual_mode_owner"),
            disposable=True,
        ),
        ghostforge_implementation_notes=("Design Ghost Forge surface patch around explicit boundary/continuity modes even before matching Plasticity ownership.",),
    ),
)


@dataclass(frozen=True)
class CadBehaviorMatrix:
    cases: dict[str, CommandBehaviorCase]

    @classmethod
    def from_defaults(cls) -> "CadBehaviorMatrix":
        return cls({case.case_id: case for case in DEFAULT_COMMAND_BEHAVIOR_CASES})

    def get(self, case_id: str) -> CommandBehaviorCase:
        return self.cases[case_id]

    def all_cases(self) -> list[CommandBehaviorCase]:
        return [self.cases[key] for key in sorted(self.cases)]

    def cases_for_command(self, command_id: str) -> list[CommandBehaviorCase]:
        return [case for case in self.all_cases() if case.command_id == command_id]

    def summary(self) -> dict[str, Any]:
        state_counts: dict[str, int] = {}
        evidence_counts: dict[str, int] = {}
        command_ids: set[str] = set()
        live_evidence_count = 0
        for case in self.cases.values():
            command_ids.add(case.command_id)
            state_counts[case.result_state] = state_counts.get(case.result_state, 0) + 1
            evidence_counts[case.plasticity_evidence_status] = evidence_counts.get(case.plasticity_evidence_status, 0) + 1
            if case.needs_live_plasticity_evidence:
                live_evidence_count += 1
        return {
            "case_count": len(self.cases),
            "covered_command_count": len(command_ids),
            "covered_command_ids": sorted(command_ids),
            "result_state_counts": dict(sorted(state_counts.items())),
            "plasticity_evidence_status_counts": dict(sorted(evidence_counts.items())),
            "cases_needing_live_plasticity_evidence": live_evidence_count,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_default_behavior_matrix() -> CadBehaviorMatrix:
    return CadBehaviorMatrix.from_defaults()


__all__ = [
    "BehaviorAutomationRoute",
    "BehaviorFailureProbe",
    "BehaviorResultState",
    "BehaviorSelectionBinding",
    "BehaviorTopologyTransition",
    "CadBehaviorMatrix",
    "CommandBehaviorCase",
    "DEFAULT_COMMAND_BEHAVIOR_CASES",
    "build_default_behavior_matrix",
]
