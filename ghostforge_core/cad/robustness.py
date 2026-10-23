"""Native CAD topology, tolerance, and failure contracts for Ghost Forge.

Plasticity recon is useful because it tells us where the hidden behavior lives:
topology identity, selection semantics, tolerances, failures, and translator
diagnostics.  This module joins the Ghost Forge CAD descriptors, fixture
behavior cases, interop contracts, and selection-state contracts into one
queryable robustness catalog.  It is a native implementation target, not a
Plasticity runtime adapter.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .behavior import CommandBehaviorCase, build_default_behavior_matrix
from .interop import build_default_interop_registry
from .registry import build_default_cad_registry
from .selection_state import build_cad_selection_contract_catalog


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


RobustnessSubjectType = Literal[
    "cad_command",
    "selection_command",
    "interop_format",
]


class CadTopologyNamingPolicy(FrozenModel):
    policy_id: str = Field(min_length=1)
    entity_kind: str = Field(min_length=1)
    prefixes: tuple[str, ...] = ()
    stable_when: tuple[str, ...] = ()
    may_create_when: tuple[str, ...] = ()
    may_delete_when: tuple[str, ...] = ()
    lineage_requirements: tuple[str, ...] = ()
    verification_evidence: tuple[str, ...] = ()


class CadToleranceContract(FrozenModel):
    tolerance_id: str = Field(min_length=1)
    subject_ids: tuple[str, ...] = ()
    source: str = "ghostforge_contract"
    linear: float | None = None
    angular_degrees: float | None = None
    unit: str = "scene_units"
    assertions: tuple[str, ...] = ()
    failure_codes: tuple[str, ...] = ()
    verification_evidence: tuple[str, ...] = ()


class CadFailureContract(FrozenModel):
    code: str = Field(min_length=1)
    category: str = "operation"
    severity: Literal["info", "warning", "error", "blocking"] = "error"
    trigger: str = ""
    recovery: str = ""
    tolerance_sensitive: bool = False
    subject_ids: tuple[str, ...] = ()
    source_layers: tuple[str, ...] = ()
    verification_evidence: tuple[str, ...] = ()


class CadRobustnessContract(FrozenModel):
    contract_id: str = Field(min_length=1)
    subject_type: RobustnessSubjectType
    subject_id: str = Field(min_length=1)
    label: str
    family: str = ""
    topology_policy_ids: tuple[str, ...] = ()
    topology_effects: tuple[str, ...] = ()
    topology_naming_assertions: tuple[str, ...] = ()
    lineage_relations: tuple[str, ...] = ()
    tolerance_contract_ids: tuple[str, ...] = ()
    failure_codes: tuple[str, ...] = ()
    fixture_case_ids: tuple[str, ...] = ()
    selection_modes: tuple[str, ...] = ()
    verification_gates: tuple[str, ...] = ()
    promotion_blockers: tuple[str, ...] = ()
    source_layers: tuple[str, ...] = ()
    runtime_dependency: str = "none"
    plasticity_role: str = "development_evidence_only"


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


def _topology_policy_ids_for_terms(terms: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    text = " ".join(terms).lower()
    policy_ids: list[str] = []
    if any(word in text for word in ("object", "body", "solid", "component", "scene")):
        policy_ids.append("object_body_identity")
    if "face" in text or "cap" in text or "blend" in text:
        policy_ids.append("face_identity")
    if "edge" in text or "boundary" in text:
        policy_ids.append("edge_boundary_identity")
    if "vertex" in text or "vertices" in text:
        policy_ids.append("vertex_identity")
    if "curve" in text or "profile" in text:
        policy_ids.append("curve_identity")
    if "surface" in text or "sheet" in text or "patch" in text:
        policy_ids.append("surface_identity")
    if "artifact" in text or "export" in text or "translator" in text or "import" in text:
        policy_ids.append("artifact_identity")
    if "selection" in text or "filter" in text or "mode" in text:
        policy_ids.append("selection_identity")
    return _unique(policy_ids or ["object_body_identity"])


def _behavior_cases_by_command() -> dict[str, list[CommandBehaviorCase]]:
    out: dict[str, list[CommandBehaviorCase]] = {}
    for case in build_default_behavior_matrix().all_cases():
        out.setdefault(case.command_id, []).append(case)
    return out


def _default_topology_policies() -> dict[str, CadTopologyNamingPolicy]:
    policies = (
        CadTopologyNamingPolicy(
            policy_id="object_body_identity",
            entity_kind="object_or_body",
            prefixes=("O_", "B_", "body_", "mesh_", "solid_"),
            stable_when=("transforming", "renaming", "recomputing normals", "exporting"),
            may_create_when=("import creates bodies", "extrude new_body", "boolean split result", "group creation"),
            may_delete_when=("delete object", "boolean subtract consumes body", "failed import rollback"),
            lineage_requirements=("record source object/body ids for every created body", "undo restores object/body identity where possible"),
            verification_evidence=("before_after_topology_snapshot", "undo_snapshot", "manifest_event"),
        ),
        CadTopologyNamingPolicy(
            policy_id="face_identity",
            entity_kind="face",
            prefixes=("F_", "face_"),
            stable_when=("transforming", "exporting", "normal recomputation", "selection filter changes"),
            may_create_when=("extrude cap/side face", "fillet blend face", "project imprint", "surface patch"),
            may_delete_when=("delete selected face", "fillet replaces sharp edge neighborhood", "trim/split removes region"),
            lineage_requirements=("created faces record source face/edge/profile ids", "modified faces record replaced/trimmed lineage"),
            verification_evidence=("face_id_map", "fixture_lineage_map", "topology_delta"),
        ),
        CadTopologyNamingPolicy(
            policy_id="edge_boundary_identity",
            entity_kind="edge_or_boundary",
            prefixes=("E_", "edge_", "B_", "border_"),
            stable_when=("transforming", "exporting", "selection conversion without topology mutation"),
            may_create_when=("face deletion exposes borders", "fillet creates blend boundaries", "project/imprint creates curve-on-surface edges"),
            may_delete_when=("weld collapses degenerate edges", "fillet replaces sharp edge", "delete selected topology"),
            lineage_requirements=("split/merged edges retain source edge ids", "boundary ids identify open borders after delete/trim"),
            verification_evidence=("edge_id_map", "boundary_report", "topology_delta"),
        ),
        CadTopologyNamingPolicy(
            policy_id="vertex_identity",
            entity_kind="vertex",
            prefixes=("V_", "vertex_"),
            stable_when=("transforming", "exporting", "normal recomputation"),
            may_create_when=("subdivide", "extrude side creation", "surface tessellation", "import tessellation"),
            may_delete_when=("weld duplicate vertices", "delete unreferenced vertices", "collapse degenerate faces"),
            lineage_requirements=("merged vertices record all source vertex ids", "deleted isolated vertices are reported"),
            verification_evidence=("vertex_id_map", "weld_report", "topology_delta"),
        ),
        CadTopologyNamingPolicy(
            policy_id="curve_identity",
            entity_kind="curve_or_profile",
            prefixes=("C_", "curve_", "profile_"),
            stable_when=("selection conversion", "projection preview", "exporting vector data"),
            may_create_when=("project curve", "extract border", "import drawing curves"),
            may_delete_when=("trim curve", "delete selected curve", "failed projection rollback"),
            lineage_requirements=("projected/extracted curves link source curve and target surface/body",),
            verification_evidence=("curve_id_map", "projection_record", "ordered_selection_record"),
        ),
        CadTopologyNamingPolicy(
            policy_id="surface_identity",
            entity_kind="surface_or_sheet",
            prefixes=("S_", "surface_", "sheet_", "patch_"),
            stable_when=("project without imprint", "selection/query operations", "exporting"),
            may_create_when=("surface patch", "loft/sweep/bridge", "import sheet bodies"),
            may_delete_when=("trim removes region", "delete selected surface", "join/merge replaces sheets"),
            lineage_requirements=("created surfaces record boundary/rail/profile ids and continuity settings",),
            verification_evidence=("surface_id_map", "continuity_report", "fixture_lineage_map"),
        ),
        CadTopologyNamingPolicy(
            policy_id="selection_identity",
            entity_kind="selection_state",
            prefixes=("selection:", "mode:", "filter:"),
            stable_when=("grid/snapping toggles", "viewport state changes", "selection mode query"),
            may_create_when=("selection query adds ids", "conversion produces result ids", "group selection set creation"),
            may_delete_when=("clear selection", "filter prunes invalid ids", "unlock/ungroup changes membership"),
            lineage_requirements=("selection conversions record source ids, result ids, and filter reasons",),
            verification_evidence=("selection_state_before_after", "hit_filter_reason_record", "reset_snapshot"),
        ),
        CadTopologyNamingPolicy(
            policy_id="artifact_identity",
            entity_kind="file_artifact",
            prefixes=("artifact:", "file:", "export:", "import:"),
            stable_when=("source scene is exported", "translator diagnostics are recorded"),
            may_create_when=("export writes artifact", "import creates scene objects", "round trip writes comparison artifact"),
            may_delete_when=("workspace-scoped cleanup removes disposable exports", "failed import rolls back transaction"),
            lineage_requirements=("artifacts link source object ids, format options, translator diagnostics, and file hashes",),
            verification_evidence=("workspace_path_file_record", "artifact_manifest_record", "translator_diagnostics_record"),
        ),
    )
    return {policy.policy_id: policy for policy in policies}


def _descriptor_contracts() -> tuple[
    dict[str, CadRobustnessContract],
    dict[str, CadFailureContract],
    dict[str, CadToleranceContract],
]:
    registry = build_default_cad_registry()
    cases_by_command = _behavior_cases_by_command()
    contracts: dict[str, CadRobustnessContract] = {}
    failures: dict[str, CadFailureContract] = {}
    tolerances: dict[str, CadToleranceContract] = {}

    for descriptor in registry.all():
        cases = cases_by_command.get(descriptor.command_id, [])
        contract_id = f"command:{descriptor.command_id}"
        topology_terms = list(descriptor.topology_effects.creates)
        topology_terms += list(descriptor.topology_effects.deletes)
        topology_terms += list(descriptor.topology_effects.modifies)
        topology_terms += list(descriptor.topology_effects.preserves)
        topology_effects = [
            *(f"creates:{item}" for item in descriptor.topology_effects.creates),
            *(f"deletes:{item}" for item in descriptor.topology_effects.deletes),
            *(f"modifies:{item}" for item in descriptor.topology_effects.modifies),
            *(f"preserves:{item}" for item in descriptor.topology_effects.preserves),
            f"id_policy:{descriptor.topology_effects.id_policy}",
        ]
        naming_assertions: list[str] = []
        lineage: list[str] = []
        failure_codes = [failure.code for failure in descriptor.failure_modes]
        tolerance_assertions: list[str] = []
        evidence_statuses: list[str] = []
        fixture_case_ids: list[str] = []
        source_layers = ["cad_descriptor"]
        for case in cases:
            fixture_case_ids.append(case.case_id)
            source_layers.append("fixture_behavior_case")
            evidence_statuses.append(case.plasticity_evidence_status)
            naming_assertions.extend(case.topology_naming_assertions)
            tolerance_assertions.extend(case.tolerance_assertions)
            for transition in case.topology_transitions:
                lineage.append(
                    f"{transition.source}:{transition.relation}"
                    + (f"->{','.join(transition.results)}" if transition.results else "")
                )
                topology_terms.append(transition.source)
                topology_terms.extend(transition.results)
            for probe in case.failure_probes:
                failure_codes.append(probe.expected_failure_code)
                failures[probe.expected_failure_code] = CadFailureContract(
                    code=probe.expected_failure_code,
                    category="fixture_behavior",
                    severity="blocking" if case.result_state != "commit_allowed" else "error",
                    trigger=probe.mutation,
                    recovery=probe.recovery,
                    tolerance_sensitive=probe.tolerance_sensitive,
                    subject_ids=(contract_id,),
                    source_layers=("fixture_behavior_case",),
                    verification_evidence=(case.automation.route_id,),
                )

        for failure in descriptor.failure_modes:
            failures[failure.code] = CadFailureContract(
                code=failure.code,
                category=descriptor.family or "operation",
                severity="blocking" if descriptor.status in {"planned", "controlled_probe_needed"} else "error",
                trigger=failure.message,
                recovery=failure.recovery,
                subject_ids=(contract_id,),
                source_layers=("cad_descriptor",),
                verification_evidence=descriptor.fixture_tests,
            )

        tolerance_id = f"tolerance:{descriptor.command_id}"
        tolerances[tolerance_id] = CadToleranceContract(
            tolerance_id=tolerance_id,
            subject_ids=(contract_id,),
            source="cad_descriptor_and_behavior",
            linear=descriptor.tolerance_policy.linear,
            angular_degrees=descriptor.tolerance_policy.angular_degrees,
            unit=descriptor.tolerance_policy.unit,
            assertions=_unique(tolerance_assertions + ([descriptor.tolerance_policy.description] if descriptor.tolerance_policy.description else [])),
            failure_codes=_unique([code for code in failure_codes if "tolerance" in code or "radius" in code or "collapsed" in code or "healing" in code]),
            verification_evidence=_unique([case.automation.route_id for case in cases] + list(descriptor.fixture_tests)),
        )

        blockers: list[str] = []
        if descriptor.status in {"planned", "controlled_probe_needed", "option", "contextual_mode"}:
            blockers.append(f"descriptor_status:{descriptor.status}")
        if any(status != "ghostforge_contract" for status in evidence_statuses):
            blockers.extend(f"plasticity_evidence:{status}" for status in evidence_statuses if status != "ghostforge_contract")

        contracts[contract_id] = CadRobustnessContract(
            contract_id=contract_id,
            subject_type="cad_command",
            subject_id=descriptor.command_id,
            label=descriptor.label,
            family=descriptor.family,
            topology_policy_ids=_topology_policy_ids_for_terms(topology_terms),
            topology_effects=_unique(topology_effects),
            topology_naming_assertions=_unique(naming_assertions),
            lineage_relations=_unique(lineage),
            tolerance_contract_ids=(tolerance_id,),
            failure_codes=_unique(failure_codes),
            fixture_case_ids=_unique(fixture_case_ids),
            selection_modes=_unique(list(descriptor.selection_contract.subobject_kinds) or ["object"]),
            verification_gates=_unique(list(descriptor.acceptance_gates) + [case.automation.route_id for case in cases]),
            promotion_blockers=_unique(blockers),
            source_layers=_unique(source_layers),
        )

    return contracts, failures, tolerances


def _selection_contracts(
    kb_root: str | None,
) -> tuple[dict[str, CadRobustnessContract], dict[str, CadFailureContract]]:
    catalog = build_cad_selection_contract_catalog(kb_root)
    contracts: dict[str, CadRobustnessContract] = {}
    failures: dict[str, CadFailureContract] = {}
    for selection in catalog.all_commands():
        contract_id = f"selection:{selection.command_id}"
        policy_ids = _topology_policy_ids_for_terms(
            list(selection.topology_naming_policy)
            + list(selection.input_modes)
            + list(selection.output_modes)
            + [selection.operation_kind]
        )
        for code in selection.failure_modes:
            failures[code] = CadFailureContract(
                code=code,
                category="selection_state",
                severity="blocking" if "owner_required" in code else "error",
                trigger=f"{selection.command_id} {selection.operation_kind}",
                recovery="Capture observed selection state, filter reason, and reset evidence before promotion.",
                subject_ids=(contract_id,),
                source_layers=("selection_state_contract",),
                verification_evidence=selection.automation_evidence,
            )
        contracts[contract_id] = CadRobustnessContract(
            contract_id=contract_id,
            subject_type="selection_command",
            subject_id=selection.command_id,
            label=selection.label,
            family="selection_state",
            topology_policy_ids=policy_ids,
            topology_effects=_unique(list(selection.expected_state_delta)),
            topology_naming_assertions=selection.topology_naming_policy,
            lineage_relations=_unique(
                [
                    "selection_source_ids->selection_result_ids"
                    if selection.operation_kind == "convert_selection"
                    else "",
                    "hit_test->filtered_selection_ids"
                    if selection.operation_kind == "select_query"
                    else "",
                ]
            ),
            failure_codes=selection.failure_modes,
            selection_modes=_unique(list(selection.input_modes) + list(selection.output_modes)),
            verification_gates=selection.automation_evidence,
            promotion_blockers=selection.promotion_blockers,
            source_layers=("selection_state_contract", "plasticity_recon_queue"),
        )
    return contracts, failures


def _interop_contracts() -> tuple[
    dict[str, CadRobustnessContract],
    dict[str, CadFailureContract],
    dict[str, CadToleranceContract],
]:
    registry = build_default_interop_registry()
    contracts: dict[str, CadRobustnessContract] = {}
    failures: dict[str, CadFailureContract] = {}
    tolerances: dict[str, CadToleranceContract] = {}
    for descriptor in registry.all():
        contract_id = f"format:{descriptor.format_id}"
        failure_codes = [failure.code for failure in descriptor.failure_modes]
        for failure in descriptor.failure_modes:
            failures[failure.code] = CadFailureContract(
                code=failure.code,
                category="file_interop",
                severity="blocking" if "path" in failure.code or "backend" in failure.code else "error",
                trigger=failure.message,
                recovery=failure.recovery,
                subject_ids=(contract_id,),
                source_layers=("interop_format_contract",),
                verification_evidence=descriptor.verification_gates,
            )
        tolerance_id = f"tolerance:format:{descriptor.format_id}"
        tolerances[tolerance_id] = CadToleranceContract(
            tolerance_id=tolerance_id,
            subject_ids=(contract_id,),
            source="interop_format_contract",
            linear=descriptor.tolerance_policy.linear,
            angular_degrees=descriptor.tolerance_policy.angular_degrees,
            unit=descriptor.tolerance_policy.unit,
            assertions=(descriptor.tolerance_policy.description,) if descriptor.tolerance_policy.description else (),
            failure_codes=_unique([code for code in failure_codes if "tolerance" in code or "healing" in code or "translator" in code]),
            verification_evidence=descriptor.verification_gates,
        )
        contracts[contract_id] = CadRobustnessContract(
            contract_id=contract_id,
            subject_type="interop_format",
            subject_id=descriptor.format_id,
            label=descriptor.label,
            family=descriptor.family,
            topology_policy_ids=_topology_policy_ids_for_terms(list(descriptor.topology_policy) + [descriptor.family, "artifact"]),
            topology_effects=descriptor.topology_policy,
            tolerance_contract_ids=(tolerance_id,),
            failure_codes=_unique(failure_codes),
            fixture_case_ids=descriptor.fixture_tests,
            selection_modes=("object", "scene") if descriptor.can_export else ("file",),
            verification_gates=_unique(list(descriptor.verification_gates) + list(descriptor.automation_requirements)),
            promotion_blockers=(
                "format_fixture_verification_required",
            )
            if "needs_fixture_verification" in descriptor.confidence
            else (),
            source_layers=("interop_format_contract", "plasticity_install_evidence"),
        )
    return contracts, failures, tolerances


@dataclass(frozen=True)
class CadRobustnessCatalog:
    topology_policies: dict[str, CadTopologyNamingPolicy]
    contracts: dict[str, CadRobustnessContract]
    failure_contracts: dict[str, CadFailureContract]
    tolerance_contracts: dict[str, CadToleranceContract]
    kb_root: str | None = None

    @classmethod
    def build(cls, kb_root: str | None = None) -> "CadRobustnessCatalog":
        topology_policies = _default_topology_policies()
        descriptor_contracts, descriptor_failures, descriptor_tolerances = _descriptor_contracts()
        selection_contracts, selection_failures = _selection_contracts(kb_root)
        interop_contracts, interop_failures, interop_tolerances = _interop_contracts()
        contracts = {**descriptor_contracts, **selection_contracts, **interop_contracts}
        failure_contracts = {**descriptor_failures, **selection_failures, **interop_failures}
        tolerance_contracts = {**descriptor_tolerances, **interop_tolerances}
        return cls(
            topology_policies=topology_policies,
            contracts=contracts,
            failure_contracts=failure_contracts,
            tolerance_contracts=tolerance_contracts,
            kb_root=str(kb_root) if kb_root is not None else None,
        )

    def all_contracts(self) -> list[CadRobustnessContract]:
        return [self.contracts[key] for key in sorted(self.contracts)]

    def all_failures(self) -> list[CadFailureContract]:
        return [self.failure_contracts[key] for key in sorted(self.failure_contracts)]

    def all_tolerances(self) -> list[CadToleranceContract]:
        return [self.tolerance_contracts[key] for key in sorted(self.tolerance_contracts)]

    def all_topology_policies(self) -> list[CadTopologyNamingPolicy]:
        return [self.topology_policies[key] for key in sorted(self.topology_policies)]

    def get_contract(self, identifier: str) -> CadRobustnessContract:
        if identifier in self.contracts:
            return self.contracts[identifier]
        matches = [contract for contract in self.contracts.values() if contract.subject_id == identifier]
        if len(matches) == 1:
            return matches[0]
        if matches:
            known = [contract.contract_id for contract in matches]
            raise KeyError(f"Ambiguous robustness contract {identifier!r}. Use one of: {known}")
        raise KeyError(f"Unknown robustness contract {identifier!r}")

    def summary(self) -> dict[str, Any]:
        subject_counts: dict[str, int] = {}
        contracts_with_blockers = 0
        tolerance_sensitive_failure_count = 0
        for contract in self.contracts.values():
            subject_counts[contract.subject_type] = subject_counts.get(contract.subject_type, 0) + 1
            if contract.promotion_blockers:
                contracts_with_blockers += 1
        for failure in self.failure_contracts.values():
            if failure.tolerance_sensitive:
                tolerance_sensitive_failure_count += 1
        return {
            "contract_count": len(self.contracts),
            "subject_type_counts": dict(sorted(subject_counts.items())),
            "topology_policy_count": len(self.topology_policies),
            "failure_contract_count": len(self.failure_contracts),
            "tolerance_contract_count": len(self.tolerance_contracts),
            "tolerance_sensitive_failure_count": tolerance_sensitive_failure_count,
            "contracts_with_promotion_blockers": contracts_with_blockers,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_robustness_catalog(kb_root: str | None = None) -> CadRobustnessCatalog:
    return CadRobustnessCatalog.build(kb_root)


__all__ = [
    "CadFailureContract",
    "CadRobustnessCatalog",
    "CadRobustnessContract",
    "CadToleranceContract",
    "CadTopologyNamingPolicy",
    "RobustnessSubjectType",
    "build_cad_robustness_catalog",
]
