"""MCP tool surface for GhostForge.

Each tool is a thin wrapper over a `ghostforge_core` operation. Argument
schemas are derived from the function signatures by FastMCP, but the actual
field defaults, ranges, and types come from the Pydantic models in
:mod:`ghostforge_core.types`. Building each request through the matching
Pydantic model keeps that file the single source of truth for validation,
JSON Schema export, and runtime coercion.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

# Importing tools.py implies the MCP server is being built, so the optional
# `mcp` dependency must already be installed. Importing `Context` at module
# scope keeps it visible to FastMCP's runtime `get_type_hints` resolution.
from mcp.server.fastmcp import Context, FastMCP

from ghostforge_core.audit import (
    audit_asset as audit_asset_op,
    list_presets as list_audit_presets_op,
)
from ghostforge_core.benchmarks import (
    BenchmarkRequest,
    make_benchmark_id,
    run_benchmark as run_benchmark_op,
)
from ghostforge_core.engines import EngineConfig, EngineHandoffError
from ghostforge_core.models import ModelDownloadError, ModelNotFound
from ghostforge_core.kb.ingest import (
    ingest_local_image,
    ingest_openverse,
    ingest_url,
)
from ghostforge_core.kb.schema import ConceptSource
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    manifest_exists,
    read_manifest,
)
from ghostforge_core.operations import mesh_info as mesh_info_op
from ghostforge_core.operations.authoring import EvaluateGraphRequest
from ghostforge_core.scene_links import (
    annotate_graph_history_sequence,
    compare_graph_history_payloads,
    graph_history_comparison_resource_uri,
    graph_resource_uri,
    plan_graph_history_followup_actions,
    scene_id_for_path,
    scene_resource_uri,
)
from ghostforge_core.slice import (
    AssetKind,
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    SliceNotFound,
    plan_vertical_slice,
    update_plan_assets,
)
from ghostforge_core.slice import execute_vertical_slice as execute_slice_op
from ghostforge_core.types import (
    AuditAssetRequest,
    ExecuteVerticalSliceRequest,
    JobHandle,
    JobStatus,
    SendToEngineRequest,
    TextureRequest,
    UnwrapRequest,
)
from ghostforge_core.validation import validate_mesh
from ghostforge_core.workers import (
    Capability,
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from ghostforge_core.workers.session import get_session_registry

from .server import get_context


_TERMINAL_STATUSES = {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}
_WORKER_OPERATION_CAPABILITIES = {
    "generate_text_to_3d": Capability.text_to_3d.value,
    "generate_image_to_3d": Capability.image_to_3d.value,
    "worker_refine_mesh": Capability.refine_mesh.value,
    "worker_texture_mesh": Capability.texture_mesh.value,
}


def _handle_to_dict(handle: JobHandle) -> dict[str, Any]:
    return handle.model_dump(mode="json")


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return get_context().storage.new_asset_dir()


def _operation_descriptors_payload() -> list[dict[str, Any]]:
    from ghostforge_core.authoring import SOURCE_OPERATION_KINDS

    ctx = get_context()
    payload: list[dict[str, Any]] = []
    for descriptor in ctx.operations.descriptors():
        capability = _WORKER_OPERATION_CAPABILITIES.get(descriptor.kind)
        operation_type = "source" if descriptor.kind in SOURCE_OPERATION_KINDS else "operation"
        if capability is not None and operation_type != "source":
            operation_type = "worker"
        workers = _operation_worker_status(capability)
        item = descriptor.model_dump(mode="json")
        item.update(
            {
                "operation_type": operation_type,
                "capability": capability,
                "capability_status": _capability_status(workers, capability=capability),
                "workers": workers,
            }
        )
        payload.append(item)
    return payload


def _cad_command_payloads() -> list[dict[str, Any]]:
    from ghostforge_core.cad import build_default_cad_registry

    registry = build_default_cad_registry()
    return [command.model_dump(mode="json") for command in registry.all()]


def _cad_command_payload(command_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_cad_registry

    registry = build_default_cad_registry()
    try:
        return registry.get(command_id).model_dump(mode="json")
    except KeyError as exc:
        known = [command["command_id"] for command in _cad_command_payloads()]
        raise KeyError(f"Unknown CAD command {command_id!r}. Known: {known}") from exc


def _cad_execution_contract_payload() -> dict[str, Any]:
    return {
        "runtime_dependency": "none",
        "plasticity_role": "development_evidence_only",
        "stages": [
            "collect_selection_context",
            "resolve_parameters_and_options",
            "preflight_selection_parameters_and_handler_state",
            "build_preview_or_commit_result",
            "record_topology_delta_undo_and_manifest",
        ],
        "preflight_inputs": {
            "command_id": "CAD descriptor id from ghostforge://cad/commands",
            "selection_items": "List of object/subobject selections with object_id, object_kind, selection_kind, topology_id, and order.",
            "active_object_id": "Current modeling target when the command requires one.",
            "active_plane_id": "Construction plane id for commands that require one.",
            "parameters": "Command parameter values keyed by descriptor parameter name.",
            "option_panel_state": "Option-panel values keyed by descriptor option name.",
        },
        "structured_outputs": [
            "CadCommandContext",
            "CadPreflightReport",
            "CadCommandResult",
            "CadTopologyDelta",
            "CadUndoRecord",
            "CadManifestEvent",
        ],
    }


def _cad_operation_graph_contract_payload() -> dict[str, Any]:
    from ghostforge_core.cad import (
        CadMeshEmissionProfile,
        CadOperationGraph,
        CadOperationGraphValidationReport,
        CadOperationNode,
        CadTopologyLineageRecord,
    )

    return {
        "runtime_dependency": "none",
        "plasticity_role": "development_evidence_only",
        "status": "native_validation_surface",
        "purpose": (
            "Validate AI-authored or tool-authored editable CAD construction graphs "
            "against Ghost Forge command descriptors before any geometry kernel, mesher, "
            "or export step mutates document state."
        ),
        "source_artifacts": [
            "PlasticityMCP/knowledge_base/ghost_forge_operation_graph_contract.json",
            "PlasticityMCP/knowledge_base/ghost_forge_ai_geometry_compiler_plan.json",
        ],
        "input_contract": {
            "tool": "validate_cad_operation_graph",
            "argument": "graph",
            "graph_model": "CadOperationGraph",
            "minimum_graph_fields": ["graph_id", "nodes"],
            "minimum_node_fields": ["node_id", "command_id"],
            "recommended_node_fields": [
                "parameters",
                "selection",
                "inputs",
                "outputs",
                "descriptor_status",
            ],
            "stable_reference_rule": (
                "Inputs and outputs should use entity_id/topology_id references that resolve "
                "through entity_table and topology_table; do not rely on transient viewport order."
            ),
        },
        "validation_gates": [
            "payload_schema_valid",
            "node_ids_unique",
            "edge_ids_unique",
            "construction_graph_acyclic",
            "commands_exist_in_descriptor_registry",
            "parameters_declared_by_descriptor",
            "selection_and_active_context_pass_preflight",
            "input_referenced_entities_exist",
            "input_referenced_topology_lineage_exists",
        ],
        "output_contract": {
            "summary": [
                "ok",
                "status",
                "diagnostic_count",
                "error_count",
                "warning_count",
                "replay_step_count",
            ],
            "validation": "CadOperationGraphValidationReport",
            "replay_plan_rule": "Returned only when no error diagnostics are present.",
        },
        "execution_contract": {
            "tool": "execute_cad_operation_graph",
            "mutation": "writes_output_mesh_and_asset_manifest",
            "supported_descriptor_status": "implemented_mesh",
            "blocked_descriptor_statuses": ["planned", "controlled_probe_needed", "alias", "option", "contextual_mode"],
            "required_arguments": ["graph", "output_dir"],
            "optional_arguments": ["input_mesh_path", "output_format", "asset_id"],
            "source_graph_rule": (
                "Graphs whose first replayed node is a source primitive or generation node can omit "
                "input_mesh_path; modifier-only graphs must pass input_mesh_path or will return "
                "executor.input_mesh_required."
            ),
            "outputs": [
                "CadOperationGraphExecutionResult",
                "output mesh artifact",
                "asset_manifest.json",
                "topology lineage table updates",
                "mesh quality report",
            ],
            "honesty_rule": (
                "This execution prototype does not run future B-rep/NURBS CAD kernel nodes; "
                "planned commands remain blocked with diagnostics."
            ),
        },
        "schemas": {
            "CadOperationGraph": CadOperationGraph.model_json_schema(),
            "CadOperationNode": CadOperationNode.model_json_schema(),
            "CadTopologyLineageRecord": CadTopologyLineageRecord.model_json_schema(),
            "CadMeshEmissionProfile": CadMeshEmissionProfile.model_json_schema(),
            "CadOperationGraphValidationReport": CadOperationGraphValidationReport.model_json_schema(),
        },
    }


def _cad_graph_validation_summary(report: Any) -> dict[str, Any]:
    diagnostics = list(getattr(report, "diagnostics", ()) or ())
    error_count = sum(1 for diagnostic in diagnostics if getattr(diagnostic, "severity", "") == "error")
    warning_count = sum(1 for diagnostic in diagnostics if getattr(diagnostic, "severity", "") == "warning")
    return {
        "ok": bool(getattr(report, "ok", False)),
        "status": getattr(report, "status", "invalid"),
        "diagnostic_count": len(diagnostics),
        "error_count": error_count,
        "warning_count": warning_count,
        "replay_step_count": len(getattr(report, "replay_plan", ()) or ()),
    }


def _cad_validation_error_payload(graph: Any, exc: Exception) -> dict[str, Any]:
    from ghostforge_core.cad import CadGraphDiagnostic, CadOperationGraphValidationReport

    graph_id = "invalid_graph_payload"
    if isinstance(graph, dict) and graph.get("graph_id"):
        graph_id = str(graph["graph_id"])

    errors: list[dict[str, Any]] = []
    raw_errors = getattr(exc, "errors", None)
    if callable(raw_errors):
        for error in raw_errors():
            if isinstance(error, dict):
                errors.append(
                    {
                        key: value
                        for key, value in error.items()
                        if key not in {"ctx", "input", "url"}
                    }
                )
    if not errors:
        errors.append({"message": str(exc)})

    report = CadOperationGraphValidationReport(
        graph_id=graph_id,
        ok=False,
        diagnostics=(
            CadGraphDiagnostic(
                code="graph.payload_invalid",
                message="CAD operation graph payload did not match the Ghost Forge graph schema.",
                topology_report={"schema_errors": errors},
                repair_suggestions=("Read ghostforge://cad/operation-graph-contract and resubmit a CadOperationGraph payload.",),
            ),
        ),
    )
    return {
        "runtime_dependency": "none",
        "plasticity_role": "development_evidence_only",
        "graph": graph if isinstance(graph, dict) else None,
        "summary": _cad_graph_validation_summary(report),
        "validation": report.model_dump(mode="json"),
    }


def _cad_operation_graph_validation_payload(graph: dict[str, Any]) -> dict[str, Any]:
    from ghostforge_core.cad import (
        CadOperationGraph,
        build_default_cad_registry,
        validate_cad_operation_graph,
    )

    try:
        operation_graph = CadOperationGraph.model_validate(graph)
    except Exception as exc:
        return _cad_validation_error_payload(graph, exc)

    report = validate_cad_operation_graph(operation_graph, build_default_cad_registry())
    return {
        "runtime_dependency": "none",
        "plasticity_role": "development_evidence_only",
        "contract_resource": "ghostforge://cad/operation-graph-contract",
        "graph": operation_graph.model_dump(mode="json"),
        "summary": _cad_graph_validation_summary(report),
        "validation": report.model_dump(mode="json"),
        "notes": [
            "This tool validates graph structure, descriptor usage, selection context, and replay order only.",
            "It does not execute a geometry kernel, write scene files, emit meshes, or call Plasticity.",
            "Agents should revise failed nodes from diagnostics before submitting work to future kernel/mesh stages.",
        ],
    }


def _cad_operation_graph_execution_payload(
    graph: dict[str, Any],
    output_dir: str,
    input_mesh_path: str | None = None,
    output_format: str = "glb",
    asset_id: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import CadOperationGraph, execute_cad_operation_graph

    try:
        operation_graph = CadOperationGraph.model_validate(graph)
    except Exception as exc:
        return _cad_validation_error_payload(graph, exc)

    result = execute_cad_operation_graph(
        operation_graph,
        output_dir=Path(output_dir),
        input_mesh_path=Path(input_mesh_path) if input_mesh_path else None,
        output_format=output_format,
        asset_id=asset_id,
    )
    payload = result.model_dump(mode="json")
    payload.update(
        {
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
            "mutation": "writes_output_mesh_and_asset_manifest",
            "contract_resource": "ghostforge://cad/operation-graph-contract",
            "notes": [
                "This tool executes only implemented mesh-backed CAD descriptors.",
                "Source graphs can omit input_mesh_path; process-only graphs require an input mesh.",
                "Planned B-rep/NURBS commands remain blocked until native kernel handlers exist.",
                "Successful runs write a mesh artifact and asset_manifest.json under output_dir.",
            ],
        }
    )
    return payload


def _cad_preflight_payload(
    command_id: str,
    selection_items: list[dict[str, Any]] | None = None,
    active_object_id: str | None = None,
    active_plane_id: str | None = None,
    parameters: dict[str, Any] | None = None,
    option_panel_state: dict[str, Any] | None = None,
    preview_requested: bool = True,
) -> dict[str, Any]:
    from ghostforge_core.cad import (
        CadSelectionItem,
        CadSelectionSet,
        build_default_cad_registry,
        build_preview_result,
        preflight_cad_command,
        resolve_cad_command_context,
    )

    registry = build_default_cad_registry()
    try:
        descriptor = registry.get(command_id)
    except KeyError as exc:
        known = [command["command_id"] for command in _cad_command_payloads()]
        raise KeyError(f"Unknown CAD command {command_id!r}. Known: {known}") from exc

    selection = CadSelectionSet(
        items=tuple(CadSelectionItem(**item) for item in (selection_items or [])),
        active_object_id=active_object_id,
        active_plane_id=active_plane_id,
    )
    context = resolve_cad_command_context(
        descriptor,
        selection=selection,
        parameters=parameters,
        option_panel_state=option_panel_state,
        preview_requested=preview_requested,
    )
    preflight = preflight_cad_command(descriptor, context)
    preview = build_preview_result(descriptor, context, preflight)
    return {
        "runtime_dependency": "none",
        "plasticity_role": "development_evidence_only",
        "descriptor": descriptor.model_dump(mode="json"),
        "context": context.model_dump(mode="json"),
        "preflight": preflight.model_dump(mode="json"),
        "preview_result": preview.model_dump(mode="json"),
    }


def _cad_fixture_payloads() -> list[dict[str, Any]]:
    from ghostforge_core.cad import build_default_fixture_catalog

    catalog = build_default_fixture_catalog()
    return [fixture.model_dump(mode="json") for fixture in catalog.all_fixtures()]


def _cad_fixture_payload(fixture_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_fixture_catalog

    catalog = build_default_fixture_catalog()
    try:
        return catalog.get_fixture(fixture_id).model_dump(mode="json")
    except KeyError as exc:
        known = [fixture["fixture_id"] for fixture in _cad_fixture_payloads()]
        raise KeyError(f"Unknown CAD fixture {fixture_id!r}. Known: {known}") from exc


def _cad_fixture_expectation_payloads(command_id: str | None = None) -> list[dict[str, Any]]:
    from ghostforge_core.cad import build_default_fixture_catalog

    catalog = build_default_fixture_catalog()
    expectations = (
        catalog.expectations_for_command(command_id)
        if command_id
        else list(catalog.expectations)
    )
    return [expectation.model_dump(mode="json") for expectation in expectations]


def _cad_behavior_matrix_payload(
    command_id: str | None = None,
    result_state: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_behavior_matrix

    matrix = build_default_behavior_matrix()
    cases = [case.model_dump(mode="json") for case in matrix.all_cases()]
    if command_id:
        cases = [case for case in cases if case.get("command_id") == command_id]
    if result_state:
        cases = [case for case in cases if case.get("result_state") == result_state]
    summary = matrix.summary()
    summary.update(
        {
            "filtered_case_count": len(cases),
            "filters": {"command_id": command_id, "result_state": result_state},
        }
    )
    return {
        "summary": summary,
        "cases": cases,
        "notes": [
            "Behavior cases are Ghost Forge native implementation contracts for fixture-level command behavior.",
            "Plasticity evidence status identifies what still needs live comparison evidence; it is not a runtime dependency.",
        ],
    }


def _cad_behavior_case_payload(case_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_behavior_matrix

    matrix = build_default_behavior_matrix()
    try:
        return matrix.get(case_id).model_dump(mode="json")
    except KeyError as exc:
        known = [case["case_id"] for case in _cad_behavior_matrix_payload()["cases"]]
        raise KeyError(f"Unknown CAD behavior case {case_id!r}. Known: {known}") from exc


def _cad_probe_matrix_payload() -> dict[str, Any]:
    from ghostforge_core.cad import build_default_probe_matrix

    matrix = build_default_probe_matrix()
    return {
        "summary": matrix.summary(),
        "command_plans": [plan.model_dump(mode="json") for plan in matrix.all_command_plans()],
        "format_plans": [plan.model_dump(mode="json") for plan in matrix.all_format_plans()],
        "static_asset_plans": [plan.model_dump(mode="json") for plan in matrix.all_static_asset_plans()],
    }


def _cad_command_probe_plan_payload(command_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_probe_matrix

    matrix = build_default_probe_matrix()
    try:
        return matrix.get_command_plan(command_id).model_dump(mode="json")
    except KeyError as exc:
        known = [plan["command_id"] for plan in _cad_probe_matrix_payload()["command_plans"]]
        raise KeyError(f"Unknown CAD probe command {command_id!r}. Known: {known}") from exc


def _cad_logic_blueprint_payload(command_id: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_logic_blueprint

    blueprint = build_default_logic_blueprint()
    patterns = (
        blueprint.patterns_for_command(command_id)
        if command_id
        else blueprint.all_patterns()
    )
    return {
        "summary": {
            **blueprint.summary(),
            "filtered_pattern_count": len(patterns),
            "filters": {"command_id": command_id},
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        },
        "patterns": [pattern.model_dump(mode="json") for pattern in patterns],
    }


def _cad_logic_pattern_payload(pattern_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_logic_blueprint

    blueprint = build_default_logic_blueprint()
    return blueprint.get(pattern_id).model_dump(mode="json")


def _cad_interop_formats_payload(
    direction: str | None = None,
    family: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_interop_registry

    registry = build_default_interop_registry()
    formats = [descriptor.model_dump(mode="json") for descriptor in registry.all()]
    if direction:
        formats = [descriptor for descriptor in formats if direction in descriptor.get("directions", [])]
    if family:
        formats = [descriptor for descriptor in formats if descriptor.get("family") == family]
    summary = registry.summary()
    summary.update(
        {
            "filtered_format_count": len(formats),
            "filters": {"direction": direction, "family": family},
        }
    )
    return {
        "summary": summary,
        "formats": formats,
        "notes": [
            "Format descriptors are Ghost Forge native contracts. Plasticity translator files and static assets are evidence only.",
            "File-touching automation must use workspace-controlled paths and record translator diagnostics.",
        ],
    }


def _cad_interop_format_payload(format_id: str) -> dict[str, Any]:
    from ghostforge_core.cad import build_default_interop_registry

    registry = build_default_interop_registry()
    try:
        return registry.get(format_id).model_dump(mode="json")
    except KeyError as exc:
        known = [descriptor["format_id"] for descriptor in _cad_interop_formats_payload()["formats"]]
        raise KeyError(f"Unknown CAD interop format {format_id!r}. Known: {known}") from exc


def _cad_development_queue_payload(
    kb_root: str | None = None,
    implementation_track: str | None = None,
    has_blocker: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_ghostforge_cad_development_queue

    queue = build_ghostforge_cad_development_queue(kb_root)
    tasks = [task.model_dump(mode="json") for task in queue.all_tasks()]
    if implementation_track:
        tasks = [task for task in tasks if task.get("implementation_track") == implementation_track]
    if has_blocker:
        tasks = [task for task in tasks if has_blocker in task.get("blockers", [])]
    summary = queue.summary()
    summary.update(
        {
            "filtered_task_count": len(tasks),
            "filters": {"implementation_track": implementation_track, "has_blocker": has_blocker},
        }
    )
    return {
        "summary": summary,
        "kb_root": queue.kb_root,
        "generated_utc": queue.generated_utc,
        "source_files": queue.source_files or {},
        "tasks": tasks,
        "notes": [
            "This queue maps Plasticity recon evidence into native Ghost Forge implementation work.",
            "Plasticity remains development evidence only; Ghost Forge owns the runtime command, fixture, interop, and UI contracts.",
        ],
    }


def _cad_development_task_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_ghostforge_cad_development_queue

    queue = build_ghostforge_cad_development_queue(kb_root)
    return queue.get(command_id).model_dump(mode="json")


def _cad_automation_runbook_payload(
    kb_root: str | None = None,
    route_kind: str | None = None,
    missing_gate: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_automation_runbook

    runbook = build_cad_automation_runbook(kb_root)
    routes = [route.model_dump(mode="json") for route in runbook.all_routes()]
    if route_kind:
        routes = [route for route in routes if route.get("route_kind") == route_kind]
    if missing_gate:
        routes = [
            route
            for route in routes
            if missing_gate
            in [
                gate["gate_id"]
                for gate in route.get("safety_gates", [])
                if gate.get("required_before_live_execution") and gate.get("status") == "missing"
            ]
        ]
    summary = runbook.summary()
    summary.update(
        {
            "filtered_route_count": len(routes),
            "filters": {"route_kind": route_kind, "missing_gate": missing_gate},
        }
    )
    return {
        "summary": summary,
        "kb_root": runbook.kb_root,
        "generated_utc": runbook.generated_utc,
        "routes": routes,
        "notes": [
            "Automation routes are declarative safety/evidence runbooks and do not call Plasticity.",
            "Live execution is allowed only when route, probe package, disposable fixture, and file safety gates are satisfied.",
        ],
    }


def _cad_automation_route_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_automation_runbook

    runbook = build_cad_automation_runbook(kb_root)
    return runbook.get(command_id).model_dump(mode="json")


def _cad_schema_drafts_payload(
    kb_root: str | None = None,
    implementation_track: str | None = None,
    has_blocker: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_schema_draft_catalog

    catalog = build_cad_schema_draft_catalog(kb_root)
    drafts = [draft.model_dump(mode="json") for draft in catalog.all_drafts()]
    if implementation_track:
        drafts = [draft for draft in drafts if draft.get("implementation_track") == implementation_track]
    if has_blocker:
        drafts = [draft for draft in drafts if has_blocker in draft.get("promotion_blockers", [])]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_draft_count": len(drafts),
            "filters": {"implementation_track": implementation_track, "has_blocker": has_blocker},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "drafts": drafts,
        "notes": [
            "Schema drafts are Ghost Forge planning artifacts derived from inferred/observed Plasticity recon templates.",
            "Template-inferred drafts can guide Qt/MCP panel design but remain blocked until observed schema and reset evidence exist.",
        ],
    }


def _cad_schema_draft_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_schema_draft_catalog

    catalog = build_cad_schema_draft_catalog(kb_root)
    draft = catalog.get(command_id)
    return {
        **draft.model_dump(mode="json"),
        "parameter_specs": [spec.model_dump(mode="json") for spec in draft.parameter_specs()],
    }


def _cad_schema_promotion_payload(
    kb_root: str | None = None,
    promotion_status: str | None = None,
    has_blocker: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_schema_promotion_catalog

    catalog = build_cad_schema_promotion_catalog(kb_root)
    candidates = [candidate.model_dump(mode="json") for candidate in catalog.all_candidates()]
    if promotion_status:
        candidates = [
            candidate
            for candidate in candidates
            if candidate.get("promotion_status") == promotion_status
        ]
    if has_blocker:
        candidates = [
            candidate
            for candidate in candidates
            if has_blocker in candidate.get("blockers", [])
        ]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_candidate_count": len(candidates),
            "filters": {"promotion_status": promotion_status, "has_blocker": has_blocker},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "candidates": candidates,
        "notes": [
            "Schema promotion candidates separate inferred templates from observed Plasticity evidence.",
            "A command is promotable only after observed controls, required evidence, validation checks, and reset verification pass.",
        ],
    }


def _cad_schema_promotion_candidate_payload(
    command_id: str,
    kb_root: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_schema_promotion_catalog

    catalog = build_cad_schema_promotion_catalog(kb_root)
    candidate = catalog.get(command_id)
    return {
        **candidate.model_dump(mode="json"),
        "parameter_specs": [spec.model_dump(mode="json") for spec in candidate.parameter_specs()],
    }


def _cad_evidence_packets_payload(
    kb_root: str | None = None,
    packet_kind: str | None = None,
    readiness: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_evidence_packet_catalog

    catalog = build_cad_evidence_packet_catalog(kb_root)
    packets = [packet.model_dump(mode="json") for packet in catalog.all_packets()]
    if packet_kind:
        packets = [packet for packet in packets if packet.get("packet_kind") == packet_kind]
    if readiness:
        packets = [packet for packet in packets if packet.get("readiness") == readiness]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_packet_count": len(packets),
            "filters": {"packet_kind": packet_kind, "readiness": readiness},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "packets": packets,
        "notes": [
            "Evidence packet plans define the exact artifact a live Plasticity probe must capture.",
            "Packets feed schema promotion, behavior fixtures, robustness contracts, interop descriptors, and static-owner classification.",
        ],
    }


def _cad_evidence_packet_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_evidence_packet_catalog

    catalog = build_cad_evidence_packet_catalog(kb_root)
    return catalog.get(command_id).model_dump(mode="json")


def _cad_probe_batches_payload(
    kb_root: str | None = None,
    batch_kind: str | None = None,
    packet_kind: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_probe_batch_plan

    plan = build_cad_probe_batch_plan(kb_root)
    batches = [batch.model_dump(mode="json") for batch in plan.all_batches()]
    if batch_kind:
        batches = [batch for batch in batches if batch.get("batch_kind") == batch_kind]
    if packet_kind:
        batches = [batch for batch in batches if batch.get("packet_kind") == packet_kind]
    summary = plan.summary()
    summary.update(
        {
            "filtered_batch_count": len(batches),
            "filters": {"batch_kind": batch_kind, "packet_kind": packet_kind},
        }
    )
    return {
        "summary": summary,
        "kb_root": plan.kb_root,
        "generated_utc": plan.generated_utc,
        "batches": batches,
        "notes": [
            "Probe batches order evidence packets into ready capture, package generation, static-owner resolution, safety repair, and promotion follow-up work.",
            "Batches are planning contracts only; Plasticity is still development evidence, not a Ghost Forge runtime dependency.",
        ],
    }


def _cad_probe_batch_payload(batch_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_probe_batch_plan

    plan = build_cad_probe_batch_plan(kb_root)
    return plan.get(batch_id).model_dump(mode="json")


def _cad_live_probe_sessions_payload(
    kb_root: str | None = None,
    session_mode: str | None = None,
    packet_kind: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_live_probe_session_catalog

    catalog = build_cad_live_probe_session_catalog(kb_root)
    sessions = [session.model_dump(mode="json") for session in catalog.all_sessions()]
    if session_mode:
        sessions = [session for session in sessions if session.get("session_mode") == session_mode]
    if packet_kind:
        sessions = [session for session in sessions if session.get("packet_kind") == packet_kind]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_session_count": len(sessions),
            "filters": {"session_mode": session_mode, "packet_kind": packet_kind},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "sessions": sessions,
        "notes": [
            "Live probe sessions are plan-only step sequences derived from batches and evidence packets.",
            "They do not execute Plasticity; they define guarded manual/automation capture order and evidence outputs.",
        ],
    }


def _cad_live_probe_session_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_live_probe_session_catalog

    catalog = build_cad_live_probe_session_catalog(kb_root)
    return catalog.get(command_id).model_dump(mode="json")


def _cad_observation_templates_payload(
    kb_root: str | None = None,
    session_mode: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_observation_template_catalog

    catalog = build_cad_observation_template_catalog(kb_root)
    templates = [template.model_dump(mode="json") for template in catalog.all_templates()]
    if session_mode:
        templates = [template for template in templates if template.get("session_mode") == session_mode]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_template_count": len(templates),
            "filters": {"session_mode": session_mode},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "templates": templates,
        "notes": [
            "Observation templates are empty receiving records for completed live Plasticity captures.",
            "A filled record must validate before it can feed Ghost Forge native schemas, behavior, interop, or static-owner relationships.",
        ],
    }


def _cad_observation_template_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import observation_template_for_command

    return observation_template_for_command(command_id, kb_root).model_dump(mode="json")


def _cad_observation_validation_payload(
    observation_record: dict[str, Any],
    kb_root: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import validate_cad_observation_record

    return validate_cad_observation_record(observation_record, kb_root).model_dump(mode="json")


def _cad_observation_ledger_payload(
    kb_root: str | None = None,
    status: str | None = None,
    promotion_target: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import load_cad_observation_ledger

    catalog = load_cad_observation_ledger(kb_root)
    entries = [entry.model_dump(mode="json") for entry in catalog.all_entries()]
    if status:
        entries = [entry for entry in entries if entry.get("validation", {}).get("status") == status]
    if promotion_target:
        entries = [
            entry
            for entry in entries
            if promotion_target in entry.get("validation", {}).get("promotion_targets", [])
        ]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_entry_count": len(entries),
            "filters": {"status": status, "promotion_target": promotion_target},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "source_files": list(catalog.source_files),
        "entries": entries,
        "notes": [
            "Observation ledger entries are completed Plasticity captures validated against Ghost Forge evidence/session contracts.",
            "Accepted entries name the exact native Ghost Forge targets they may feed; rejected entries keep their blockers visible.",
        ],
    }


def _cad_observation_ledger_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import load_cad_observation_ledger

    catalog = load_cad_observation_ledger(kb_root)
    entries = [entry.model_dump(mode="json") for entry in catalog.entries_for_command(command_id)]
    return {
        "command_id": command_id,
        "kb_root": catalog.kb_root,
        "entry_count": len(entries),
        "entries": entries,
        "latest": entries[-1] if entries else None,
    }


def _cad_native_handoffs_payload(
    kb_root: str | None = None,
    handoff_status: str | None = None,
    target: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_native_handoff_catalog

    catalog = build_cad_native_handoff_catalog(kb_root)
    handoffs = [handoff.model_dump(mode="json") for handoff in catalog.all_handoffs()]
    if handoff_status:
        handoffs = [handoff for handoff in handoffs if handoff.get("handoff_status") == handoff_status]
    if target:
        handoffs = [
            handoff
            for handoff in handoffs
            if target in handoff.get("promotion_targets", [])
            or any(step.get("target") == target or step.get("step_id") == target for step in handoff.get("steps", []))
        ]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_handoff_count": len(handoffs),
            "filters": {"handoff_status": handoff_status, "target": target},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "handoffs": handoffs,
        "notes": [
            "Native CAD handoffs convert validated observation ledger entries into concrete Ghost Forge implementation steps.",
            "Rejected captures remain blocked handoffs; accepted captures name descriptor, Qt/MCP schema, handler-test, interop, robustness, or static-owner work.",
        ],
    }


def _cad_native_handoff_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_native_handoff_catalog

    catalog = build_cad_native_handoff_catalog(kb_root)
    handoffs = [handoff.model_dump(mode="json") for handoff in catalog.handoffs_for_command(command_id)]
    return {
        "command_id": command_id,
        "kb_root": catalog.kb_root,
        "handoff_count": len(handoffs),
        "handoffs": handoffs,
        "latest": handoffs[-1] if handoffs else None,
    }


def _cad_capture_campaign_payload(
    kb_root: str | None = None,
    status: str | None = None,
    packet_kind: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_capture_campaign_catalog

    catalog = build_cad_capture_campaign_catalog(kb_root)
    items = [item.model_dump(mode="json") for item in catalog.all_items()]
    if status:
        items = [item for item in items if item.get("status") == status]
    if packet_kind:
        items = [item for item in items if item.get("packet_kind") == packet_kind]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_item_count": len(items),
            "filters": {"status": status, "packet_kind": packet_kind},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "items": items,
        "notes": [
            "Capture campaign items join live sessions, observation ledger entries, and native handoffs.",
            "They tell the next recon pass what to capture, recapture, unblock, or apply inside Ghost Forge.",
        ],
    }


def _cad_capture_campaign_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_capture_campaign_catalog

    catalog = build_cad_capture_campaign_catalog(kb_root)
    return catalog.get(command_id).model_dump(mode="json")


def _cad_selection_contracts_payload(
    kb_root: str | None = None,
    operation_kind: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_selection_contract_catalog

    catalog = build_cad_selection_contract_catalog(kb_root)
    commands = [contract.model_dump(mode="json") for contract in catalog.all_commands()]
    if operation_kind:
        commands = [contract for contract in commands if contract.get("operation_kind") == operation_kind]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_command_count": len(commands),
            "filters": {"operation_kind": operation_kind},
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "generated_utc": catalog.generated_utc,
        "modes": [mode.model_dump(mode="json") for mode in catalog.all_modes()],
        "commands": commands,
        "notes": [
            "Selection contracts are native Ghost Forge picker/preflight contracts derived from recon evidence.",
            "They define queryable selection state rather than relying on hidden viewport state.",
        ],
    }


def _cad_selection_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_selection_contract_catalog

    catalog = build_cad_selection_contract_catalog(kb_root)
    return catalog.get_command(command_id).model_dump(mode="json")


def _cad_robustness_contracts_payload(
    kb_root: str | None = None,
    subject_type: str | None = None,
    has_failure: str | None = None,
    has_topology_policy: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_robustness_catalog

    catalog = build_cad_robustness_catalog(kb_root)
    contracts = [contract.model_dump(mode="json") for contract in catalog.all_contracts()]
    if subject_type:
        contracts = [contract for contract in contracts if contract.get("subject_type") == subject_type]
    if has_failure:
        contracts = [contract for contract in contracts if has_failure in contract.get("failure_codes", [])]
    if has_topology_policy:
        contracts = [
            contract
            for contract in contracts
            if has_topology_policy in contract.get("topology_policy_ids", [])
        ]
    summary = catalog.summary()
    summary.update(
        {
            "filtered_contract_count": len(contracts),
            "filters": {
                "subject_type": subject_type,
                "has_failure": has_failure,
                "has_topology_policy": has_topology_policy,
            },
        }
    )
    return {
        "summary": summary,
        "kb_root": catalog.kb_root,
        "topology_policies": [policy.model_dump(mode="json") for policy in catalog.all_topology_policies()],
        "tolerance_contracts": [
            tolerance.model_dump(mode="json") for tolerance in catalog.all_tolerances()
        ],
        "failure_contracts": [
            failure.model_dump(mode="json") for failure in catalog.all_failures()
        ],
        "contracts": contracts,
        "notes": [
            "Robustness contracts join native CAD descriptors, fixture behavior, interop formats, and selection-state contracts.",
            "PlasticityMCP is evidence only; these records define Ghost Forge topology identity, tolerance, and failure behavior.",
        ],
    }


def _cad_robustness_contract_payload(
    contract_id: str,
    kb_root: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_robustness_catalog

    catalog = build_cad_robustness_catalog(kb_root)
    contract = catalog.get_contract(contract_id)
    tolerance_contracts = [
        catalog.tolerance_contracts[tolerance_id].model_dump(mode="json")
        for tolerance_id in contract.tolerance_contract_ids
        if tolerance_id in catalog.tolerance_contracts
    ]
    failure_contracts = [
        catalog.failure_contracts[code].model_dump(mode="json")
        for code in contract.failure_codes
        if code in catalog.failure_contracts
    ]
    topology_policies = [
        catalog.topology_policies[policy_id].model_dump(mode="json")
        for policy_id in contract.topology_policy_ids
        if policy_id in catalog.topology_policies
    ]
    return {
        **contract.model_dump(mode="json"),
        "topology_policies": topology_policies,
        "tolerance_contracts": tolerance_contracts,
        "failure_contracts": failure_contracts,
    }


def _plasticity_recon_coverage_payload(
    kb_root: str | None = None,
    readiness_bucket: str | None = None,
    priority: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_recon_coverage

    snapshot = load_plasticity_recon_coverage(kb_root)
    commands = [row.model_dump(mode="json") for row in snapshot.commands]
    if readiness_bucket:
        commands = [row for row in commands if row.get("readiness_bucket") == readiness_bucket]
    if priority:
        commands = [row for row in commands if row.get("priority") == priority]
    summary = snapshot.coverage_summary()
    summary.update(
        {
            "filtered_command_count": len(commands),
            "filters": {"readiness_bucket": readiness_bucket, "priority": priority},
        }
    )
    return {
        "summary": summary,
        "kb_root": snapshot.kb_root,
        "generated_utc": snapshot.generated_utc,
        "source_files": snapshot.source_files,
        "basis": snapshot.basis,
        "readiness_summary": snapshot.summary,
        "operating_sequence": list(snapshot.operating_sequence),
        "format_families": list(snapshot.format_families),
        "commands": commands,
    }


def _plasticity_recon_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_recon_coverage

    snapshot = load_plasticity_recon_coverage(kb_root)
    try:
        return snapshot.command(command_id).model_dump(mode="json")
    except KeyError as exc:
        known = [row.command_id for row in snapshot.commands]
        raise KeyError(f"Unknown Plasticity recon command {command_id!r}. Known: {known}") from exc


def _plasticity_observation_evidence_payload(
    kb_root: str | None = None,
    schema_status: str | None = None,
    probe_kind: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_observation_evidence

    snapshot = load_plasticity_observation_evidence(kb_root)
    commands = [row.model_dump(mode="json") for row in snapshot.commands]
    templates = [row.model_dump(mode="json") for row in snapshot.templates]
    if schema_status:
        commands = [row for row in commands if row.get("schema_status") == schema_status]
        templates = [row for row in templates if row.get("schema_status") == schema_status]
    if probe_kind:
        commands = [row for row in commands if row.get("probe_kind") == probe_kind]
        templates = [row for row in templates if row.get("probe_kind") == probe_kind]
    summary = snapshot.observation_summary()
    summary.update(
        {
            "filtered_command_count": len(commands),
            "filtered_template_count": len(templates),
            "filters": {"schema_status": schema_status, "probe_kind": probe_kind},
        }
    )
    return {
        "summary": summary,
        "kb_root": snapshot.kb_root,
        "generated_utc": snapshot.generated_utc,
        "source_files": snapshot.source_files,
        "ledger_basis": snapshot.ledger_basis,
        "template_basis": snapshot.template_basis,
        "template_groups": {key: list(value) for key, value in snapshot.template_groups.items()},
        "latest_session": snapshot.latest_session.model_dump(mode="json") if snapshot.latest_session else None,
        "commands": commands,
        "templates": templates,
    }


def _plasticity_observation_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_observation_evidence

    snapshot = load_plasticity_observation_evidence(kb_root)
    status = snapshot.command_status(command_id).model_dump(mode="json")
    try:
        template = snapshot.command_template(command_id).model_dump(mode="json")
    except KeyError:
        template = None
    return {"status": status, "template": template}


def _plasticity_probe_packages_payload(
    kb_root: str | None = None,
    requires_file_evidence: bool | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_probe_packages

    snapshot = load_plasticity_probe_packages(kb_root)
    packages = [row.model_dump(mode="json") for row in snapshot.packages]
    if requires_file_evidence is not None:
        packages = [
            row
            for row in packages
            if any("file" in evidence for evidence in row.get("required_evidence", ())) is requires_file_evidence
        ]
    summary = snapshot.package_summary()
    summary.update(
        {
            "filtered_package_count": len(packages),
            "filters": {"requires_file_evidence": requires_file_evidence},
        }
    )
    return {
        "summary": summary,
        "kb_root": snapshot.kb_root,
        "generated_utc": snapshot.generated_utc,
        "source_files": snapshot.source_files,
        "basis": snapshot.basis,
        "packages": packages,
    }


def _plasticity_probe_package_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import load_plasticity_probe_packages

    snapshot = load_plasticity_probe_packages(kb_root)
    return snapshot.package(command_id).model_dump(mode="json")


def _cad_parity_report_payload(
    kb_root: str | None = None,
    recommended_action: str | None = None,
    has_blocker: str | None = None,
) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_parity_report

    report = build_cad_parity_report(kb_root)
    commands = [row.model_dump(mode="json") for row in report.commands]
    if recommended_action:
        commands = [row for row in commands if row.get("recommended_ghostforge_action") == recommended_action]
    if has_blocker:
        commands = [row for row in commands if has_blocker in row.get("blockers", [])]
    summary = dict(report.summary)
    summary.update(
        {
            "filtered_command_count": len(commands),
            "filters": {"recommended_action": recommended_action, "has_blocker": has_blocker},
        }
    )
    return {
        "summary": summary,
        "kb_root": report.kb_root,
        "commands": commands,
    }


def _cad_parity_command_payload(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
    from ghostforge_core.cad import build_cad_parity_report

    report = build_cad_parity_report(kb_root)
    return report.command(command_id).model_dump(mode="json")


def _cad_registry_summary(commands: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    family_counts: dict[str, int] = {}
    for command in commands:
        status = str(command.get("status") or "<missing>")
        family = str(command.get("family") or "<missing>")
        status_counts[status] = status_counts.get(status, 0) + 1
        family_counts[family] = family_counts.get(family, 0) + 1
    return {
        "command_count": len(commands),
        "status_counts": dict(sorted(status_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "top_level_command_count": sum(1 for command in commands if command.get("is_top_level_command", True)),
        "relationship_count": sum(
            1
            for command in commands
            if command.get("alias_of") or command.get("option_of") or command.get("contextual_mode_of")
        ),
    }


def _cad_fixture_summary(
    fixtures: list[dict[str, Any]],
    expectations: list[dict[str, Any]],
) -> dict[str, Any]:
    geometry_kind_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for fixture in fixtures:
        geometry_kind = str(fixture.get("geometry_kind") or "<missing>")
        geometry_kind_counts[geometry_kind] = geometry_kind_counts.get(geometry_kind, 0) + 1
    for expectation in expectations:
        status = str(expectation.get("verification_status") or "<missing>")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "fixture_count": len(fixtures),
        "expectation_count": len(expectations),
        "geometry_kind_counts": dict(sorted(geometry_kind_counts.items())),
        "verification_status_counts": dict(sorted(status_counts.items())),
        "commands_with_expectations": sorted({str(row["command_id"]) for row in expectations}),
    }


def _operation_worker_status(capability: str | None) -> list[dict[str, Any]]:
    if capability is None:
        return []
    ctx = get_context()
    cap = Capability(capability)
    rows: list[dict[str, Any]] = []
    for worker in ctx.workers.for_capability(cap):
        try:
            probe = worker.probe()
            runnable = probe.runnable
            reason = probe.reason
            device = probe.device
        except Exception as exc:  # pragma: no cover - defensive MCP boundary
            runnable = False
            reason = str(exc)
            device = None
        rows.append(
            {
                "name": worker.name,
                "priority": worker.priority,
                "is_stub": getattr(worker, "is_stub", False),
                "license": getattr(worker, "license", None),
                "runnable": runnable,
                "reason": reason,
                "device": device,
            }
        )
    rows.sort(key=lambda row: (not row["runnable"], -int(row["priority"]), row["name"]))
    return rows


def _capability_status(workers: list[dict[str, Any]], *, capability: str | None) -> str:
    if capability is None:
        return "available"
    if any(row["runnable"] and not row["is_stub"] for row in workers):
        return "runnable"
    if any(row["runnable"] and row["is_stub"] for row in workers):
        return "stub"
    if workers:
        return "missing"
    return "unavailable"


def _graph_with_evaluation_payload(graph_id: str) -> dict[str, Any]:
    ctx = get_context()
    graph = ctx.graphs.load(graph_id)
    evaluation = ctx.graphs.load_evaluation(graph_id)
    out: dict[str, Any] = {"graph": graph.model_dump(mode="json")}
    if evaluation is not None:
        out["evaluation"] = evaluation.model_dump(mode="json")
    return out


def _graph_with_overrides(graph, *, input_path: str | None, output_path: str | None):  # type: ignore[no-untyped-def]
    updates: dict[str, Any] = {}
    if input_path is not None:
        updates["base_asset_path"] = input_path
    if output_path is not None:
        updates["output_path"] = output_path
    if not updates:
        return graph
    return graph.model_copy(update=updates)


def _scene_root() -> Path:
    return get_context().storage.root / "project" / "scenes"


def _scene_paths() -> list[Path]:
    root = _scene_root()
    if not root.exists():
        return []
    return sorted(path for path in root.glob("*.gforge") if path.is_file())


def _scene_index_payload() -> list[dict[str, Any]]:
    scenes: list[dict[str, Any]] = []
    for path in _scene_paths():
        payload = _load_scene_payload(path)
        scenes.append(
            {
                "scene_id": payload["scene_id"],
                "name": path.stem,
                "path": str(path),
                "resource_uri": payload["resource_uri"],
                "saved_at": payload.get("saved_at"),
                "object_count": len(payload.get("objects") or []),
            }
        )
    return scenes


def _scene_payload_by_id(scene_id: str) -> dict[str, Any]:
    safe = scene_id_for_path(scene_id)
    for path in _scene_paths():
        payload = _load_scene_payload(path)
        if payload["scene_id"] == safe:
            return payload
    raise KeyError(f"scene {scene_id!r} not found")


def _scene_object_payload(scene_id: str, object_id: str) -> dict[str, Any]:
    scene = _scene_payload_by_id(scene_id)
    for item in scene.get("objects") or []:
        if isinstance(item, dict) and str(item.get("object_id")) == object_id:
            return item
    raise KeyError(f"object {object_id!r} not found in scene {scene_id!r}")


def _scene_object_graph_history(scene_id: str, object_id: str) -> list[dict[str, Any]]:
    item = _scene_object_payload(scene_id, object_id)
    history = item.get("operation_graph_history")
    if not isinstance(history, list):
        return []
    return [dict(row) for row in history if isinstance(row, dict)]


def _scene_object_graph_history_item(scene_id: str, object_id: str, history_id: str) -> dict[str, Any]:
    for row in _scene_object_graph_history(scene_id, object_id):
        if str(row.get("history_id")) == history_id:
            return row
    raise KeyError(
        f"graph history {history_id!r} not found for object {object_id!r} in scene {scene_id!r}"
    )


def _scene_object_graph_history_comparison(
    scene_id: str,
    object_id: str,
    left_history_id: str,
    right_history_id: str,
) -> dict[str, Any]:
    left = _scene_object_graph_history_item(scene_id, object_id, left_history_id)
    right = _scene_object_graph_history_item(scene_id, object_id, right_history_id)
    comparison = compare_graph_history_payloads(left, right)
    return {
        "scene_id": scene_id_for_path(scene_id),
        "object_id": object_id,
        "left_history_id": left_history_id,
        "right_history_id": right_history_id,
        "resource_uri": graph_history_comparison_resource_uri(
            scene_id,
            object_id,
            left_history_id,
            right_history_id,
        ),
        "comparison": comparison,
        "followups": plan_graph_history_followup_actions(left, right),
    }


def _load_scene_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"scene document must be an object: {path}")
    scene_id = str(payload.get("scene_id") or scene_id_for_path(path))
    out = dict(payload)
    out["scene_id"] = scene_id
    out["scene_path"] = str(path)
    out["resource_uri"] = scene_resource_uri(scene_id)
    out["mcp_links"] = {"scene": out["resource_uri"]}

    objects = out.get("objects")
    normalized_objects: list[dict[str, Any]] = []
    if isinstance(objects, list):
        for item in objects:
            if not isinstance(item, dict):
                continue
            normalized_objects.append(_scene_object_with_links(item, scene_id=scene_id, scene_path=path))
    out["objects"] = normalized_objects
    return out


def _scene_object_with_links(item: dict[str, Any], *, scene_id: str, scene_path: Path) -> dict[str, Any]:
    out = dict(item)
    object_id = str(out.get("object_id") or "")
    links = dict(out.get("mcp_links") if isinstance(out.get("mcp_links"), dict) else {})
    links["scene"] = scene_resource_uri(scene_id)
    graph_payload = out.get("operation_graph")
    graph_id = ""
    if isinstance(graph_payload, dict):
        graph_id = str(graph_payload.get("graph_id") or "")
    if graph_id:
        links["graph"] = graph_resource_uri(graph_id)
    history = out.get("operation_graph_history")
    history_rows = [dict(row) for row in history if isinstance(row, dict)] if isinstance(history, list) else []
    out["operation_graph_history"] = list(
        annotate_graph_history_sequence(
            history_rows,
            scene_id=scene_id,
            scene_path=scene_path,
            object_id=object_id,
        )
    )
    out["scene_id"] = scene_id
    out["scene_path"] = str(scene_path)
    out["mcp_links"] = links
    return out


def register_tools(server: FastMCP) -> None:
    """Attach all GhostForge tools to a FastMCP server instance."""

    @server.tool(description="Return MCP server health, data root, and registered job kinds.")
    def health() -> dict[str, Any]:
        ctx = get_context()
        return {
            "status": "ok",
            "name": "ghostforge",
            "version": "0.1.0",
            "data_root": str(ctx.storage.root),
            "dispatch_jobs": ctx.config.dispatch_jobs,
            "max_workers": ctx.config.max_workers,
            "kinds": [
                descriptor.model_dump(mode="json")
                for descriptor in ctx.registry.list()
            ],
        }

    @server.tool(description="List job kinds the server can dispatch and their capabilities.")
    def list_capabilities() -> list[dict[str, Any]]:
        return [d.model_dump(mode="json") for d in get_context().registry.list()]

    @server.tool(
        description=(
            "Inspect a mesh file (OBJ, GLB, GLTF, STL, PLY, FBX where supported). "
            "Returns vertex/face counts, watertightness, bounds, and size."
        )
    )
    def mesh_info(mesh_path: str) -> dict[str, Any]:
        request = mesh_info_op.MeshInfoRequest(mesh_path=Path(mesh_path))
        info = mesh_info_op.run(request)
        return info.model_dump(mode="json")

    @server.tool(
        description=(
            "Run lightweight validation on a mesh file. Returns errors, warnings, "
            "and info issues without producing artifacts."
        )
    )
    def validate_mesh_tool(mesh_path: str) -> dict[str, Any]:
        return validate_mesh(Path(mesh_path)).model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a UV unwrap job (xatlas). Returns a job handle whose status "
            "transitions through pending -> running -> succeeded|failed. Poll "
            "with `get_job` or stream progress via `wait_for_job`."
        )
    )
    def submit_unwrap(
        input_mesh_path: str,
        output_dir: str | None = None,
        atlas_size: int = 1024,
        padding: int = 2,
        output_format: str = "glb",
        force_unwrap: bool = False,
        uv_only: bool = True,
    ) -> dict[str, Any]:
        spec = UnwrapRequest(
            input_mesh_path=Path(input_mesh_path),
            output_dir=_resolve_output_dir(output_dir),
            atlas_size=atlas_size,
            padding=padding,
            output_format=output_format,
            force_unwrap=force_unwrap,
            uv_only=uv_only,
        )
        handle = get_context().runner.submit("unwrap_uvs", spec)
        return _handle_to_dict(handle)

    @server.tool(
        description=(
            "Submit a texture generation job (procedural or AI-driven). Returns "
            "a job handle. Set `use_ai=True` to drive Stable Diffusion when the "
            "AI extras are installed."
        )
    )
    def submit_texture(
        input_mesh_path: str,
        prompt: str = "worn metal surface, detailed, high quality PBR",
        output_dir: str | None = None,
        reference_image_path: str | None = None,
        texture_size: int = 1024,
        use_ai: bool = False,
        ai_steps: int = 20,
        output_format: str = "glb",
        force_unwrap: bool = False,
    ) -> dict[str, Any]:
        spec = TextureRequest(
            input_mesh_path=Path(input_mesh_path),
            output_dir=_resolve_output_dir(output_dir),
            prompt=prompt,
            reference_image_path=Path(reference_image_path) if reference_image_path else None,
            texture_size=texture_size,
            use_ai=use_ai,
            ai_steps=ai_steps,
            output_format=output_format,
            force_unwrap=force_unwrap,
        )
        handle = get_context().runner.submit("generate_texture_set", spec)
        return _handle_to_dict(handle)

    @server.tool(description="Fetch the current state of a job by id.")
    def get_job(job_id: str) -> dict[str, Any]:
        return _handle_to_dict(get_context().jobs.get(job_id))

    @server.tool(description="List jobs filtered by status and/or kind.")
    def list_jobs(
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        handles = get_context().jobs.list(
            status=status,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        return [_handle_to_dict(h) for h in handles]

    @server.tool(
        description=(
            "Request cancellation of a running job. Returns the latest handle. "
            "Cancellation is cooperative; the job transitions to `cancelled` "
            "once the worker observes the request."
        )
    )
    def cancel_job(job_id: str) -> dict[str, Any]:
        ctx = get_context()
        ctx.jobs.request_cancel(job_id)
        return _handle_to_dict(ctx.jobs.get(job_id))

    # ------------------------------------------------------------------
    # Worker registry
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List all registered model workers. Each entry includes the "
            "static descriptor (capabilities, license, links) and the latest "
            "probe result (runnable, missing dependencies, device, VRAM)."
        )
    )
    def list_workers() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for worker in ctx.workers.all():
            descriptor = ctx.workers.describe(worker)
            probe = worker.probe()
            out.append(
                {
                    "descriptor": descriptor.model_dump(mode="json"),
                    "probe": probe.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "List capabilities and the workers that advertise them, with each "
            "worker's probe runnable flag. Useful for selecting an explicit "
            "worker before submitting a job."
        )
    )
    def list_worker_capabilities() -> dict[str, list[dict[str, Any]]]:
        ctx = get_context()
        capabilities_map: dict[str, list[dict[str, Any]]] = {}
        for capability in Capability:
            entries: list[dict[str, Any]] = []
            for worker in ctx.workers.for_capability(capability):
                probe = worker.probe()
                entries.append(
                    {
                        "name": worker.name,
                        "priority": worker.priority,
                        "is_stub": getattr(worker, "is_stub", False),
                        "license": getattr(worker, "license", None),
                        "runnable": probe.runnable,
                        "reason": probe.reason,
                    }
                )
            entries.sort(key=lambda e: e["priority"], reverse=True)
            if entries:
                capabilities_map[capability.value] = entries
        return capabilities_map

    @server.tool(description="Re-probe a specific worker and return the result.")
    def probe_worker(name: str) -> dict[str, Any]:
        return get_context().workers.probe(name).model_dump(mode="json")

    def _resolve_output_dir_for_workers(output_dir: str | None) -> Path:
        if output_dir:
            path = Path(output_dir).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path
        return get_context().storage.new_asset_dir()

    @server.tool(
        description=(
            "Submit an image-to-3D job. Auto-selects the highest-priority "
            "runnable worker that advertises image_to_3d unless `worker` is "
            "specified. Returns a job handle; poll with get_job or "
            "wait_for_job."
        )
    )
    def submit_image_to_3d(
        input_image_path: str,
        prompt: str | None = None,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = ImageTo3DRequest(
            input_image_path=Path(input_image_path),
            prompt=prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
        )
        handle = ctx.runner.submit("image_to_3d", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a hosted text-to-3D job. The default worker is tripo_api "
            "when GHOSTFORGE_TRIPO_API_KEY or TRIPO_API_KEY is set in the "
            "server environment. Smart mesh options map to Tripo H3 controls "
            "for texture/PBR, smart low-poly, quad remesh, face limits, UVs, "
            "auto-size, and geometry quality."
        )
    )
    def submit_text_to_3d(
        prompt: str,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        negative_prompt: str | None = None,
        output_format: str = "glb",
        model_version: str = "v3.1-20260211",
        texture: bool = True,
        pbr: bool = True,
        texture_quality: str = "standard",
        smart_low_poly: bool = False,
        quad: bool = False,
        face_limit: int | None = None,
        auto_size: bool = False,
        export_uv: bool = True,
        geometry_quality: str = "standard",
        generate_parts: bool = False,
        compress: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        extras: dict[str, Any] = {
            "model_version": model_version,
            "texture": texture,
            "pbr": pbr,
            "texture_quality": texture_quality,
            "smart_low_poly": smart_low_poly,
            "quad": quad,
            "auto_size": auto_size,
            "export_uv": export_uv,
            "geometry_quality": geometry_quality,
            "generate_parts": generate_parts,
        }
        if face_limit is not None:
            extras["face_limit"] = face_limit
        if compress:
            extras["compress"] = compress
        spec = TextTo3DRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
            extras=extras,
        )
        handle = ctx.runner.submit("text_to_3d", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a mesh-texturing job (Paint3D / SyncMVD style). Reads an "
            "existing mesh and a text prompt; produces a textured mesh + "
            "base-color map."
        )
    )
    def submit_texture_mesh(
        input_mesh_path: str,
        prompt: str,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        reference_image_path: str | None = None,
        texture_size: int = 1024,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = TextureMeshRequest(
            input_mesh_path=Path(input_mesh_path),
            prompt=prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            reference_image_path=Path(reference_image_path) if reference_image_path else None,
            texture_size=texture_size,
            output_format=output_format,
        )
        handle = ctx.runner.submit("texture_mesh", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a mesh-refinement job (retopology, decimation). Currently "
            "only the stub worker is registered; real workers will be wired "
            "as they're added."
        )
    )
    def submit_refine_mesh(
        input_mesh_path: str,
        target_face_count: int | None = None,
        preserve_uvs: bool = True,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = RefineMeshRequest(
            input_mesh_path=Path(input_mesh_path),
            target_face_count=target_face_count,
            preserve_uvs=preserve_uvs,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
        )
        handle = ctx.runner.submit("refine_mesh", spec)
        return handle.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    def _parse_sources(sources: list[str] | None) -> list[ConceptSource] | None:
        if not sources:
            return None
        try:
            return [ConceptSource(s) for s in sources]
        except ValueError as exc:
            raise ValueError(
                f"Unknown concept source. Valid: {[s.value for s in ConceptSource]}"
            ) from exc

    @server.tool(
        description=(
            "Return knowledge base status: backend, embedder, total concept count, "
            "and embedding dimension. Useful for diagnosing whether OpenCLIP / "
            "LanceDB are active."
        )
    )
    def kb_status() -> dict[str, Any]:
        kb = get_context().kb
        return {
            "backend": kb.backend,
            "embedder": kb.embedding_model,
            "embedding_dim": kb.embedding_dim,
            "count": kb.count(),
            "image_dir": str(kb.image_dir),
        }

    @server.tool(
        description=(
            "Ingest a local image as a knowledge base concept. License is "
            "mandatory (use 'CC0-1.0' for public domain, an SPDX id, or "
            "'project-internal' for in-house references)."
        )
    )
    def kb_ingest_local_image(
        image_path: str,
        title: str,
        license: str,
        description: str = "",
        attribution: str | None = None,
        creator: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = ingest_local_image(
            kb,
            Path(image_path),
            title=title,
            license=license,
            description=description,
            attribution=attribution,
            creator=creator,
            tags=tags,
            source_url=source_url,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Download an image URL and ingest it as a knowledge base concept. "
            "License is mandatory and must accurately describe the source's "
            "terms; refusing with 'unknown' is intentional, not a bug."
        )
    )
    def kb_ingest_url(
        url: str,
        title: str,
        license: str,
        description: str = "",
        attribution: str | None = None,
        creator: str | None = None,
        tags: list[str] | None = None,
        license_url: str | None = None,
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = ingest_url(
            kb,
            url,
            title=title,
            license=license,
            description=description,
            attribution=attribution,
            creator=creator,
            tags=tags,
            license_url=license_url,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Search Openverse and ingest the top results as concepts. "
            "license_filter defaults to permissive licenses (cc0, pdm, by, "
            "by-sa). Returns the list of ingested entries."
        )
    )
    def kb_ingest_openverse(
        query: str,
        count: int = 5,
        license_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        entries = ingest_openverse(
            kb,
            query,
            license_filter=license_filter,
            count=count,
        )
        return [e.model_dump(mode="json") for e in entries]

    @server.tool(
        description=(
            "Add a project style guide. License defaults to 'project-internal' "
            "to indicate the text is owned by the project. Style guides are "
            "embedded alongside image concepts and bias retrieval toward "
            "in-house art direction."
        )
    )
    def kb_ingest_style_guide(
        title: str,
        text: str,
        tags: list[str] | None = None,
        license: str = "project-internal",
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = kb.add_text(
            title=title,
            text=text,
            license=license,
            source=ConceptSource.style_guide,
            tags=tags,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Run a similarity search over knowledge base concepts using a text "
            "query. Cross-modal text→image retrieval is meaningful only when "
            "the OpenCLIP embedder is active; with the default hash embedder, "
            "text queries match best against style-guide entries."
        )
    )
    def kb_search_text(
        query: str,
        k: int = 5,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        results = kb.search_text(
            query,
            k=k,
            sources=_parse_sources(sources),
            tags=tags,
        )
        return [r.model_dump(mode="json") for r in results]

    @server.tool(
        description=(
            "Run a similarity search over knowledge base concepts using a "
            "reference image."
        )
    )
    def kb_search_image(
        image_path: str,
        k: int = 5,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        results = kb.search_image_path(
            Path(image_path),
            k=k,
            sources=_parse_sources(sources),
            tags=tags,
        )
        return [r.model_dump(mode="json") for r in results]

    @server.tool(description="Fetch a single knowledge base concept by id.")
    def kb_get(concept_id: str) -> dict[str, Any]:
        return get_context().kb.get(concept_id).model_dump(mode="json")

    @server.tool(description="List concepts, optionally filtered by source.")
    def kb_list(
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        entries = kb.list(
            limit=limit,
            offset=offset,
            sources=_parse_sources(sources),
        )
        return [e.model_dump(mode="json") for e in entries]

    @server.tool(
        description=(
            "Attach knowledge base concept citations to an asset manifest. "
            "Creates the manifest if absent. Each citation captures the "
            "source URL, license, attribution, and an optional usage note "
            "so downstream engines and audits can trace provenance."
        )
    )
    def kb_cite_in_manifest(
        asset_dir: str,
        concept_ids: list[str],
        note: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)
        builder = ManifestBuilder.for_dir(path)
        for concept_id in concept_ids:
            citation = ctx.kb.make_citation(concept_id, note=note)
            builder.add_concept_citation(citation)
        manifest, _ = builder.write()
        return manifest.model_dump(mode="json")

    @server.tool(
        description=(
            "Read the AssetManifest at an asset directory. Returns the full v1 "
            "manifest JSON document, including geometry, materials, LODs, "
            "validation summary, license, and engine targets."
        )
    )
    def read_asset_manifest(asset_dir: str) -> dict[str, Any]:
        path = Path(asset_dir)
        if not manifest_exists(path):
            raise FileNotFoundError(f"No asset manifest at {path}")
        return read_manifest(path).model_dump(mode="json")

    @server.tool(
        description=(
            "Annotate an existing AssetManifest with license info, engine "
            "targets, tags, and free-form description. Creates the manifest "
            "if it does not yet exist. Useful for agents preparing assets for "
            "Unity or Unreal handoff."
        )
    )
    def update_asset_manifest(
        asset_dir: str,
        name: str | None = None,
        description: str | None = None,
        license_spdx: str | None = None,
        license_holder: str | None = None,
        license_attribution: str | None = None,
        license_source_url: str | None = None,
        engine_targets: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)

        builder = ManifestBuilder.for_dir(path)
        builder.with_name(name).with_description(description)

        if any(
            v is not None
            for v in (license_spdx, license_holder, license_attribution, license_source_url)
        ):
            builder.with_license(
                LicenseSpec(
                    spdx=license_spdx,
                    holder=license_holder,
                    attribution=license_attribution,
                    source_url=license_source_url,
                )
            )

        for engine_name in engine_targets or []:
            try:
                builder.add_engine_target(EngineTargetSpec(engine=EngineTarget(engine_name)))
            except ValueError as exc:
                raise ValueError(
                    f"Unknown engine target '{engine_name}'. "
                    f"Valid options: {[e.value for e in EngineTarget]}"
                ) from exc

        for tag in tags or []:
            builder.add_tag(tag)

        manifest, _ = builder.write()
        return manifest.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Game-readiness audit
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List available audit presets. Each preset bundles thresholds "
            "for an engine: 'default' is engine-agnostic, 'unity' adds "
            "lightmap-UV / 65k-vert / power-of-two texture rules, 'unreal' "
            "raises poly ceilings for Nanite-friendly assets and uses "
            "/Game-style content paths."
        )
    )
    def list_audit_presets() -> list[dict[str, Any]]:
        return [preset.model_dump(mode="json") for preset in list_audit_presets_op()]

    @server.tool(
        description=(
            "Run the game-readiness audit on an asset directory. Returns the "
            "structured AuditReport including per-rule status and any "
            "issues. By default the report is also written back into "
            "manifest.validation and appended to "
            "manifest.custom['audit_history'] so engine adapters and other "
            "consumers see the verdict. Set persist=False for a dry-run "
            "audit. The optional Khronos glTF Validator runs when "
            "gltf-validator is on PATH or pointed to by "
            "GHOSTFORGE_GLTF_VALIDATOR."
        )
    )
    def audit_asset(
        asset_dir: str,
        preset: str = "default",
        run_gltf_validator: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        report = audit_asset_op(
            Path(asset_dir),
            preset=preset,
            run_gltf_validator=run_gltf_validator,
            persist=persist,
        )
        return report.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a game-readiness audit as a background job. Useful when "
            "the glTF Validator is enabled and assets are large; otherwise "
            "audit_asset blocks on the same logic and returns immediately."
        )
    )
    def submit_audit(
        asset_dir: str,
        preset: str = "default",
        run_gltf_validator: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = AuditAssetRequest(
            asset_dir=Path(asset_dir),
            preset=preset,
            run_gltf_validator=run_gltf_validator,
            persist=persist,
        )
        handle = ctx.runner.submit("audit_asset", spec)
        return _handle_to_dict(handle)

    # ------------------------------------------------------------------
    # Engine handoff
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List configured engine adapters (Unity-MCP-Ghost, Unreal-MCP-"
            "Ghost). Each entry shows the adapter name, the engine target it "
            "fulfils, the active transport, the configured import tool, and "
            "the latest probe result. Prefer create_engine_export_bridge for "
            "offline handoff packages; direct send tools require an explicitly "
            "configured transport."
        )
    )
    def list_engine_adapters() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for adapter in ctx.engines.all():
            cfg = adapter.get_config()
            probe = adapter.probe()
            out.append(
                {
                    "name": adapter.name,
                    "engine_target": adapter.engine_target.value,
                    "config": cfg.model_dump(mode="json"),
                    "probe": probe.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "Configure or re-configure an engine adapter at runtime. "
            "Choose transport='stdio' (with command list) for spawning a "
            "Unity/Unreal MCP server locally, or transport='http' (with url) "
            "to attach to an already-running engine MCP. Setting "
            "transport='none' resets the adapter to its unconfigured state. "
            "Returns the updated config + probe."
        )
    )
    def configure_engine_adapter(
        name: str,
        transport: str,
        command: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        import_tool: str = "import_asset",
        import_args_extra: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(name)
        if transport not in {"stdio", "http", "none"}:
            raise ValueError(
                f"transport must be one of 'stdio', 'http', 'none' (got {transport!r})"
            )
        cfg = EngineConfig(
            name=name,
            transport=transport,  # type: ignore[arg-type]
            command=list(command or []),
            cwd=cwd,
            env=dict(env or {}),
            url=url,
            headers=dict(headers or {}),
            import_tool=import_tool,
            import_args_extra=dict(import_args_extra or {}),
            timeout_seconds=timeout_seconds,
            project_path=project_path,
        )
        adapter.configure(cfg)
        return {
            "name": adapter.name,
            "config": adapter.get_config().model_dump(mode="json"),
            "probe": adapter.probe().model_dump(mode="json"),
        }

    @server.tool(
        description=(
            "Hand a finished asset to Unity-MCP-Ghost. Validates the asset "
            "manifest, runs the game-readiness audit (Unity preset by "
            "default), checks engine_targets includes 'unity' (use force=True "
            "to override both engine_target and audit error gating), and "
            "either calls the configured import tool over MCP or, with "
            "dry_run=True, records a planned handoff in the manifest without "
            "contacting Unity. Returns the handoff result including the "
            "audit summary and engine response."
        )
    )
    def send_to_unity(
        asset_dir: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        return _run_send(
            engine="unity",
            asset_dir=asset_dir,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=extra_args,
            audit=audit,
            audit_preset=audit_preset,
        )

    @server.tool(
        description=(
            "Optional direct handoff to a configured Unreal-MCP-Ghost "
            "transport. For the default product workflow, use "
            "create_engine_export_bridge and import that JSON from the Unreal "
            "side. Default target paths follow Unreal's /Game/ convention."
        )
    )
    def send_to_unreal(
        asset_dir: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        return _run_send(
            engine="unreal",
            asset_dir=asset_dir,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=extra_args,
            audit=audit,
            audit_preset=audit_preset,
        )

    @server.tool(
        description=(
            "Create an offline export bridge package for Unity-MCP-Ghost or "
            "Unreal-MCP-Ghost. This validates the Ghost-Forge asset manifest "
            "and writes ghostforge_bridge_<engine>.json, but it does not call "
            "or control the game editor directly."
        )
    )
    def create_engine_export_bridge(
        asset_dir: str,
        target_engine: str,
        target_path: str | None = None,
        bridge_dir: str | None = None,
        recommended_tool: str = "import_asset",
        notes: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.export_bridge import create_export_bridge_package

        package, path = create_export_bridge_package(
            asset_dir,
            target_engine=target_engine,
            target_path=target_path,
            bridge_dir=bridge_dir,
            recommended_tool=recommended_tool,
            notes=notes,
        )
        return {
            "package": package.model_dump(mode="json"),
            "package_path": str(path),
            "direct_engine_call": False,
        }

    @server.tool(
        description=(
            "Submit an engine handoff as a background job. Useful when the "
            "engine MCP may take a while (large meshes, project-wide reimport "
            "passes). Poll the returned handle with get_job or wait_for_job."
        )
    )
    def submit_send_to_engine(
        asset_dir: str,
        engine: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = SendToEngineRequest(
            asset_dir=Path(asset_dir),
            engine=engine,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=dict(extra_args or {}),
            audit=audit,
            audit_preset=audit_preset,
        )
        handle = ctx.runner.submit("send_to_engine", spec)
        return _handle_to_dict(handle)

    def _run_send(
        *,
        engine: str,
        asset_dir: str,
        target_path: str | None,
        dry_run: bool,
        force: bool,
        extra_args: dict[str, Any] | None,
        audit: bool,
        audit_preset: str | None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(engine)
        try:
            result = adapter.send_asset(
                Path(asset_dir),
                target_path=target_path,
                dry_run=dry_run,
                force=force,
                extra_args=dict(extra_args or {}) or None,
                audit=audit,
                audit_preset=audit_preset,
            )
        except EngineHandoffError:
            raise
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # GPU + scheduler tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "Report current GPU detection state and scheduler lane status. "
            "Returns the detection backend (torch/pynvml/none), per-GPU "
            "VRAM and in-flight job counts, and the configured CPU "
            "concurrency budget."
        )
    )
    def list_gpus() -> dict[str, Any]:
        ctx = get_context()
        if ctx.scheduler is None:
            from ghostforge_core.gpu import detect_gpus

            status = detect_gpus(force=True)
            return {
                "scheduler_enabled": False,
                "backend": status.backend,
                "cpu_only": status.cpu_only,
                "gpus": [g.model_dump(mode="json") for g in status.gpus],
                "notes": list(status.notes),
            }
        snapshot = ctx.scheduler.status()
        snapshot["scheduler_enabled"] = True
        return snapshot

    @server.tool(
        description=(
            "Force a fresh GPU re-detection (bypasses the short cache). "
            "Useful after driver reinstalls, container restarts, or eGPU "
            "hot-plug. Returns the new status."
        )
    )
    def refresh_gpus() -> dict[str, Any]:
        ctx = get_context()
        if ctx.scheduler is None:
            from ghostforge_core.gpu import detect_gpus, reset_cache_for_tests

            reset_cache_for_tests()
            status = detect_gpus(force=True)
            return {
                "scheduler_enabled": False,
                "backend": status.backend,
                "cpu_only": status.cpu_only,
                "gpus": [g.model_dump(mode="json") for g in status.gpus],
            }
        ctx.scheduler.refresh(force=True)
        return ctx.scheduler.status()

    @server.tool(
        description=(
            "Return per-worker resource declarations: CUDA requirement, "
            "min/recommended VRAM, max concurrent runs per GPU, CPU "
            "fallback availability, and the model artifacts each worker "
            "depends on. Drives `download_model` decisions."
        )
    )
    def get_worker_resources() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for worker in ctx.workers.all():
            descriptor = ctx.workers.describe(worker)
            out.append(
                {
                    "name": descriptor.name,
                    "is_stub": descriptor.is_stub,
                    "capabilities": [c.value for c in descriptor.capabilities],
                    "resources": descriptor.resources.model_dump(mode="json"),
                    "required_models": list(descriptor.required_models),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Model registry tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List every registered model artifact and its current cache "
            "status (cached/missing files, integrity)."
        )
    )
    def list_models() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for artifact in ctx.models.list():
            status = ctx.models.status(artifact.model_id)
            out.append(
                {
                    "artifact": artifact.model_dump(mode="json"),
                    "status": status.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "Cache state for a single model. `model_id` matches the id "
            "exposed by `get_worker_resources` and `list_models`."
        )
    )
    def model_status(model_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            return ctx.models.status(model_id).model_dump(mode="json")
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")

    @server.tool(
        description=(
            "List the model artifacts a worker depends on, with cache "
            "status for each. Use to decide whether `download_model` is "
            "needed before scheduling."
        )
    )
    def list_required_models(worker_name: str) -> list[dict[str, Any]]:
        ctx = get_context()
        worker = ctx.workers.get(worker_name)
        descriptor = ctx.workers.describe(worker)
        out: list[dict[str, Any]] = []
        for model_id in descriptor.required_models:
            try:
                status = ctx.models.status(model_id)
                out.append(status.model_dump(mode="json"))
            except ModelNotFound:
                out.append({"model_id": model_id, "registered": False})
        return out

    @server.tool(
        description=(
            "Download a registered model into the cache. Idempotent — "
            "skipped when fully cached and verified, unless `force=True`. "
            "Pass `token` for HuggingFace gated repos. Returns the new "
            "cache status."
        )
    )
    def download_model(
        model_id: str,
        force: bool = False,
        token: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        try:
            status = ctx.models.download(model_id, force=force, token=token)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        except ModelDownloadError as exc:
            raise RuntimeError(str(exc))
        return status.model_dump(mode="json")

    @server.tool(
        description=(
            "Recompute sha256 for every file of a cached model and update "
            "its integrity timestamp. Use after a suspect download or "
            "when surfacing a 'verified' badge in the UI."
        )
    )
    def verify_model(model_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            status = ctx.models.verify(model_id)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        except ModelDownloadError as exc:
            raise RuntimeError(str(exc))
        return status.model_dump(mode="json")

    @server.tool(
        description=(
            "Delete cached files for a single model (or all models when "
            "`model_id=None`). Returns the count of cleared model dirs."
        )
    )
    def clear_model_cache(model_id: str | None = None) -> dict[str, Any]:
        ctx = get_context()
        try:
            removed = ctx.models.clear(model_id)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        return {"cleared": removed, "model_id": model_id}

    # ------------------------------------------------------------------
    # Benchmark tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "Run a worker through repeated invocations and return wall-time "
            "stats. `spec` is the worker request payload (e.g. a "
            "TextTo3DRequest dict). Persists a JSON report under "
            "data/benchmarks/."
        )
    )
    def run_benchmark(
        worker_name: str,
        capability: str,
        spec: dict[str, Any],
        runs: int = 1,
        warmup_runs: int = 0,
        note: str | None = None,
        benchmark_id: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        request = BenchmarkRequest(
            benchmark_id=benchmark_id or make_benchmark_id(prefix=worker_name),
            worker_name=worker_name,
            capability=Capability(capability),
            spec=spec,
            runs=runs,
            warmup_runs=warmup_runs,
            note=note,
        )
        result = run_benchmark_op(
            request,
            registry=ctx.workers,
            store=ctx.benchmarks,
            storage=ctx.storage,
        )
        return result.model_dump(mode="json")

    @server.tool(
        description=(
            "List recent benchmark reports (newest first). `limit` caps "
            "the number returned."
        )
    )
    def list_benchmarks(limit: int = 50) -> list[dict[str, Any]]:
        ctx = get_context()
        return [r.model_dump(mode="json") for r in ctx.benchmarks.list(limit=limit)]

    @server.tool(
        description="Fetch a single benchmark report by id."
    )
    def get_benchmark(benchmark_id: str) -> dict[str, Any]:
        ctx = get_context()
        result = ctx.benchmarks.load(benchmark_id)
        if result is None:
            raise ValueError(f"benchmark not found: {benchmark_id}")
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Worker session tools (Prompt 9)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List loaded worker sessions (cached model checkpoints / pipelines) "
            "with their idle times. Use to decide whether to free GPU memory."
        )
    )
    def list_worker_sessions() -> list[dict[str, Any]]:
        return get_session_registry().status()

    @server.tool(
        description=(
            "Free a loaded worker session by name (e.g. "
            "'diffusers_texture.txt2img'), or all of them when `name` is "
            "null. Set `force=True` to evict even when the session is in "
            "use. Returns the number of sessions actually freed."
        )
    )
    def free_worker_session(
        name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        freed = get_session_registry().free(name, force=force)
        return {"freed": freed, "name": name, "force": force}

    @server.tool(
        description=(
            "Free worker sessions that have been idle longer than "
            "`idle_for_seconds`. When omitted, each session uses its own "
            "configured idle timeout. Returns the number of sessions "
            "evicted."
        )
    )
    def free_idle_worker_sessions(
        idle_for_seconds: float | None = None,
    ) -> dict[str, Any]:
        freed = get_session_registry().free_idle(idle_for_seconds=idle_for_seconds)
        return {"freed": freed, "idle_for_seconds": idle_for_seconds}

    # ------------------------------------------------------------------
    # Vertical slice tools (Prompt 7)
    # ------------------------------------------------------------------

    def _coerce_brief(payload: dict[str, Any]) -> GameBrief:
        if "license" in payload and isinstance(payload["license"], dict):
            payload = {**payload, "license": LicenseSpec(**payload["license"])}
        return GameBrief(**payload)

    def _coerce_assets(items: list[dict[str, Any]]) -> list[AssetSpec]:
        out: list[AssetSpec] = []
        for entry in items:
            data = dict(entry)
            if "license" in data and isinstance(data["license"], dict):
                data["license"] = LicenseSpec(**data["license"])
            if "kind" in data and isinstance(data["kind"], str):
                data["kind"] = AssetKind(data["kind"])
            if "strategy" in data and isinstance(data["strategy"], str):
                data["strategy"] = GenerationStrategy(data["strategy"])
            if "target_engine" in data and isinstance(data["target_engine"], str):
                data["target_engine"] = EngineTarget(data["target_engine"])
            if "reference_image_path" in data and isinstance(data["reference_image_path"], str):
                data["reference_image_path"] = Path(data["reference_image_path"])
            if "input_mesh_path" in data and isinstance(data["input_mesh_path"], str):
                data["input_mesh_path"] = Path(data["input_mesh_path"])
            out.append(AssetSpec(**data))
        return out

    @server.tool(
        description=(
            "Create and persist a vertical slice plan. `brief` describes the "
            "game and target engine; `assets` is a list of asset specs (each "
            "with at least `asset_id` and `description`). Returns the saved "
            "plan including its slice_id."
        )
    )
    def create_vertical_slice(
        brief: dict[str, Any],
        assets: list[dict[str, Any]],
        slice_id: str | None = None,
        fail_fast: bool = False,
        skip_audit: bool = False,
        skip_handoff: bool = False,
    ) -> dict[str, Any]:
        ctx = get_context()
        plan = plan_vertical_slice(
            store=ctx.slices,
            brief=_coerce_brief(brief),
            assets=_coerce_assets(assets),
            slice_id=slice_id,
            fail_fast=fail_fast,
            skip_audit=skip_audit,
            skip_handoff=skip_handoff,
        )
        return plan.model_dump(mode="json")

    @server.tool(
        description=(
            "Replace the asset list on an existing slice plan. Useful for "
            "agent-driven plan refinement (LLM proposes assets, operator "
            "tweaks before executing)."
        )
    )
    def update_vertical_slice_assets(
        slice_id: str,
        assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ctx = get_context()
        plan = update_plan_assets(ctx.slices, slice_id, _coerce_assets(assets))
        return plan.model_dump(mode="json")

    @server.tool(
        description=(
            "Return a slice's plan and latest run state. Use this to inspect "
            "per-asset stage progress and outputs."
        )
    )
    def get_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        run = ctx.slices.load_run(slice_id)
        return {
            "plan": plan.model_dump(mode="json"),
            "run": run.model_dump(mode="json") if run is not None else None,
        }

    @server.tool(
        description=(
            "List all known slices with their current status, asset count, "
            "and target engine."
        )
    )
    def list_vertical_slices() -> list[dict[str, Any]]:
        ctx = get_context()
        return [s.model_dump(mode="json") for s in ctx.slices.list_summaries()]

    @server.tool(
        description=(
            "Delete a slice's plan and run history (does not delete generated "
            "asset directories outside data/slices/)."
        )
    )
    def delete_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            ctx.slices.delete(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        return {"deleted": True, "slice_id": slice_id}

    @server.tool(
        description=(
            "Run a planned slice synchronously. For each asset, walks the "
            "pipeline (kb_search -> generate -> unwrap -> texture -> cite -> "
            "annotate -> audit -> handoff) and persists per-stage state. "
            "Suitable for short slices; use `submit_vertical_slice` for "
            "long-running ones so the client doesn't block."
        )
    )
    def execute_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        run = execute_slice_op(
            plan,
            store=ctx.slices,
            kb=ctx.kb,
            engines=ctx.engines,
        )
        return run.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a slice run as a background job. Returns a job handle; "
            "poll with `get_job` or stream progress via `wait_for_job`."
        )
    )
    def submit_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        spec = ExecuteVerticalSliceRequest(slice_id=slice_id)
        handle = ctx.runner.submit("execute_vertical_slice", spec)
        return _handle_to_dict(handle)

    @server.tool(
        description=(
            "Invoke an arbitrary tool on a configured engine MCP server. Use "
            "for engine actions outside the GhostForge surface — placement, "
            "screenshots, scene control. Requires the engine adapter to be "
            "configured (see `configure_engine_adapter`)."
        )
    )
    def call_engine_tool(
        engine: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(engine)
        return adapter.call_tool(tool_name, dict(arguments or {}))

    # ------------------------------------------------------------------
    # Retarget: cross-engine linting + planner (P12)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List the engine profiles GhostForge can retarget assets for. "
            "Each profile describes axis convention, units, naming, and "
            "lightmap requirements."
        )
    )
    def list_engine_profiles() -> list[dict[str, Any]]:
        from ghostforge_core.retarget import list_profiles

        return [p.model_dump(mode="json") for p in list_profiles()]

    @server.tool(
        description=(
            "Run the cross-engine audit against an asset for the given target. "
            "Returns the full AuditReport with retarget rule output included. "
            "Use the report's `issues` to drive a manual fix or call "
            "`generate_retarget_graph` to auto-plan one."
        )
    )
    def lint_for_engine(
        asset_dir: str,
        target_engine: str,
        run_gltf_validator: bool = False,
    ) -> dict[str, Any]:
        from ghostforge_core.audit import audit_asset
        from ghostforge_core.retarget.presets import (
            retarget_rules_for_preset,
            unity_retarget_preset,
            unreal_retarget_preset,
        )

        if target_engine not in {"unity", "unreal"}:
            raise ValueError("target_engine must be 'unity' or 'unreal'")
        factory = unity_retarget_preset if target_engine == "unity" else unreal_retarget_preset
        report = audit_asset(
            Path(asset_dir),
            preset=factory(),
            rules=retarget_rules_for_preset(target_engine),
            run_gltf_validator=run_gltf_validator,
            persist=False,
        )
        return report.model_dump(mode="json")

    @server.tool(
        description=(
            "Auto-plan a retarget edit graph for the given asset and engine. "
            "Reads the manifest, runs the cross-engine audit, and emits an "
            "EditGraph populated with `retarget_axis` / `retarget_units` / "
            "`retarget_pivot_for_engine` / `retarget_apply_naming` nodes "
            "addressing each diagnostic in stable order. Set `persist_graph=True` "
            "to save the graph for later evaluation via `evaluate_edit_graph`."
        )
    )
    def generate_retarget_graph(
        asset_dir: str,
        target_engine: str,
        base_name: str | None = None,
        graph_id: str | None = None,
        graph_name: str | None = None,
        output_path: str | None = None,
        persist_graph: bool = False,
    ) -> dict[str, Any]:
        from ghostforge_core.retarget import plan_retarget_graph_for_asset

        if target_engine not in {"unity", "unreal"}:
            raise ValueError("target_engine must be 'unity' or 'unreal'")
        graph, report = plan_retarget_graph_for_asset(
            asset_dir,
            target_engine=target_engine,
            base_name=base_name,
            graph_id=graph_id,
            graph_name=graph_name,
            output_path=output_path,
        )
        if persist_graph:
            ctx = get_context()
            ctx.graphs.save(graph)
        return {
            "graph": graph.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------
    # Authoring: operations + edit graphs (P11)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List every authoring operation the core can apply to a mesh "
            "(transform, decimate, smooth, AI source generation, worker "
            "retopo/texturing, etc). Returns descriptors with kind, label, "
            "parameter schema, source/worker type, capability status, and "
            "matching workers."
        )
    )
    def list_operations() -> list[dict[str, Any]]:
        return _operation_descriptors_payload()

    @server.resource(
        "ghostforge://operations",
        name="operation_descriptors",
        description=(
            "Inspectable Ghost Forge authoring operation descriptors with "
            "source/worker type and capability status."
        ),
        mime_type="application/json",
    )
    def operation_descriptors_resource() -> dict[str, Any]:
        return {"operations": _operation_descriptors_payload()}

    @server.tool(
        description=(
            "List Ghost Forge CAD command descriptors inspired by Plasticity recon. "
            "Each descriptor exposes parameter schema, option panel schema, selection "
            "contract, topology effects, tolerance policy, failure modes, undo, "
            "fixtures, and Qt/MCP reachability."
        )
    )
    def list_cad_commands(
        family: str | None = None,
        status: str | None = None,
        include_relationships: bool = True,
    ) -> dict[str, Any]:
        commands = _cad_command_payloads()
        if family:
            commands = [command for command in commands if command.get("family") == family]
        if status:
            commands = [command for command in commands if command.get("status") == status]
        if not include_relationships:
            commands = [
                command
                for command in commands
                if not (command.get("alias_of") or command.get("option_of") or command.get("contextual_mode_of"))
            ]
        return {
            "summary": _cad_registry_summary(commands),
            "commands": commands,
            "notes": [
                "CAD command descriptors are richer than authoring operations because modeling readiness requires parameters, selection, topology, tolerance, failure, undo, fixture, and automation contracts.",
                "Relationship entries preserve Plasticity static-asset uncertainty as aliases, options, or contextual modes instead of claiming unproven standalone commands.",
            ],
        }

    @server.tool(
        description=(
            "Inspect one Ghost Forge CAD command descriptor, including the "
            "parameter/option schema and automation readiness gates."
        )
    )
    def get_cad_command(command_id: str) -> dict[str, Any]:
        return _cad_command_payload(command_id)

    @server.tool(
        description=(
            "Run native Ghost Forge CAD preflight for a command descriptor. "
            "This validates selection context, active object/plane requirements, "
            "parameter values, relationship ownership, and implementation gates "
            "without calling Plasticity."
        )
    )
    def preflight_cad_command(
        command_id: str,
        selection_items: list[dict[str, Any]] | None = None,
        active_object_id: str | None = None,
        active_plane_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        option_panel_state: dict[str, Any] | None = None,
        preview_requested: bool = True,
    ) -> dict[str, Any]:
        return _cad_preflight_payload(
            command_id,
            selection_items,
            active_object_id,
            active_plane_id,
            parameters,
            option_panel_state,
            preview_requested,
        )

    @server.tool(
        description=(
            "Validate an AI-authored Ghost Forge CAD operation graph without "
            "executing geometry or mutating project state. Returns descriptor, "
            "preflight, topology-reference, and replay-order diagnostics that "
            "an agent can use to repair the graph."
        )
    )
    def validate_cad_operation_graph(graph: dict[str, Any]) -> dict[str, Any]:
        return _cad_operation_graph_validation_payload(graph)

    @server.tool(
        description=(
            "Execute a validated Ghost Forge CAD operation graph through the "
            "controlled native mesh-backed prototype. Writes an output mesh and "
            "asset_manifest.json under `output_dir`; planned CAD-kernel nodes "
            "remain blocked with diagnostics."
        )
    )
    def execute_cad_operation_graph(
        graph: dict[str, Any],
        output_dir: str,
        input_mesh_path: str | None = None,
        output_format: str = "glb",
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        return _cad_operation_graph_execution_payload(
            graph,
            output_dir,
            input_mesh_path,
            output_format,
            asset_id,
        )

    @server.resource(
        "ghostforge://cad/commands",
        name="cad_command_descriptors",
        description="Ghost Forge CAD command descriptors derived from Plasticity recon and current mesh tools.",
        mime_type="application/json",
    )
    def cad_command_descriptors_resource() -> dict[str, Any]:
        commands = _cad_command_payloads()
        return {"summary": _cad_registry_summary(commands), "commands": commands}

    @server.resource(
        "ghostforge://cad/commands/{command_id}",
        name="cad_command_descriptor",
        description="One Ghost Forge CAD command descriptor with parameter, selection, topology, tolerance, failure, undo, fixture, and automation contracts.",
        mime_type="application/json",
    )
    def cad_command_descriptor_resource(command_id: str) -> dict[str, Any]:
        return _cad_command_payload(command_id)

    @server.resource(
        "ghostforge://cad/execution-contract",
        name="cad_execution_contract",
        description="Native Ghost Forge CAD command execution/preflight contract with no Plasticity runtime dependency.",
        mime_type="application/json",
    )
    def cad_execution_contract_resource() -> dict[str, Any]:
        return _cad_execution_contract_payload()

    @server.resource(
        "ghostforge://cad/operation-graph-contract",
        name="cad_operation_graph_contract",
        description="Native Ghost Forge CAD operation graph validation contract for AI/tool-authored construction graphs.",
        mime_type="application/json",
    )
    def cad_operation_graph_contract_resource() -> dict[str, Any]:
        return _cad_operation_graph_contract_payload()

    @server.tool(
        description=(
            "List deterministic CAD fixture geometry used to verify command behavior. "
            "Fixtures expose primitive recipes, named topology, selection sets, "
            "tolerance notes, and the Plasticity-inspired modeling behaviors they test."
        )
    )
    def list_cad_fixtures(geometry_kind: str | None = None) -> dict[str, Any]:
        fixtures = _cad_fixture_payloads()
        expectations = _cad_fixture_expectation_payloads()
        if geometry_kind:
            fixtures = [fixture for fixture in fixtures if fixture.get("geometry_kind") == geometry_kind]
        return {
            "summary": _cad_fixture_summary(fixtures, expectations),
            "fixtures": fixtures,
            "notes": [
                "Fixture topology names are the contract surface for topology naming, selection rules, and regression probes.",
                "Future live Plasticity automation should promote each planned expectation from contract_defined to observed_with_evidence.",
            ],
        }

    @server.tool(
        description="Inspect one CAD fixture, including named topology and reusable selection sets."
    )
    def get_cad_fixture(fixture_id: str) -> dict[str, Any]:
        return _cad_fixture_payload(fixture_id)

    @server.tool(
        description=(
            "List expected CAD command behavior on fixture geometry, including "
            "parameters, topology deltas, known failures, and verification status."
        )
    )
    def list_cad_command_fixture_expectations(command_id: str | None = None) -> dict[str, Any]:
        fixtures = _cad_fixture_payloads()
        expectations = _cad_fixture_expectation_payloads(command_id)
        return {
            "summary": _cad_fixture_summary(fixtures, expectations),
            "expectations": expectations,
        }

    @server.tool(
        description=(
            "List native Ghost Forge CAD fixture behavior cases. These go deeper "
            "than fixture expectations by defining selected topology, exact "
            "parameters/options, preflight requirements, topology lineage, "
            "failure probes, tolerances, and automation evidence."
        )
    )
    def list_cad_behavior_cases(
        command_id: str | None = None,
        result_state: str | None = None,
    ) -> dict[str, Any]:
        return _cad_behavior_matrix_payload(command_id, result_state)

    @server.tool(
        description="Inspect one native Ghost Forge CAD fixture behavior case."
    )
    def get_cad_behavior_case(case_id: str) -> dict[str, Any]:
        return _cad_behavior_case_payload(case_id)

    @server.resource(
        "ghostforge://cad/fixtures",
        name="cad_fixtures",
        description="Deterministic CAD fixtures with named topology and selection sets.",
        mime_type="application/json",
    )
    def cad_fixtures_resource() -> dict[str, Any]:
        fixtures = _cad_fixture_payloads()
        expectations = _cad_fixture_expectation_payloads()
        return {"summary": _cad_fixture_summary(fixtures, expectations), "fixtures": fixtures}

    @server.resource(
        "ghostforge://cad/fixtures/{fixture_id}",
        name="cad_fixture",
        description="One deterministic CAD fixture with named topology and reusable selections.",
        mime_type="application/json",
    )
    def cad_fixture_resource(fixture_id: str) -> dict[str, Any]:
        return _cad_fixture_payload(fixture_id)

    @server.resource(
        "ghostforge://cad/command-fixtures",
        name="cad_command_fixture_expectations",
        description="Expected command behavior on CAD fixtures, including topology deltas and failure cases.",
        mime_type="application/json",
    )
    def cad_command_fixture_expectations_resource() -> dict[str, Any]:
        fixtures = _cad_fixture_payloads()
        expectations = _cad_fixture_expectation_payloads()
        return {"summary": _cad_fixture_summary(fixtures, expectations), "expectations": expectations}

    @server.resource(
        "ghostforge://cad/behavior-cases",
        name="cad_behavior_cases",
        description="Native Ghost Forge CAD fixture behavior cases with topology lineage, failure probes, tolerances, and automation evidence.",
        mime_type="application/json",
    )
    def cad_behavior_cases_resource() -> dict[str, Any]:
        return _cad_behavior_matrix_payload()

    @server.resource(
        "ghostforge://cad/behavior-cases/{case_id}",
        name="cad_behavior_case",
        description="One native Ghost Forge CAD fixture behavior case.",
        mime_type="application/json",
    )
    def cad_behavior_case_resource(case_id: str) -> dict[str, Any]:
        return _cad_behavior_case_payload(case_id)

    @server.tool(
        description=(
            "List the Plasticity-to-Ghost-Forge CAD probe matrix. The matrix "
            "tracks the remaining evidence needed for parameter panels, option "
            "panels, fixture behavior, selection rules, topology naming, failures, "
            "tolerances, import/export settings, static assets, and automation routes."
        )
    )
    def list_cad_probe_matrix() -> dict[str, Any]:
        return _cad_probe_matrix_payload()

    @server.tool(
        description=(
            "Inspect the probe plan for one CAD command, including Plasticity "
            "automation route and Ghost Forge implementation implications."
        )
    )
    def get_cad_command_probe_plan(command_id: str) -> dict[str, Any]:
        return _cad_command_probe_plan_payload(command_id)

    @server.resource(
        "ghostforge://cad/probe-matrix",
        name="cad_probe_matrix",
        description="Plasticity-to-Ghost-Forge CAD probe matrix for parity evidence collection.",
        mime_type="application/json",
    )
    def cad_probe_matrix_resource() -> dict[str, Any]:
        return _cad_probe_matrix_payload()

    @server.resource(
        "ghostforge://cad/probe-matrix/{command_id}",
        name="cad_command_probe_plan",
        description="One CAD command probe plan with automation route and evidence targets.",
        mime_type="application/json",
    )
    def cad_command_probe_plan_resource(command_id: str) -> dict[str, Any]:
        return _cad_command_probe_plan_payload(command_id)

    @server.tool(
        description=(
            "List native Ghost Forge CAD logic patterns distilled from Plasticity "
            "recon. This is Ghost Forge-owned design logic, not a runtime "
            "dependency on Plasticity or PlasticityMCP."
        )
    )
    def list_cad_logic_blueprint(command_id: str | None = None) -> dict[str, Any]:
        return _cad_logic_blueprint_payload(command_id)

    @server.tool(
        description="Inspect one native Ghost Forge CAD logic pattern."
    )
    def get_cad_logic_pattern(pattern_id: str) -> dict[str, Any]:
        return _cad_logic_pattern_payload(pattern_id)

    @server.tool(
        description=(
            "List native Ghost Forge CAD import/export format contracts. "
            "These expose format-specific option schemas, backend gates, "
            "topology policies, tolerances, failures, fixture tests, and "
            "workspace-safe automation requirements."
        )
    )
    def list_cad_interop_formats(
        direction: str | None = None,
        family: str | None = None,
    ) -> dict[str, Any]:
        return _cad_interop_formats_payload(direction, family)

    @server.tool(
        description="Inspect one native Ghost Forge CAD import/export format contract."
    )
    def get_cad_interop_format(format_id: str) -> dict[str, Any]:
        return _cad_interop_format_payload(format_id)

    @server.tool(
        description=(
            "List Ghost Forge CAD development tasks generated from PlasticityMCP "
            "recon artifacts. The queue joins command index rows, inferred "
            "parameter templates, observation status, probe packages, automation "
            "routes, file-safety gates, and static-asset mapping blockers."
        )
    )
    def list_cad_development_queue(
        kb_root: str | None = None,
        implementation_track: str | None = None,
        has_blocker: str | None = None,
    ) -> dict[str, Any]:
        return _cad_development_queue_payload(kb_root, implementation_track, has_blocker)

    @server.tool(
        description="Inspect one Ghost Forge CAD development task derived from Plasticity recon evidence."
    )
    def get_cad_development_task(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_development_task_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List declarative Ghost Forge CAD automation routes derived from the "
            "development queue. Each route exposes safety gates, live-execution "
            "eligibility, required evidence, reset verification, workspace write "
            "scope, and native Ghost Forge consumer."
        )
    )
    def list_cad_automation_runbook(
        kb_root: str | None = None,
        route_kind: str | None = None,
        missing_gate: str | None = None,
    ) -> dict[str, Any]:
        return _cad_automation_runbook_payload(kb_root, route_kind, missing_gate)

    @server.tool(
        description="Inspect one Ghost Forge CAD automation route by command id."
    )
    def get_cad_automation_route(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_automation_route_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List Ghost Forge CAD schema drafts generated from PlasticityMCP "
            "parameter templates. Drafts expose parameter candidates, option-panel "
            "groups, UI control hints, validation rules, and promotion blockers."
        )
    )
    def list_cad_schema_drafts(
        kb_root: str | None = None,
        implementation_track: str | None = None,
        has_blocker: str | None = None,
    ) -> dict[str, Any]:
        return _cad_schema_drafts_payload(kb_root, implementation_track, has_blocker)

    @server.tool(
        description="Inspect one Ghost Forge CAD schema draft and descriptor-ready ParameterSpec candidates."
    )
    def get_cad_schema_draft(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_schema_draft_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List CAD schema promotion candidates. This separates inferred "
            "Plasticity templates from observed parameter/option-panel evidence "
            "and reports exactly which gates block promotion into native Ghost "
            "Forge descriptors."
        )
    )
    def list_cad_schema_promotions(
        kb_root: str | None = None,
        promotion_status: str | None = None,
        has_blocker: str | None = None,
    ) -> dict[str, Any]:
        return _cad_schema_promotion_payload(kb_root, promotion_status, has_blocker)

    @server.tool(
        description="Inspect one CAD schema promotion candidate and descriptor-ready observed ParameterSpec entries."
    )
    def get_cad_schema_promotion(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_schema_promotion_candidate_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List CAD evidence packet plans for live Plasticity probes. Each "
            "packet defines the required parameter, option-panel, fixture, "
            "topology, failure/tolerance, file-artifact, static-owner, and reset "
            "evidence needed before Ghost Forge can promote or implement behavior."
        )
    )
    def list_cad_evidence_packets(
        kb_root: str | None = None,
        packet_kind: str | None = None,
        readiness: str | None = None,
    ) -> dict[str, Any]:
        return _cad_evidence_packets_payload(kb_root, packet_kind, readiness)

    @server.tool(
        description="Inspect one CAD evidence packet plan by command id."
    )
    def get_cad_evidence_packet(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_evidence_packet_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List CAD live-probe batches. Batches order evidence packets into "
            "ready capture, probe-package generation, static-owner resolution, "
            "safety-gate repair, and post-capture promotion work."
        )
    )
    def list_cad_probe_batches(
        kb_root: str | None = None,
        batch_kind: str | None = None,
        packet_kind: str | None = None,
    ) -> dict[str, Any]:
        return _cad_probe_batches_payload(kb_root, batch_kind, packet_kind)

    @server.tool(
        description="Inspect one CAD live-probe batch by id, for example ready_live_capture:file_interop_packet."
    )
    def get_cad_probe_batch(batch_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_probe_batch_payload(batch_id, kb_root)

    @server.tool(
        description=(
            "List concrete CAD live-probe session plans. Sessions expand a "
            "batch/evidence packet into ordered guarded steps for baseline, "
            "command panel, behavior/artifact capture, reset, and observation recording."
        )
    )
    def list_cad_live_probe_sessions(
        kb_root: str | None = None,
        session_mode: str | None = None,
        packet_kind: str | None = None,
    ) -> dict[str, Any]:
        return _cad_live_probe_sessions_payload(kb_root, session_mode, packet_kind)

    @server.tool(
        description="Inspect one concrete CAD live-probe session by command id."
    )
    def get_cad_live_probe_session(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_live_probe_session_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List CAD live-observation record templates. These are the receiving "
            "records that completed Plasticity captures must fill before Ghost "
            "Forge can promote schemas, behavior, interop, or static-owner evidence."
        )
    )
    def list_cad_observation_templates(
        kb_root: str | None = None,
        session_mode: str | None = None,
    ) -> dict[str, Any]:
        return _cad_observation_templates_payload(kb_root, session_mode)

    @server.tool(
        description="Inspect one empty CAD observation record template by command id."
    )
    def get_cad_observation_template(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_observation_template_payload(command_id, kb_root)

    @server.tool(
        description=(
            "Validate a completed CAD live-observation record against the current "
            "session/evidence packet. Reports exactly whether the capture can feed "
            "schema promotion, fixture behavior parity, interop contracts, or "
            "static-owner classification."
        )
    )
    def validate_cad_observation_record(
        observation_record: dict[str, Any],
        kb_root: str | None = None,
    ) -> dict[str, Any]:
        return _cad_observation_validation_payload(observation_record, kb_root)

    @server.tool(
        description=(
            "List validated CAD observation ledger entries loaded from the "
            "knowledge base. These are completed Plasticity captures that have "
            "been checked against Ghost Forge evidence/session contracts."
        )
    )
    def list_cad_observation_ledger(
        kb_root: str | None = None,
        status: str | None = None,
        promotion_target: str | None = None,
    ) -> dict[str, Any]:
        return _cad_observation_ledger_payload(kb_root, status, promotion_target)

    @server.tool(
        description="Inspect validated CAD observation ledger entries for one command id."
    )
    def get_cad_observation_ledger_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_observation_ledger_command_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List native Ghost Forge CAD implementation handoffs generated from "
            "validated observation-ledger entries. Handoffs translate accepted "
            "Plasticity evidence into descriptor, Qt/MCP schema, handler-test, "
            "interop, robustness, or static-owner work."
        )
    )
    def list_cad_native_handoffs(
        kb_root: str | None = None,
        handoff_status: str | None = None,
        target: str | None = None,
    ) -> dict[str, Any]:
        return _cad_native_handoffs_payload(kb_root, handoff_status, target)

    @server.tool(
        description="Inspect native Ghost Forge CAD implementation handoffs for one command id."
    )
    def get_cad_native_handoff_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_native_handoff_command_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List CAD capture campaign items. Campaigns join live-probe sessions, "
            "observation ledger state, and native handoffs to tell the next recon "
            "pass what to capture, recapture, unblock, or apply in Ghost Forge."
        )
    )
    def list_cad_capture_campaign(
        kb_root: str | None = None,
        status: str | None = None,
        packet_kind: str | None = None,
    ) -> dict[str, Any]:
        return _cad_capture_campaign_payload(kb_root, status, packet_kind)

    @server.tool(
        description="Inspect one CAD capture campaign item by command id."
    )
    def get_cad_capture_campaign_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_capture_campaign_command_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List native Ghost Forge CAD selection-state contracts. Returns "
            "selection modes, topology id policies, state-transition contracts, "
            "failure modes, and automation evidence for selection/snapping commands."
        )
    )
    def list_cad_selection_contracts(
        kb_root: str | None = None,
        operation_kind: str | None = None,
    ) -> dict[str, Any]:
        return _cad_selection_contracts_payload(kb_root, operation_kind)

    @server.tool(
        description="Inspect one native Ghost Forge CAD selection-state command contract."
    )
    def get_cad_selection_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_selection_command_payload(command_id, kb_root)

    @server.tool(
        description=(
            "List native Ghost Forge CAD robustness contracts. These join command "
            "descriptors, fixture behavior, file interop, and selection state into "
            "topology naming policies, lineage requirements, tolerance contracts, "
            "failure contracts, and promotion blockers."
        )
    )
    def list_cad_robustness_contracts(
        kb_root: str | None = None,
        subject_type: str | None = None,
        has_failure: str | None = None,
        has_topology_policy: str | None = None,
    ) -> dict[str, Any]:
        return _cad_robustness_contracts_payload(
            kb_root,
            subject_type,
            has_failure,
            has_topology_policy,
        )

    @server.tool(
        description="Inspect one native Ghost Forge CAD robustness contract by contract id or subject id."
    )
    def get_cad_robustness_contract(contract_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_robustness_contract_payload(contract_id, kb_root)

    @server.resource(
        "ghostforge://cad/logic-blueprint",
        name="cad_logic_blueprint",
        description="Native Ghost Forge CAD logic blueprint distilled from recon evidence.",
        mime_type="application/json",
    )
    def cad_logic_blueprint_resource() -> dict[str, Any]:
        return _cad_logic_blueprint_payload()

    @server.resource(
        "ghostforge://cad/logic-blueprint/{pattern_id}",
        name="cad_logic_pattern",
        description="One native Ghost Forge CAD logic pattern.",
        mime_type="application/json",
    )
    def cad_logic_pattern_resource(pattern_id: str) -> dict[str, Any]:
        return _cad_logic_pattern_payload(pattern_id)

    @server.resource(
        "ghostforge://cad/interop-formats",
        name="cad_interop_formats",
        description="Native Ghost Forge CAD import/export format contracts with option schemas and verification gates.",
        mime_type="application/json",
    )
    def cad_interop_formats_resource() -> dict[str, Any]:
        return _cad_interop_formats_payload()

    @server.resource(
        "ghostforge://cad/interop-formats/{format_id}",
        name="cad_interop_format",
        description="One native Ghost Forge CAD import/export format contract.",
        mime_type="application/json",
    )
    def cad_interop_format_resource(format_id: str) -> dict[str, Any]:
        return _cad_interop_format_payload(format_id)

    @server.resource(
        "ghostforge://cad/development-queue",
        name="cad_development_queue",
        description="Ghost Forge CAD implementation queue derived from Plasticity recon evidence.",
        mime_type="application/json",
    )
    def cad_development_queue_resource() -> dict[str, Any]:
        return _cad_development_queue_payload()

    @server.resource(
        "ghostforge://cad/development-queue/{command_id}",
        name="cad_development_task",
        description="One Ghost Forge CAD implementation task derived from Plasticity recon evidence.",
        mime_type="application/json",
    )
    def cad_development_task_resource(command_id: str) -> dict[str, Any]:
        return _cad_development_task_payload(command_id)

    @server.resource(
        "ghostforge://cad/automation-runbook",
        name="cad_automation_runbook",
        description="Declarative Ghost Forge CAD automation routes with safety gates and evidence requirements.",
        mime_type="application/json",
    )
    def cad_automation_runbook_resource() -> dict[str, Any]:
        return _cad_automation_runbook_payload()

    @server.resource(
        "ghostforge://cad/automation-runbook/{command_id}",
        name="cad_automation_route",
        description="One declarative Ghost Forge CAD automation route.",
        mime_type="application/json",
    )
    def cad_automation_route_resource(command_id: str) -> dict[str, Any]:
        return _cad_automation_route_payload(command_id)

    @server.resource(
        "ghostforge://cad/schema-drafts",
        name="cad_schema_drafts",
        description="Ghost Forge CAD schema drafts derived from PlasticityMCP parameter templates.",
        mime_type="application/json",
    )
    def cad_schema_drafts_resource() -> dict[str, Any]:
        return _cad_schema_drafts_payload()

    @server.resource(
        "ghostforge://cad/schema-drafts/{command_id}",
        name="cad_schema_draft",
        description="One Ghost Forge CAD schema draft with parameter and option-panel candidates.",
        mime_type="application/json",
    )
    def cad_schema_draft_resource(command_id: str) -> dict[str, Any]:
        return _cad_schema_draft_payload(command_id)

    @server.resource(
        "ghostforge://cad/schema-promotions",
        name="cad_schema_promotions",
        description="CAD schema promotion candidates with observed-evidence gates and blockers.",
        mime_type="application/json",
    )
    def cad_schema_promotions_resource() -> dict[str, Any]:
        return _cad_schema_promotion_payload()

    @server.resource(
        "ghostforge://cad/schema-promotions/{command_id}",
        name="cad_schema_promotion",
        description="One CAD schema promotion candidate with gates, blockers, and observed ParameterSpec entries.",
        mime_type="application/json",
    )
    def cad_schema_promotion_resource(command_id: str) -> dict[str, Any]:
        return _cad_schema_promotion_candidate_payload(command_id)

    @server.resource(
        "ghostforge://cad/evidence-packets",
        name="cad_evidence_packets",
        description="CAD live-probe evidence packet plans for schema, behavior, topology, file, and reset capture.",
        mime_type="application/json",
    )
    def cad_evidence_packets_resource() -> dict[str, Any]:
        return _cad_evidence_packets_payload()

    @server.resource(
        "ghostforge://cad/evidence-packets/{command_id}",
        name="cad_evidence_packet",
        description="One CAD evidence packet plan for a live Plasticity probe.",
        mime_type="application/json",
    )
    def cad_evidence_packet_resource(command_id: str) -> dict[str, Any]:
        return _cad_evidence_packet_payload(command_id)

    @server.resource(
        "ghostforge://cad/probe-batches",
        name="cad_probe_batches",
        description="Ordered CAD live-probe batches derived from evidence packet readiness.",
        mime_type="application/json",
    )
    def cad_probe_batches_resource() -> dict[str, Any]:
        return _cad_probe_batches_payload()

    @server.resource(
        "ghostforge://cad/probe-batches/{batch_id}",
        name="cad_probe_batch",
        description="One ordered CAD live-probe batch.",
        mime_type="application/json",
    )
    def cad_probe_batch_resource(batch_id: str) -> dict[str, Any]:
        return _cad_probe_batch_payload(batch_id)

    @server.resource(
        "ghostforge://cad/live-probe-sessions",
        name="cad_live_probe_sessions",
        description="Concrete plan-only CAD live-probe sessions derived from probe batches and evidence packets.",
        mime_type="application/json",
    )
    def cad_live_probe_sessions_resource() -> dict[str, Any]:
        return _cad_live_probe_sessions_payload()

    @server.resource(
        "ghostforge://cad/live-probe-sessions/{command_id}",
        name="cad_live_probe_session",
        description="One concrete CAD live-probe session plan.",
        mime_type="application/json",
    )
    def cad_live_probe_session_resource(command_id: str) -> dict[str, Any]:
        return _cad_live_probe_session_payload(command_id)

    @server.resource(
        "ghostforge://cad/observation-templates",
        name="cad_observation_templates",
        description="Empty CAD live-observation records for validated Plasticity evidence capture.",
        mime_type="application/json",
    )
    def cad_observation_templates_resource() -> dict[str, Any]:
        return _cad_observation_templates_payload()

    @server.resource(
        "ghostforge://cad/observation-templates/{command_id}",
        name="cad_observation_template",
        description="One empty CAD live-observation record template.",
        mime_type="application/json",
    )
    def cad_observation_template_resource(command_id: str) -> dict[str, Any]:
        return _cad_observation_template_payload(command_id)

    @server.resource(
        "ghostforge://cad/observation-ledger",
        name="cad_observation_ledger",
        description="Validated CAD live-observation ledger loaded from knowledge-base capture records.",
        mime_type="application/json",
    )
    def cad_observation_ledger_resource() -> dict[str, Any]:
        return _cad_observation_ledger_payload()

    @server.resource(
        "ghostforge://cad/observation-ledger/{command_id}",
        name="cad_observation_ledger_command",
        description="Validated CAD live-observation ledger entries for one command.",
        mime_type="application/json",
    )
    def cad_observation_ledger_command_resource(command_id: str) -> dict[str, Any]:
        return _cad_observation_ledger_command_payload(command_id)

    @server.resource(
        "ghostforge://cad/native-handoffs",
        name="cad_native_handoffs",
        description="Native Ghost Forge CAD implementation handoffs from validated observation evidence.",
        mime_type="application/json",
    )
    def cad_native_handoffs_resource() -> dict[str, Any]:
        return _cad_native_handoffs_payload()

    @server.resource(
        "ghostforge://cad/native-handoffs/{command_id}",
        name="cad_native_handoff_command",
        description="Native Ghost Forge CAD implementation handoffs for one command.",
        mime_type="application/json",
    )
    def cad_native_handoff_command_resource(command_id: str) -> dict[str, Any]:
        return _cad_native_handoff_command_payload(command_id)

    @server.resource(
        "ghostforge://cad/capture-campaign",
        name="cad_capture_campaign",
        description="Plasticity recon capture campaign joined with ledger and Ghost Forge handoff readiness.",
        mime_type="application/json",
    )
    def cad_capture_campaign_resource() -> dict[str, Any]:
        return _cad_capture_campaign_payload()

    @server.resource(
        "ghostforge://cad/capture-campaign/{command_id}",
        name="cad_capture_campaign_command",
        description="One Plasticity recon capture campaign item.",
        mime_type="application/json",
    )
    def cad_capture_campaign_command_resource(command_id: str) -> dict[str, Any]:
        return _cad_capture_campaign_command_payload(command_id)

    @server.resource(
        "ghostforge://cad/selection-contracts",
        name="cad_selection_contracts",
        description="Native Ghost Forge CAD selection modes and command state-transition contracts.",
        mime_type="application/json",
    )
    def cad_selection_contracts_resource() -> dict[str, Any]:
        return _cad_selection_contracts_payload()

    @server.resource(
        "ghostforge://cad/selection-contracts/{command_id}",
        name="cad_selection_command",
        description="One native Ghost Forge CAD selection-state command contract.",
        mime_type="application/json",
    )
    def cad_selection_command_resource(command_id: str) -> dict[str, Any]:
        return _cad_selection_command_payload(command_id)

    @server.resource(
        "ghostforge://cad/robustness-contracts",
        name="cad_robustness_contracts",
        description="Native Ghost Forge CAD topology, tolerance, failure, and lineage contracts.",
        mime_type="application/json",
    )
    def cad_robustness_contracts_resource() -> dict[str, Any]:
        return _cad_robustness_contracts_payload()

    @server.resource(
        "ghostforge://cad/robustness-contracts/{contract_id}",
        name="cad_robustness_contract",
        description="One native Ghost Forge CAD robustness contract with expanded policies, tolerances, and failures.",
        mime_type="application/json",
    )
    def cad_robustness_contract_resource(contract_id: str) -> dict[str, Any]:
        return _cad_robustness_contract_payload(contract_id)

    @server.tool(
        description=(
            "Load current PlasticityMCP recon coverage from generated knowledge-base "
            "artifacts. This exposes every command readiness row, automation route, "
            "parameter-observation gap, static mapping status, and file-format family "
            "that the Plasticity recon has recorded."
        )
    )
    def list_plasticity_recon_coverage(
        kb_root: str | None = None,
        readiness_bucket: str | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        return _plasticity_recon_coverage_payload(kb_root, readiness_bucket, priority)

    @server.tool(
        description="Inspect one command row from the current PlasticityMCP recon coverage."
    )
    def get_plasticity_recon_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _plasticity_recon_command_payload(command_id, kb_root)

    @server.resource(
        "ghostforge://cad/plasticity-recon-coverage",
        name="plasticity_recon_coverage",
        description="Current PlasticityMCP command readiness and automation-route coverage loaded from recon artifacts.",
        mime_type="application/json",
    )
    def plasticity_recon_coverage_resource() -> dict[str, Any]:
        return _plasticity_recon_coverage_payload()

    @server.resource(
        "ghostforge://cad/plasticity-recon-coverage/{command_id}",
        name="plasticity_recon_command",
        description="One PlasticityMCP command readiness row with parameter gaps and automation route.",
        mime_type="application/json",
    )
    def plasticity_recon_command_resource(command_id: str) -> dict[str, Any]:
        return _plasticity_recon_command_payload(command_id)

    @server.tool(
        description=(
            "Load PlasticityMCP parameter observation evidence, separating inferred "
            "templates, ledger status, latest probe-session requirements, observed "
            "schema counts, evidence screenshots, and reset verification."
        )
    )
    def list_plasticity_observation_evidence(
        kb_root: str | None = None,
        schema_status: str | None = None,
        probe_kind: str | None = None,
    ) -> dict[str, Any]:
        return _plasticity_observation_evidence_payload(kb_root, schema_status, probe_kind)

    @server.tool(
        description=(
            "Inspect one Plasticity command's parameter-observation ledger status "
            "and inferred command template."
        )
    )
    def get_plasticity_observation_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _plasticity_observation_command_payload(command_id, kb_root)

    @server.resource(
        "ghostforge://cad/plasticity-observation-evidence",
        name="plasticity_observation_evidence",
        description="PlasticityMCP parameter observation ledger and inferred schema templates.",
        mime_type="application/json",
    )
    def plasticity_observation_evidence_resource() -> dict[str, Any]:
        return _plasticity_observation_evidence_payload()

    @server.resource(
        "ghostforge://cad/plasticity-observation-evidence/{command_id}",
        name="plasticity_observation_command",
        description="One Plasticity command's observation status and inferred parameter template.",
        mime_type="application/json",
    )
    def plasticity_observation_command_resource(command_id: str) -> dict[str, Any]:
        return _plasticity_observation_command_payload(command_id)

    @server.tool(
        description=(
            "Load PlasticityMCP ready-to-run parameter probe packages. Packages "
            "are the executable evidence units for live probing: fixture setup, "
            "required screenshots, validation checks, reset steps, and observation slots."
        )
    )
    def list_plasticity_probe_packages(
        kb_root: str | None = None,
        requires_file_evidence: bool | None = None,
    ) -> dict[str, Any]:
        return _plasticity_probe_packages_payload(kb_root, requires_file_evidence)

    @server.tool(
        description="Inspect one PlasticityMCP parameter probe package by command id."
    )
    def get_plasticity_probe_package(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _plasticity_probe_package_payload(command_id, kb_root)

    @server.resource(
        "ghostforge://cad/plasticity-probe-packages",
        name="plasticity_probe_packages",
        description="PlasticityMCP ready-to-run parameter probe packages.",
        mime_type="application/json",
    )
    def plasticity_probe_packages_resource() -> dict[str, Any]:
        return _plasticity_probe_packages_payload()

    @server.resource(
        "ghostforge://cad/plasticity-probe-packages/{command_id}",
        name="plasticity_probe_package",
        description="One PlasticityMCP parameter probe package.",
        mime_type="application/json",
    )
    def plasticity_probe_package_resource(command_id: str) -> dict[str, Any]:
        return _plasticity_probe_package_payload(command_id)

    @server.tool(
        description=(
            "Join Ghost Forge CAD descriptors, fixture expectations, probe plans, "
            "Plasticity readiness rows, and observation evidence into one parity "
            "readiness report with blockers and recommended next actions."
        )
    )
    def list_cad_parity_report(
        kb_root: str | None = None,
        recommended_action: str | None = None,
        has_blocker: str | None = None,
    ) -> dict[str, Any]:
        return _cad_parity_report_payload(kb_root, recommended_action, has_blocker)

    @server.tool(
        description="Inspect one joined Ghost Forge / Plasticity CAD parity readiness row."
    )
    def get_cad_parity_command(command_id: str, kb_root: str | None = None) -> dict[str, Any]:
        return _cad_parity_command_payload(command_id, kb_root)

    @server.resource(
        "ghostforge://cad/parity-report",
        name="cad_parity_report",
        description="Joined CAD parity readiness report with blockers and next actions.",
        mime_type="application/json",
    )
    def cad_parity_report_resource() -> dict[str, Any]:
        return _cad_parity_report_payload()

    @server.resource(
        "ghostforge://cad/parity-report/{command_id}",
        name="cad_parity_command",
        description="One joined CAD parity readiness row.",
        mime_type="application/json",
    )
    def cad_parity_command_resource(command_id: str) -> dict[str, Any]:
        return _cad_parity_command_payload(command_id)

    # ------------------------------------------------------------------
    # Workflow prompts
    # ------------------------------------------------------------------

    @server.prompt(
        description=(
            "Plan a manifest-backed text-to-3D prop workflow using authoring "
            "graphs, worker capability checks, audit, and offline engine bridge packaging."
        )
    )
    def generate_engine_ready_prop(
        asset_prompt: str,
        target_engine: str = "unity",
        art_direction: str = "",
        target_path: str = "",
    ) -> str:
        return (
            "Generate an engine-ready Ghost Forge prop while keeping Ghost Forge the source of truth.\n\n"
            f"Asset prompt: {asset_prompt}\n"
            f"Target engine: {target_engine}\n"
            f"Art direction: {art_direction or 'use project style and practical game-ready defaults'}\n"
            f"Target engine path: {target_path or 'choose a conventional GhostForge asset path'}\n\n"
            "Workflow:\n"
            "1. Call `list_worker_capabilities` and `list_operations`; confirm a text-to-3D worker is runnable or honestly report stub/missing status.\n"
            "2. Create an edit graph with `create_edit_graph`; append `generate_text_to_3d` as the first enabled node using the prompt above and a suitable `parameter_presets` entry from `list_operations`.\n"
            "3. Append cleanup/process nodes when available, such as `worker_refine_mesh`, `worker_texture_mesh`, `recenter`, `normalize_scale`, `recompute_normals`, `bake_lightmap_uv`, or `bake_convex_collision`, using descriptor schemas and presets instead of guessed parameters.\n"
            "4. Run `submit_evaluate_edit_graph`, then `wait_for_job`; inspect `ghostforge://graphs/{graph_id}` and `ghostforge://graphs/{graph_id}/evaluation` before continuing.\n"
            "5. Run `audit_asset` with the target-engine preset and persist the audit into the manifest.\n"
            "6. If audit errors remain, update the graph with corrective nodes and evaluate again; keep all changes in the graph history.\n"
            "7. Create `ghostforge_bridge_<engine>.json` with `create_engine_export_bridge`; do not call Unity/Unreal directly unless a configured adapter is explicitly requested.\n"
            "8. Report the graph id, asset directory, manifest path, audit status, bridge package path, and any remaining blocking diagnostics."
        )

    @server.prompt(
        description=(
            "Plan a Unity repair loop for an existing generated asset using scene graph-history resources, retarget diagnostics, audit, and bridge packaging."
        )
    )
    def repair_generated_mesh_for_unity(
        asset_dir: str = "",
        graph_id: str = "",
        scene_id: str = "",
        object_id: str = "",
        history_id: str = "",
    ) -> str:
        scene_hint = (
            f"`ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/{history_id}`"
            if scene_id and object_id and history_id
            else "`ghostforge://scenes` and the relevant scene/object graph-history resource"
        )
        return (
            "Repair a generated mesh for Unity while preserving Ghost Forge provenance and graph intent.\n\n"
            f"Asset directory: {asset_dir or 'inspect the selected graph history or manifest to resolve this'}\n"
            f"Graph id: {graph_id or 'resolve from scene history or manifest provenance'}\n"
            f"Scene/history resource: {scene_hint}\n\n"
            "Workflow:\n"
            "1. Inspect the scene/history resource and `ghostforge://graphs/{graph_id}` when available; identify the latest output mesh, manifest, audit history, and bridge history.\n"
            "2. Run `audit_asset` with `preset='unity'` and `persist=True`; treat audit errors as blockers unless the user explicitly asks for a forced handoff.\n"
            "3. If axis, unit, pivot, naming, collision, UV, or texture diagnostics appear, call `generate_retarget_graph` with `target_engine='unity'` and `persist_graph=True`, or append equivalent graph nodes manually using `list_operations` descriptor schemas.\n"
            "4. Re-evaluate with `submit_evaluate_edit_graph` and `wait_for_job`; inspect the graph evaluation resource and saved scene graph-history rows after completion.\n"
            "5. Re-run the Unity audit and compare remaining/new/resolved diagnostics before packaging.\n"
            "6. Create the offline Unity bridge package with `create_engine_export_bridge(target_engine='unity')`; do not bypass the manifest or embed provider secrets.\n"
            "7. Report the corrected graph id, manifest validation status, resolved/remaining diagnostics, and bridge package path."
        )

    @server.prompt(
        description=(
            "Plan an Unreal static-mesh package workflow using audits, retargeting, manifests, and offline bridge packages."
        )
    )
    def prepare_unreal_static_mesh_package(
        asset_dir: str,
        target_path: str = "/Game/GhostForge",
        package_goal: str = "static mesh import",
    ) -> str:
        return (
            "Prepare an Unreal static-mesh package from a Ghost Forge asset without making the game editor authoritative.\n\n"
            f"Asset directory: {asset_dir}\n"
            f"Unreal target path: {target_path}\n"
            f"Package goal: {package_goal}\n\n"
            "Workflow:\n"
            "1. Inspect the asset manifest and graph/scene resources linked from its provenance; confirm the primary mesh, license/provenance, engine targets, and latest audit status.\n"
            "2. Run `audit_asset` with `preset='unreal'` and persist the result. Use `run_gltf_validator=True` when glTF validation is available.\n"
            "3. If Unreal conventions fail, call `generate_retarget_graph(target_engine='unreal', persist_graph=True)` or append corrective graph nodes; then submit and wait for graph evaluation.\n"
            "4. Re-run the Unreal audit and summarize resolved, remaining, and newly introduced diagnostics.\n"
            "5. Create `ghostforge_bridge_unreal.json` with `create_engine_export_bridge(target_engine='unreal', target_path=...)`.\n"
            "6. Prefer the offline bridge package for Unreal-MCP-Ghost import. Use `send_to_unreal` only when an adapter is configured and the user explicitly wants direct handoff.\n"
            "7. Return the manifest path, bridge package path, recommended MCP server/tool, target path, and any remaining blockers."
        )

    @server.tool(
        description=(
            "Create a new edit graph. The graph captures a non-destructive "
            "stack of operations layered onto a base asset. Returns the "
            "graph_id you can use with the other graph tools."
        )
    )
    def create_edit_graph(
        name: str = "",
        description: str = "",
        asset_id: str | None = None,
        base_asset_path: str | None = None,
        output_path: str | None = None,
        graph_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import EditGraph

        ctx = get_context()
        gid = graph_id or ctx.graphs.make_id()
        graph = EditGraph(
            graph_id=gid,
            name=name,
            description=description,
            asset_id=asset_id,
            base_asset_path=base_asset_path,
            output_path=output_path,
        )
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(description="List every persisted edit graph (graph metadata only).")
    def list_edit_graphs() -> list[dict[str, Any]]:
        ctx = get_context()
        return [g.model_dump(mode="json") for g in ctx.graphs.list()]

    @server.resource(
        "ghostforge://graphs",
        name="edit_graphs",
        description="Inspectable list of persisted Ghost Forge edit graphs.",
        mime_type="application/json",
    )
    def edit_graphs_resource() -> dict[str, Any]:
        return {"graphs": list_edit_graphs()}

    @server.tool(description="Fetch one edit graph plus its last evaluation report (if any).")
    def get_edit_graph(graph_id: str) -> dict[str, Any]:
        return _graph_with_evaluation_payload(graph_id)

    @server.resource(
        "ghostforge://graphs/{graph_id}",
        name="edit_graph",
        description="Inspectable edit graph resource with its last evaluation report.",
        mime_type="application/json",
    )
    def edit_graph_resource(graph_id: str) -> dict[str, Any]:
        return _graph_with_evaluation_payload(graph_id)

    @server.resource(
        "ghostforge://graphs/{graph_id}/evaluation",
        name="edit_graph_evaluation",
        description="Last evaluation report for a persisted edit graph.",
        mime_type="application/json",
    )
    def edit_graph_evaluation_resource(graph_id: str) -> dict[str, Any]:
        ctx = get_context()
        evaluation = ctx.graphs.load_evaluation(graph_id)
        return {
            "graph_id": graph_id,
            "evaluation": None if evaluation is None else evaluation.model_dump(mode="json"),
        }

    @server.resource(
        "ghostforge://scenes",
        name="scene_documents",
        description="Inspectable Qt scene documents saved under the Ghost Forge project scenes directory.",
        mime_type="application/json",
    )
    def scene_documents_resource() -> dict[str, Any]:
        return {"scenes": _scene_index_payload()}

    @server.resource(
        "ghostforge://scenes/{scene_id}",
        name="scene_document",
        description="Inspectable Ghost Forge scene document with graph links and history rows.",
        mime_type="application/json",
    )
    def scene_document_resource(scene_id: str) -> dict[str, Any]:
        return _scene_payload_by_id(scene_id)

    @server.resource(
        "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history",
        name="scene_object_graph_history",
        description="Graph result history rows for one scene object.",
        mime_type="application/json",
    )
    def scene_object_graph_history_resource(scene_id: str, object_id: str) -> dict[str, Any]:
        return {
            "scene_id": scene_id,
            "object_id": object_id,
            "history": _scene_object_graph_history(scene_id, object_id),
        }

    @server.resource(
        "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/{history_id}",
        name="scene_object_graph_history_item",
        description="One stable graph-history row for a scene object.",
        mime_type="application/json",
    )
    def scene_object_graph_history_item_resource(
        scene_id: str,
        object_id: str,
        history_id: str,
    ) -> dict[str, Any]:
        return _scene_object_graph_history_item(scene_id, object_id, history_id)

    @server.resource(
        "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/{left_history_id}/compare/{right_history_id}",
        name="scene_object_graph_history_comparison",
        description="Structured comparison between two graph-history rows for one scene object.",
        mime_type="application/json",
    )
    def scene_object_graph_history_comparison_resource(
        scene_id: str,
        object_id: str,
        left_history_id: str,
        right_history_id: str,
    ) -> dict[str, Any]:
        return _scene_object_graph_history_comparison(
            scene_id,
            object_id,
            left_history_id,
            right_history_id,
        )

    @server.tool(
        description=(
            "Compare two saved graph-history rows for one Qt scene object. "
            "Returns changed status/audit/output fields, path/resource deltas, "
            "audit issue additions/removals, and retarget diagnostic list changes."
        )
    )
    def compare_scene_graph_history(
        scene_id: str,
        object_id: str,
        left_history_id: str,
        right_history_id: str,
    ) -> dict[str, Any]:
        return _scene_object_graph_history_comparison(
            scene_id,
            object_id,
            left_history_id,
            right_history_id,
        )

    @server.tool(
        description=(
            "Plan follow-up actions from two saved graph-history rows. "
            "Returns append_graph_node repair suggestions for retarget deltas "
            "and submit_audit task suggestions for validation regressions."
        )
    )
    def plan_scene_graph_history_followups(
        scene_id: str,
        object_id: str,
        left_history_id: str,
        right_history_id: str,
        base_name: str | None = None,
    ) -> dict[str, Any]:
        left = _scene_object_graph_history_item(scene_id, object_id, left_history_id)
        right = _scene_object_graph_history_item(scene_id, object_id, right_history_id)
        return {
            "scene_id": scene_id_for_path(scene_id),
            "object_id": object_id,
            "left_history_id": left_history_id,
            "right_history_id": right_history_id,
            "resource_uri": graph_history_comparison_resource_uri(
                scene_id,
                object_id,
                left_history_id,
                right_history_id,
            ),
            "followups": plan_graph_history_followup_actions(
                left,
                right,
                base_name=base_name,
            ),
        }

    @server.tool(description="Delete an edit graph and its evaluation report.")
    def delete_edit_graph(graph_id: str) -> dict[str, Any]:
        ctx = get_context()
        ctx.graphs.delete(graph_id)
        return {"deleted": graph_id}

    @server.tool(
        description=(
            "Append an operation node to the end of an edit graph. Use "
            "`list_operations` to discover valid `kind` values and their "
            "parameter schema."
        )
    )
    def append_graph_node(
        graph_id: str,
        kind: str,
        params: dict[str, Any] | None = None,
        label: str = "",
        enabled: bool = True,
        notes: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import OperationNode

        ctx = get_context()
        if not ctx.operations.has(kind):
            raise ValueError(f"unknown operation kind {kind!r}")
        graph = ctx.graphs.load(graph_id)
        nid = node_id or f"node-{len(graph.nodes) + 1:03d}"
        node = OperationNode(
            id=nid,
            kind=kind,
            label=label,
            enabled=enabled,
            params=dict(params or {}),
            notes=notes,
        )
        graph = graph.with_nodes(list(graph.nodes) + [node])
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Update an existing node's params, label, enabled flag, notes, or "
            "kind. Only the keys you supply are changed."
        )
    )
    def update_graph_node(
        graph_id: str,
        node_id: str,
        kind: str | None = None,
        params: dict[str, Any] | None = None,
        label: str | None = None,
        enabled: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        nodes = list(graph.nodes)
        idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
        if idx is None:
            raise KeyError(f"node {node_id!r} not in graph {graph_id!r}")
        update: dict[str, Any] = {}
        if kind is not None:
            if not ctx.operations.has(kind):
                raise ValueError(f"unknown operation kind {kind!r}")
            update["kind"] = kind
        if params is not None:
            update["params"] = dict(params)
        if label is not None:
            update["label"] = label
        if enabled is not None:
            update["enabled"] = enabled
        if notes is not None:
            update["notes"] = notes
        nodes[idx] = nodes[idx].model_copy(update=update)
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(description="Remove a node from an edit graph.")
    def remove_graph_node(graph_id: str, node_id: str) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        nodes = [n for n in graph.nodes if n.id != node_id]
        if len(nodes) == len(graph.nodes):
            raise KeyError(f"node {node_id!r} not in graph {graph_id!r}")
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Reorder graph nodes. `order` must contain every existing node id "
            "exactly once, in the new desired order."
        )
    )
    def reorder_graph_nodes(graph_id: str, order: list[str]) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        by_id = {n.id: n for n in graph.nodes}
        if set(order) != set(by_id) or len(order) != len(by_id):
            raise ValueError("order must contain every existing node id exactly once")
        nodes = [by_id[i] for i in order]
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Evaluate an edit graph end-to-end: load the base asset, apply "
            "every enabled node in order, write the result to `output_path` "
            "(defaults to the graph's stored output_path), and persist the "
            "per-step evaluation report. Use `fail_fast=True` to abort on "
            "the first failed node."
        )
    )
    def evaluate_edit_graph(
        graph_id: str,
        input_path: str | None = None,
        output_path: str | None = None,
        output_format: str = "glb",
        fail_fast: bool = False,
        manifest_dir: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import evaluate_graph as evaluate_op
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        ctx = get_context()
        graph = _graph_with_overrides(
            ctx.graphs.load(graph_id),
            input_path=input_path,
            output_path=output_path,
        )
        ctx.graphs.save(graph)
        result, _ = evaluate_op(
            graph,
            registry=ctx.operations,
            input_path=None,
            output_path=None,
            output_format=output_format,
            fail_fast=fail_fast,
        )
        ctx.graphs.save_evaluation(result)
        payload = result.model_dump(mode="json")
        payload["graph"] = graph.model_dump(mode="json")
        side_effects = (result.metadata or {}).get("side_effects") or []
        if manifest_dir and side_effects:
            try:
                manifest = apply_side_effects_to_manifest(
                    manifest_dir, side_effects, asset_id=asset_id
                )
                if manifest is not None:
                    payload["manifest"] = manifest.model_dump(mode="json")
            except Exception as exc:
                payload["manifest_error"] = str(exc)
        return payload

    @server.tool(
        description=(
            "Submit an edit-graph evaluation job. Use this for long-running "
            "graphs that invoke AI workers; poll with `get_job`, stream with "
            "`wait_for_job`, then inspect `ghostforge://graphs/{graph_id}/evaluation`."
        )
    )
    def submit_evaluate_edit_graph(
        graph_id: str,
        input_path: str | None = None,
        output_path: str | None = None,
        output_format: str = "glb",
        fail_fast: bool = False,
        manifest_dir: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        spec = EvaluateGraphRequest(
            graph_id=graph_id,
            input_path=Path(input_path) if input_path else None,
            output_path=Path(output_path) if output_path else None,
            output_format=output_format,
            fail_fast=fail_fast,
            manifest_dir=Path(manifest_dir) if manifest_dir else None,
            asset_id=asset_id,
        )
        handle = get_context().runner.submit("evaluate_edit_graph", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Evaluate an EditGraph and emit per-step progress notifications. "
            "The MCP client must include a `progressToken` in the request "
            "`_meta` to receive notifications; without one the tool still "
            "returns the final EvaluationResult but emits no progress events. "
            "Pass `manifest_dir` to apply collision/lightmap side-effects to "
            "an asset manifest after evaluation."
        )
    )
    async def evaluate_edit_graph_streaming(
        graph_id: str,
        ctx: Context,
        input_path: str | None = None,
        output_path: str | None = None,
        output_format: str = "glb",
        fail_fast: bool = False,
        manifest_dir: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import evaluate_graph_streaming
        from ghostforge_core.authoring.schema import EvaluationResult
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        core = get_context()
        graph = _graph_with_overrides(
            core.graphs.load(graph_id),
            input_path=input_path,
            output_path=output_path,
        )
        core.graphs.save(graph)

        loop = asyncio.get_event_loop()
        last_event: dict[str, Any] | None = None

        # The streaming evaluator is a synchronous generator. Run it on a
        # worker thread and pump events back to the MCP client via
        # report_progress so we never block the asyncio loop.
        def _drain(queue: asyncio.Queue) -> None:
            try:
                for event in evaluate_graph_streaming(
                    graph,
                    registry=core.operations,
                    input_path=None,
                    output_path=None,
                    output_format=output_format,
                    fail_fast=fail_fast,
                ):
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        queue: asyncio.Queue = asyncio.Queue()
        runner = loop.run_in_executor(None, _drain, queue)

        while True:
            event = await queue.get()
            if event is None:
                break
            last_event = event
            if event.get("event") == "step":
                progress = float(event.get("progress") or 0.0)
                msg_parts = [event.get("kind", ""), event.get("status", "")]
                if event.get("message"):
                    msg_parts.append(str(event["message"]))
                if event.get("error"):
                    msg_parts.append(f"error: {event['error']}")
                try:
                    await ctx.report_progress(
                        progress=progress,
                        total=100.0,
                        message=" ".join(p for p in msg_parts if p).strip() or None,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

        await runner

        result_payload: dict[str, Any] | None = None
        if last_event is not None and last_event.get("event") == "completed":
            raw_result = last_event.get("result")
            result_payload = dict(raw_result or {}) if isinstance(raw_result, dict) else raw_result
            try:
                final = EvaluationResult.model_validate(raw_result)
                core.graphs.save_evaluation(final)
            except Exception:
                pass
            if isinstance(result_payload, dict):
                result_payload["graph"] = graph.model_dump(mode="json")

            side_effects = (
                (result_payload or {}).get("metadata", {}).get("side_effects") or []
            )
            if manifest_dir and side_effects:
                try:
                    manifest = apply_side_effects_to_manifest(
                        manifest_dir, side_effects, asset_id=asset_id
                    )
                    if manifest is not None:
                        result_payload["manifest"] = manifest.model_dump(mode="json")
                except Exception as exc:
                    result_payload["manifest_error"] = str(exc)

        return {"result": result_payload, "events_seen": last_event is not None}

    @server.tool(
        description=(
            "Block until a job reaches a terminal state, streaming progress "
            "notifications. The MCP client must include a `progressToken` in "
            "the request `_meta` to receive progress events; without one this "
            "still returns the final handle but emits no progress."
        )
    )
    async def wait_for_job(
        job_id: str,
        ctx: Context,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 0.25,
    ) -> dict[str, Any]:
        core = get_context()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(timeout_seconds, 0.0)
        last_percent: float | None = None
        last_stage: str | None = None

        while True:
            handle = core.jobs.get(job_id)
            progress = handle.progress
            if progress is not None:
                if progress.percent != last_percent or progress.stage != last_stage:
                    try:
                        await ctx.report_progress(
                            progress=progress.percent,
                            total=100.0,
                            message=f"{progress.stage}: {progress.message}".strip(": "),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Progress notifications are best-effort. The client may
                        # not have requested progress (no progressToken), or may
                        # have disconnected; never fail the tool because of it.
                        pass
                    last_percent = progress.percent
                    last_stage = progress.stage

            if handle.status in _TERMINAL_STATUSES:
                return _handle_to_dict(handle)

            if loop.time() >= deadline:
                raise TimeoutError(
                    f"Job {job_id} did not reach a terminal state within "
                    f"{timeout_seconds:.1f}s (last status={handle.status.value})"
                )
            await asyncio.sleep(max(poll_interval_seconds, 0.05))


__all__ = ["register_tools"]
