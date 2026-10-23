"""Native CAD command execution contracts for Ghost Forge.

This module is the first implementation layer under the CAD logic blueprint.
It does not call Plasticity and does not depend on PlasticityMCP.  It defines
the data that Ghost Forge core must own while executing CAD-like commands:
selection context, resolved parameters/options, preflight results, topology
deltas, undo records, and manifest provenance.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schema import CadCommandDescriptor, FailureMode, ParameterSpec


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


SelectionKind = Literal["object", "vertex", "edge", "face", "curve", "surface", "solid", "element"]
CadExecutionStatus = Literal["preflight_failed", "preview_ready", "committed", "blocked"]


class CadSelectionItem(FrozenModel):
    object_id: str = Field(min_length=1)
    object_kind: str = "mesh"
    selection_kind: SelectionKind = "object"
    topology_id: str | None = None
    order: int = 0
    filter_reason: str = "accepted"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CadSelectionSet(FrozenModel):
    items: tuple[CadSelectionItem, ...] = ()
    active_object_id: str | None = None
    active_plane_id: str | None = None

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def selection_kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.selection_kind for item in self.items}))

    @property
    def object_kinds(self) -> tuple[str, ...]:
        return tuple(sorted({item.object_kind for item in self.items}))


class CadTopologySnapshot(FrozenModel):
    object_ids: tuple[str, ...] = ()
    vertex_count: int = 0
    edge_count: int = 0
    face_count: int = 0
    component_count: int = 0
    bounds: tuple[float, float, float, float, float, float] | None = None
    topology_names: dict[str, str] = Field(default_factory=dict)
    material_slots: tuple[str, ...] = ()


class CadTopologyLineage(FrozenModel):
    source_id: str
    result_ids: tuple[str, ...] = ()
    relation: str = Field(pattern="^(preserved|created|deleted|modified|split|merged|replaced)$")


class CadTopologyDelta(FrozenModel):
    before: CadTopologySnapshot = Field(default_factory=CadTopologySnapshot)
    after: CadTopologySnapshot = Field(default_factory=CadTopologySnapshot)
    creates: tuple[str, ...] = ()
    deletes: tuple[str, ...] = ()
    modifies: tuple[str, ...] = ()
    preserves: tuple[str, ...] = ()
    lineage: tuple[CadTopologyLineage, ...] = ()
    result_summary: dict[str, Any] = Field(default_factory=dict)


class CadCommandFailure(FrozenModel):
    code: str = Field(min_length=1)
    message: str
    recovery: str = ""
    severity: Literal["error", "warning"] = "error"
    source: Literal["descriptor", "selection", "parameter", "topology", "tolerance", "handler"] = "descriptor"

    @classmethod
    def from_failure_mode(cls, failure: FailureMode, *, source: str = "descriptor") -> "CadCommandFailure":
        return cls(
            code=failure.code,
            message=failure.message,
            recovery=failure.recovery,
            source=source,  # type: ignore[arg-type]
        )


class CadResolvedParameter(FrozenModel):
    name: str
    value: Any = None
    source: Literal["default", "user", "option_panel"] = "default"
    unit: str | None = None


class CadCommandContext(FrozenModel):
    command_id: str
    descriptor_status: str
    selection: CadSelectionSet = Field(default_factory=CadSelectionSet)
    parameters: tuple[CadResolvedParameter, ...] = ()
    option_panel_state: tuple[CadResolvedParameter, ...] = ()
    tolerance: dict[str, Any] = Field(default_factory=dict)
    preview_requested: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    def parameter_value(self, name: str) -> Any:
        for parameter in self.parameters:
            if parameter.name == name:
                return parameter.value
        raise KeyError(name)


class CadPreflightReport(FrozenModel):
    command_id: str
    ok: bool
    failures: tuple[CadCommandFailure, ...] = ()
    warnings: tuple[CadCommandFailure, ...] = ()
    selection_summary: dict[str, Any] = Field(default_factory=dict)
    parameter_summary: dict[str, Any] = Field(default_factory=dict)


class CadUndoRecord(FrozenModel):
    transaction_name: str
    reversible: bool = True
    delta_kind: str = "cad_topology_delta"
    command_id: str
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    topology_delta: CadTopologyDelta = Field(default_factory=CadTopologyDelta)
    notes: tuple[str, ...] = ()


class CadManifestEvent(FrozenModel):
    event_type: str = "cad.command"
    command_id: str
    effects: tuple[str, ...] = ()
    parameter_snapshot: dict[str, Any] = Field(default_factory=dict)
    selection_summary: dict[str, Any] = Field(default_factory=dict)
    topology_summary: dict[str, Any] = Field(default_factory=dict)
    tolerance: dict[str, Any] = Field(default_factory=dict)


class CadCommandResult(FrozenModel):
    command_id: str
    status: CadExecutionStatus
    preflight: CadPreflightReport
    topology_delta: CadTopologyDelta = Field(default_factory=CadTopologyDelta)
    undo_record: CadUndoRecord | None = None
    manifest_event: CadManifestEvent | None = None
    preview_payload: dict[str, Any] = Field(default_factory=dict)


def resolve_cad_command_context(
    descriptor: CadCommandDescriptor,
    *,
    selection: CadSelectionSet | None = None,
    parameters: dict[str, Any] | None = None,
    option_panel_state: dict[str, Any] | None = None,
    preview_requested: bool = True,
) -> CadCommandContext:
    parameters = parameters or {}
    option_panel_state = option_panel_state or {}
    resolved = tuple(
        _resolve_parameter(spec, parameters, source="user")
        for spec in descriptor.parameter_schema
    )
    options = tuple(
        _resolve_parameter(spec, option_panel_state, source="option_panel")
        for spec in descriptor.option_panel_schema
    )
    tolerance: dict[str, Any] = {
        "linear": descriptor.tolerance_policy.linear,
        "angular_degrees": descriptor.tolerance_policy.angular_degrees,
        "unit": descriptor.tolerance_policy.unit,
        "description": descriptor.tolerance_policy.description,
    }
    return CadCommandContext(
        command_id=descriptor.command_id,
        descriptor_status=descriptor.status,
        selection=selection or CadSelectionSet(),
        parameters=resolved,
        option_panel_state=options,
        tolerance=tolerance,
        preview_requested=preview_requested,
    )


def preflight_cad_command(
    descriptor: CadCommandDescriptor,
    context: CadCommandContext,
) -> CadPreflightReport:
    failures: list[CadCommandFailure] = []
    warnings: list[CadCommandFailure] = []
    failures.extend(_selection_failures(descriptor, context.selection))
    failures.extend(_parameter_failures(descriptor.parameter_schema, context.parameters))
    if descriptor.status in {"alias", "option", "contextual_mode"}:
        warnings.append(
            CadCommandFailure(
                code="relationship.owner_required",
                message="This descriptor is a relationship entry and must execute through its owning command.",
                recovery="Resolve alias_of, option_of, or contextual_mode_of before commit.",
                severity="warning",
                source="descriptor",
            )
        )
    if descriptor.status == "planned":
        failures.append(
            CadCommandFailure(
                code="handler.planned",
                message="No native Ghost Forge CAD handler is registered for this planned command yet.",
                recovery="Keep this command in preview/planning mode until a handler is implemented.",
                source="handler",
            )
        )
    if descriptor.status == "controlled_probe_needed":
        warnings.append(
            CadCommandFailure(
                code="evidence.controlled_probe_needed",
                message="Command behavior still needs controlled evidence before product exposure.",
                recovery="Run fixture/export probes before removing controlled gates.",
                severity="warning",
                source="descriptor",
            )
        )
    return CadPreflightReport(
        command_id=descriptor.command_id,
        ok=not failures,
        failures=tuple(failures),
        warnings=tuple(warnings),
        selection_summary={
            "count": context.selection.count,
            "selection_kinds": context.selection.selection_kinds,
            "object_kinds": context.selection.object_kinds,
            "active_object_id": context.selection.active_object_id,
            "active_plane_id": context.selection.active_plane_id,
        },
        parameter_summary={parameter.name: parameter.value for parameter in context.parameters},
    )


def build_preview_result(
    descriptor: CadCommandDescriptor,
    context: CadCommandContext,
    preflight: CadPreflightReport,
) -> CadCommandResult:
    status: CadExecutionStatus = "preview_ready" if preflight.ok else "preflight_failed"
    return CadCommandResult(
        command_id=descriptor.command_id,
        status=status,
        preflight=preflight,
        preview_payload={
            "preview_contract": list(descriptor.preview_contract),
            "parameter_snapshot": {parameter.name: parameter.value for parameter in context.parameters},
            "warnings": [warning.model_dump(mode="json") for warning in preflight.warnings],
        },
    )


def build_committed_result(
    descriptor: CadCommandDescriptor,
    context: CadCommandContext,
    preflight: CadPreflightReport,
    topology_delta: CadTopologyDelta,
) -> CadCommandResult:
    if not preflight.ok:
        return CadCommandResult(
            command_id=descriptor.command_id,
            status="preflight_failed",
            preflight=preflight,
            topology_delta=topology_delta,
        )
    parameter_snapshot = {parameter.name: parameter.value for parameter in context.parameters}
    undo = CadUndoRecord(
        transaction_name=descriptor.undo_contract.transaction_name,
        reversible=descriptor.undo_contract.reversible,
        delta_kind=descriptor.undo_contract.delta_kind,
        command_id=descriptor.command_id,
        parameter_snapshot=parameter_snapshot,
        topology_delta=topology_delta,
        notes=descriptor.undo_contract.notes,
    )
    manifest = CadManifestEvent(
        command_id=descriptor.command_id,
        effects=descriptor.manifest_effect,
        parameter_snapshot=parameter_snapshot,
        selection_summary=preflight.selection_summary,
        topology_summary=topology_delta.result_summary,
        tolerance=context.tolerance,
    )
    return CadCommandResult(
        command_id=descriptor.command_id,
        status="committed",
        preflight=preflight,
        topology_delta=topology_delta,
        undo_record=undo,
        manifest_event=manifest,
    )


def _resolve_parameter(
    spec: ParameterSpec,
    values: dict[str, Any],
    *,
    source: str,
) -> CadResolvedParameter:
    has_user_value = spec.name in values
    value = values.get(spec.name, spec.default)
    return CadResolvedParameter(
        name=spec.name,
        value=value,
        source=source if has_user_value else "default",  # type: ignore[arg-type]
        unit=spec.unit,
    )


def _selection_failures(
    descriptor: CadCommandDescriptor,
    selection: CadSelectionSet,
) -> list[CadCommandFailure]:
    contract = descriptor.selection_contract
    failures: list[CadCommandFailure] = []
    if selection.count < contract.min_count:
        failures.append(
            CadCommandFailure(
                code="selection.count_below_minimum",
                message=f"{descriptor.label} requires at least {contract.min_count} selection item(s).",
                recovery="Select compatible objects or sub-objects before running the command.",
                source="selection",
            )
        )
    if contract.max_count is not None and selection.count > contract.max_count:
        failures.append(
            CadCommandFailure(
                code="selection.count_above_maximum",
                message=f"{descriptor.label} accepts at most {contract.max_count} selection item(s).",
                recovery="Reduce the selection and try again.",
                source="selection",
            )
        )
    if contract.requires_active_object and not selection.active_object_id:
        failures.append(
            CadCommandFailure(
                code="selection.active_object_missing",
                message=f"{descriptor.label} requires an active object.",
                recovery="Activate the target object before running the command.",
                source="selection",
            )
        )
    if contract.active_plane_required and not selection.active_plane_id:
        failures.append(
            CadCommandFailure(
                code="selection.active_plane_missing",
                message=f"{descriptor.label} requires an active construction plane.",
                recovery="Set or select a construction plane first.",
                source="selection",
            )
        )
    allowed_object_kinds = set(contract.object_kinds)
    disallowed_objects = [
        item.object_kind
        for item in selection.items
        if item.object_kind not in allowed_object_kinds
    ]
    if disallowed_objects:
        failures.append(
            CadCommandFailure(
                code="selection.object_kind_unsupported",
                message=f"{descriptor.label} does not accept object kinds: {sorted(set(disallowed_objects))}.",
                recovery="Change selection filter or select compatible objects.",
                source="selection",
            )
        )
    allowed_subobjects = set(contract.subobject_kinds)
    if allowed_subobjects:
        disallowed_subobjects = [
            item.selection_kind
            for item in selection.items
            if item.selection_kind != "object" and item.selection_kind not in allowed_subobjects
        ]
        if disallowed_subobjects:
            failures.append(
                CadCommandFailure(
                    code="selection.subobject_kind_unsupported",
                    message=f"{descriptor.label} does not accept subobject kinds: {sorted(set(disallowed_subobjects))}.",
                    recovery="Use a compatible face, edge, vertex, curve, or object selection.",
                    source="selection",
                )
            )
    return failures


def _parameter_failures(
    specs: tuple[ParameterSpec, ...],
    parameters: tuple[CadResolvedParameter, ...],
) -> list[CadCommandFailure]:
    by_name = {parameter.name: parameter for parameter in parameters}
    failures: list[CadCommandFailure] = []
    for spec in specs:
        parameter = by_name[spec.name]
        value = parameter.value
        if spec.required and value is None:
            failures.append(
                CadCommandFailure(
                    code=f"parameter.{spec.name}.required",
                    message=f"Parameter {spec.name!r} is required.",
                    recovery="Provide a value before running the command.",
                    source="parameter",
                )
            )
        if spec.values and value is not None and value not in spec.values:
            failures.append(
                CadCommandFailure(
                    code=f"parameter.{spec.name}.invalid_enum",
                    message=f"Parameter {spec.name!r} must be one of {list(spec.values)!r}.",
                    recovery="Choose one of the descriptor enum values.",
                    source="parameter",
                )
            )
        if isinstance(value, (int, float)):
            if spec.minimum is not None and value < spec.minimum:
                failures.append(
                    CadCommandFailure(
                        code=f"parameter.{spec.name}.below_minimum",
                        message=f"Parameter {spec.name!r} is below minimum {spec.minimum}.",
                        recovery="Increase the value and try again.",
                        source="parameter",
                    )
                )
            if spec.maximum is not None and value > spec.maximum:
                failures.append(
                    CadCommandFailure(
                        code=f"parameter.{spec.name}.above_maximum",
                        message=f"Parameter {spec.name!r} is above maximum {spec.maximum}.",
                        recovery="Decrease the value and try again.",
                        source="parameter",
                    )
                )
    return failures


__all__ = [
    "CadCommandContext",
    "CadCommandFailure",
    "CadCommandResult",
    "CadExecutionStatus",
    "CadManifestEvent",
    "CadPreflightReport",
    "CadResolvedParameter",
    "CadSelectionItem",
    "CadSelectionSet",
    "CadTopologyDelta",
    "CadTopologyLineage",
    "CadTopologySnapshot",
    "CadUndoRecord",
    "SelectionKind",
    "build_committed_result",
    "build_preview_result",
    "preflight_cad_command",
    "resolve_cad_command_context",
]
