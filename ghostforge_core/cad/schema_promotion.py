"""Promotion protocol for CAD command parameter and option-panel evidence.

PlasticityMCP gives Ghost Forge two different kinds of knowledge: inferred
templates and observed evidence.  Those must never be treated the same.  This
module defines the promotion gates that decide when a command's Plasticity
observation is strong enough to become a native Ghost Forge schema contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .automation import CadAutomationRoute, build_cad_automation_runbook
from .plasticity_recon import (
    PlasticityCommandObservationStatus,
    PlasticityCommandTemplate,
    PlasticityProbePackage,
    PlasticityProbeParameterSlot,
    load_plasticity_observation_evidence,
    load_plasticity_probe_packages,
)
from .schema import ParameterSpec
from .schema_drafts import (
    CadCommandSchemaDraft,
    CadParameterDraft,
    build_cad_schema_draft_catalog,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


PromotionStatus = Literal[
    "template_only_blocked",
    "observed_partial_blocked",
    "ready_for_observed_partial",
    "ready_for_observed_schema",
    "promotable_to_descriptor",
]

PromotionGateStatus = Literal["passed", "missing", "failed", "not_applicable"]


class CadSchemaPromotionGate(FrozenModel):
    gate_id: str = Field(min_length=1)
    status: PromotionGateStatus
    required_for_partial: bool = True
    required_for_schema: bool = True
    evidence: tuple[str, ...] = ()
    notes: str = ""


class CadObservedParameterPromotion(FrozenModel):
    name: str = Field(min_length=1)
    observed_type: str = ""
    observed_control: str = ""
    confidence: str = ""
    value_or_options: Any = None
    maps_to_template: bool = False
    maps_to_draft: bool = False
    promotion_blockers: tuple[str, ...] = ()

    @property
    def is_observed(self) -> bool:
        return bool(self.observed_control and self.confidence)


class CadSchemaPromotionCandidate(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    current_schema_status: str = ""
    promotion_status: PromotionStatus
    implementation_track: str = ""
    probe_kind: str = ""
    fixture: str = ""
    route_kind: str = ""
    live_execution_allowed: bool = False
    template_parameters: tuple[str, ...] = ()
    observed_parameters: tuple[CadObservedParameterPromotion, ...] = ()
    option_panel_groups: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    validation_checks: tuple[str, ...] = ()
    passed_validation_checks: tuple[str, ...] = ()
    failed_validation_checks: tuple[str, ...] = ()
    evidence_screenshots: tuple[str, ...] = ()
    reset_verified: bool = False
    side_effects_observed: tuple[str, ...] = ()
    gates: tuple[CadSchemaPromotionGate, ...] = ()
    blockers: tuple[str, ...] = ()
    next_action: str = ""
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"

    @property
    def ready_for_native_descriptor(self) -> bool:
        return self.promotion_status == "promotable_to_descriptor"

    def parameter_specs(self) -> tuple[ParameterSpec, ...]:
        specs: list[ParameterSpec] = []
        for parameter in self.observed_parameters:
            if not parameter.is_observed:
                continue
            values: tuple[Any, ...] = ()
            if isinstance(parameter.value_or_options, list):
                values = tuple(parameter.value_or_options)
            specs.append(
                ParameterSpec(
                    name=parameter.name,
                    type=_ghostforge_type(parameter.observed_type),
                    required=True,
                    values=values,
                    description=f"Observed Plasticity control: {parameter.observed_control}",
                    ui={
                        "control": _ui_control(parameter.observed_control, parameter.observed_type),
                        "source": "plasticity_observed_schema",
                        "confidence": parameter.confidence,
                    },
                )
            )
        return tuple(specs)


@dataclass(frozen=True)
class CadSchemaPromotionCatalog:
    candidates: dict[str, CadSchemaPromotionCandidate]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadSchemaPromotionCandidate:
        return self.candidates[command_id]

    def all_candidates(self) -> list[CadSchemaPromotionCandidate]:
        return [self.candidates[key] for key in sorted(self.candidates)]

    def by_status(self, promotion_status: str) -> list[CadSchemaPromotionCandidate]:
        return [candidate for candidate in self.all_candidates() if candidate.promotion_status == promotion_status]

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        gate_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        route_counts: dict[str, int] = {}
        observed_parameter_count = 0
        live_allowed = 0
        reset_verified = 0
        for candidate in self.candidates.values():
            status_counts[candidate.promotion_status] = status_counts.get(candidate.promotion_status, 0) + 1
            route_counts[candidate.route_kind or "<missing>"] = route_counts.get(candidate.route_kind or "<missing>", 0) + 1
            if candidate.live_execution_allowed:
                live_allowed += 1
            if candidate.reset_verified:
                reset_verified += 1
            observed_parameter_count += sum(1 for parameter in candidate.observed_parameters if parameter.is_observed)
            for gate in candidate.gates:
                if gate.status != "passed":
                    key = f"{gate.gate_id}:{gate.status}"
                    gate_counts[key] = gate_counts.get(key, 0) + 1
            for blocker in candidate.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "candidate_count": len(self.candidates),
            "promotion_status_counts": dict(sorted(status_counts.items())),
            "route_kind_counts": dict(sorted(route_counts.items())),
            "nonpassing_gate_counts": dict(sorted(gate_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "observed_parameter_count": observed_parameter_count,
            "live_execution_allowed_count": live_allowed,
            "reset_verified_count": reset_verified,
            "promotable_to_descriptor_count": status_counts.get("promotable_to_descriptor", 0),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_schema_promotion_catalog(kb_root: str | Path | None = None) -> CadSchemaPromotionCatalog:
    observation = load_plasticity_observation_evidence(kb_root)
    packages = load_plasticity_probe_packages(kb_root)
    drafts = build_cad_schema_draft_catalog(kb_root)
    runbook = build_cad_automation_runbook(kb_root)
    package_map = {package.command_id: package for package in packages.packages}
    status_map = {status.command_id: status for status in observation.commands}
    template_map = {template.command_id: template for template in observation.templates}
    candidates: dict[str, CadSchemaPromotionCandidate] = {}
    command_ids = sorted(set(status_map) | set(template_map) | set(drafts.drafts) | set(package_map))
    for command_id in command_ids:
        route = runbook.routes.get(command_id)
        candidate = _candidate(
            command_id=command_id,
            status=status_map.get(command_id),
            template=template_map.get(command_id),
            draft=drafts.drafts.get(command_id),
            package=package_map.get(command_id),
            route=route,
        )
        candidates[command_id] = candidate
    return CadSchemaPromotionCatalog(
        candidates=candidates,
        kb_root=observation.kb_root,
        generated_utc=observation.generated_utc,
    )


def _candidate(
    *,
    command_id: str,
    status: PlasticityCommandObservationStatus | None,
    template: PlasticityCommandTemplate | None,
    draft: CadCommandSchemaDraft | None,
    package: PlasticityProbePackage | None,
    route: CadAutomationRoute | None,
) -> CadSchemaPromotionCandidate:
    template_parameters = (
        tuple(parameter.name for parameter in template.parameters_to_observe)
        if template
        else (draft.template_parameters if draft else ())
    )
    observed_slots = _observed_slots(status, template, package)
    observed_parameters = tuple(
        _observed_parameter(slot, template_parameters, draft)
        for slot in observed_slots
    )
    evidence_screenshots = status.evidence_screenshots if status else ()
    validation_checks = package.validation_checks if package else (template.validation_checks if template else ())
    passed_checks = tuple(
        check.check
        for check in (package.observation_validation_results if package else ())
        if check.passed
    )
    failed_checks = tuple(
        check.check
        for check in (package.observation_validation_results if package else ())
        if not check.passed
    )
    reset_verified = bool((status and status.reset_verified) or (package and package.observation_reset_verified))
    gates = _promotion_gates(
        status=status,
        template_parameters=template_parameters,
        observed_parameters=observed_parameters,
        package=package,
        route=route,
        evidence_screenshots=evidence_screenshots,
        validation_checks=validation_checks,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        reset_verified=reset_verified,
    )
    blockers = _blockers(gates, observed_parameters, status, route)
    promotion_status = _promotion_status(gates, blockers, status, package)
    return CadSchemaPromotionCandidate(
        command_id=command_id,
        label=(status.label if status else "") or (template.label if template else "") or (draft.label if draft else ""),
        current_schema_status=(status.schema_status if status else "") or (template.schema_status if template else ""),
        promotion_status=promotion_status,
        implementation_track=draft.implementation_track if draft else (route.implementation_track if route else ""),
        probe_kind=(status.probe_kind if status else "") or (template.probe_kind if template else ""),
        fixture=(status.fixture if status else "") or (template.fixture if template else ""),
        route_kind=route.route_kind if route else "",
        live_execution_allowed=route.live_execution_allowed if route else False,
        template_parameters=template_parameters,
        observed_parameters=observed_parameters,
        option_panel_groups=tuple(group.group_id for group in draft.option_panel_groups) if draft else (),
        required_evidence=package.required_evidence if package else (),
        validation_checks=validation_checks,
        passed_validation_checks=passed_checks,
        failed_validation_checks=failed_checks,
        evidence_screenshots=evidence_screenshots,
        reset_verified=reset_verified,
        side_effects_observed=package.side_effects_observed if package else (),
        gates=gates,
        blockers=blockers,
        next_action=_next_action(promotion_status, blockers, package, route),
    )


def _observed_slots(
    status: PlasticityCommandObservationStatus | None,
    template: PlasticityCommandTemplate | None,
    package: PlasticityProbePackage | None,
) -> tuple[PlasticityProbeParameterSlot, ...]:
    if package and package.observed_parameter_slots:
        return package.observed_parameter_slots
    names: tuple[str, ...] = ()
    if status and status.missing_template_parameters:
        names = status.missing_template_parameters
    elif template:
        names = tuple(parameter.name for parameter in template.parameters_to_observe)
    return tuple(PlasticityProbeParameterSlot(name=name) for name in names)


def _observed_parameter(
    slot: PlasticityProbeParameterSlot,
    template_parameters: tuple[str, ...],
    draft: CadCommandSchemaDraft | None,
) -> CadObservedParameterPromotion:
    draft_names = {parameter.name for parameter in (draft.parameter_drafts if draft else ())}
    blockers: list[str] = []
    if not slot.observed_control:
        blockers.append("control_not_observed")
    if not slot.confidence:
        blockers.append("confidence_not_recorded")
    if slot.name not in template_parameters:
        blockers.append("not_in_template")
    if draft and slot.name not in draft_names:
        blockers.append("not_in_schema_draft")
    if slot.type == "enum" and not slot.value_or_options:
        blockers.append("enum_options_not_observed")
    return CadObservedParameterPromotion(
        name=slot.name,
        observed_type=slot.type,
        observed_control=slot.observed_control,
        confidence=slot.confidence,
        value_or_options=slot.value_or_options,
        maps_to_template=slot.name in template_parameters,
        maps_to_draft=not draft or slot.name in draft_names,
        promotion_blockers=tuple(blockers),
    )


def _promotion_gates(
    *,
    status: PlasticityCommandObservationStatus | None,
    template_parameters: tuple[str, ...],
    observed_parameters: tuple[CadObservedParameterPromotion, ...],
    package: PlasticityProbePackage | None,
    route: CadAutomationRoute | None,
    evidence_screenshots: tuple[str, ...],
    validation_checks: tuple[str, ...],
    passed_checks: tuple[str, ...],
    failed_checks: tuple[str, ...],
    reset_verified: bool,
) -> tuple[CadSchemaPromotionGate, ...]:
    observed_names = {parameter.name for parameter in observed_parameters if parameter.is_observed}
    template_names = set(template_parameters)
    all_template_observed = bool(template_names) and template_names.issubset(observed_names)
    any_parameter_observed = any(parameter.is_observed for parameter in observed_parameters)
    all_validation_passed = bool(validation_checks) and not failed_checks and set(validation_checks).issubset(set(passed_checks))
    package_available = package is not None
    route_available = route is not None
    required_evidence = set(package.required_evidence if package else ())
    evidence_present = set(evidence_screenshots)
    all_required_evidence_present = bool(required_evidence) and required_evidence.issubset(evidence_present)
    live_or_non_live_route = bool(route and (route.live_execution_allowed or route.route_kind in {"safe_parameter_probe", "viewport_state_probe", "selection_state_probe"}))
    gates = [
        CadSchemaPromotionGate(
            gate_id="probe_package_available",
            status="passed" if package_available else "missing",
            required_for_partial=True,
            required_for_schema=True,
            evidence=(package.command_id,) if package else (),
            notes="A promotion needs a reproducible probe package or equivalent observation record.",
        ),
        CadSchemaPromotionGate(
            gate_id="automation_route_available",
            status="passed" if route_available else "missing",
            required_for_partial=True,
            required_for_schema=True,
            evidence=(route.route_kind,) if route else (),
            notes="Ghost Forge must know how the evidence was gathered and reset.",
        ),
        CadSchemaPromotionGate(
            gate_id="live_or_safe_route",
            status="passed" if live_or_non_live_route else "missing",
            required_for_partial=False,
            required_for_schema=True,
            evidence=(route.route_kind,) if route else (),
            notes="Schema promotion requires a route that is safe to execute or explicitly non-mutating.",
        ),
        CadSchemaPromotionGate(
            gate_id="parameter_controls_observed",
            status="passed" if any_parameter_observed else "missing",
            required_for_partial=True,
            required_for_schema=True,
            evidence=tuple(sorted(observed_names)),
            notes="At least one concrete control must be observed for partial promotion.",
        ),
        CadSchemaPromotionGate(
            gate_id="all_template_parameters_observed",
            status="passed" if all_template_observed else "missing",
            required_for_partial=False,
            required_for_schema=True,
            evidence=tuple(sorted(observed_names)),
            notes="Observed schema promotion needs every template parameter mapped to a control.",
        ),
        CadSchemaPromotionGate(
            gate_id="required_evidence_referenced",
            status="passed" if all_required_evidence_present else "missing",
            required_for_partial=True,
            required_for_schema=True,
            evidence=evidence_screenshots,
            notes="Required screenshots/state captures must be referenced by the observation ledger.",
        ),
        CadSchemaPromotionGate(
            gate_id="validation_checks_passed",
            status="passed" if all_validation_passed else ("failed" if failed_checks else "missing"),
            required_for_partial=True,
            required_for_schema=True,
            evidence=passed_checks,
            notes="Validation checks must pass with evidence before promotion.",
        ),
        CadSchemaPromotionGate(
            gate_id="reset_verified",
            status="passed" if reset_verified else "missing",
            required_for_partial=True,
            required_for_schema=True,
            evidence=("reset_verified",) if reset_verified else (),
            notes="A command probe is not promotable until escape/undo/file cleanup restores the fixture.",
        ),
        CadSchemaPromotionGate(
            gate_id="ledger_status_matches_schema",
            status="passed" if status and status.schema_status == "observed_schema" else "missing",
            required_for_partial=False,
            required_for_schema=True,
            evidence=(status.schema_status,) if status else (),
            notes="The Plasticity observation ledger must explicitly mark observed_schema.",
        ),
    ]
    return tuple(gates)


def _blockers(
    gates: tuple[CadSchemaPromotionGate, ...],
    observed_parameters: tuple[CadObservedParameterPromotion, ...],
    status: PlasticityCommandObservationStatus | None,
    route: CadAutomationRoute | None,
) -> tuple[str, ...]:
    blockers: list[str] = []
    for gate in gates:
        if gate.status != "passed" and (gate.required_for_partial or gate.required_for_schema):
            blockers.append(f"{gate.gate_id}:{gate.status}")
    for parameter in observed_parameters:
        blockers.extend(f"parameter.{parameter.name}.{blocker}" for blocker in parameter.promotion_blockers)
    if status and status.schema_status == "template_inferred_needs_probe":
        blockers.append("ledger.template_only")
    if route:
        blockers.extend(f"automation.{gate_id}_missing" for gate_id in route.missing_required_gates)
    return tuple(dict.fromkeys(blockers))


def _promotion_status(
    gates: tuple[CadSchemaPromotionGate, ...],
    blockers: tuple[str, ...],
    status: PlasticityCommandObservationStatus | None,
    package: PlasticityProbePackage | None,
) -> PromotionStatus:
    gate_map = {gate.gate_id: gate for gate in gates}
    partial_gates_passed = all(
        gate.status == "passed"
        for gate in gates
        if gate.required_for_partial
    )
    schema_gates_passed = all(
        gate.status == "passed"
        for gate in gates
        if gate.required_for_schema
    )
    if schema_gates_passed and status and status.schema_status == "observed_schema" and not blockers:
        return "promotable_to_descriptor"
    if schema_gates_passed:
        return "ready_for_observed_schema"
    if partial_gates_passed:
        return "ready_for_observed_partial"
    if status and status.schema_status == "observed_partial":
        return "observed_partial_blocked"
    if package and package.observation_schema_status == "observed_partial" and gate_map["parameter_controls_observed"].status == "passed":
        return "observed_partial_blocked"
    return "template_only_blocked"


def _next_action(
    promotion_status: PromotionStatus,
    blockers: tuple[str, ...],
    package: PlasticityProbePackage | None,
    route: CadAutomationRoute | None,
) -> str:
    if promotion_status == "promotable_to_descriptor":
        return "promote observed parameters into native Ghost Forge descriptor and Qt/MCP option panel"
    if "probe_package_available:missing" in blockers:
        return "generate a probe package before live observation"
    if "automation_route_available:missing" in blockers:
        return "add a declarative automation route before probing"
    if any(blocker.startswith("automation.") for blocker in blockers):
        return "satisfy automation safety gates before live Plasticity probing"
    if "parameter_controls_observed:missing" in blockers:
        return "run the package and record observed controls for each visible option"
    if "required_evidence_referenced:missing" in blockers:
        return "attach required screenshots/state captures to the observation ledger"
    if "validation_checks_passed:failed" in blockers or "validation_checks_passed:missing" in blockers:
        return "complete validation checks with pass/fail evidence"
    if "reset_verified:missing" in blockers:
        return "verify reset/undo/file cleanup for the fixture"
    if package:
        return "refresh observation ledger from completed probe package"
    if route:
        return route.next_action
    return "record live Plasticity observation evidence"


def _ghostforge_type(observed_type: str) -> str:
    value = observed_type.lower()
    if value in {"number", "float", "distance", "angle"}:
        return "float"
    if value in {"integer", "int"}:
        return "int"
    if value in {"bool", "boolean", "toggle"}:
        return "bool"
    if value in {"enum", "choice"}:
        return "enum"
    if "path" in value:
        return "path"
    if value in {"vector", "axis", "point"}:
        return "vector3"
    return value or "string"


def _ui_control(observed_control: str, observed_type: str) -> str:
    text = f"{observed_control} {observed_type}".lower()
    if "combo" in text or "dropdown" in text or "enum" in text:
        return "dropdown"
    if "checkbox" in text or "toggle" in text or "bool" in text:
        return "checkbox"
    if "slider" in text:
        return "slider"
    if "path" in text or "file" in text:
        return "file_picker"
    if "number" in text or "float" in text or "distance" in text:
        return "numeric_input"
    return "field"


__all__ = [
    "CadObservedParameterPromotion",
    "CadSchemaPromotionCandidate",
    "CadSchemaPromotionCatalog",
    "CadSchemaPromotionGate",
    "PromotionGateStatus",
    "PromotionStatus",
    "build_cad_schema_promotion_catalog",
]
