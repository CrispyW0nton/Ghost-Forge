"""Native Ghost Forge CAD logic blueprint.

Plasticity recon is development evidence, not a runtime dependency.  This file
captures the modeling logic Ghost Forge should own: command pipelines,
selection semantics, topology identity, option-panel behavior, tolerance
handling, export/import policy, and verification gates.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CadLogicStage(FrozenModel):
    stage_id: str = Field(min_length=1)
    purpose: str
    required_inputs: tuple[str, ...] = ()
    produced_outputs: tuple[str, ...] = ()
    failure_codes: tuple[str, ...] = ()


class CadLogicPattern(FrozenModel):
    pattern_id: str = Field(min_length=1)
    label: str
    applies_to: tuple[str, ...] = ()
    intent: str
    command_pipeline: tuple[CadLogicStage, ...] = ()
    selection_logic: tuple[str, ...] = ()
    parameter_logic: tuple[str, ...] = ()
    option_panel_logic: tuple[str, ...] = ()
    topology_logic: tuple[str, ...] = ()
    tolerance_logic: tuple[str, ...] = ()
    failure_logic: tuple[str, ...] = ()
    undo_manifest_logic: tuple[str, ...] = ()
    verification_logic: tuple[str, ...] = ()
    ghostforge_advantage: tuple[str, ...] = ()


def _stage(
    stage_id: str,
    purpose: str,
    *,
    required_inputs: tuple[str, ...] = (),
    produced_outputs: tuple[str, ...] = (),
    failure_codes: tuple[str, ...] = (),
) -> CadLogicStage:
    return CadLogicStage(
        stage_id=stage_id,
        purpose=purpose,
        required_inputs=required_inputs,
        produced_outputs=produced_outputs,
        failure_codes=failure_codes,
    )


DEFAULT_CAD_LOGIC_PATTERNS: tuple[CadLogicPattern, ...] = (
    CadLogicPattern(
        pattern_id="descriptor_driven_command_pipeline",
        label="Descriptor Driven Command Pipeline",
        applies_to=("extrude", "fillet", "project", "transform", "delete_selection", "export_mesh"),
        intent="Every modeling command is data-described, preflighted, previewed, committed, undoable, and manifest-recorded by Ghost Forge core.",
        command_pipeline=(
            _stage(
                "collect_context",
                "Read active document, active tool plane, selection set, command descriptor, and fixture/test context.",
                required_inputs=("scene_state", "selection_state", "cad_command_descriptor"),
                produced_outputs=("command_context",),
                failure_codes=("selection.empty", "active_plane.missing"),
            ),
            _stage(
                "resolve_parameters",
                "Merge defaults, user-entered values, option-panel state, unit conversions, and inferred preview settings.",
                required_inputs=("command_context", "parameter_schema", "option_panel_schema"),
                produced_outputs=("resolved_parameters",),
                failure_codes=("parameter.missing_required", "parameter.out_of_range"),
            ),
            _stage(
                "preflight_geometry",
                "Validate selection kinds, topology health, tolerance feasibility, self-intersection risk, and destructive/file safety.",
                required_inputs=("resolved_parameters", "selected_topology"),
                produced_outputs=("preflight_report",),
                failure_codes=("geometry.non_finite", "tolerance.failed", "operation.self_intersection"),
            ),
            _stage(
                "preview_result",
                "Build reversible preview geometry and warnings without mutating the committed scene.",
                required_inputs=("preflight_report",),
                produced_outputs=("preview_geometry", "preview_warnings"),
            ),
            _stage(
                "commit_transaction",
                "Execute the operation in a named undo transaction and produce structured topology/result deltas.",
                required_inputs=("resolved_parameters", "preflight_report"),
                produced_outputs=("topology_delta", "result_summary", "undo_record"),
                failure_codes=("kernel.unsupported", "operation.failed"),
            ),
            _stage(
                "record_provenance",
                "Persist command id, parameters, selection lineage, topology delta, tolerance report, and audit effects into the manifest.",
                required_inputs=("topology_delta", "result_summary", "undo_record"),
                produced_outputs=("manifest_event",),
            ),
        ),
        selection_logic=(
            "Selection is a core domain object, not Qt widget state.",
            "Each selected item carries object id, subobject kind, topology id, selection order, and filter reason.",
            "Commands declare accepted object/subobject kinds, min/max counts, ordering, active-object, and active-plane requirements.",
        ),
        parameter_logic=(
            "Parameters are typed data with defaults, units, ranges, enum values, and validation rules.",
            "The same schema drives Qt controls, MCP payloads, operation graph nodes, test fixtures, and manifest serialization.",
            "Inferred Plasticity templates inform schema candidates, but final Ghost Forge schemas must be verified by Ghost Forge tests.",
        ),
        option_panel_logic=(
            "Option panels are projections of command schema groups, not handwritten per-widget logic.",
            "Transient options are stored in command context until commit, then recorded in the undo and manifest event.",
            "Aliases/contextual modes are represented as relationships to owner commands instead of top-level command duplication.",
        ),
        topology_logic=(
            "Every commit returns created, deleted, modified, preserved, and lineage topology ids.",
            "Face/edge ids are stable where mathematically possible and lineage-recorded where operations split or replace topology.",
            "Topology summaries include counts, bounds, components, material slots, and names before and after execution.",
        ),
        tolerance_logic=(
            "Tolerance is an explicit command input or policy, never a hidden global magic number.",
            "Linear and angular tolerances are stored with the command result and are testable against fixture geometry.",
        ),
        failure_logic=(
            "Failures are structured product behavior: code, message, recovery, and optional partial diagnostics.",
            "Preflight failures do not mutate the scene.",
        ),
        undo_manifest_logic=(
            "Undo records carry command id, parameter snapshot, topology delta, and file/manifest side effects.",
            "Manifest provenance is emitted by core command execution, not by Qt or MCP wrappers.",
        ),
        verification_logic=(
            "A command is not ready until descriptor, schema, selection contract, fixture expectations, topology delta, failure modes, undo, Qt, MCP, and manifest behavior are covered.",
            "Plasticity observations are used as comparator evidence, not runtime dependencies.",
        ),
        ghostforge_advantage=(
            "Artists and agents can inspect why a command is available, blocked, or unsafe before running it.",
            "The same command logic can run from Qt, MCP, tests, and future headless automation.",
        ),
    ),
    CadLogicPattern(
        pattern_id="topology_identity_and_lineage",
        label="Topology Identity And Lineage",
        applies_to=("extrude", "fillet", "project", "delete_selection", "weld", "transform"),
        intent="Ghost Forge tracks topology identity explicitly so direct-modeling operations remain explainable and testable.",
        command_pipeline=(
            _stage("snapshot_before", "Capture stable ids, counts, names, materials, bounds, and selection lineage before execution.", produced_outputs=("before_topology_snapshot",)),
            _stage("solve_operation", "Run the mesh or future CAD-kernel operation while collecting replacement/split/merge relations.", required_inputs=("before_topology_snapshot",), produced_outputs=("raw_result_geometry", "lineage_relations")),
            _stage("assign_result_ids", "Preserve ids where possible and assign lineage-tagged ids to created or replacement topology.", required_inputs=("lineage_relations",), produced_outputs=("after_topology_snapshot", "topology_delta")),
        ),
        selection_logic=(
            "Selection stores topology ids that survive preflight and can be mapped through result lineage.",
            "Ordered selections remain ordered through the command context for commands such as project, loft, sweep, and bridge.",
        ),
        parameter_logic=("Topology-affecting parameters are stored with result lineage so later audits can explain why topology changed.",),
        option_panel_logic=("Options that change topology policy, such as join/cut/new body, imprint, trim, heal, or chain selection, must be explicit schema values.",),
        topology_logic=(
            "Preserve unaffected ids.",
            "Record split, merge, delete, replace, and create relationships.",
            "Expose topology deltas to tests, manifests, undo, and MCP.",
        ),
        tolerance_logic=("Lineage decisions record the tolerance used to merge, weld, stitch, or heal nearby topology.",),
        failure_logic=(
            "If identity cannot be mapped confidently, return a warning or failure depending on command acceptance gates.",
            "Deletion of all geometry is a distinct failure from deletion of selected subobjects.",
        ),
        undo_manifest_logic=("Undo restores both geometry and stable topology ids where possible.",),
        verification_logic=("Fixture tests must assert which ids are preserved, created, deleted, modified, and lineage-linked.",),
        ghostforge_advantage=("Ghost Forge can make topology naming inspectable instead of mysterious.",),
    ),
    CadLogicPattern(
        pattern_id="export_import_format_pipeline",
        label="Export Import Format Pipeline",
        applies_to=("export_mesh", "file_import", "file_export", "step_stp", "iges_igs", "parasolid_x_t_x_b", "sat_sab", "dwg_dxf"),
        intent="File interop is a descriptor-driven translation pipeline with explicit options, safety, provenance, and round-trip tests.",
        command_pipeline=(
            _stage(
                "resolve_io_scope",
                "Resolve selected objects, whole-scene scope, hidden/locked inclusion, units, axis preset, and target path.",
                required_inputs=("scene_state", "selection_state", "format_descriptor"),
                produced_outputs=("io_scope",),
                failure_codes=("export.empty_scene", "path.missing"),
            ),
            _stage(
                "resolve_format_options",
                "Resolve format-specific options such as tessellation angle, max width, inflection, healing, layers, schema version, names, materials, normals, and UVs.",
                required_inputs=("io_scope", "format_option_schema"),
                produced_outputs=("resolved_format_options",),
                failure_codes=("format.unsupported_option",),
            ),
            _stage(
                "translate_geometry",
                "Translate CAD or mesh data through the selected backend without mutating source scene topology.",
                required_inputs=("resolved_format_options",),
                produced_outputs=("artifact_record", "translation_report"),
                failure_codes=("translator.failed", "permission.denied"),
            ),
            _stage(
                "verify_artifact",
                "Verify emitted file location, extension, size, format family, and optional round-trip summary.",
                required_inputs=("artifact_record",),
                produced_outputs=("file_artifact_manifest", "round_trip_report"),
            ),
        ),
        selection_logic=(
            "Export scope is explicit: selection, visible scene, whole scene, or named set.",
            "Import creates new named objects and records source file provenance.",
        ),
        parameter_logic=(
            "Format, target path, units, axis/up conversion, include materials, and overwrite policy are required schema concepts.",
            "Mesh tessellation controls such as angle tolerance, max width, and inflection are separate format options.",
        ),
        option_panel_logic=(
            "Format-specific option panels are generated from format descriptors, not from generic file-dialog code.",
            "Potential Plasticity static options become Ghost Forge option candidates only after fixture/export evidence validates them.",
        ),
        topology_logic=(
            "Export preserves source scene topology.",
            "Import records created object ids, source names, layers, units, and translation warnings.",
        ),
        tolerance_logic=(
            "Mesh export stores tessellation tolerance.",
            "CAD import stores healing/stitching tolerance and reports changed topology.",
        ),
        failure_logic=(
            "File failures include missing path, permission denied, unsupported format, translator unavailable, empty export scope, and invalid units.",
            "File failures do not partially mutate the scene unless an import transaction can be fully undone.",
        ),
        undo_manifest_logic=(
            "Export creates artifact provenance, not scene mutation.",
            "Import is a scene mutation transaction with source-file provenance.",
        ),
        verification_logic=(
            "Each supported format needs fixture export/import tests and option-specific assertions.",
            "File probes must write only to workspace-controlled temporary paths.",
        ),
        ghostforge_advantage=("Ghost Forge can make CAD/game export settings reproducible and auditable from day one.",),
    ),
    CadLogicPattern(
        pattern_id="static_asset_classification",
        label="Static Asset Classification",
        applies_to=("face_change_grow", "xnurbs_boundary", "transform", "export_mesh"),
        intent="Static assets become evidence candidates, not automatic top-level commands.",
        command_pipeline=(
            _stage("collect_static_evidence", "Read static asset names, screenshots, nearby command candidates, and palette search results.", produced_outputs=("static_evidence_record",)),
            _stage("classify_relationship", "Classify as command, alias, option, contextual mode, tutorial/media asset, or unresolved candidate.", required_inputs=("static_evidence_record",), produced_outputs=("command_relationship_record",)),
            _stage("verify_owner", "Probe likely owner commands before surfacing a Qt action or MCP mutation path.", required_inputs=("command_relationship_record",), produced_outputs=("owner_verification_report",)),
        ),
        selection_logic=("Relationship candidates inherit selection rules from their owner command until proven standalone.",),
        parameter_logic=("Static inferred options are candidates until an observed option panel confirms control names and values.",),
        option_panel_logic=("Options such as Face Change Grow or XNURBS Boundary attach to owner command panels instead of creating duplicate command handlers.",),
        topology_logic=("Relationship entries must not claim topology effects until owner command behavior is observed.",),
        tolerance_logic=("Contextual surface modes inherit owner tolerance policy until a dedicated solver exists.",),
        failure_logic=("Unverified ownership blocks top-level exposure.",),
        undo_manifest_logic=("Manifest records option ownership and source evidence when a relationship is implemented.",),
        verification_logic=("Negative palette evidence must remain visible in docs/tests so Ghost Forge does not invent unsupported commands.",),
        ghostforge_advantage=("Ghost Forge avoids copying UI names blindly and instead builds a cleaner command model.",),
    ),
)


@dataclass(frozen=True)
class CadLogicBlueprint:
    patterns: dict[str, CadLogicPattern]

    @classmethod
    def from_defaults(cls) -> "CadLogicBlueprint":
        return cls({pattern.pattern_id: pattern for pattern in DEFAULT_CAD_LOGIC_PATTERNS})

    def all_patterns(self) -> list[CadLogicPattern]:
        return [self.patterns[key] for key in sorted(self.patterns)]

    def get(self, pattern_id: str) -> CadLogicPattern:
        return self.patterns[pattern_id]

    def patterns_for_command(self, command_id: str) -> list[CadLogicPattern]:
        return [pattern for pattern in self.all_patterns() if command_id in pattern.applies_to]

    def summary(self) -> dict[str, object]:
        commands: set[str] = set()
        for pattern in self.patterns.values():
            commands.update(pattern.applies_to)
        return {
            "pattern_count": len(self.patterns),
            "covered_command_or_format_count": len(commands),
            "covered_command_or_format_ids": sorted(commands),
        }


def build_default_logic_blueprint() -> CadLogicBlueprint:
    return CadLogicBlueprint.from_defaults()


__all__ = [
    "CadLogicBlueprint",
    "CadLogicPattern",
    "CadLogicStage",
    "DEFAULT_CAD_LOGIC_PATTERNS",
    "build_default_logic_blueprint",
]
