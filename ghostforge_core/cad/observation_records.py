"""Validation records for completed CAD live-probe observations.

Evidence packets and live-probe sessions define what to capture from
Plasticity.  This module is the receiving gate: a captured observation must
validate here before it can influence Ghost Forge native schemas, behavior
fixtures, interop contracts, or static-asset classification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_packets import build_cad_evidence_packet_catalog
from .live_probe_sessions import CadLiveProbeSessionPlan, build_cad_live_probe_session_catalog


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


ObservationSectionStatus = Literal["captured", "missing", "failed", "not_applicable"]
ObservationValidationStatus = Literal[
    "accepted_for_promotion",
    "accepted_for_partial",
    "accepted_for_static_owner",
    "rejected_unknown_command",
    "rejected_blocked_session",
    "rejected_missing_evidence",
    "rejected_failed_checks",
]


class CadObservedControl(FrozenModel):
    control_id: str = Field(min_length=1)
    label: str = ""
    control_type: str = ""
    maps_to_parameter: str = ""
    default_value: Any = None
    current_value: Any = None
    option_values: tuple[Any, ...] = ()
    unit: str = ""
    confidence: str = ""
    evidence_refs: tuple[str, ...] = ()
    notes: str = ""

    @property
    def is_usable(self) -> bool:
        return bool(self.maps_to_parameter and self.control_type and self.evidence_refs)


class CadCapturedEvidenceSection(FrozenModel):
    section_id: str = Field(min_length=1)
    status: ObservationSectionStatus = "missing"
    evidence_refs: tuple[str, ...] = ()
    fields: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""

    @property
    def is_captured(self) -> bool:
        return self.status == "captured" and bool(self.evidence_refs or self.fields)


class CadObservationValidationResult(FrozenModel):
    check_id: str = Field(min_length=1)
    passed: bool
    evidence_refs: tuple[str, ...] = ()
    notes: str = ""


class CadTopologyObservation(FrozenModel):
    before_counts: dict[str, int] = Field(default_factory=dict)
    after_counts: dict[str, int] = Field(default_factory=dict)
    created_ids: tuple[str, ...] = ()
    deleted_ids: tuple[str, ...] = ()
    modified_ids: tuple[str, ...] = ()
    lineage_map: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_captured(self) -> bool:
        return bool(self.evidence_refs and (self.after_counts or self.created_ids or self.deleted_ids or self.modified_ids))


class CadFileArtifactObservation(FrozenModel):
    path: str = ""
    format_id: str = ""
    operation: Literal["import", "export", "unknown"] = "unknown"
    translator_diagnostics: tuple[str, ...] = ()
    source_topology_preserved: bool | None = None
    evidence_refs: tuple[str, ...] = ()

    @property
    def is_captured(self) -> bool:
        return bool(self.path and self.format_id and self.evidence_refs)


class CadStaticOwnerObservation(FrozenModel):
    static_asset_id: str = ""
    classification: Literal["command", "alias", "option", "contextual_mode", "tutorial_or_media", "unresolved"] = "unresolved"
    owner_command_id: str = ""
    negative_palette_evidence_refs: tuple[str, ...] = ()
    owner_panel_evidence_refs: tuple[str, ...] = ()
    notes: str = ""

    @property
    def is_classified(self) -> bool:
        if self.classification == "unresolved":
            return False
        if self.classification in {"option", "contextual_mode", "alias"}:
            return bool(self.owner_command_id and self.owner_panel_evidence_refs)
        return bool(self.negative_palette_evidence_refs or self.owner_panel_evidence_refs)


class CadLiveProbeObservationRecord(FrozenModel):
    command_id: str = Field(min_length=1)
    plasticity_version: str = ""
    probe_timestamp: str = ""
    fixture: str = ""
    session_mode: str = ""
    captured_sections: tuple[CadCapturedEvidenceSection, ...] = ()
    observed_controls: tuple[CadObservedControl, ...] = ()
    validation_results: tuple[CadObservationValidationResult, ...] = ()
    topology_delta: CadTopologyObservation | None = None
    file_artifacts: tuple[CadFileArtifactObservation, ...] = ()
    static_owner_classification: CadStaticOwnerObservation | None = None
    reset_verified: bool = False
    notes: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


class CadObservationValidationReport(FrozenModel):
    command_id: str = Field(min_length=1)
    status: ObservationValidationStatus
    session_mode: str = ""
    required_sections: tuple[str, ...] = ()
    accepted_sections: tuple[str, ...] = ()
    missing_sections: tuple[str, ...] = ()
    failed_sections: tuple[str, ...] = ()
    required_parameters: tuple[str, ...] = ()
    observed_parameters: tuple[str, ...] = ()
    missing_parameters: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    promotion_targets: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


@dataclass(frozen=True)
class CadObservationTemplateCatalog:
    templates: dict[str, CadLiveProbeObservationRecord]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadLiveProbeObservationRecord:
        return self.templates[command_id]

    def all_templates(self) -> list[CadLiveProbeObservationRecord]:
        return [self.templates[key] for key in sorted(self.templates)]

    def summary(self) -> dict[str, Any]:
        return {
            "template_count": len(self.templates),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_observation_template_catalog(kb_root: str | Path | None = None) -> CadObservationTemplateCatalog:
    sessions = build_cad_live_probe_session_catalog(kb_root)
    packets = build_cad_evidence_packet_catalog(kb_root)
    templates = {
        session.command_id: _template_for_session(session, packets.get(session.command_id).parameter_names)
        for session in sessions.all_sessions()
    }
    return CadObservationTemplateCatalog(
        templates=templates,
        kb_root=sessions.kb_root,
        generated_utc=sessions.generated_utc,
    )


def observation_template_for_command(
    command_id: str,
    kb_root: str | Path | None = None,
) -> CadLiveProbeObservationRecord:
    return build_cad_observation_template_catalog(kb_root).get(command_id)


def validate_cad_observation_record(
    record: CadLiveProbeObservationRecord | dict[str, Any],
    kb_root: str | Path | None = None,
) -> CadObservationValidationReport:
    observation = (
        record
        if isinstance(record, CadLiveProbeObservationRecord)
        else CadLiveProbeObservationRecord.model_validate(record)
    )
    try:
        sessions = build_cad_live_probe_session_catalog(kb_root)
        packets = build_cad_evidence_packet_catalog(kb_root)
        session = sessions.get(observation.command_id)
        packet = packets.get(observation.command_id)
    except KeyError:
        return CadObservationValidationReport(
            command_id=observation.command_id,
            status="rejected_unknown_command",
            blockers=("command_not_found_in_live_probe_catalog",),
            next_action="add or refresh the recon catalog before validating this observation",
        )

    required_sections = session.required_sections
    section_map = {section.section_id: section for section in observation.captured_sections}
    accepted_sections = tuple(
        section_id
        for section_id in required_sections
        if section_id in section_map and section_map[section_id].is_captured
    )
    failed_sections = tuple(
        section.section_id
        for section in observation.captured_sections
        if section.status == "failed"
    )
    missing_sections = tuple(section_id for section_id in required_sections if section_id not in accepted_sections)
    required_parameters = packet.parameter_names
    observed_parameters = _observed_parameters(observation)
    missing_parameters = tuple(name for name in required_parameters if name not in observed_parameters)
    failed_checks = tuple(result.check_id for result in observation.validation_results if not result.passed)
    blockers = _blockers(
        session=session,
        missing_sections=missing_sections,
        failed_sections=failed_sections,
        missing_parameters=missing_parameters,
        failed_checks=failed_checks,
        observation=observation,
    )
    targets = _promotion_targets(
        observation=observation,
        accepted_sections=accepted_sections,
        missing_parameters=missing_parameters,
        failed_checks=failed_checks,
    )
    status = _status(session, observation, missing_sections, missing_parameters, failed_checks, blockers)
    return CadObservationValidationReport(
        command_id=observation.command_id,
        status=status,
        session_mode=session.session_mode,
        required_sections=required_sections,
        accepted_sections=accepted_sections,
        missing_sections=missing_sections,
        failed_sections=failed_sections,
        required_parameters=required_parameters,
        observed_parameters=observed_parameters,
        missing_parameters=missing_parameters,
        failed_checks=failed_checks,
        promotion_targets=targets,
        blockers=blockers,
        warnings=_warnings(session, observation),
        next_action=_next_action(status, blockers, missing_sections, missing_parameters),
    )


def _template_for_session(
    session: CadLiveProbeSessionPlan,
    parameter_names: tuple[str, ...],
) -> CadLiveProbeObservationRecord:
    sections = tuple(
        CadCapturedEvidenceSection(section_id=section_id, status="missing")
        for section_id in session.required_sections
    )
    controls = tuple(
        CadObservedControl(
            control_id=f"{session.command_id}.{parameter}",
            maps_to_parameter=parameter,
        )
        for parameter in parameter_names
    )
    return CadLiveProbeObservationRecord(
        command_id=session.command_id,
        fixture=session.fixture,
        session_mode=session.session_mode,
        captured_sections=sections,
        observed_controls=controls,
        reset_verified=False,
    )


def _observed_parameters(observation: CadLiveProbeObservationRecord) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for control in observation.observed_controls:
        if not control.is_usable:
            continue
        if control.maps_to_parameter in seen:
            continue
        seen.add(control.maps_to_parameter)
        out.append(control.maps_to_parameter)
    return tuple(out)


def _blockers(
    *,
    session: CadLiveProbeSessionPlan,
    missing_sections: tuple[str, ...],
    failed_sections: tuple[str, ...],
    missing_parameters: tuple[str, ...],
    failed_checks: tuple[str, ...],
    observation: CadLiveProbeObservationRecord,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if session.session_mode == "blocked" and not _static_owner_capture_valid(observation):
        blockers.append("session.blocked")
    blockers.extend(f"section.{section}.missing" for section in missing_sections)
    blockers.extend(f"section.{section}.failed" for section in failed_sections)
    blockers.extend(f"parameter.{parameter}.missing_observed_control" for parameter in missing_parameters)
    blockers.extend(f"validation.{check}.failed" for check in failed_checks)
    if "reset_verification" in session.required_sections and not observation.reset_verified:
        blockers.append("reset_verification.missing")
    if _requires_file_artifact(session) and not any(artifact.is_captured for artifact in observation.file_artifacts):
        blockers.append("file_artifact.missing")
    if _requires_static_owner(session) and not _static_owner_capture_valid(observation):
        blockers.append("static_owner_classification.missing")
    return tuple(dict.fromkeys(blockers))


def _promotion_targets(
    *,
    observation: CadLiveProbeObservationRecord,
    accepted_sections: tuple[str, ...],
    missing_parameters: tuple[str, ...],
    failed_checks: tuple[str, ...],
) -> tuple[str, ...]:
    targets: list[str] = []
    if "parameter_panel" in accepted_sections and not missing_parameters and not failed_checks and observation.reset_verified:
        targets.extend(["schema_promotion", "qt_option_panel", "mcp_payload_schema"])
    if "topology_delta" in accepted_sections and observation.topology_delta and observation.topology_delta.is_captured:
        targets.extend(["fixture_behavior_parity", "robustness_catalog", "native_handler_tests"])
    if "file_artifact" in accepted_sections and any(artifact.is_captured for artifact in observation.file_artifacts):
        targets.extend(["interop_contract", "manifest_artifact_policy"])
    if "static_owner_classification" in accepted_sections and _static_owner_capture_valid(observation):
        targets.extend(["registry_relationships", "schema_drafts"])
    return tuple(dict.fromkeys(targets))


def _status(
    session: CadLiveProbeSessionPlan,
    observation: CadLiveProbeObservationRecord,
    missing_sections: tuple[str, ...],
    missing_parameters: tuple[str, ...],
    failed_checks: tuple[str, ...],
    blockers: tuple[str, ...],
) -> ObservationValidationStatus:
    if "session.blocked" in blockers:
        return "rejected_blocked_session"
    if failed_checks or any(blocker.endswith(".failed") for blocker in blockers):
        return "rejected_failed_checks"
    if _requires_static_owner(session) and _static_owner_capture_valid(observation):
        return "accepted_for_static_owner"
    if missing_sections:
        return "rejected_missing_evidence"
    if missing_parameters or not observation.reset_verified:
        return "accepted_for_partial"
    return "accepted_for_promotion"


def _warnings(
    session: CadLiveProbeSessionPlan,
    observation: CadLiveProbeObservationRecord,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if observation.fixture and session.fixture and observation.fixture != session.fixture:
        warnings.append(f"fixture_mismatch:{observation.fixture}!={session.fixture}")
    if observation.session_mode and observation.session_mode != session.session_mode:
        warnings.append(f"session_mode_mismatch:{observation.session_mode}!={session.session_mode}")
    return tuple(warnings)


def _next_action(
    status: ObservationValidationStatus,
    blockers: tuple[str, ...],
    missing_sections: tuple[str, ...],
    missing_parameters: tuple[str, ...],
) -> str:
    if status == "accepted_for_promotion":
        return "refresh schema promotion, parity, behavior, robustness, and interop catalogs from this accepted observation"
    if status == "accepted_for_static_owner":
        return "apply the owner classification to registry relationships before exposing a standalone command"
    if missing_sections:
        return f"capture missing section: {missing_sections[0]}"
    if missing_parameters:
        return f"capture observed control for parameter: {missing_parameters[0]}"
    if blockers:
        return f"resolve blocker: {blockers[0]}"
    return "review the observation before promotion"


def _requires_file_artifact(session: CadLiveProbeSessionPlan) -> bool:
    return "file_artifact" in session.required_sections


def _requires_static_owner(session: CadLiveProbeSessionPlan) -> bool:
    return "static_owner_classification" in session.required_sections


def _static_owner_capture_valid(observation: CadLiveProbeObservationRecord) -> bool:
    owner = observation.static_owner_classification
    return bool(owner and owner.is_classified)


__all__ = [
    "CadCapturedEvidenceSection",
    "CadFileArtifactObservation",
    "CadLiveProbeObservationRecord",
    "CadObservationTemplateCatalog",
    "CadObservationValidationReport",
    "CadObservationValidationResult",
    "CadObservedControl",
    "CadStaticOwnerObservation",
    "CadTopologyObservation",
    "ObservationSectionStatus",
    "ObservationValidationStatus",
    "build_cad_observation_template_catalog",
    "observation_template_for_command",
    "validate_cad_observation_record",
]
