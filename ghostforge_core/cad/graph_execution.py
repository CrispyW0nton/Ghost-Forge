"""Controlled native execution for Ghost Forge CAD operation graphs.

This is the first deliberately small execution spine under the CAD graph IR.
It only runs descriptor-backed commands that already have implemented mesh
handlers. Planned B-rep/NURBS commands remain validation failures until a real
kernel exists, but successful mesh-backed graphs now produce concrete mesh
artifacts, topology lineage records, quality diagnostics, and manifests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ghostforge_core.authoring import (
    OperationContext,
    OperationError,
    OperationRegistry,
    default_operation_registry,
)
from ghostforge_core.manifest import ManifestBuilder, ProvenanceStep, Units

from .execution import (
    CadTopologyDelta,
    CadTopologyLineage,
    CadTopologySnapshot,
    build_committed_result,
    preflight_cad_command,
    resolve_cad_command_context,
)
from .operation_graph import (
    CadGraphDiagnostic,
    CadGraphEntity,
    CadOperationGraph,
    CadOperationGraphValidationReport,
    CadOperationNode,
    CadTopologyLineageRecord,
    validate_cad_operation_graph,
)
from .registry import CadCommandRegistry, build_default_cad_registry


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


CadGraphExecutionStatus = Literal["succeeded", "failed", "blocked"]


class CadMeshQualityReport(FrozenModel):
    vertex_count: int = Field(ge=0)
    face_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    face_arity_distribution: dict[str, int] = Field(default_factory=dict)
    nonmanifold_edge_count: int = Field(default=0, ge=0)
    boundary_edge_count: int = Field(default=0, ge=0)
    degenerate_face_count: int = Field(default=0, ge=0)
    flipped_normal_count: int = Field(default=0, ge=0)
    tolerance_deviation: float = Field(default=0.0, ge=0.0)
    source_lineage_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    topology_lineage_record_count: int = Field(default=0, ge=0)
    checks: tuple[str, ...] = ()


class CadGraphExecutionStep(FrozenModel):
    order: int
    node_id: str
    command_id: str
    status: Literal["committed", "failed", "blocked"] = "committed"
    operation_kind: str = ""
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    topology_delta: CadTopologyDelta = Field(default_factory=CadTopologyDelta)
    lineage_record_id: str | None = None
    manifest_event: dict[str, Any] | None = None
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()


class CadOperationGraphExecutionResult(FrozenModel):
    graph_id: str
    status: CadGraphExecutionStatus
    validation: CadOperationGraphValidationReport
    graph: CadOperationGraph
    steps: tuple[CadGraphExecutionStep, ...] = ()
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()
    mesh_quality_report: CadMeshQualityReport | None = None
    output_mesh_path: Path | None = None
    manifest_path: Path | None = None
    artifact_manifest: dict[str, Any] = Field(default_factory=dict)


def execute_cad_operation_graph(
    graph: CadOperationGraph,
    *,
    output_dir: Path | str,
    input_mesh_path: Path | str | None = None,
    output_format: str = "glb",
    asset_id: str | None = None,
    registry: CadCommandRegistry | None = None,
    operations: OperationRegistry | None = None,
) -> CadOperationGraphExecutionResult:
    """Execute a validated CAD graph through implemented native mesh handlers.

    This function intentionally does not claim full CAD-kernel support. It uses
    the same descriptor validation as MCP/Qt, then runs only descriptors whose
    status is already `implemented_mesh` and whose `source_operation` is present
    in the shared authoring operation registry.
    """

    registry = registry or build_default_cad_registry()
    operations = operations or default_operation_registry()
    validation = validate_cad_operation_graph(graph, registry)
    if not validation.ok:
        return CadOperationGraphExecutionResult(
            graph_id=graph.graph_id,
            status="blocked",
            validation=validation,
            graph=graph,
            diagnostics=validation.diagnostics,
        )

    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    mesh = _load_mesh(input_mesh_path) if input_mesh_path is not None else None
    current_graph = graph
    node_by_id = {node.node_id: node for node in graph.nodes}
    steps: list[CadGraphExecutionStep] = []
    diagnostics: list[CadGraphDiagnostic] = []

    for replay_step in validation.replay_plan:
        node = node_by_id[replay_step.node_id]
        descriptor = registry.get(node.command_id)
        operation_kind = descriptor.source_operation or descriptor.command_id
        if descriptor.status != "implemented_mesh":
            diagnostic = CadGraphDiagnostic(
                code="executor.descriptor_not_implemented",
                message=(
                    f"Node {node.node_id!r} uses descriptor {descriptor.command_id!r}, "
                    f"which is {descriptor.status!r}, not implemented_mesh."
                ),
                node_id=node.node_id,
                repair_suggestions=("Keep this node in planning mode until a native kernel handler exists.",),
            )
            diagnostics.append(diagnostic)
            steps.append(
                CadGraphExecutionStep(
                    order=replay_step.order,
                    node_id=node.node_id,
                    command_id=node.command_id,
                    status="blocked",
                    operation_kind=operation_kind,
                    diagnostics=(diagnostic,),
                )
            )
            return CadOperationGraphExecutionResult(
                graph_id=graph.graph_id,
                status="blocked",
                validation=validation,
                graph=current_graph,
                steps=tuple(steps),
                diagnostics=tuple(diagnostics),
            )
        if not operations.has(operation_kind):
            diagnostic = CadGraphDiagnostic(
                code="executor.handler_missing",
                message=f"No shared authoring operation handler is registered for {operation_kind!r}.",
                node_id=node.node_id,
                repair_suggestions=("Register a native operation handler or remap the CAD descriptor source operation.",),
            )
            diagnostics.append(diagnostic)
            steps.append(
                CadGraphExecutionStep(
                    order=replay_step.order,
                    node_id=node.node_id,
                    command_id=node.command_id,
                    status="blocked",
                    operation_kind=operation_kind,
                    diagnostics=(diagnostic,),
                )
            )
            return CadOperationGraphExecutionResult(
                graph_id=graph.graph_id,
                status="blocked",
                validation=validation,
                graph=current_graph,
                steps=tuple(steps),
                diagnostics=tuple(diagnostics),
            )
        if mesh is None and not _can_start_without_input(node, descriptor):
            diagnostic = CadGraphDiagnostic(
                code="executor.input_mesh_required",
                message=(
                    f"Node {node.node_id!r} uses {descriptor.command_id!r}, which requires "
                    "an input mesh or an earlier source node."
                ),
                node_id=node.node_id,
                repair_suggestions=("Add a source primitive/generation node first or pass input_mesh_path.",),
            )
            diagnostics.append(diagnostic)
            steps.append(
                CadGraphExecutionStep(
                    order=replay_step.order,
                    node_id=node.node_id,
                    command_id=node.command_id,
                    status="blocked",
                    operation_kind=operation_kind,
                    diagnostics=(diagnostic,),
                )
            )
            return CadOperationGraphExecutionResult(
                graph_id=graph.graph_id,
                status="blocked",
                validation=validation,
                graph=current_graph,
                steps=tuple(steps),
                diagnostics=tuple(diagnostics),
            )

        before = _snapshot(mesh, object_id=_active_object_id(node))
        try:
            new_mesh = operations.get(operation_kind)(
                OperationContext(
                    mesh=mesh,
                    params=dict(node.parameters),
                    node_id=node.node_id,
                    graph_id=graph.graph_id,
                    output_dir=output_root,
                    side_effects=[],
                )
            )
        except OperationError as exc:
            diagnostic = CadGraphDiagnostic(
                code="executor.operation_failed",
                message=str(exc),
                node_id=node.node_id,
                repair_suggestions=("Adjust node parameters or selection and validate the graph again.",),
            )
            diagnostics.append(diagnostic)
            steps.append(
                CadGraphExecutionStep(
                    order=replay_step.order,
                    node_id=node.node_id,
                    command_id=node.command_id,
                    status="failed",
                    operation_kind=operation_kind,
                    diagnostics=(diagnostic,),
                )
            )
            return CadOperationGraphExecutionResult(
                graph_id=graph.graph_id,
                status="failed",
                validation=validation,
                graph=current_graph,
                steps=tuple(steps),
                diagnostics=tuple(diagnostics),
            )
        except Exception as exc:  # pragma: no cover - defensive handler boundary
            diagnostic = CadGraphDiagnostic(
                code="executor.operation_unexpected_error",
                message=f"Unexpected error while executing {operation_kind!r}: {exc}",
                node_id=node.node_id,
                repair_suggestions=("Inspect the native operation handler and add a focused fixture test.",),
            )
            diagnostics.append(diagnostic)
            steps.append(
                CadGraphExecutionStep(
                    order=replay_step.order,
                    node_id=node.node_id,
                    command_id=node.command_id,
                    status="failed",
                    operation_kind=operation_kind,
                    diagnostics=(diagnostic,),
                )
            )
            return CadOperationGraphExecutionResult(
                graph_id=graph.graph_id,
                status="failed",
                validation=validation,
                graph=current_graph,
                steps=tuple(steps),
                diagnostics=tuple(diagnostics),
            )

        mesh = new_mesh
        after = _snapshot(mesh, object_id=_active_object_id(node))
        delta = _topology_delta(before, after, node, descriptor.topology_effects.model_dump(mode="json"))
        context = resolve_cad_command_context(
            descriptor,
            selection=node.selection,
            parameters=node.parameters,
        )
        preflight = preflight_cad_command(descriptor, context)
        committed = build_committed_result(descriptor, context, preflight, delta)
        lineage_record_id = f"lineage:{node.node_id}"
        lineage = _lineage_record(node, context.tolerance, lineage_record_id)
        current_graph = _with_lineage(current_graph, node, lineage_record_id, lineage)
        steps.append(
            CadGraphExecutionStep(
                order=replay_step.order,
                node_id=node.node_id,
                command_id=node.command_id,
                status="committed",
                operation_kind=operation_kind,
                parameter_snapshot=dict(node.parameters),
                topology_delta=delta,
                lineage_record_id=lineage_record_id,
                manifest_event=(
                    committed.manifest_event.model_dump(mode="json")
                    if committed.manifest_event is not None
                    else None
                ),
            )
        )

    if mesh is None:
        diagnostic = CadGraphDiagnostic(
            code="executor.no_output_mesh",
            message="CAD operation graph did not produce a mesh artifact.",
            repair_suggestions=("Add an enabled source node or provide input_mesh_path before execution.",),
        )
        return CadOperationGraphExecutionResult(
            graph_id=graph.graph_id,
            status="blocked",
            validation=validation,
            graph=current_graph,
            steps=tuple(steps),
            diagnostics=tuple(diagnostics + [diagnostic]),
        )

    safe_graph_id = _safe_name(graph.graph_id)
    output_format = output_format.lower().lstrip(".") or "glb"
    output_mesh = output_root / f"{safe_graph_id}.{output_format}"
    mesh.export(str(output_mesh))
    quality = _quality_report(mesh, topology_lineage_record_count=len(current_graph.topology_table))
    manifest, manifest_path = _write_execution_manifest(
        graph=current_graph,
        result_steps=steps,
        quality=quality,
        output_mesh=output_mesh,
        output_root=output_root,
        asset_id=asset_id or safe_graph_id,
    )
    return CadOperationGraphExecutionResult(
        graph_id=graph.graph_id,
        status="succeeded",
        validation=validation,
        graph=current_graph,
        steps=tuple(steps),
        diagnostics=tuple(diagnostics),
        mesh_quality_report=quality,
        output_mesh_path=output_mesh,
        manifest_path=manifest_path,
        artifact_manifest=manifest.model_dump(mode="json"),
    )


def _load_mesh(path: Path | str):
    import trimesh

    loaded = trimesh.load(str(path), process=False, force="mesh")
    if isinstance(loaded, trimesh.Scene):
        meshes = [mesh for mesh in loaded.geometry.values() if isinstance(mesh, trimesh.Trimesh)]
        if not meshes:
            raise ValueError(f"No mesh geometry found in {path}")
        loaded = trimesh.util.concatenate(meshes)
    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Expected mesh geometry in {path}, got {type(loaded).__name__}")
    return loaded


def _can_start_without_input(node: CadOperationNode, descriptor: Any) -> bool:
    creates = set(descriptor.topology_effects.creates)
    return (
        not node.inputs
        and descriptor.selection_contract.min_count == 0
        and not descriptor.selection_contract.requires_active_object
        and bool({"mesh", "body", "solid"} & creates)
    )


def _active_object_id(node: CadOperationNode) -> str:
    if node.selection.active_object_id:
        return node.selection.active_object_id
    if node.selection.items:
        return node.selection.items[0].object_id
    if node.inputs and node.inputs[0].entity_id:
        return node.inputs[0].entity_id
    if node.outputs and node.outputs[0].entity_id:
        return node.outputs[0].entity_id
    return "mesh"


def _snapshot(mesh: Any | None, *, object_id: str) -> CadTopologySnapshot:
    if mesh is None:
        return CadTopologySnapshot()
    bounds = None
    if getattr(mesh, "bounds", None) is not None:
        b = mesh.bounds
        bounds = (
            float(b[0][0]),
            float(b[0][1]),
            float(b[0][2]),
            float(b[1][0]),
            float(b[1][1]),
            float(b[1][2]),
        )
    return CadTopologySnapshot(
        object_ids=(object_id,),
        vertex_count=int(len(mesh.vertices)),
        edge_count=int(len(mesh.edges_unique)) if hasattr(mesh, "edges_unique") else int(len(mesh.edges)),
        face_count=int(len(mesh.faces)),
        component_count=int(len(mesh.split(only_watertight=False))) if len(mesh.faces) else 0,
        bounds=bounds,
    )


def _topology_delta(
    before: CadTopologySnapshot,
    after: CadTopologySnapshot,
    node: CadOperationNode,
    topology_effects: dict[str, Any],
) -> CadTopologyDelta:
    input_ids = tuple(ref.entity_id for ref in node.inputs if ref.entity_id) or tuple(before.object_ids)
    output_ids = tuple(ref.entity_id for ref in node.outputs if ref.entity_id) or tuple(after.object_ids)
    if input_ids:
        lineage = tuple(
            CadTopologyLineage(
                source_id=source_id,
                result_ids=output_ids,
                relation="modified",
            )
            for source_id in input_ids
        )
    else:
        lineage = (
            CadTopologyLineage(
                source_id=f"source:{node.node_id}",
                result_ids=output_ids,
                relation="created",
            ),
        )
    return CadTopologyDelta(
        before=before,
        after=after,
        creates=tuple(topology_effects.get("creates") or ()),
        deletes=tuple(topology_effects.get("deletes") or ()),
        modifies=tuple(topology_effects.get("modifies") or ()),
        preserves=tuple(topology_effects.get("preserves") or ()),
        lineage=lineage,
        result_summary={
            "vertex_count": after.vertex_count,
            "edge_count": after.edge_count,
            "face_count": after.face_count,
            "component_count": after.component_count,
            "vertex_delta": after.vertex_count - before.vertex_count,
            "edge_delta": after.edge_count - before.edge_count,
            "face_delta": after.face_count - before.face_count,
            "bounds_changed": before.bounds != after.bounds,
        },
    )


def _lineage_record(
    node: CadOperationNode,
    tolerance: dict[str, Any],
    lineage_record_id: str,
) -> CadTopologyLineageRecord:
    input_entities = tuple(ref.entity_id for ref in node.inputs if ref.entity_id)
    selected_topology = tuple(item.topology_id for item in node.selection.items if item.topology_id)
    output_refs = tuple(
        ref.topology_id or ref.entity_id or ref.ref_id
        for ref in node.outputs
    ) or (lineage_record_id,)
    return CadTopologyLineageRecord(
        operation_node_id=node.node_id,
        command_id=node.command_id,
        input_entity_refs=input_entities or tuple(item.object_id for item in node.selection.items),
        input_topology_refs=selected_topology,
        created_refs=(),
        deleted_refs=(),
        renamed_refs={ref: ref for ref in selected_topology},
        continuity_report={"prototype_mesh_handler": True},
        tolerance_report=tolerance,
        diagnostics=node.diagnostics,
        lineage_confidence=1.0,
    ).model_copy(update={"created_refs": output_refs if not selected_topology else ()})


def _with_lineage(
    graph: CadOperationGraph,
    node: CadOperationNode,
    lineage_record_id: str,
    lineage: CadTopologyLineageRecord,
) -> CadOperationGraph:
    topology_table = dict(graph.topology_table)
    topology_table[lineage_record_id] = lineage
    entity_table = dict(graph.entity_table)
    for ref in node.outputs:
        if ref.entity_id and ref.entity_id not in entity_table:
            entity_table[ref.entity_id] = CadGraphEntity(
                entity_id=ref.entity_id,
                kind="mesh",
                producing_node_id=node.node_id,
                source_refs=node.inputs,
            )
    return graph.model_copy(update={"topology_table": topology_table, "entity_table": entity_table})


def _quality_report(mesh: Any, *, topology_lineage_record_count: int) -> CadMeshQualityReport:
    import numpy as np

    face_arity_distribution: dict[str, int] = {}
    for face in mesh.faces:
        key = str(len(face))
        face_arity_distribution[key] = face_arity_distribution.get(key, 0) + 1
    boundary_edges = 0
    nonmanifold_edges = 0
    if hasattr(mesh, "edges_unique_inverse"):
        counts = np.bincount(mesh.edges_unique_inverse)
        boundary_edges = int(np.sum(counts == 1))
        nonmanifold_edges = int(np.sum(counts > 2))
    areas = getattr(mesh, "area_faces", [])
    degenerate = int(np.sum(np.asarray(areas) <= 1e-12)) if len(areas) else 0
    return CadMeshQualityReport(
        vertex_count=int(len(mesh.vertices)),
        face_count=int(len(mesh.faces)),
        edge_count=int(len(mesh.edges_unique)) if hasattr(mesh, "edges_unique") else int(len(mesh.edges)),
        face_arity_distribution=face_arity_distribution,
        nonmanifold_edge_count=nonmanifold_edges,
        boundary_edge_count=boundary_edges,
        degenerate_face_count=degenerate,
        flipped_normal_count=0,
        tolerance_deviation=0.0,
        source_lineage_coverage=1.0 if topology_lineage_record_count else 0.0,
        topology_lineage_record_count=topology_lineage_record_count,
        checks=(
            "face_arity_distribution_recorded",
            "nonmanifold_edges_counted",
            "boundary_edges_counted",
            "degenerate_faces_counted",
            "source_lineage_coverage_recorded",
        ),
    )


def _write_execution_manifest(
    *,
    graph: CadOperationGraph,
    result_steps: list[CadGraphExecutionStep],
    quality: CadMeshQualityReport,
    output_mesh: Path,
    output_root: Path,
    asset_id: str,
):
    builder = ManifestBuilder.for_dir(output_root, asset_id=asset_id)
    builder.with_name(graph.graph_id)
    builder.with_description("Ghost Forge native CAD operation graph execution output.")
    builder.with_geometry_from_mesh(output_mesh, units=Units(graph.document_units) if graph.document_units in Units.__members__ else Units.meters)
    builder.with_validation_from_mesh(output_mesh)
    builder.add_artifact_from_path(output_mesh, role="mesh.primary")
    builder.add_provenance(
        ProvenanceStep(
            kind="cad_operation_graph",
            parameters={
                "graph_id": graph.graph_id,
                "node_ids": [step.node_id for step in result_steps],
                "command_ids": [step.command_id for step in result_steps],
            },
            notes="Executed through Ghost Forge native mesh-backed CAD graph prototype.",
        )
    )
    builder.with_custom("cad_operation_graph", graph.model_dump(mode="json"))
    builder.with_custom(
        "cad_execution",
        {
            "status": "succeeded",
            "step_count": len(result_steps),
            "steps": [step.model_dump(mode="json") for step in result_steps],
        },
    )
    builder.with_custom("cad_mesh_quality_report", quality.model_dump(mode="json"))
    return builder.write()


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "cad_graph"


__all__ = [
    "CadGraphExecutionStatus",
    "CadGraphExecutionStep",
    "CadMeshQualityReport",
    "CadOperationGraphExecutionResult",
    "execute_cad_operation_graph",
]
