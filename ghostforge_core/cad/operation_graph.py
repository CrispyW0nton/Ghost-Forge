"""Native CAD operation graph IR for Ghost Forge.

This module is deliberately independent of Plasticity.  It gives manual tools,
AI planners, and MCP automation a shared typed construction graph that can be
validated against Ghost Forge CAD descriptors before any geometry kernel or
mesh export step mutates document state.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .execution import (
    CadCommandFailure,
    CadSelectionSet,
    preflight_cad_command,
    resolve_cad_command_context,
)
from .registry import CadCommandRegistry
from .schema import CadCommandDescriptor


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


CadGraphDiagnosticSeverity = Literal["info", "warning", "error"]
CadGraphEdgeKind = Literal["construction", "topology", "selection", "material", "export", "dependency"]
CadGraphEntityKind = Literal["body", "shell", "face", "edge", "vertex", "curve", "surface", "mesh", "artifact"]


class CadGraphDiagnostic(FrozenModel):
    status: Literal["ok", "warning", "failed"] = "failed"
    severity: CadGraphDiagnosticSeverity = "error"
    code: str = Field(min_length=1)
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    failed_preconditions: tuple[str, ...] = ()
    tolerance_report: dict[str, Any] = Field(default_factory=dict)
    topology_report: dict[str, Any] = Field(default_factory=dict)
    repair_suggestions: tuple[str, ...] = ()

    @classmethod
    def from_command_failure(
        cls,
        failure: CadCommandFailure,
        *,
        node_id: str,
    ) -> "CadGraphDiagnostic":
        return cls(
            status="warning" if failure.severity == "warning" else "failed",
            severity=failure.severity,
            code=failure.code,
            message=failure.message,
            node_id=node_id,
            failed_preconditions=(failure.source,),
            repair_suggestions=(failure.recovery,) if failure.recovery else (),
        )


class CadGraphReference(FrozenModel):
    ref_id: str = Field(min_length=1)
    entity_id: str | None = None
    topology_id: str | None = None
    role: str = "input"
    lineage_path: tuple[str, ...] = ()


class CadGraphEntity(FrozenModel):
    entity_id: str = Field(min_length=1)
    kind: CadGraphEntityKind = "body"
    label: str = ""
    producing_node_id: str | None = None
    source_refs: tuple[CadGraphReference, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class CadTopologyLineageRecord(FrozenModel):
    operation_node_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    input_entity_refs: tuple[str, ...] = ()
    input_topology_refs: tuple[str, ...] = ()
    created_refs: tuple[str, ...] = ()
    deleted_refs: tuple[str, ...] = ()
    split_refs: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    merged_refs: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    renamed_refs: dict[str, str] = Field(default_factory=dict)
    continuity_report: dict[str, Any] = Field(default_factory=dict)
    tolerance_report: dict[str, Any] = Field(default_factory=dict)
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()
    lineage_confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CadMeshEmissionProfile(FrozenModel):
    profile_id: str = "default_mesh"
    format: str = "obj"
    scope: str = "selected_or_scene"
    units: str = "meters"
    tolerances: dict[str, Any] = Field(default_factory=dict)
    normal_policy: str = "preserve_or_recompute"
    uv_policy: str = "preserve_when_available"
    topology_quality_checks: tuple[str, ...] = (
        "manifold_or_declared_nonmanifold",
        "normal_orientation_checked",
        "degenerate_faces_reported",
        "source_lineage_coverage",
    )
    artifact_manifest: str | None = None


class CadOperationNode(FrozenModel):
    node_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    label: str = ""
    operation_family: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs: tuple[CadGraphReference, ...] = ()
    outputs: tuple[CadGraphReference, ...] = ()
    selection: CadSelectionSet = Field(default_factory=CadSelectionSet)
    selection_contract: dict[str, Any] = Field(default_factory=dict)
    tolerances: dict[str, Any] = Field(default_factory=dict)
    topology_effects: dict[str, Any] = Field(default_factory=dict)
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()
    undo_token: str = ""
    undo_policy: dict[str, Any] = Field(default_factory=dict)
    descriptor_status: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class CadOperationEdge(FrozenModel):
    edge_id: str = Field(min_length=1)
    from_node_id: str = Field(min_length=1)
    to_node_id: str = Field(min_length=1)
    kind: CadGraphEdgeKind = "dependency"
    source_ref: str | None = None
    target_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CadOperationGraph(FrozenModel):
    graph_id: str = Field(min_length=1)
    document_units: str = "meters"
    nodes: tuple[CadOperationNode, ...] = ()
    edges: tuple[CadOperationEdge, ...] = ()
    entity_table: dict[str, CadGraphEntity] = Field(default_factory=dict)
    topology_table: dict[str, CadTopologyLineageRecord] = Field(default_factory=dict)
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()
    export_profiles: tuple[CadMeshEmissionProfile, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class CadGraphReplayStep(FrozenModel):
    order: int
    node_id: str
    command_id: str
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()


class CadOperationGraphValidationReport(FrozenModel):
    graph_id: str
    ok: bool
    status: Literal["valid", "invalid"] = "invalid"
    diagnostics: tuple[CadGraphDiagnostic, ...] = ()
    replay_plan: tuple[CadGraphReplayStep, ...] = ()


def cad_operation_node_from_descriptor(
    descriptor: CadCommandDescriptor,
    *,
    node_id: str,
    parameters: dict[str, Any] | None = None,
    selection: CadSelectionSet | None = None,
    inputs: tuple[CadGraphReference, ...] = (),
    outputs: tuple[CadGraphReference, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> CadOperationNode:
    """Create a graph node whose editable fields mirror a CAD descriptor."""

    return CadOperationNode(
        node_id=node_id,
        command_id=descriptor.command_id,
        label=descriptor.label,
        operation_family=descriptor.family,
        parameters=dict(parameters or {}),
        inputs=inputs,
        outputs=outputs,
        selection=selection or CadSelectionSet(),
        selection_contract=descriptor.selection_contract.model_dump(mode="json"),
        tolerances=descriptor.tolerance_policy.model_dump(mode="json"),
        topology_effects=descriptor.topology_effects.model_dump(mode="json"),
        undo_token=f"{node_id}:{descriptor.undo_contract.transaction_name}",
        undo_policy=descriptor.undo_contract.model_dump(mode="json"),
        descriptor_status=descriptor.status,
        metadata=dict(metadata or {}),
    )


def validate_cad_operation_graph(
    graph: CadOperationGraph,
    registry: CadCommandRegistry,
) -> CadOperationGraphValidationReport:
    diagnostics: list[CadGraphDiagnostic] = list(graph.diagnostics)
    diagnostics.extend(_graph_shape_diagnostics(graph))
    replay_node_ids, replay_diagnostics = _replay_node_ids(graph)
    diagnostics.extend(replay_diagnostics)
    node_by_id = {node.node_id: node for node in graph.nodes}

    for node in graph.nodes:
        if not registry.has(node.command_id):
            diagnostics.append(
                CadGraphDiagnostic(
                    code="descriptor.unknown_command",
                    message=f"Node {node.node_id!r} references unknown CAD command {node.command_id!r}.",
                    node_id=node.node_id,
                    repair_suggestions=("Choose a command id from the CAD descriptor registry.",),
                )
            )
            continue
        descriptor = registry.get(node.command_id)
        diagnostics.extend(_node_descriptor_diagnostics(node, descriptor))
        context = resolve_cad_command_context(
            descriptor,
            selection=node.selection,
            parameters=node.parameters,
        )
        preflight = preflight_cad_command(descriptor, context)
        diagnostics.extend(
            CadGraphDiagnostic.from_command_failure(failure, node_id=node.node_id)
            for failure in preflight.failures
        )
        diagnostics.extend(
            CadGraphDiagnostic.from_command_failure(warning, node_id=node.node_id)
            for warning in preflight.warnings
        )

    replay_steps = tuple(
        CadGraphReplayStep(
            order=index,
            node_id=node_id,
            command_id=node_by_id[node_id].command_id,
            parameter_snapshot=dict(node_by_id[node_id].parameters),
            input_refs=tuple(ref.ref_id for ref in node_by_id[node_id].inputs),
            output_refs=tuple(ref.ref_id for ref in node_by_id[node_id].outputs),
        )
        for index, node_id in enumerate(replay_node_ids)
        if node_id in node_by_id
    )
    ok = not any(diagnostic.severity == "error" for diagnostic in diagnostics)
    return CadOperationGraphValidationReport(
        graph_id=graph.graph_id,
        ok=ok,
        status="valid" if ok else "invalid",
        diagnostics=tuple(diagnostics),
        replay_plan=replay_steps if ok else (),
    )


def _graph_shape_diagnostics(graph: CadOperationGraph) -> list[CadGraphDiagnostic]:
    diagnostics: list[CadGraphDiagnostic] = []
    seen_nodes: set[str] = set()
    for node in graph.nodes:
        if node.node_id in seen_nodes:
            diagnostics.append(
                CadGraphDiagnostic(
                    code="graph.duplicate_node_id",
                    message=f"Duplicate operation node id {node.node_id!r}.",
                    node_id=node.node_id,
                    repair_suggestions=("Assign stable unique node ids before validation.",),
                )
            )
        seen_nodes.add(node.node_id)
        for ref in node.inputs:
            if ref.entity_id and ref.entity_id not in graph.entity_table:
                diagnostics.append(
                    CadGraphDiagnostic(
                        code="graph.entity_ref_missing",
                        message=f"Node {node.node_id!r} references missing entity {ref.entity_id!r}.",
                        node_id=node.node_id,
                        repair_suggestions=("Create the source entity or retarget the node input through lineage.",),
                    )
                )
            if ref.topology_id and ref.topology_id not in graph.topology_table:
                diagnostics.append(
                    CadGraphDiagnostic(
                        code="graph.topology_ref_missing",
                        message=f"Node {node.node_id!r} references missing topology lineage {ref.topology_id!r}.",
                        node_id=node.node_id,
                        topology_report={"topology_id": ref.topology_id},
                        repair_suggestions=("Attach a topology lineage record or retarget downstream references.",),
                    )
                )
    seen_edges: set[str] = set()
    node_ids = {node.node_id for node in graph.nodes}
    for edge in graph.edges:
        if edge.edge_id in seen_edges:
            diagnostics.append(
                CadGraphDiagnostic(
                    code="graph.duplicate_edge_id",
                    message=f"Duplicate operation edge id {edge.edge_id!r}.",
                    edge_id=edge.edge_id,
                    repair_suggestions=("Assign stable unique edge ids before validation.",),
                )
            )
        seen_edges.add(edge.edge_id)
        for endpoint_name, endpoint in (("from_node_id", edge.from_node_id), ("to_node_id", edge.to_node_id)):
            if endpoint not in node_ids:
                diagnostics.append(
                    CadGraphDiagnostic(
                        code=f"graph.edge.{endpoint_name}.missing",
                        message=f"Edge {edge.edge_id!r} references missing node {endpoint!r}.",
                        edge_id=edge.edge_id,
                        repair_suggestions=("Remove the edge or add the referenced operation node.",),
                    )
                )
    return diagnostics


def _node_descriptor_diagnostics(
    node: CadOperationNode,
    descriptor: CadCommandDescriptor,
) -> list[CadGraphDiagnostic]:
    diagnostics: list[CadGraphDiagnostic] = []
    allowed = {spec.name for spec in descriptor.parameter_schema}
    unknown = tuple(sorted(set(node.parameters) - allowed))
    if unknown:
        diagnostics.append(
            CadGraphDiagnostic(
                code="parameter.unknown",
                message=f"Node {node.node_id!r} has parameters not declared by {descriptor.command_id!r}: {list(unknown)!r}.",
                node_id=node.node_id,
                failed_preconditions=("parameter",),
                repair_suggestions=("Use only descriptor-supported parameter names.",),
            )
        )
    if node.descriptor_status and node.descriptor_status != descriptor.status:
        diagnostics.append(
            CadGraphDiagnostic(
                status="warning",
                severity="warning",
                code="descriptor.status_drift",
                message=(
                    f"Node {node.node_id!r} was authored against descriptor status "
                    f"{node.descriptor_status!r}, current status is {descriptor.status!r}."
                ),
                node_id=node.node_id,
                repair_suggestions=("Refresh node metadata from the current CAD descriptor registry.",),
            )
        )
    return diagnostics


def _replay_node_ids(graph: CadOperationGraph) -> tuple[tuple[str, ...], tuple[CadGraphDiagnostic, ...]]:
    node_ids = [node.node_id for node in graph.nodes]
    node_id_set = set(node_ids)
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    in_degree: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in graph.edges:
        if edge.from_node_id not in node_id_set or edge.to_node_id not in node_id_set:
            continue
        adjacency[edge.from_node_id].append(edge.to_node_id)
        in_degree[edge.to_node_id] += 1

    queue = deque(node_id for node_id in node_ids if in_degree[node_id] == 0)
    ordered: list[str] = []
    while queue:
        node_id = queue.popleft()
        ordered.append(node_id)
        for downstream in adjacency[node_id]:
            in_degree[downstream] -= 1
            if in_degree[downstream] == 0:
                queue.append(downstream)

    if len(ordered) == len(node_ids):
        return tuple(ordered), ()
    cyclic = tuple(node_id for node_id in node_ids if node_id not in ordered)
    return tuple(ordered), (
        CadGraphDiagnostic(
            code="graph.cycle_detected",
            message=f"CAD operation graph contains a cycle involving nodes: {list(cyclic)!r}.",
            topology_report={"cyclic_node_ids": cyclic},
            repair_suggestions=("Break the construction loop or declare a future procedural loop node explicitly.",),
        ),
    )


__all__ = [
    "CadGraphDiagnostic",
    "CadGraphDiagnosticSeverity",
    "CadGraphEdgeKind",
    "CadGraphEntity",
    "CadGraphEntityKind",
    "CadGraphReference",
    "CadMeshEmissionProfile",
    "CadOperationEdge",
    "CadOperationGraph",
    "CadOperationGraphValidationReport",
    "CadOperationNode",
    "CadGraphReplayStep",
    "CadTopologyLineageRecord",
    "cad_operation_node_from_descriptor",
    "validate_cad_operation_graph",
]
