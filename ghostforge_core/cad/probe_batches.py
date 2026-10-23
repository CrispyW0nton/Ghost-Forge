"""Batch planning for CAD recon evidence packets.

Evidence packets define what one Plasticity probe must capture.  This module
orders those packets into safe batches so Ghost Forge can advance the recon
without treating 141 commands as one undifferentiated pile of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_packets import CadProbeEvidencePacketPlan, build_cad_evidence_packet_catalog


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


ProbeBatchKind = Literal[
    "ready_live_capture",
    "probe_package_generation",
    "static_owner_resolution",
    "safety_gate_repair",
    "post_capture_promotion",
]


class CadProbeBatchCommand(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    packet_kind: str = ""
    packet_readiness: str = ""
    route_kind: str = ""
    fixture: str = ""
    live_execution_allowed: bool = False
    package_available: bool = False
    file_artifact_required: bool = False
    static_owner_required: bool = False
    required_sections: tuple[str, ...] = ()
    first_blocker: str = ""
    next_action: str = ""
    priority_score: int = 0


class CadProbeBatch(FrozenModel):
    batch_id: str = Field(min_length=1)
    batch_kind: ProbeBatchKind
    packet_kind: str = ""
    label: str
    live_execution_allowed: bool = False
    command_count: int = 0
    commands: tuple[CadProbeBatchCommand, ...] = ()
    required_safety_gates: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


@dataclass(frozen=True)
class CadProbeBatchPlan:
    batches: dict[str, CadProbeBatch]
    kb_root: str
    generated_utc: str = ""

    def get(self, batch_id: str) -> CadProbeBatch:
        return self.batches[batch_id]

    def all_batches(self) -> list[CadProbeBatch]:
        return [self.batches[key] for key in sorted(self.batches)]

    def summary(self) -> dict[str, Any]:
        batch_kind_counts: dict[str, int] = {}
        command_kind_counts: dict[str, int] = {}
        packet_kind_counts: dict[str, int] = {}
        command_count = 0
        live_allowed = 0
        file_artifacts = 0
        static_owners = 0
        for batch in self.batches.values():
            batch_kind_counts[batch.batch_kind] = batch_kind_counts.get(batch.batch_kind, 0) + 1
            command_kind_counts[batch.batch_kind] = command_kind_counts.get(batch.batch_kind, 0) + batch.command_count
            if batch.packet_kind:
                packet_kind_counts[batch.packet_kind] = packet_kind_counts.get(batch.packet_kind, 0) + batch.command_count
            command_count += batch.command_count
            for command in batch.commands:
                live_allowed += int(command.live_execution_allowed)
                file_artifacts += int(command.file_artifact_required)
                static_owners += int(command.static_owner_required)
        return {
            "batch_count": len(self.batches),
            "command_count": command_count,
            "batch_kind_counts": dict(sorted(batch_kind_counts.items())),
            "command_kind_counts": dict(sorted(command_kind_counts.items())),
            "packet_kind_command_counts": dict(sorted(packet_kind_counts.items())),
            "live_execution_allowed_count": live_allowed,
            "file_artifact_command_count": file_artifacts,
            "static_owner_command_count": static_owners,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_probe_batch_plan(kb_root: str | Path | None = None) -> CadProbeBatchPlan:
    catalog = build_cad_evidence_packet_catalog(kb_root)
    grouped: dict[tuple[ProbeBatchKind, str], list[CadProbeEvidencePacketPlan]] = {}
    for packet in catalog.all_packets():
        batch_kind = _batch_kind(packet)
        grouped.setdefault((batch_kind, packet.packet_kind), []).append(packet)
    batches: dict[str, CadProbeBatch] = {}
    for (batch_kind, packet_kind), packets in grouped.items():
        commands = tuple(sorted((_command(packet) for packet in packets), key=lambda item: (-item.priority_score, item.command_id)))
        batch_id = f"{batch_kind}:{packet_kind}"
        batches[batch_id] = CadProbeBatch(
            batch_id=batch_id,
            batch_kind=batch_kind,
            packet_kind=packet_kind,
            label=f"{_batch_label(batch_kind)} / {packet_kind}",
            live_execution_allowed=batch_kind == "ready_live_capture",
            command_count=len(commands),
            commands=commands,
            required_safety_gates=_safety_gates(batch_kind, packet_kind),
            required_outputs=_required_outputs(batch_kind, packet_kind),
            success_criteria=_success_criteria(batch_kind, packet_kind),
            next_action=_next_action(batch_kind, commands),
        )
    return CadProbeBatchPlan(
        batches=batches,
        kb_root=catalog.kb_root,
        generated_utc=catalog.generated_utc,
    )


def _batch_kind(packet: CadProbeEvidencePacketPlan) -> ProbeBatchKind:
    if packet.readiness == "ready_to_capture":
        return "ready_live_capture"
    if packet.readiness == "waiting_for_probe_package":
        return "probe_package_generation"
    if packet.readiness == "waiting_for_static_owner":
        return "static_owner_resolution"
    if packet.readiness == "captured_but_not_promotable":
        return "post_capture_promotion"
    return "safety_gate_repair"


def _command(packet: CadProbeEvidencePacketPlan) -> CadProbeBatchCommand:
    return CadProbeBatchCommand(
        command_id=packet.command_id,
        label=packet.label,
        packet_kind=packet.packet_kind,
        packet_readiness=packet.readiness,
        route_kind=packet.route_kind,
        fixture=packet.fixture,
        live_execution_allowed=packet.live_execution_allowed,
        package_available=packet.package_available,
        file_artifact_required=packet.file_artifact_required,
        static_owner_required=packet.static_owner_required,
        required_sections=packet.required_section_ids,
        first_blocker=packet.blockers[0] if packet.blockers else "",
        next_action=packet.next_action,
        priority_score=_priority_score(packet),
    )


def _priority_score(packet: CadProbeEvidencePacketPlan) -> int:
    score = {
        "ready_to_capture": 1000,
        "captured_but_not_promotable": 700,
        "planning_only_missing_gates": 500,
        "waiting_for_static_owner": 400,
        "waiting_for_probe_package": 100,
    }.get(packet.readiness, 0)
    score += {
        "file_interop_packet": 80,
        "fixture_mutation_packet": 70,
        "static_owner_packet": 60,
        "selection_state_packet": 40,
        "safe_parameter_packet": 30,
        "viewport_state_packet": 20,
    }.get(packet.packet_kind, 0)
    if packet.command_id == "export_mesh":
        score += 200
    if packet.command_id in {"face_change", "xnurbs"}:
        score += 150
    return score + len(packet.required_section_ids)


def _batch_label(batch_kind: ProbeBatchKind) -> str:
    return {
        "ready_live_capture": "Ready Live Capture",
        "probe_package_generation": "Probe Package Generation",
        "static_owner_resolution": "Static Owner Resolution",
        "safety_gate_repair": "Safety Gate Repair",
        "post_capture_promotion": "Post-Capture Promotion",
    }[batch_kind]


def _safety_gates(batch_kind: ProbeBatchKind, packet_kind: str) -> tuple[str, ...]:
    gates = ["automation_route", "probe_package", "reset_verification"]
    if batch_kind in {"ready_live_capture", "safety_gate_repair"}:
        gates.append("disposable_fixture")
    if packet_kind == "file_interop_packet":
        gates.extend(["workspace_write_scope", "workspace_controlled_path"])
    if packet_kind == "static_owner_packet":
        gates.append("owner_command_resolution")
    return tuple(dict.fromkeys(gates))


def _required_outputs(batch_kind: ProbeBatchKind, packet_kind: str) -> tuple[str, ...]:
    if batch_kind == "probe_package_generation":
        return ("parameter_probe_package", "evidence_capture_plan", "reset_plan")
    if batch_kind == "static_owner_resolution":
        return ("negative_palette_screenshot", "candidate_owner_panel_screenshots", "owner_classification")
    if batch_kind == "safety_gate_repair":
        return ("repaired_automation_route", "recomputed_evidence_packet")
    if batch_kind == "post_capture_promotion":
        return ("updated_observation_ledger", "schema_promotion_status")
    outputs = ["baseline_state", "parameter_panel", "option_panel", "reset_verification", "observation_record"]
    if packet_kind in {"fixture_mutation_packet", "file_interop_packet"}:
        outputs.extend(["topology_delta", "failure_tolerance"])
    if packet_kind == "file_interop_packet":
        outputs.append("file_artifact_record")
    if packet_kind == "selection_state_packet":
        outputs.append("selection_state_delta")
    if packet_kind == "viewport_state_packet":
        outputs.append("viewport_state_delta")
    return tuple(outputs)


def _success_criteria(batch_kind: ProbeBatchKind, packet_kind: str) -> tuple[str, ...]:
    if batch_kind == "ready_live_capture":
        return ("all required packet sections filled", "validation checks recorded", "reset verified", "ledger refreshed")
    if batch_kind == "probe_package_generation":
        return ("package exists", "fixture setup documented", "evidence fields documented", "reset strategy documented")
    if batch_kind == "static_owner_resolution":
        return ("owner command identified or unresolved evidence recorded", "standalone promotion remains blocked until owner exists")
    if batch_kind == "post_capture_promotion":
        return ("promotion blockers reduced", "descriptor-ready schema generated when gates pass")
    return ("missing safety gate repaired", "packet readiness recalculated")


def _next_action(batch_kind: ProbeBatchKind, commands: tuple[CadProbeBatchCommand, ...]) -> str:
    if not commands:
        return "no commands in batch"
    first = commands[0]
    if batch_kind == "ready_live_capture":
        return f"capture evidence packet for {first.command_id}"
    if batch_kind == "probe_package_generation":
        return f"generate probe package for {first.command_id}"
    if batch_kind == "static_owner_resolution":
        return f"resolve static owner for {first.command_id}"
    if batch_kind == "post_capture_promotion":
        return f"complete schema promotion blockers for {first.command_id}"
    return f"repair safety gate for {first.command_id}: {first.first_blocker}"


__all__ = [
    "CadProbeBatch",
    "CadProbeBatchCommand",
    "CadProbeBatchPlan",
    "ProbeBatchKind",
    "build_cad_probe_batch_plan",
]
