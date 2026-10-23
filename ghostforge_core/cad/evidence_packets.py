"""Evidence packet plans for Plasticity-to-Ghost-Forge CAD probes.

The recon goal needs more than a command list.  Every live Plasticity probe
must return a structured packet that Ghost Forge can use to promote schemas,
verify fixture behavior, classify static assets, and design native handlers.
This module defines those packet plans without executing Plasticity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from .automation import CadAutomationRoute, build_cad_automation_runbook
from .behavior import CommandBehaviorCase, build_default_behavior_matrix
from .robustness import CadRobustnessContract, build_cad_robustness_catalog
from .schema_promotion import CadSchemaPromotionCandidate, build_cad_schema_promotion_catalog


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


EvidencePacketKind = Literal[
    "safe_parameter_packet",
    "fixture_mutation_packet",
    "file_interop_packet",
    "static_owner_packet",
    "selection_state_packet",
    "viewport_state_packet",
]

EvidenceSectionStatus = Literal["satisfied", "planned", "blocked", "not_applicable"]

PacketReadiness = Literal[
    "ready_to_capture",
    "planning_only_missing_gates",
    "waiting_for_probe_package",
    "waiting_for_static_owner",
    "captured_but_not_promotable",
]


class CadEvidencePacketSection(FrozenModel):
    section_id: str = Field(min_length=1)
    status: EvidenceSectionStatus
    required: bool = True
    fields: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    producer: str = ""
    consumed_by: tuple[str, ...] = ()
    notes: str = ""


class CadProbeEvidencePacketPlan(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    packet_kind: EvidencePacketKind
    readiness: PacketReadiness
    implementation_track: str = ""
    route_kind: str = ""
    live_execution_allowed: bool = False
    package_available: bool = False
    fixture: str = ""
    behavior_case_ids: tuple[str, ...] = ()
    parameter_names: tuple[str, ...] = ()
    option_panel_groups: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    reset_requirements: tuple[str, ...] = ()
    topology_policy_ids: tuple[str, ...] = ()
    topology_targets: tuple[str, ...] = ()
    failure_targets: tuple[str, ...] = ()
    tolerance_targets: tuple[str, ...] = ()
    file_artifact_required: bool = False
    static_owner_required: bool = False
    sections: tuple[CadEvidencePacketSection, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"

    @computed_field
    @property
    def required_section_ids(self) -> tuple[str, ...]:
        return tuple(section.section_id for section in self.sections if section.required)


@dataclass(frozen=True)
class CadEvidencePacketCatalog:
    packets: dict[str, CadProbeEvidencePacketPlan]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadProbeEvidencePacketPlan:
        return self.packets[command_id]

    def all_packets(self) -> list[CadProbeEvidencePacketPlan]:
        return [self.packets[key] for key in sorted(self.packets)]

    def by_kind(self, packet_kind: str) -> list[CadProbeEvidencePacketPlan]:
        return [packet for packet in self.all_packets() if packet.packet_kind == packet_kind]

    def summary(self) -> dict[str, Any]:
        kind_counts: dict[str, int] = {}
        readiness_counts: dict[str, int] = {}
        section_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        live_allowed = 0
        file_artifact = 0
        static_owner = 0
        for packet in self.packets.values():
            kind_counts[packet.packet_kind] = kind_counts.get(packet.packet_kind, 0) + 1
            readiness_counts[packet.readiness] = readiness_counts.get(packet.readiness, 0) + 1
            if packet.live_execution_allowed:
                live_allowed += 1
            if packet.file_artifact_required:
                file_artifact += 1
            if packet.static_owner_required:
                static_owner += 1
            for section in packet.sections:
                if section.required:
                    section_counts[section.section_id] = section_counts.get(section.section_id, 0) + 1
            for blocker in packet.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "packet_count": len(self.packets),
            "packet_kind_counts": dict(sorted(kind_counts.items())),
            "readiness_counts": dict(sorted(readiness_counts.items())),
            "required_section_counts": dict(sorted(section_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "live_execution_allowed_count": live_allowed,
            "file_artifact_packet_count": file_artifact,
            "static_owner_packet_count": static_owner,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_evidence_packet_catalog(kb_root: str | Path | None = None) -> CadEvidencePacketCatalog:
    runbook = build_cad_automation_runbook(kb_root)
    promotions = build_cad_schema_promotion_catalog(kb_root)
    behavior = build_default_behavior_matrix()
    robustness = build_cad_robustness_catalog(kb_root)
    packets: dict[str, CadProbeEvidencePacketPlan] = {}
    for route in runbook.all_routes():
        promotion = promotions.candidates.get(route.command_id)
        behavior_cases = behavior.cases_for_command(route.command_id)
        robustness_contract = _robustness_for_command(robustness.contracts, route.command_id)
        packets[route.command_id] = _packet_plan(route, promotion, behavior_cases, robustness_contract)
    return CadEvidencePacketCatalog(
        packets=packets,
        kb_root=runbook.kb_root,
        generated_utc=runbook.generated_utc,
    )


def _robustness_for_command(
    contracts: dict[str, CadRobustnessContract],
    command_id: str,
) -> CadRobustnessContract | None:
    for key in (f"command:{command_id}", f"selection:{command_id}", f"format:{command_id}"):
        if key in contracts:
            return contracts[key]
    for contract in contracts.values():
        if contract.subject_id == command_id:
            return contract
    return None


def _packet_plan(
    route: CadAutomationRoute,
    promotion: CadSchemaPromotionCandidate | None,
    behavior_cases: list[CommandBehaviorCase],
    robustness: CadRobustnessContract | None,
) -> CadProbeEvidencePacketPlan:
    packet_kind = _packet_kind(route.route_kind)
    file_artifact_required = route.route_kind == "file_interop_probe"
    static_owner_required = route.route_kind == "static_owner_probe"
    parameter_names = _unique(
        list(promotion.template_parameters if promotion else ())
        + [
            name
            for case in behavior_cases
            for name in list(case.parameters) + list(case.option_panel_state)
        ]
    )
    topology_targets = _unique(
        [
            item
            for case in behavior_cases
            for transition in case.topology_transitions
            for item in (transition.source, *transition.results)
        ]
        + list(robustness.topology_effects if robustness else ())
    )
    failure_targets = _unique(
        [probe.expected_failure_code for case in behavior_cases for probe in case.failure_probes]
        + list(robustness.failure_codes if robustness else ())
    )
    tolerance_targets = _unique(
        [assertion for case in behavior_cases for assertion in case.tolerance_assertions]
        + list(robustness.tolerance_contract_ids if robustness else ())
    )
    required_evidence = _unique(
        list(route.evidence.required)
        + list(promotion.required_evidence if promotion else ())
        + [evidence for case in behavior_cases for evidence in case.automation.required_evidence]
    )
    reset_requirements = _unique(
        list(route.evidence.reset_verification)
        + [evidence for case in behavior_cases for evidence in case.automation.reset_verification]
    )
    sections = _sections(
        route=route,
        promotion=promotion,
        behavior_cases=behavior_cases,
        required_evidence=required_evidence,
        parameter_names=parameter_names,
        topology_targets=topology_targets,
        failure_targets=failure_targets,
        tolerance_targets=tolerance_targets,
        file_artifact_required=file_artifact_required,
        static_owner_required=static_owner_required,
    )
    blockers = _blockers(route, promotion, sections)
    readiness = _readiness(route, promotion, blockers, static_owner_required)
    return CadProbeEvidencePacketPlan(
        command_id=route.command_id,
        label=route.label,
        packet_kind=packet_kind,
        readiness=readiness,
        implementation_track=route.implementation_track,
        route_kind=route.route_kind,
        live_execution_allowed=route.live_execution_allowed,
        package_available=route.package_available,
        fixture=route.fixture,
        behavior_case_ids=tuple(case.case_id for case in behavior_cases),
        parameter_names=parameter_names,
        option_panel_groups=promotion.option_panel_groups if promotion else (),
        required_evidence=required_evidence,
        reset_requirements=reset_requirements,
        topology_policy_ids=robustness.topology_policy_ids if robustness else (),
        topology_targets=topology_targets,
        failure_targets=failure_targets,
        tolerance_targets=tolerance_targets,
        file_artifact_required=file_artifact_required,
        static_owner_required=static_owner_required,
        sections=sections,
        blockers=blockers,
        next_action=_next_action(readiness, blockers, route, promotion),
    )


def _sections(
    *,
    route: CadAutomationRoute,
    promotion: CadSchemaPromotionCandidate | None,
    behavior_cases: list[CommandBehaviorCase],
    required_evidence: tuple[str, ...],
    parameter_names: tuple[str, ...],
    topology_targets: tuple[str, ...],
    failure_targets: tuple[str, ...],
    tolerance_targets: tuple[str, ...],
    file_artifact_required: bool,
    static_owner_required: bool,
) -> tuple[CadEvidencePacketSection, ...]:
    evidence_refs = promotion.evidence_screenshots if promotion else ()
    sections = [
        CadEvidencePacketSection(
            section_id="session_identity",
            status="planned" if route.route_ready else "blocked",
            fields=("command_id", "label", "plasticity_version", "probe_timestamp", "fixture", "route_kind"),
            evidence_refs=(route.command_id,),
            producer="automation_runbook",
            consumed_by=("schema_promotion", "parity_report"),
            notes="Identifies the exact command, fixture, and route used for the probe.",
        ),
        CadEvidencePacketSection(
            section_id="baseline_state",
            status=_section_status(required_evidence, evidence_refs, ("baseline_screenshot", "before_topology_snapshot", "before_selection_state")),
            fields=("baseline_screenshot", "before_topology_snapshot", "before_selection_state", "viewport_state"),
            evidence_refs=evidence_refs,
            producer="live_probe",
            consumed_by=("behavior_matrix", "schema_promotion", "reset_verification"),
            notes="Captures the source fixture before command invocation.",
        ),
        CadEvidencePacketSection(
            section_id="parameter_panel",
            status="planned" if parameter_names else "not_applicable",
            required=bool(parameter_names),
            fields=parameter_names,
            evidence_refs=tuple(name for name in parameter_names if promotion and any(p.name == name and p.is_observed for p in promotion.observed_parameters)),
            producer="command_panel_observer",
            consumed_by=("schema_promotion", "qt_option_panel", "mcp_payload_schema"),
            notes="Maps visible Plasticity controls to Ghost Forge parameter names.",
        ),
        CadEvidencePacketSection(
            section_id="option_panel",
            status="planned" if promotion and promotion.option_panel_groups else "not_applicable",
            required=bool(promotion and promotion.option_panel_groups),
            fields=promotion.option_panel_groups if promotion else (),
            evidence_refs=evidence_refs,
            producer="command_panel_observer",
            consumed_by=("schema_drafts", "schema_promotion", "qt_option_panel"),
            notes="Records control groups, modes, toggles, defaults, and enums.",
        ),
        CadEvidencePacketSection(
            section_id="topology_delta",
            status="planned" if topology_targets else "not_applicable",
            required=bool(topology_targets),
            fields=("before_counts", "after_counts", "created_ids", "deleted_ids", "modified_ids", "lineage_map", *topology_targets),
            evidence_refs=tuple(case.case_id for case in behavior_cases),
            producer="fixture_probe",
            consumed_by=("behavior_matrix", "robustness_catalog", "native_handler_tests"),
            notes="Records exact fixture geometry changes and topology lineage.",
        ),
        CadEvidencePacketSection(
            section_id="failure_tolerance",
            status="planned" if failure_targets or tolerance_targets else "not_applicable",
            required=bool(failure_targets or tolerance_targets),
            fields=("failure_code", "trigger", "recovery", "tolerance_value", "tolerance_unit", *failure_targets, *tolerance_targets),
            evidence_refs=tuple(case.case_id for case in behavior_cases),
            producer="fixture_failure_probe",
            consumed_by=("robustness_catalog", "native_handler_tests", "user_error_messages"),
            notes="Captures expected failure cases and tolerance-sensitive boundaries.",
        ),
        CadEvidencePacketSection(
            section_id="file_artifact",
            status="planned" if file_artifact_required else "not_applicable",
            required=file_artifact_required,
            fields=("workspace_path_file_record", "artifact_manifest_record", "translator_diagnostics", "source_topology_preserved"),
            evidence_refs=evidence_refs,
            producer="file_interop_probe",
            consumed_by=("interop_contract", "manifest", "schema_promotion"),
            notes="Required for import/export commands that read or write files.",
        ),
        CadEvidencePacketSection(
            section_id="static_owner_classification",
            status="blocked" if static_owner_required else "not_applicable",
            required=static_owner_required,
            fields=("negative_palette_screenshot", "candidate_owner_panel_screenshots", "observed_option_owner", "alias_or_option_mapping"),
            evidence_refs=evidence_refs,
            producer="static_owner_probe",
            consumed_by=("registry_relationships", "schema_drafts", "robustness_catalog"),
            notes="Classifies static assets as commands, aliases, options, tutorial/media, or contextual modes.",
        ),
        CadEvidencePacketSection(
            section_id="reset_verification",
            status="satisfied" if promotion and promotion.reset_verified else "planned",
            fields=("undo_or_escape_result", "after_reset_snapshot", "workspace_cleanup_record", *route.evidence.reset_verification),
            evidence_refs=evidence_refs,
            producer="live_probe",
            consumed_by=("schema_promotion", "automation_runbook", "parity_report"),
            notes="Proves the fixture/document/workspace is safe after probing.",
        ),
    ]
    return tuple(sections)


def _section_status(
    required_evidence: tuple[str, ...],
    evidence_refs: tuple[str, ...],
    aliases: tuple[str, ...],
) -> EvidenceSectionStatus:
    required = any(alias in required_evidence for alias in aliases)
    if not required:
        return "planned"
    if any(alias in evidence_refs for alias in aliases):
        return "satisfied"
    return "planned"


def _packet_kind(route_kind: str) -> EvidencePacketKind:
    return {
        "safe_parameter_probe": "safe_parameter_packet",
        "fixture_mutation_probe": "fixture_mutation_packet",
        "file_interop_probe": "file_interop_packet",
        "static_owner_probe": "static_owner_packet",
        "selection_state_probe": "selection_state_packet",
        "viewport_state_probe": "viewport_state_packet",
    }.get(route_kind, "safe_parameter_packet")  # type: ignore[return-value]


def _blockers(
    route: CadAutomationRoute,
    promotion: CadSchemaPromotionCandidate | None,
    sections: tuple[CadEvidencePacketSection, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not route.package_available:
        blockers.append("probe_package_missing")
    blockers.extend(f"automation.{gate}_missing" for gate in route.missing_required_gates)
    if promotion:
        blockers.extend(promotion.blockers)
    for section in sections:
        if section.required and section.status == "blocked":
            blockers.append(f"section.{section.section_id}.blocked")
    return tuple(dict.fromkeys(blockers))


def _readiness(
    route: CadAutomationRoute,
    promotion: CadSchemaPromotionCandidate | None,
    blockers: tuple[str, ...],
    static_owner_required: bool,
) -> PacketReadiness:
    if static_owner_required:
        return "waiting_for_static_owner"
    if not route.package_available:
        return "waiting_for_probe_package"
    if any(blocker.startswith("automation.") for blocker in blockers):
        return "planning_only_missing_gates"
    if promotion and promotion.promotion_status in {"ready_for_observed_partial", "ready_for_observed_schema"}:
        return "captured_but_not_promotable"
    if route.live_execution_allowed:
        return "ready_to_capture"
    return "planning_only_missing_gates"


def _next_action(
    readiness: PacketReadiness,
    blockers: tuple[str, ...],
    route: CadAutomationRoute,
    promotion: CadSchemaPromotionCandidate | None,
) -> str:
    if readiness == "ready_to_capture":
        return "run live probe and fill every required evidence packet section"
    if readiness == "waiting_for_probe_package":
        return "create probe package with fixture setup, evidence fields, and reset steps"
    if readiness == "waiting_for_static_owner":
        return "identify owning command before executing or promoting static asset evidence"
    if readiness == "captured_but_not_promotable" and promotion:
        return promotion.next_action
    if blockers:
        return f"resolve first blocker: {blockers[0]}"
    return route.next_action


def _unique(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


__all__ = [
    "CadEvidencePacketCatalog",
    "CadEvidencePacketSection",
    "CadProbeEvidencePacketPlan",
    "EvidencePacketKind",
    "EvidenceSectionStatus",
    "PacketReadiness",
    "build_cad_evidence_packet_catalog",
]
