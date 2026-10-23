"""Concrete plan-only sessions for CAD live probes.

Probe batches decide order. Evidence packets decide what to capture. This
module combines both into step-by-step session plans that automation can inspect
before any live Plasticity action is attempted.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_packets import CadProbeEvidencePacketPlan, build_cad_evidence_packet_catalog
from .probe_batches import CadProbeBatchCommand, build_cad_probe_batch_plan


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


LiveProbeSessionMode = Literal["plan_only", "ready_for_manual_live_capture", "blocked"]


class CadLiveProbeSessionStep(FrozenModel):
    step_id: str = Field(min_length=1)
    order: int
    title: str
    action: str
    required_inputs: tuple[str, ...] = ()
    expected_outputs: tuple[str, ...] = ()
    evidence_sections: tuple[str, ...] = ()
    mutates_document: bool = False
    touches_files: bool = False
    safety_gate: str = ""


class CadLiveProbeSessionPlan(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    batch_id: str = ""
    session_mode: LiveProbeSessionMode = "plan_only"
    packet_kind: str = ""
    readiness: str = ""
    fixture: str = ""
    live_execution_allowed: bool = False
    required_safety_gates: tuple[str, ...] = ()
    required_sections: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    steps: tuple[CadLiveProbeSessionStep, ...] = ()
    completion_criteria: tuple[str, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


@dataclass(frozen=True)
class CadLiveProbeSessionCatalog:
    sessions: dict[str, CadLiveProbeSessionPlan]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadLiveProbeSessionPlan:
        return self.sessions[command_id]

    def all_sessions(self) -> list[CadLiveProbeSessionPlan]:
        return [self.sessions[key] for key in sorted(self.sessions)]

    def summary(self) -> dict[str, Any]:
        mode_counts: dict[str, int] = {}
        packet_counts: dict[str, int] = {}
        blocked = 0
        ready = 0
        file_touching = 0
        for session in self.sessions.values():
            mode_counts[session.session_mode] = mode_counts.get(session.session_mode, 0) + 1
            packet_counts[session.packet_kind] = packet_counts.get(session.packet_kind, 0) + 1
            blocked += int(session.session_mode == "blocked")
            ready += int(session.session_mode == "ready_for_manual_live_capture")
            file_touching += int(any(step.touches_files for step in session.steps))
        return {
            "session_count": len(self.sessions),
            "session_mode_counts": dict(sorted(mode_counts.items())),
            "packet_kind_counts": dict(sorted(packet_counts.items())),
            "blocked_session_count": blocked,
            "manual_live_capture_ready_count": ready,
            "file_touching_session_count": file_touching,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_live_probe_session_catalog(kb_root: str | Path | None = None) -> CadLiveProbeSessionCatalog:
    packets = build_cad_evidence_packet_catalog(kb_root)
    batches = build_cad_probe_batch_plan(kb_root)
    by_command: dict[str, tuple[str, CadProbeBatchCommand]] = {}
    for batch in batches.all_batches():
        for command in batch.commands:
            by_command[command.command_id] = (batch.batch_id, command)
    sessions: dict[str, CadLiveProbeSessionPlan] = {}
    for packet in packets.all_packets():
        batch_id, command = by_command.get(packet.command_id, ("", None))  # type: ignore[assignment]
        sessions[packet.command_id] = _session(packet, batch_id, command)
    return CadLiveProbeSessionCatalog(
        sessions=sessions,
        kb_root=packets.kb_root,
        generated_utc=packets.generated_utc,
    )


def _session(
    packet: CadProbeEvidencePacketPlan,
    batch_id: str,
    command: CadProbeBatchCommand | None,
) -> CadLiveProbeSessionPlan:
    mode = _mode(packet)
    safety_gates = _safety_gates(packet)
    steps = _steps(packet, mode)
    return CadLiveProbeSessionPlan(
        command_id=packet.command_id,
        label=packet.label,
        batch_id=batch_id,
        session_mode=mode,
        packet_kind=packet.packet_kind,
        readiness=packet.readiness,
        fixture=packet.fixture,
        live_execution_allowed=packet.live_execution_allowed,
        required_safety_gates=safety_gates,
        required_sections=packet.required_section_ids,
        required_evidence=packet.required_evidence,
        blockers=packet.blockers,
        steps=steps,
        completion_criteria=_completion_criteria(packet),
        next_action=command.next_action if command else packet.next_action,
    )


def _mode(packet: CadProbeEvidencePacketPlan) -> LiveProbeSessionMode:
    if packet.readiness == "ready_to_capture" and packet.live_execution_allowed:
        return "ready_for_manual_live_capture"
    if packet.readiness in {"waiting_for_probe_package", "waiting_for_static_owner", "planning_only_missing_gates"}:
        return "blocked"
    return "plan_only"


def _safety_gates(packet: CadProbeEvidencePacketPlan) -> tuple[str, ...]:
    gates = ["automation_route", "probe_package", "reset_verification"]
    if packet.packet_kind in {"fixture_mutation_packet", "file_interop_packet", "static_owner_packet"}:
        gates.append("disposable_fixture")
    if packet.file_artifact_required:
        gates.extend(["workspace_write_scope", "workspace_controlled_path"])
    if packet.static_owner_required:
        gates.append("owner_command_resolution")
    return tuple(dict.fromkeys(gates))


def _steps(packet: CadProbeEvidencePacketPlan, mode: LiveProbeSessionMode) -> tuple[CadLiveProbeSessionStep, ...]:
    if mode == "blocked":
        return (
            CadLiveProbeSessionStep(
                step_id="resolve_blocker",
                order=1,
                title="Resolve Blocker",
                action=packet.next_action,
                required_inputs=packet.blockers[:1],
                expected_outputs=("updated_evidence_packet",),
                safety_gate=packet.blockers[0] if packet.blockers else "",
            ),
        )
    steps = [
        CadLiveProbeSessionStep(
            step_id="guard_preflight",
            order=1,
            title="Guard Preflight",
            action="Verify package, route, fixture, write scope, and reset plan before opening Plasticity command UI.",
            required_inputs=("evidence_packet", "probe_batch", "safety_gates"),
            expected_outputs=("preflight_pass_record",),
            safety_gate="automation_route",
        ),
        CadLiveProbeSessionStep(
            step_id="prepare_fixture",
            order=2,
            title="Prepare Fixture",
            action=f"Prepare fixture {packet.fixture!r} and record source document/workspace state.",
            required_inputs=("fixture",),
            expected_outputs=("fixture_ready_record",),
            evidence_sections=("session_identity",),
            mutates_document=False,
            touches_files=packet.file_artifact_required,
            safety_gate="disposable_fixture" if packet.packet_kind in {"fixture_mutation_packet", "file_interop_packet"} else "",
        ),
        CadLiveProbeSessionStep(
            step_id="capture_baseline",
            order=3,
            title="Capture Baseline",
            action="Capture baseline screenshot, selection state, topology summary, viewport state, and file workspace state.",
            expected_outputs=("baseline_state",),
            evidence_sections=("baseline_state",),
        ),
        CadLiveProbeSessionStep(
            step_id="invoke_command_panel",
            order=4,
            title="Invoke Command Panel",
            action="Open the command through the approved palette/query route and capture the visible command result.",
            required_inputs=("palette_query", "fixture_ready_record"),
            expected_outputs=("command_invocation_record", "palette_result_screenshot"),
            evidence_sections=("session_identity",),
        ),
        CadLiveProbeSessionStep(
            step_id="capture_parameters",
            order=5,
            title="Capture Parameters",
            action="Capture visible parameter controls, defaults, groups, enum values, toggles, units, and validation affordances.",
            required_inputs=packet.parameter_names,
            expected_outputs=("observed_parameter_controls", "option_panel_state"),
            evidence_sections=("parameter_panel", "option_panel"),
        ),
    ]
    order = 6
    if "topology_delta" in packet.required_section_ids:
        steps.append(
            CadLiveProbeSessionStep(
                step_id="capture_fixture_behavior",
                order=order,
                title="Capture Fixture Behavior",
                action="Apply only the controlled fixture action and capture before/after topology, lineage, failures, and tolerances.",
                expected_outputs=("topology_delta", "failure_tolerance"),
                evidence_sections=("topology_delta", "failure_tolerance"),
                mutates_document=True,
                safety_gate="disposable_fixture",
            )
        )
        order += 1
    if packet.file_artifact_required:
        steps.append(
            CadLiveProbeSessionStep(
                step_id="capture_file_artifact",
                order=order,
                title="Capture File Artifact",
                action="Write only to the workspace-controlled export/import path and record artifact diagnostics.",
                expected_outputs=("workspace_path_file_record", "artifact_manifest_record", "translator_diagnostics"),
                evidence_sections=("file_artifact",),
                mutates_document=True,
                touches_files=True,
                safety_gate="workspace_controlled_path",
            )
        )
        order += 1
    if packet.static_owner_required:
        steps.append(
            CadLiveProbeSessionStep(
                step_id="capture_static_owner",
                order=order,
                title="Capture Static Owner",
                action="Capture negative palette evidence and candidate owner command panels without standalone promotion.",
                expected_outputs=("negative_palette_screenshot", "candidate_owner_panel_screenshots", "owner_classification"),
                evidence_sections=("static_owner_classification",),
                safety_gate="owner_command_resolution",
            )
        )
        order += 1
    steps.extend(
        [
            CadLiveProbeSessionStep(
                step_id="verify_reset",
                order=order,
                title="Verify Reset",
                action="Escape, undo, or clean workspace artifacts and prove the fixture returned to baseline.",
                expected_outputs=("reset_verification",),
                evidence_sections=("reset_verification",),
                touches_files=packet.file_artifact_required,
                safety_gate="reset_verification",
            ),
            CadLiveProbeSessionStep(
                step_id="record_observation",
                order=order + 1,
                title="Record Observation",
                action="Write the completed evidence packet into the observation ledger and refresh Ghost Forge recon catalogs.",
                expected_outputs=("observation_ledger_row", "schema_promotion_update", "parity_update"),
            ),
        ]
    )
    return tuple(steps)


def _completion_criteria(packet: CadProbeEvidencePacketPlan) -> tuple[str, ...]:
    criteria = ["all required sections have evidence", "validation checks include pass/fail evidence", "reset is verified"]
    if packet.file_artifact_required:
        criteria.append("workspace file artifact record is captured")
    if packet.static_owner_required:
        criteria.append("owner classification is recorded before promotion")
    if "topology_delta" in packet.required_section_ids:
        criteria.append("topology delta and lineage are captured")
    return tuple(criteria)


__all__ = [
    "CadLiveProbeSessionCatalog",
    "CadLiveProbeSessionPlan",
    "CadLiveProbeSessionStep",
    "LiveProbeSessionMode",
    "build_cad_live_probe_session_catalog",
]
