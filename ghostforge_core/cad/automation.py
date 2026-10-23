"""Automation runbooks for CAD recon and native Ghost Forge implementation.

The development queue says what work exists.  This module turns each task into
an automation route with safety gates, required evidence, reset verification,
and the native Ghost Forge subsystem that should consume the result.  The
runbook is declarative: it does not call Plasticity and is safe to inspect from
tests, Qt, or MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .development_queue import (
    GhostForgeCadDevelopmentTask,
    build_ghostforge_cad_development_queue,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


AutomationRouteKind = Literal[
    "safe_parameter_probe",
    "fixture_mutation_probe",
    "file_interop_probe",
    "static_owner_probe",
    "viewport_state_probe",
    "selection_state_probe",
]

AutomationGateStatus = Literal["satisfied", "missing", "not_applicable"]


class CadAutomationGate(FrozenModel):
    gate_id: str = Field(min_length=1)
    status: AutomationGateStatus
    reason: str
    required_before_live_execution: bool = True


class CadAutomationEvidence(FrozenModel):
    required: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    reset_verification: tuple[str, ...] = ()


class CadAutomationRoute(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    implementation_track: str = ""
    route_kind: AutomationRouteKind
    priority: str = ""
    planning_allowed: bool = True
    live_execution_allowed: bool = False
    package_available: bool = False
    route_ready: bool = False
    tools: tuple[str, ...] = ()
    safety_gates: tuple[CadAutomationGate, ...] = ()
    evidence: CadAutomationEvidence = Field(default_factory=CadAutomationEvidence)
    workspace_write_scope: str = ""
    fixture: str = ""
    native_consumer: str = ""
    blockers: tuple[str, ...] = ()
    next_action: str = ""

    @property
    def missing_required_gates(self) -> tuple[str, ...]:
        return tuple(
            gate.gate_id
            for gate in self.safety_gates
            if gate.required_before_live_execution and gate.status == "missing"
        )


@dataclass(frozen=True)
class CadAutomationRunbook:
    routes: dict[str, CadAutomationRoute]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadAutomationRoute:
        return self.routes[command_id]

    def all_routes(self) -> list[CadAutomationRoute]:
        return [self.routes[key] for key in sorted(self.routes)]

    def by_kind(self, route_kind: str) -> list[CadAutomationRoute]:
        return [route for route in self.all_routes() if route.route_kind == route_kind]

    def summary(self) -> dict[str, Any]:
        kind_counts: dict[str, int] = {}
        blocked_gate_counts: dict[str, int] = {}
        live_allowed = 0
        package_available = 0
        file_touching = 0
        for route in self.routes.values():
            kind_counts[route.route_kind] = kind_counts.get(route.route_kind, 0) + 1
            if route.live_execution_allowed:
                live_allowed += 1
            if route.package_available:
                package_available += 1
            if route.route_kind == "file_interop_probe":
                file_touching += 1
            for gate_id in route.missing_required_gates:
                blocked_gate_counts[gate_id] = blocked_gate_counts.get(gate_id, 0) + 1
        return {
            "route_count": len(self.routes),
            "route_kind_counts": dict(sorted(kind_counts.items())),
            "live_execution_allowed_count": live_allowed,
            "package_available_count": package_available,
            "file_touching_route_count": file_touching,
            "blocked_gate_counts": dict(sorted(blocked_gate_counts.items())),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_automation_runbook(kb_root: str | Path | None = None) -> CadAutomationRunbook:
    queue = build_ghostforge_cad_development_queue(kb_root)
    routes = {
        task.command_id: _route_from_task(task)
        for task in queue.all_tasks()
    }
    return CadAutomationRunbook(
        routes=routes,
        kb_root=queue.kb_root,
        generated_utc=queue.generated_utc,
    )


def _route_from_task(task: GhostForgeCadDevelopmentTask) -> CadAutomationRoute:
    route_kind = _route_kind(task)
    gates = _gates_for_task(task, route_kind)
    evidence = _evidence_for_task(task, route_kind)
    live_allowed = (
        task.route_ready
        and task.package_available
        and not any(gate.required_before_live_execution and gate.status == "missing" for gate in gates)
    )
    return CadAutomationRoute(
        command_id=task.command_id,
        label=task.label,
        implementation_track=task.implementation_track,
        route_kind=route_kind,
        priority=task.priority,
        planning_allowed=True,
        live_execution_allowed=live_allowed,
        package_available=task.package_available,
        route_ready=task.route_ready,
        tools=task.automation_tools,
        safety_gates=gates,
        evidence=evidence,
        workspace_write_scope=_workspace_write_scope(task, route_kind),
        fixture=task.fixture,
        native_consumer=_native_consumer(task),
        blockers=task.blockers,
        next_action=_next_action(task, route_kind, live_allowed),
    )


def _route_kind(task: GhostForgeCadDevelopmentTask) -> AutomationRouteKind:
    if "static_asset.owner_unresolved" in task.blockers:
        return "static_owner_probe"
    if task.file_touching or task.implementation_track == "file_interop":
        return "file_interop_probe"
    if task.implementation_track == "viewport_state":
        return "viewport_state_probe"
    if task.implementation_track == "selection_state":
        return "selection_state_probe"
    if task.requires_disposable_fixture or task.implementation_track in {"solid_modeling_kernel", "surface_curve_kernel", "transform_command"}:
        return "fixture_mutation_probe"
    return "safe_parameter_probe"


def _gates_for_task(
    task: GhostForgeCadDevelopmentTask,
    route_kind: AutomationRouteKind,
) -> tuple[CadAutomationGate, ...]:
    gates = [
        CadAutomationGate(
            gate_id="automation_route",
            status="satisfied" if task.route_ready else "missing",
            reason="At least one MCP/planned automation tool is available." if task.route_ready else "No automation route is present in recon evidence.",
        ),
        CadAutomationGate(
            gate_id="probe_package",
            status="satisfied" if task.package_available else "missing",
            reason="Runnable probe package exists." if task.package_available else "Create a probe package before live execution.",
        ),
    ]
    if route_kind in {"fixture_mutation_probe", "file_interop_probe", "static_owner_probe"}:
        gates.append(
            CadAutomationGate(
                gate_id="disposable_fixture",
                status="satisfied" if task.requires_disposable_fixture or task.package_available else "missing",
                reason="Probe must run on a disposable fixture/document and prove reset.",
            )
        )
    if route_kind == "file_interop_probe":
        gates.append(
            CadAutomationGate(
                gate_id="workspace_write_scope",
                status="satisfied" if task.workspace_safety_gate else "missing",
                reason=(
                    "File-touching probe is constrained to a workspace-controlled path."
                    if task.workspace_safety_gate
                    else "File-touching probe lacks a workspace-controlled write/reset gate."
                ),
            )
        )
    if route_kind == "static_owner_probe":
        gates.append(
            CadAutomationGate(
                gate_id="owner_command_resolution",
                status="missing",
                reason="Static asset must be matched to an owning command before any standalone execution.",
            )
        )
    gates.append(
        CadAutomationGate(
            gate_id="reset_verification",
            status="satisfied" if task.package_available and "plasticity.reset_not_verified" not in task.blockers else "missing",
            reason="Reset/undo evidence must be recorded before parity promotion.",
            required_before_live_execution=False,
        )
    )
    return tuple(gates)


def _evidence_for_task(
    task: GhostForgeCadDevelopmentTask,
    route_kind: AutomationRouteKind,
) -> CadAutomationEvidence:
    required = list(task.required_evidence)
    if not required:
        required.extend(("baseline_screenshot", "post_invocation_screenshot"))
    if task.template_parameters or task.parameter_names_to_resolve:
        required.append("observed_parameter_schema")
    if route_kind in {"fixture_mutation_probe", "static_owner_probe"}:
        required.extend(("fixture_topology_delta", "undo_or_reset_snapshot"))
    if route_kind == "file_interop_probe":
        required.extend(("workspace_path_file_record", "artifact_or_translator_diagnostics"))
    if route_kind == "static_owner_probe":
        required.extend(("negative_palette_screenshot", "candidate_owner_panel_screenshots", "observed_option_owner"))
    if route_kind == "selection_state_probe":
        required.extend(("selection_before_after_state", "selection_filter_state"))
    if route_kind == "viewport_state_probe":
        required.extend(("viewport_before_after_state", "camera_grid_overlay_state"))
    return CadAutomationEvidence(
        required=tuple(dict.fromkeys(required)),
        optional=tuple(task.evidence_screenshots),
        reset_verification=_reset_verification(route_kind),
    )


def _reset_verification(route_kind: AutomationRouteKind) -> tuple[str, ...]:
    if route_kind == "file_interop_probe":
        return ("remove_only_workspace_artifacts", "source_document_snapshot_unchanged")
    if route_kind == "static_owner_probe":
        return ("escape_or_cancel_owner_command", "source_fixture_snapshot_unchanged")
    if route_kind in {"fixture_mutation_probe", "selection_state_probe", "viewport_state_probe"}:
        return ("undo_or_escape_restores_fixture", "after_state_matches_before_snapshot")
    return ("escape_closes_panel", "no_document_mutation")


def _workspace_write_scope(task: GhostForgeCadDevelopmentTask, route_kind: AutomationRouteKind) -> str:
    if route_kind != "file_interop_probe":
        return "no_file_writes_expected"
    if task.workspace_safety_gate:
        return "workspace_controlled_fixture_exports_only"
    return "blocked_until_workspace_controlled_path_is_defined"


def _native_consumer(task: GhostForgeCadDevelopmentTask) -> str:
    return {
        "solid_modeling_kernel": "ghostforge_core.cad.behavior + future kernel handler",
        "surface_curve_kernel": "ghostforge_core.cad.behavior + future surface/curve handler",
        "file_interop": "ghostforge_core.cad.interop",
        "selection_state": "ghostforge_core selection state contract",
        "viewport_state": "ghostforge_qt viewport state contract",
        "transform_command": "ghostforge_core.cad.execution transform handler",
        "command_state": "ghostforge_core.cad.schema command descriptor",
        "static_asset_resolution": "ghostforge_core.cad.registry relationship descriptor",
    }.get(task.implementation_track, "ghostforge_core.cad")


def _next_action(
    task: GhostForgeCadDevelopmentTask,
    route_kind: AutomationRouteKind,
    live_allowed: bool,
) -> str:
    if live_allowed:
        return "run_probe_package_capture_evidence_and_record_observation"
    if route_kind == "file_interop_probe" and not task.workspace_safety_gate:
        return "add_workspace_controlled_output_fixture_before_live_probe"
    if route_kind == "static_owner_probe":
        return "probe_candidate_owner_commands_without_promoting_static_asset"
    if not task.package_available:
        return "create_probe_package_with_fixture_setup_evidence_and_reset_steps"
    if not task.route_ready:
        return "create_or_repair_mcp_automation_route"
    return task.next_plasticity_action or "collect_required_evidence_before_promotion"


__all__ = [
    "AutomationGateStatus",
    "AutomationRouteKind",
    "CadAutomationEvidence",
    "CadAutomationGate",
    "CadAutomationRoute",
    "CadAutomationRunbook",
    "build_cad_automation_runbook",
]
