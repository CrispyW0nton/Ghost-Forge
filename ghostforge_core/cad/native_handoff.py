"""Native Ghost Forge CAD implementation handoffs from validated observations.

Once Plasticity observations validate, Ghost Forge still needs a disciplined
handoff into product work: descriptor edits, Qt panel schema changes, handler
tests, robustness assertions, file interop contracts, and static-owner
relationships.  This module converts accepted/rejected observation-ledger
entries into that implementation-facing work queue.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .development_queue import GhostForgeCadDevelopmentTask, build_ghostforge_cad_development_queue
from .observation_ledger import CadObservationLedgerEntry, load_cad_observation_ledger


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


HandoffStatus = Literal[
    "ready_for_native_application",
    "partial_evidence_available",
    "ready_for_static_owner_application",
    "blocked_by_validation",
]


class CadNativeHandoffStep(FrozenModel):
    step_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    action: str
    required_inputs: tuple[str, ...] = ()
    produced_artifacts: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()


class CadNativeImplementationHandoff(FrozenModel):
    handoff_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    label: str = ""
    implementation_track: str = ""
    ledger_entry_id: str = ""
    validation_status: str = ""
    handoff_status: HandoffStatus
    promotion_targets: tuple[str, ...] = ()
    source_file: str = ""
    observed_parameters: tuple[str, ...] = ()
    accepted_sections: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    steps: tuple[CadNativeHandoffStep, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


@dataclass(frozen=True)
class CadNativeImplementationHandoffCatalog:
    handoffs: dict[str, CadNativeImplementationHandoff]
    kb_root: str

    def get(self, handoff_id: str) -> CadNativeImplementationHandoff:
        return self.handoffs[handoff_id]

    def all_handoffs(self) -> list[CadNativeImplementationHandoff]:
        return [self.handoffs[key] for key in sorted(self.handoffs)]

    def handoffs_for_command(self, command_id: str) -> list[CadNativeImplementationHandoff]:
        return [handoff for handoff in self.all_handoffs() if handoff.command_id == command_id]

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        track_counts: dict[str, int] = {}
        target_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        step_count = 0
        for handoff in self.handoffs.values():
            status_counts[handoff.handoff_status] = status_counts.get(handoff.handoff_status, 0) + 1
            track_counts[handoff.implementation_track or "<missing>"] = track_counts.get(handoff.implementation_track or "<missing>", 0) + 1
            step_count += len(handoff.steps)
            for target in handoff.promotion_targets:
                target_counts[target] = target_counts.get(target, 0) + 1
            for blocker in handoff.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "handoff_count": len(self.handoffs),
            "command_count": len({handoff.command_id for handoff in self.handoffs.values()}),
            "step_count": step_count,
            "handoff_status_counts": dict(sorted(status_counts.items())),
            "implementation_track_counts": dict(sorted(track_counts.items())),
            "promotion_target_counts": dict(sorted(target_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_native_handoff_catalog(kb_root: str | Path | None = None) -> CadNativeImplementationHandoffCatalog:
    ledger = load_cad_observation_ledger(kb_root)
    queue = build_ghostforge_cad_development_queue(kb_root)
    handoffs: dict[str, CadNativeImplementationHandoff] = {}
    for entry in ledger.all_entries():
        task = queue.tasks.get(entry.command_id)
        handoff = _handoff(entry, task)
        handoffs[handoff.handoff_id] = handoff
    return CadNativeImplementationHandoffCatalog(
        handoffs=handoffs,
        kb_root=ledger.kb_root,
    )


def _handoff(
    entry: CadObservationLedgerEntry,
    task: GhostForgeCadDevelopmentTask | None,
) -> CadNativeImplementationHandoff:
    status = _handoff_status(entry)
    steps = _steps(entry) if status != "blocked_by_validation" else ()
    blockers = entry.validation.blockers
    if task and task.blockers and status != "blocked_by_validation":
        blockers = tuple(dict.fromkeys((*blockers, *task.blockers)))
    return CadNativeImplementationHandoff(
        handoff_id=f"{entry.command_id}:{entry.source_index}",
        command_id=entry.command_id,
        label=task.label if task else entry.command_id,
        implementation_track=task.implementation_track if task else "",
        ledger_entry_id=entry.entry_id,
        validation_status=entry.validation.status,
        handoff_status=status,
        promotion_targets=entry.validation.promotion_targets,
        source_file=entry.source_file,
        observed_parameters=entry.validation.observed_parameters,
        accepted_sections=entry.validation.accepted_sections,
        blockers=blockers,
        steps=steps,
        next_action=_next_action(status, steps, blockers),
    )


def _handoff_status(entry: CadObservationLedgerEntry) -> HandoffStatus:
    if entry.validation.status == "accepted_for_promotion":
        return "ready_for_native_application"
    if entry.validation.status == "accepted_for_static_owner":
        return "ready_for_static_owner_application"
    if entry.validation.status == "accepted_for_partial":
        return "partial_evidence_available"
    return "blocked_by_validation"


def _steps(entry: CadObservationLedgerEntry) -> tuple[CadNativeHandoffStep, ...]:
    steps: list[CadNativeHandoffStep] = []
    targets = set(entry.validation.promotion_targets)
    if {"schema_promotion", "qt_option_panel", "mcp_payload_schema"} & targets:
        steps.append(
            CadNativeHandoffStep(
                step_id="apply_descriptor_schema",
                target="cad_command_descriptor",
                action="Promote observed controls into the native command parameter and option-panel schema.",
                required_inputs=("observed_parameters", "captured_parameter_panel", "reset_verification"),
                produced_artifacts=("ParameterSpec updates", "Qt panel schema", "MCP payload schema"),
                verification=("schema promotion gates pass", "descriptor tests cover observed controls"),
            )
        )
    if {"fixture_behavior_parity", "native_handler_tests"} & targets:
        steps.append(
            CadNativeHandoffStep(
                step_id="apply_fixture_behavior",
                target="native_handler_tests",
                action="Convert captured topology delta and fixture behavior into Ghost Forge handler regression tests.",
                required_inputs=("topology_delta", "accepted_sections"),
                produced_artifacts=("fixture behavior case update", "handler regression test"),
                verification=("topology id lineage assertions pass", "undo/reset behavior is covered"),
            )
        )
    if "robustness_catalog" in targets:
        steps.append(
            CadNativeHandoffStep(
                step_id="apply_robustness_contract",
                target="robustness_catalog",
                action="Promote captured failure, tolerance, topology naming, and lineage evidence into robustness contracts.",
                required_inputs=("failure_tolerance", "topology_delta"),
                produced_artifacts=("failure contract update", "tolerance contract update"),
                verification=("failure codes are structured", "tolerance boundaries have tests"),
            )
        )
    if {"interop_contract", "manifest_artifact_policy"} & targets:
        steps.append(
            CadNativeHandoffStep(
                step_id="apply_interop_contract",
                target="file_interop",
                action="Promote captured import/export options and artifact diagnostics into native interop format contracts.",
                required_inputs=("file_artifact", "observed_controls", "translator_diagnostics"),
                produced_artifacts=("InteropFormatDescriptor update", "manifest artifact policy"),
                verification=("workspace path safety tests pass", "translator diagnostics are represented"),
            )
        )
    if {"registry_relationships", "schema_drafts"} & targets:
        steps.append(
            CadNativeHandoffStep(
                step_id="apply_static_owner_relationship",
                target="cad_registry_relationships",
                action="Apply static-asset owner classification as command, alias, option, contextual mode, or tutorial/media evidence.",
                required_inputs=("static_owner_classification", "negative_palette_evidence", "owner_panel_evidence"),
                produced_artifacts=("registry relationship update", "schema draft relationship update"),
                verification=("static asset is not promoted as a standalone command unless classified as command",),
            )
        )
    return tuple(steps)


def _next_action(
    status: HandoffStatus,
    steps: tuple[CadNativeHandoffStep, ...],
    blockers: tuple[str, ...],
) -> str:
    if status == "blocked_by_validation":
        return f"fix capture blocker before native application: {blockers[0]}" if blockers else "fix validation blocker before native application"
    if steps:
        return f"implement handoff step: {steps[0].step_id}"
    if blockers:
        return f"resolve implementation blocker: {blockers[0]}"
    return "review accepted evidence and apply native Ghost Forge updates"


__all__ = [
    "CadNativeHandoffStep",
    "CadNativeImplementationHandoff",
    "CadNativeImplementationHandoffCatalog",
    "HandoffStatus",
    "build_cad_native_handoff_catalog",
]
