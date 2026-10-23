"""Capture campaign planning for Plasticity-to-Ghost-Forge CAD recon.

This layer answers the operational question after packet/session/ledger/handoff
planning: what should be captured next, what is blocked, and what already has
enough validated evidence to move into native Ghost Forge implementation?
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .live_probe_sessions import CadLiveProbeSessionPlan, build_cad_live_probe_session_catalog
from .native_handoff import CadNativeImplementationHandoff, build_cad_native_handoff_catalog
from .observation_ledger import CadObservationLedgerEntry, load_cad_observation_ledger


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


CaptureCampaignStatus = Literal[
    "ready_to_capture",
    "handoff_ready",
    "partial_capture_needs_followup",
    "recapture_required",
    "blocked_package_needed",
    "blocked_static_owner_resolution",
    "blocked_safety_gate",
]


class CadCaptureCampaignItem(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    status: CaptureCampaignStatus
    session_mode: str = ""
    packet_kind: str = ""
    fixture: str = ""
    batch_id: str = ""
    live_execution_allowed: bool = False
    file_touching: bool = False
    required_sections: tuple[str, ...] = ()
    required_safety_gates: tuple[str, ...] = ()
    latest_ledger_status: str = ""
    latest_handoff_status: str = ""
    handoff_targets: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    required_outputs: tuple[str, ...] = ()
    ledger_filename: str = "cad_live_observation_records.json"
    priority_score: int = 0
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


@dataclass(frozen=True)
class CadCaptureCampaignCatalog:
    items: dict[str, CadCaptureCampaignItem]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadCaptureCampaignItem:
        return self.items[command_id]

    def all_items(self) -> list[CadCaptureCampaignItem]:
        return [self.items[key] for key in sorted(self.items)]

    def by_status(self, status: str) -> list[CadCaptureCampaignItem]:
        return [item for item in self.all_items() if item.status == status]

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        packet_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        ready = 0
        file_touching = 0
        handoff_ready = 0
        for item in self.items.values():
            status_counts[item.status] = status_counts.get(item.status, 0) + 1
            packet_counts[item.packet_kind or "<missing>"] = packet_counts.get(item.packet_kind or "<missing>", 0) + 1
            ready += int(item.status == "ready_to_capture")
            handoff_ready += int(item.status == "handoff_ready")
            file_touching += int(item.file_touching)
            for blocker in item.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "item_count": len(self.items),
            "status_counts": dict(sorted(status_counts.items())),
            "packet_kind_counts": dict(sorted(packet_counts.items())),
            "ready_to_capture_count": ready,
            "handoff_ready_count": handoff_ready,
            "file_touching_count": file_touching,
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_capture_campaign_catalog(kb_root: str | Path | None = None) -> CadCaptureCampaignCatalog:
    sessions = build_cad_live_probe_session_catalog(kb_root)
    ledger = load_cad_observation_ledger(kb_root)
    handoffs = build_cad_native_handoff_catalog(kb_root)
    latest_ledger = {entry.command_id: entry for entry in ledger.all_entries()}
    latest_handoff = {handoff.command_id: handoff for handoff in handoffs.all_handoffs()}
    items = {
        session.command_id: _campaign_item(
            session=session,
            ledger_entry=latest_ledger.get(session.command_id),
            handoff=latest_handoff.get(session.command_id),
        )
        for session in sessions.all_sessions()
    }
    return CadCaptureCampaignCatalog(
        items=items,
        kb_root=sessions.kb_root,
        generated_utc=sessions.generated_utc,
    )


def _campaign_item(
    *,
    session: CadLiveProbeSessionPlan,
    ledger_entry: CadObservationLedgerEntry | None,
    handoff: CadNativeImplementationHandoff | None,
) -> CadCaptureCampaignItem:
    status = _status(session, ledger_entry, handoff)
    blockers = _blockers(session, ledger_entry, handoff, status)
    outputs = _required_outputs(session, status)
    handoff_targets = handoff.promotion_targets if handoff else ()
    return CadCaptureCampaignItem(
        command_id=session.command_id,
        label=session.label,
        status=status,
        session_mode=session.session_mode,
        packet_kind=session.packet_kind,
        fixture=session.fixture,
        batch_id=session.batch_id,
        live_execution_allowed=session.live_execution_allowed,
        file_touching=any(step.touches_files for step in session.steps),
        required_sections=session.required_sections,
        required_safety_gates=session.required_safety_gates,
        latest_ledger_status=ledger_entry.validation.status if ledger_entry else "",
        latest_handoff_status=handoff.handoff_status if handoff else "",
        handoff_targets=handoff_targets,
        blockers=blockers,
        required_outputs=outputs,
        ledger_filename=_ledger_filename(session),
        priority_score=_priority_score(status, session),
        next_action=_next_action(status, session, handoff, blockers),
    )


def _status(
    session: CadLiveProbeSessionPlan,
    ledger_entry: CadObservationLedgerEntry | None,
    handoff: CadNativeImplementationHandoff | None,
) -> CaptureCampaignStatus:
    if handoff and handoff.handoff_status in {"ready_for_native_application", "ready_for_static_owner_application"}:
        return "handoff_ready"
    if ledger_entry and ledger_entry.validation.status == "accepted_for_partial":
        return "partial_capture_needs_followup"
    if ledger_entry and ledger_entry.validation.status.startswith("rejected_"):
        return "recapture_required"
    if session.session_mode == "ready_for_manual_live_capture":
        return "ready_to_capture"
    if any("probe_package_missing" in blocker for blocker in session.blockers):
        return "blocked_package_needed"
    if "static_owner_classification" in session.required_sections or any("owner" in blocker for blocker in session.blockers):
        return "blocked_static_owner_resolution"
    return "blocked_safety_gate"


def _blockers(
    session: CadLiveProbeSessionPlan,
    ledger_entry: CadObservationLedgerEntry | None,
    handoff: CadNativeImplementationHandoff | None,
    status: CaptureCampaignStatus,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if status == "handoff_ready":
        blockers.extend(handoff.blockers if handoff else ())
    elif ledger_entry:
        blockers.extend(ledger_entry.validation.blockers)
    else:
        blockers.extend(session.blockers)
    return tuple(dict.fromkeys(blocker for blocker in blockers if blocker))


def _required_outputs(session: CadLiveProbeSessionPlan, status: CaptureCampaignStatus) -> tuple[str, ...]:
    if status == "handoff_ready":
        return ("native_handoff_applied", "descriptor_or_relationship_update", "verification_tests")
    if status == "blocked_package_needed":
        return ("probe_package", "evidence_capture_plan", "reset_plan")
    if status == "blocked_static_owner_resolution":
        return ("negative_palette_evidence", "candidate_owner_panels", "owner_classification")
    outputs = ["observation_record", "validation_report", "reset_verification"]
    for step in session.steps:
        outputs.extend(step.expected_outputs)
    return tuple(dict.fromkeys(outputs))


def _ledger_filename(session: CadLiveProbeSessionPlan) -> str:
    if "static_owner_classification" in session.required_sections:
        return "cad_observation_records.json"
    return "cad_live_observation_records.json"


def _priority_score(status: CaptureCampaignStatus, session: CadLiveProbeSessionPlan) -> int:
    score = {
        "ready_to_capture": 1000,
        "recapture_required": 900,
        "partial_capture_needs_followup": 800,
        "handoff_ready": 700,
        "blocked_static_owner_resolution": 450,
        "blocked_safety_gate": 250,
        "blocked_package_needed": 100,
    }[status]
    if session.packet_kind == "file_interop_packet":
        score += 80
    if session.packet_kind == "fixture_mutation_packet":
        score += 70
    if session.command_id == "export_mesh":
        score += 200
    if session.command_id in {"face_change", "xnurbs"}:
        score += 150
    return score + len(session.required_sections)


def _next_action(
    status: CaptureCampaignStatus,
    session: CadLiveProbeSessionPlan,
    handoff: CadNativeImplementationHandoff | None,
    blockers: tuple[str, ...],
) -> str:
    if status == "handoff_ready":
        return handoff.next_action if handoff else "apply validated native handoff"
    if status == "ready_to_capture":
        return f"run live session and append record to {_ledger_filename(session)}"
    if status == "recapture_required":
        return f"recapture {session.command_id} and replace rejected ledger evidence"
    if status == "partial_capture_needs_followup":
        return f"capture missing evidence for {session.command_id}"
    if status == "blocked_package_needed":
        return f"generate probe package for {session.command_id}"
    if status == "blocked_static_owner_resolution":
        return f"resolve owner classification for {session.command_id}"
    return f"repair blocker for {session.command_id}: {blockers[0]}" if blockers else session.next_action


__all__ = [
    "CadCaptureCampaignCatalog",
    "CadCaptureCampaignItem",
    "CaptureCampaignStatus",
    "build_cad_capture_campaign_catalog",
]
