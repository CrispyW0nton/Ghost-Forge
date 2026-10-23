"""Joined Ghost Forge / Plasticity CAD parity readiness report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .fixtures import build_default_fixture_catalog
from .plasticity_recon import (
    PlasticityObservationEvidenceSnapshot,
    PlasticityReconCoverageSnapshot,
    load_plasticity_observation_evidence,
    load_plasticity_recon_coverage,
)
from .probes import CadProbeMatrix, build_default_probe_matrix
from .registry import CadCommandRegistry, build_default_cad_registry
from .schema import CadCommandDescriptor


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


PLASTICITY_COMMAND_ALIASES: dict[str, str] = {
    "delete_selection": "delete",
    "face_change_grow": "face_change",
    "xnurbs_boundary": "xnurbs",
}


class CadParityCommandReport(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    family: str = ""
    ghostforge_status: str = ""
    ghostforge_implementation_kind: str = ""
    plasticity_command_id: str | None = None
    descriptor_ready: bool = False
    fixture_contract_ready: bool = False
    probe_plan_ready: bool = False
    ghostforge_mcp_ready: bool = False
    ghostforge_qt_ready: bool = False
    plasticity_route_ready: bool = False
    plasticity_schema_status: str | None = None
    plasticity_readiness_bucket: str | None = None
    plasticity_next_tool: str | None = None
    plasticity_probe_kind: str | None = None
    observed_parameter_count: int | None = None
    missing_parameters: tuple[str, ...] = ()
    reset_verified: bool | None = None
    latest_session_command: bool = False
    static_asset_resolution: str | None = None
    blockers: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    recommended_ghostforge_action: str = ""

    @property
    def is_ready_for_parity_claim(self) -> bool:
        return not self.blockers


class CadParityReport(FrozenModel):
    kb_root: str | None = None
    command_count: int
    commands: tuple[CadParityCommandReport, ...]
    summary: dict[str, Any] = Field(default_factory=dict)

    def command(self, command_id: str) -> CadParityCommandReport:
        for command in self.commands:
            if command.command_id == command_id:
                return command
        raise KeyError(command_id)


def _plasticity_command_id(command: CadCommandDescriptor) -> str:
    return PLASTICITY_COMMAND_ALIASES.get(command.command_id, command.command_id)


def _optional_coverage(
    coverage: PlasticityReconCoverageSnapshot,
    command_id: str,
):
    try:
        return coverage.command(command_id)
    except KeyError:
        return None


def _optional_observation(
    observation: PlasticityObservationEvidenceSnapshot,
    command_id: str,
):
    try:
        return observation.command_status(command_id)
    except KeyError:
        return None


def _optional_probe_plan(matrix: CadProbeMatrix, command_id: str):
    try:
        return matrix.get_command_plan(command_id)
    except KeyError:
        return None


def _command_blockers(
    *,
    command: CadCommandDescriptor,
    fixture_contract_ready: bool,
    probe_plan_ready: bool,
    route_ready: bool,
    observation_status: str | None,
    reset_verified: bool | None,
) -> list[str]:
    blockers: list[str] = []
    if not command.parameter_schema:
        blockers.append("ghostforge.parameter_schema_missing")
    if not command.selection_contract:
        blockers.append("ghostforge.selection_contract_missing")
    if not command.failure_modes:
        blockers.append("ghostforge.failure_modes_missing")
    if not fixture_contract_ready:
        blockers.append("ghostforge.fixture_expectation_missing")
    if not probe_plan_ready:
        blockers.append("ghostforge.probe_plan_missing")
    if command.status in {"planned", "controlled_probe_needed"}:
        blockers.append(f"ghostforge.implementation_{command.status}")
    if command.status in {"option", "alias", "contextual_mode"}:
        blockers.append("plasticity.relationship_owner_unverified")
    if not route_ready and command.status != "implemented_mesh":
        blockers.append("plasticity.automation_route_missing")
    if observation_status != "observed_schema":
        blockers.append("plasticity.observed_schema_missing")
    if reset_verified is not True:
        blockers.append("plasticity.reset_not_verified")
    return blockers


def _next_actions(
    *,
    command: CadCommandDescriptor,
    coverage_next_tool: str | None,
    missing_parameters: tuple[str, ...],
    blockers: list[str],
) -> list[str]:
    actions: list[str] = []
    if coverage_next_tool:
        actions.append(f"Run Plasticity `{coverage_next_tool}` for `{_plasticity_command_id(command)}`.")
    if missing_parameters:
        actions.append("Resolve missing Plasticity parameters: " + ", ".join(missing_parameters) + ".")
    if "ghostforge.implementation_planned" in blockers:
        actions.append("Keep Ghost Forge command descriptor planned until a CAD kernel handler exists.")
    if "ghostforge.implementation_controlled_probe_needed" in blockers:
        actions.append("Keep command behind controlled-probe gates until file/dialog behavior is observed.")
    if "plasticity.relationship_owner_unverified" in blockers:
        actions.append("Probe likely owner commands before surfacing this as a top-level Qt action.")
    if "plasticity.observed_schema_missing" in blockers:
        actions.append("Do not promote inferred parameter templates to final Ghost Forge option panels yet.")
    if "plasticity.reset_not_verified" in blockers:
        actions.append("Capture undo/escape/reset evidence before declaring automation robust.")
    return actions


def _recommended_action(command: CadCommandDescriptor, blockers: list[str]) -> str:
    if not blockers:
        return "ready_for_parity_claim"
    if any(blocker.startswith("ghostforge.implementation_") for blocker in blockers):
        return "implement_or_gate_ghostforge_handler"
    if "plasticity.relationship_owner_unverified" in blockers:
        return "resolve_static_asset_ownership"
    if "plasticity.observed_schema_missing" in blockers:
        return "run_live_plasticity_parameter_probe"
    if command.status == "implemented_mesh":
        return "harden_mesh_command_against_plasticity_observations"
    return "continue_evidence_collection"


def build_cad_parity_report(
    kb_root: str | Path | None = None,
    *,
    registry: CadCommandRegistry | None = None,
    probe_matrix: CadProbeMatrix | None = None,
) -> CadParityReport:
    registry = registry or build_default_cad_registry()
    probe_matrix = probe_matrix or build_default_probe_matrix()
    fixtures = build_default_fixture_catalog()
    coverage = load_plasticity_recon_coverage(kb_root)
    observation = load_plasticity_observation_evidence(kb_root)
    latest_session_command_id = observation.latest_session.command_id if observation.latest_session else None

    reports: list[CadParityCommandReport] = []
    for command in registry.all():
        plasticity_id = _plasticity_command_id(command)
        coverage_row = _optional_coverage(coverage, plasticity_id)
        observation_row = _optional_observation(observation, plasticity_id)
        probe_plan = _optional_probe_plan(probe_matrix, command.command_id)
        fixture_contract_ready = bool(fixtures.expectations_for_command(command.command_id))
        probe_plan_ready = probe_plan is not None
        route_ready = bool(coverage_row and coverage_row.has_automation_route)
        observation_status = observation_row.schema_status if observation_row else None
        reset_verified = observation_row.reset_verified if observation_row else None
        missing_parameters = observation_row.missing_template_parameters if observation_row else ()
        blockers = _command_blockers(
            command=command,
            fixture_contract_ready=fixture_contract_ready,
            probe_plan_ready=probe_plan_ready,
            route_ready=route_ready,
            observation_status=observation_status,
            reset_verified=reset_verified,
        )
        reports.append(
            CadParityCommandReport(
                command_id=command.command_id,
                label=command.label,
                family=command.family,
                ghostforge_status=command.status,
                ghostforge_implementation_kind=command.implementation_kind,
                plasticity_command_id=plasticity_id if coverage_row or observation_row else None,
                descriptor_ready=bool(command.parameter_schema and command.selection_contract and command.failure_modes),
                fixture_contract_ready=fixture_contract_ready,
                probe_plan_ready=probe_plan_ready,
                ghostforge_mcp_ready=bool(command.mcp_surface),
                ghostforge_qt_ready=bool(command.qt_surface),
                plasticity_route_ready=route_ready,
                plasticity_schema_status=observation_status,
                plasticity_readiness_bucket=coverage_row.readiness_bucket if coverage_row else None,
                plasticity_next_tool=coverage_row.next_tool if coverage_row else None,
                plasticity_probe_kind=coverage_row.probe_kind if coverage_row else (observation_row.probe_kind if observation_row else None),
                observed_parameter_count=observation_row.observed_parameter_count if observation_row else None,
                missing_parameters=missing_parameters,
                reset_verified=reset_verified,
                latest_session_command=plasticity_id == latest_session_command_id,
                static_asset_resolution=probe_plan.static_asset_resolution if probe_plan else None,
                blockers=tuple(blockers),
                next_actions=tuple(_next_actions(
                    command=command,
                    coverage_next_tool=coverage_row.next_tool if coverage_row else None,
                    missing_parameters=missing_parameters,
                    blockers=blockers,
                )),
                recommended_ghostforge_action=_recommended_action(command, blockers),
            )
        )

    status_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    blocker_counts: dict[str, int] = {}
    for report in reports:
        status_counts[report.ghostforge_status] = status_counts.get(report.ghostforge_status, 0) + 1
        action_counts[report.recommended_ghostforge_action] = action_counts.get(report.recommended_ghostforge_action, 0) + 1
        for blocker in report.blockers:
            blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1

    return CadParityReport(
        kb_root=str(kb_root) if kb_root is not None else coverage.kb_root,
        command_count=len(reports),
        commands=tuple(sorted(reports, key=lambda row: (row.family, row.command_id))),
        summary={
            "command_count": len(reports),
            "ready_for_parity_claim_count": sum(1 for row in reports if row.is_ready_for_parity_claim),
            "plasticity_route_ready_count": sum(1 for row in reports if row.plasticity_route_ready),
            "observed_schema_count": sum(1 for row in reports if row.plasticity_schema_status == "observed_schema"),
            "reset_verified_count": sum(1 for row in reports if row.reset_verified is True),
            "status_counts": dict(sorted(status_counts.items())),
            "recommended_action_counts": dict(sorted(action_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "latest_session_command_id": latest_session_command_id,
        },
    )


__all__ = [
    "CadParityCommandReport",
    "CadParityReport",
    "PLASTICITY_COMMAND_ALIASES",
    "build_cad_parity_report",
]
