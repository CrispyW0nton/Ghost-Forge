"""Default Ghost Forge CAD command registry.

The first descriptors are intentionally modest: they wrap existing mesh tools
and mark Plasticity-derived CAD families as planned or contextual.  The value is
the contract shape.  Every future command should become inspectable here before
it is surfaced in Qt or MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .schema import (
    CadCommandDescriptor,
    FailureMode,
    FormatOption,
    ParameterSpec,
    SelectionContract,
    TolerancePolicy,
    TopologyEffects,
    UndoContract,
)


def _param(name: str, type_: str, **kwargs: object) -> ParameterSpec:
    return ParameterSpec(name=name, type=type_, **kwargs)


def _failure(code: str, message: str, recovery: str) -> FailureMode:
    return FailureMode(code=code, message=message, recovery=recovery)


COMMON_MESH_FAILURES = (
    _failure("selection.empty", "No compatible mesh or sub-object selection is active.", "Select a mesh or valid sub-objects."),
    _failure("geometry.empty", "Input geometry has no faces or vertices.", "Import or generate valid geometry first."),
    _failure("geometry.non_finite", "Input geometry contains NaN or infinite coordinates.", "Run validation and repair before modeling."),
)

COMMON_SOURCE_FAILURES = (
    _failure("primitive.invalid_parameters", "Primitive dimensions or placement parameters are invalid.", "Use finite positive dimensions before executing the source node."),
)


def _mesh_command(
    *,
    command_id: str,
    label: str,
    family: str,
    source_operation: str,
    parameters: tuple[ParameterSpec, ...] = (),
    selection: SelectionContract | None = None,
    topology: TopologyEffects | None = None,
    tolerance: TolerancePolicy | None = None,
    failures: tuple[FailureMode, ...] = (),
    base_failures: tuple[FailureMode, ...] = COMMON_MESH_FAILURES,
) -> CadCommandDescriptor:
    return CadCommandDescriptor(
        command_id=command_id,
        label=label,
        family=family,
        status="implemented_mesh",
        implementation_kind="trimesh",
        source_operation=source_operation,
        selection_contract=selection or SelectionContract(min_count=1),
        parameter_schema=parameters,
        option_panel_schema=parameters,
        preview_contract=("mesh_bounds", "mesh_stats_delta"),
        topology_effects=topology or TopologyEffects(modifies=("vertices", "faces", "normals")),
        tolerance_policy=tolerance or TolerancePolicy(description="Mesh-space tolerance; not a B-rep kernel tolerance."),
        failure_modes=base_failures + failures,
        undo_contract=UndoContract(transaction_name=label, delta_kind="mesh_file_delta"),
        fixture_tests=("fixture_cube_mesh", "fixture_degenerate_mesh"),
        manifest_effect=("provenance.operation", "validation.geometry_summary"),
        mcp_surface={"resource": "ghostforge://cad/commands/{command_id}", "mutation": "writes_new_mesh"},
        qt_surface={"action": f"cad.{command_id}", "panel": "ModelingToolsPanel"},
        acceptance_gates=(
            "descriptor_exists",
            "parameter_schema_exists",
            "selection_contract_enforced",
            "topology_summary_recorded",
            "undo_transaction_recorded",
            "manifest_provenance_recorded",
        ),
    )


def _planned_cad_command(
    *,
    command_id: str,
    label: str,
    family: str,
    plasticity_sources: tuple[str, ...],
    parameters: tuple[ParameterSpec, ...],
    selection: SelectionContract,
    topology: TopologyEffects,
    tolerance: TolerancePolicy,
) -> CadCommandDescriptor:
    return CadCommandDescriptor(
        command_id=command_id,
        label=label,
        family=family,
        status="planned",
        implementation_kind="future_cad_kernel",
        plasticity_reference={"sources": plasticity_sources},
        selection_contract=selection,
        parameter_schema=parameters,
        option_panel_schema=parameters,
        preview_contract=("preview_geometry", "selection_highlight", "failure_preflight"),
        topology_effects=topology,
        tolerance_policy=tolerance,
        failure_modes=COMMON_MESH_FAILURES
        + (
            _failure("kernel.unsupported", "No B-rep/NURBS implementation is available yet.", "Use an implemented mesh operation or keep this as a planned command."),
            _failure("tolerance.failed", "The requested operation cannot satisfy the tolerance policy.", "Adjust tolerance or simplify the input topology."),
        ),
        undo_contract=UndoContract(transaction_name=label, delta_kind="cad_topology_delta"),
        fixture_tests=("fixture_cube_solid", "fixture_sheet_patch", "fixture_curve_profile"),
        manifest_effect=("provenance.operation", "cad.topology_delta", "validation.tolerance_report"),
        mcp_surface={"resource": "ghostforge://cad/commands/{command_id}", "mutation": "planned"},
        qt_surface={"action": f"cad.{command_id}", "panel": "CadCommandPanel"},
        acceptance_gates=(
            "cad_kernel_handler_exists",
            "fixture_behavior_observed",
            "failure_modes_tested",
            "undo_delta_round_trip",
            "mcp_and_qt_share_descriptor",
        ),
    )


def _relationship_command(
    *,
    command_id: str,
    label: str,
    status: str,
    target: str,
    plasticity_sources: tuple[str, ...],
    parameters: tuple[ParameterSpec, ...],
) -> CadCommandDescriptor:
    updates = {}
    if status == "alias":
        updates["alias_of"] = target
    elif status == "option":
        updates["option_of"] = target
    else:
        updates["contextual_mode_of"] = target
    return CadCommandDescriptor(
        command_id=command_id,
        label=label,
        family="surface" if "xnurbs" in command_id else "solid",
        status=status,  # type: ignore[arg-type]
        implementation_kind="relationship",
        plasticity_reference={"sources": plasticity_sources, "mapping_review": "likely_option_or_alias"},
        selection_contract=SelectionContract(min_count=1, subobject_kinds=("face", "edge", "curve")),
        parameter_schema=parameters,
        option_panel_schema=parameters,
        topology_effects=TopologyEffects(modifies=("option_panel",), preserves=("source_geometry",)),
        tolerance_policy=TolerancePolicy(description="Inherited from the owning command."),
        failure_modes=(
            _failure("mapping.unverified", "Plasticity evidence suggests this is not a standalone command.", "Review owning command behavior before implementation."),
        ),
        undo_contract=UndoContract(transaction_name=label, delta_kind="option_state_delta"),
        fixture_tests=("fixture_command_option_mapping",),
        manifest_effect=("provenance.option_mapping",),
        mcp_surface={"resource": "ghostforge://cad/commands/{command_id}", "mutation": "none"},
        qt_surface={"panel": "CadCommandPanel", "relationship_target": target},
        acceptance_gates=("owning_command_verified", "option_panel_schema_verified"),
        **updates,
    )


DEFAULT_CAD_COMMANDS: tuple[CadCommandDescriptor, ...] = (
    _mesh_command(
        command_id="create_box",
        label="Create Box",
        family="primitive",
        source_operation="create_box",
        parameters=(
            _param("extents", "vec3", default=[1.0, 1.0, 1.0], unit="scene_units", description="Positive XYZ box dimensions."),
            _param("center", "vec3", default=[0.0, 0.0, 0.0], unit="scene_units", description="XYZ location for the generated box center."),
        ),
        selection=SelectionContract(min_count=0, requires_active_object=False, notes=("Source primitive; no input selection required.",)),
        topology=TopologyEffects(creates=("mesh", "vertices", "edges", "faces"), preserves=()),
        tolerance=TolerancePolicy(linear=0.0, description="Deterministic mesh primitive construction; no B-rep tolerance is applied."),
        failures=(
            _failure("primitive.extents_nonpositive", "All box extents must be positive.", "Use extents greater than zero on every axis."),
        ),
        base_failures=COMMON_SOURCE_FAILURES,
    ),
    _mesh_command(
        command_id="transform",
        label="Transform",
        family="transform",
        source_operation="transform",
        parameters=(
            _param("translate", "vec3", default=[0.0, 0.0, 0.0], unit="scene_units"),
            _param("rotate_euler_deg", "vec3", default=[0.0, 0.0, 0.0], unit="degrees"),
            _param("scale", "scalar_or_vec3", default=1.0),
        ),
        topology=TopologyEffects(modifies=("vertices", "object_transform"), preserves=("face_ids", "material_slots")),
    ),
    _mesh_command(
        command_id="delete_selection",
        label="Delete Selection",
        family="selection",
        source_operation="delete",
        selection=SelectionContract(min_count=1, subobject_kinds=("vertex", "edge", "face", "element")),
        topology=TopologyEffects(deletes=("selected_faces", "unreferenced_vertices"), modifies=("connectivity",)),
        failures=(
            _failure("delete.all_geometry", "Delete would remove every face.", "Select a smaller subset or delete the object instead."),
        ),
    ),
    _mesh_command(
        command_id="weld",
        label="Weld",
        family="topology",
        source_operation="weld",
        parameters=(_param("tolerance", "float", default=1e-6, minimum=0.0, unit="scene_units"),),
        selection=SelectionContract(min_count=1, subobject_kinds=("vertex", "edge")),
        topology=TopologyEffects(deletes=("duplicate_vertices", "collapsed_faces"), modifies=("vertices", "faces", "normals")),
        tolerance=TolerancePolicy(linear=1e-6, description="Vertices closer than the weld tolerance may collapse."),
        failures=(
            _failure("weld.collapsed_all_faces", "Weld collapsed every selected face.", "Lower tolerance or select fewer vertices."),
        ),
    ),
    _mesh_command(
        command_id="recompute_normals",
        label="Recompute Normals",
        family="cleanup",
        source_operation="recompute_normals",
        topology=TopologyEffects(modifies=("normals",), preserves=("vertices", "faces", "materials")),
    ),
    _mesh_command(
        command_id="normalize_scale",
        label="Normalize Scale",
        family="transform",
        source_operation="normalize_scale",
        parameters=(_param("target_extent", "float", default=1.0, minimum=1e-6, unit="scene_units"),),
        topology=TopologyEffects(modifies=("vertices", "bounds"), preserves=("faces", "materials")),
        failures=(
            _failure("scale.zero_volume", "Cannot normalize a zero-volume mesh.", "Repair or replace the input geometry."),
        ),
    ),
    _planned_cad_command(
        command_id="extrude",
        label="Extrude",
        family="solid",
        plasticity_sources=("command_palette_filtered", "static_operation_asset"),
        selection=SelectionContract(min_count=1, subobject_kinds=("face", "curve", "profile"), ordered=False),
        parameters=(
            _param("distance", "float", required=True, unit="scene_units"),
            _param("direction", "enum", default="normal", values=("normal", "axis", "vector")),
            _param("operation", "enum", default="new_body", values=("new_body", "join", "cut", "intersect")),
            _param("draft_angle_deg", "float", default=0.0, unit="degrees"),
        ),
        topology=TopologyEffects(creates=("solid", "faces", "edges"), modifies=("selected_profiles",)),
        tolerance=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="Profile extrusion and side-face stitching tolerance."),
    ),
    _planned_cad_command(
        command_id="fillet",
        label="Fillet",
        family="solid",
        plasticity_sources=("command_palette_filtered", "static_operation_asset"),
        selection=SelectionContract(min_count=1, subobject_kinds=("edge",), ordered=False),
        parameters=(
            _param("radius", "float", required=True, minimum=0.0, unit="scene_units"),
            _param("continuity", "enum", default="g1", values=("g1", "g2")),
            _param("setback", "bool", default=False),
        ),
        topology=TopologyEffects(creates=("blend_faces",), deletes=("sharp_edges",), modifies=("adjacent_faces",)),
        tolerance=TolerancePolicy(linear=1e-5, angular_degrees=0.1, description="Edge blend construction tolerance."),
    ),
    _planned_cad_command(
        command_id="project",
        label="Project",
        family="curve",
        plasticity_sources=("command_palette_saved_probe_confirmed", "static_operation_asset"),
        selection=SelectionContract(min_count=2, subobject_kinds=("curve", "face", "surface"), ordered=True),
        parameters=(
            _param("projection_mode", "enum", default="normal", values=("normal", "camera", "direction")),
            _param("imprint_result", "bool", default=False),
            _param("trim_to_target", "bool", default=False),
        ),
        topology=TopologyEffects(creates=("projected_curves",), modifies=("target_surface",)),
        tolerance=TolerancePolicy(linear=1e-5, description="Curve-on-surface projection tolerance."),
    ),
    _planned_cad_command(
        command_id="export_mesh",
        label="Export Mesh",
        family="export",
        plasticity_sources=("static_operation_asset",),
        selection=SelectionContract(object_kinds=("mesh", "scene"), min_count=1, requires_active_object=False),
        parameters=(
            _param("format", "enum", default="glb", values=("glb", "obj", "stl", "fbx", "ply")),
            _param("target_path", "path", required=True),
            _param("include_materials", "bool", default=True),
            _param("axis_preset", "enum", default="ghostforge", values=("ghostforge", "unity", "unreal", "blender")),
        ),
        topology=TopologyEffects(preserves=("scene_geometry",)),
        tolerance=TolerancePolicy(linear=1e-5, angular_degrees=1.0, description="Tessellation/export tolerance."),
    ).model_copy(
        update={
            "status": "controlled_probe_needed",
            "implementation_kind": "export_pipeline",
            "format_options": (
                FormatOption(name="angle_tolerance", type="float", default=1.0, applies_to=("mesh_export",), description="Plasticity static asset suggests this option."),
                FormatOption(name="max_width", type="float", default=None, applies_to=("mesh_export",), description="Plasticity static asset suggests this option."),
                FormatOption(name="inflect", type="bool", default=False, applies_to=("mesh_export",), description="Plasticity static asset suggests this option."),
            ),
        }
    ),
    _relationship_command(
        command_id="face_change_grow",
        label="Face Change: Grow",
        status="option",
        target="match_face",
        plasticity_sources=("face-change-grow.png", "palette_negative_review:face_change"),
        parameters=(_param("grow", "bool", default=True, description="Static Plasticity asset appears to describe a face-change option."),),
    ),
    _relationship_command(
        command_id="xnurbs_boundary",
        label="XNURBS Boundary",
        status="contextual_mode",
        target="surface_patch",
        plasticity_sources=("xnurbs-boundary.png", "palette_negative_review:xnurbs"),
        parameters=(
            _param("boundary_mode", "enum", default="boundary", values=("boundary", "quad_sided")),
            _param("continuity", "enum", default="g1", values=("g0", "g1", "g2")),
        ),
    ),
)


@dataclass
class CadCommandRegistry:
    _commands: dict[str, CadCommandDescriptor]

    @classmethod
    def from_commands(cls, commands: Iterable[CadCommandDescriptor]) -> "CadCommandRegistry":
        return cls({command.command_id: command for command in commands})

    def get(self, command_id: str) -> CadCommandDescriptor:
        return self._commands[command_id]

    def has(self, command_id: str) -> bool:
        return command_id in self._commands

    def all(self) -> list[CadCommandDescriptor]:
        return sorted(self._commands.values(), key=lambda command: (command.family, command.command_id))

    def by_status(self, status: str) -> list[CadCommandDescriptor]:
        return [command for command in self.all() if command.status == status]

    def relationship_commands(self) -> list[CadCommandDescriptor]:
        return [
            command
            for command in self.all()
            if command.alias_of or command.option_of or command.contextual_mode_of
        ]


def build_default_cad_registry() -> CadCommandRegistry:
    return CadCommandRegistry.from_commands(DEFAULT_CAD_COMMANDS)


__all__ = [
    "DEFAULT_CAD_COMMANDS",
    "CadCommandRegistry",
    "build_default_cad_registry",
]
