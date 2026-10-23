"""Load PlasticityMCP recon coverage into Ghost Forge.

This adapter keeps Ghost Forge tied to current evidence instead of a copied
feature list.  It reads the generated PlasticityMCP knowledge-base artifacts
when they are available and flattens their command readiness rows into an
inspectable coverage snapshot.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, computed_field


DEFAULT_PLASTICITY_KB_ROOT = Path(
    os.environ.get(
        "PLASTICITY_MCP_KB_ROOT",
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base",
    )
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PlasticityReconCommandCoverage(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    readiness_bucket: str = ""
    stage: str = ""
    priority: str = ""
    probe_kind: str = ""
    fixture: str = ""
    preferred_query: str = ""
    next_tool: str = ""
    next_action: str = ""
    safe_search_allowed: bool | None = None
    destructive_or_file_touching: bool | None = None
    observed_parameter_count: int | None = None
    missing_parameter_count: int | None = None
    template_parameter_count: int | None = None
    gaps: tuple[str, ...] = ()
    mcp_route: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any], *, fallback_bucket: str = "") -> "PlasticityReconCommandCoverage":
        return cls(
            command_id=str(row["command_id"]),
            label=str(row.get("label") or ""),
            readiness_bucket=str(row.get("readiness_bucket") or fallback_bucket),
            stage=str(row.get("stage") or ""),
            priority=str(row.get("priority") or ""),
            probe_kind=str(row.get("probe_kind") or ""),
            fixture=str(row.get("fixture") or ""),
            preferred_query=str(row.get("preferred_query") or ""),
            next_tool=str(row.get("next_tool") or ""),
            next_action=str(row.get("next_action") or ""),
            safe_search_allowed=row.get("safe_search_allowed"),
            destructive_or_file_touching=row.get("destructive_or_file_touching"),
            observed_parameter_count=row.get("observed_parameter_count"),
            missing_parameter_count=row.get("missing_parameter_count"),
            template_parameter_count=row.get("template_parameter_count"),
            gaps=tuple(str(gap) for gap in row.get("gaps", ())),
            mcp_route=tuple(dict(step) for step in row.get("mcp_route", ())),
        )

    @property
    def has_automation_route(self) -> bool:
        return bool(self.mcp_route)

    @property
    def needs_observed_schema(self) -> bool:
        return (self.missing_parameter_count or 0) > 0 or "needs" in self.stage


class PlasticityReconCoverageSnapshot(FrozenModel):
    kb_root: str
    generated_utc: str = ""
    source_files: dict[str, bool] = Field(default_factory=dict)
    basis: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    bucket_counts: dict[str, int] = Field(default_factory=dict)
    operating_sequence: tuple[str, ...] = ()
    goal_requirement_status_counts: dict[str, int] = Field(default_factory=dict)
    static_mapping_status_counts: dict[str, int] = Field(default_factory=dict)
    format_families: tuple[str, ...] = ()
    commands: tuple[PlasticityReconCommandCoverage, ...] = ()

    def command(self, command_id: str) -> PlasticityReconCommandCoverage:
        for row in self.commands:
            if row.command_id == command_id:
                return row
        raise KeyError(command_id)

    def commands_by_bucket(self, readiness_bucket: str) -> list[PlasticityReconCommandCoverage]:
        return [row for row in self.commands if row.readiness_bucket == readiness_bucket]

    def coverage_summary(self) -> dict[str, Any]:
        priority_counts: dict[str, int] = {}
        probe_kind_counts: dict[str, int] = {}
        fixture_counts: dict[str, int] = {}
        for row in self.commands:
            priority_counts[row.priority or "<missing>"] = priority_counts.get(row.priority or "<missing>", 0) + 1
            probe_kind_counts[row.probe_kind or "<missing>"] = probe_kind_counts.get(row.probe_kind or "<missing>", 0) + 1
            fixture_counts[row.fixture or "<missing>"] = fixture_counts.get(row.fixture or "<missing>", 0) + 1
        return {
            "loaded_command_count": len(self.commands),
            "commands_with_automation_routes": sum(1 for row in self.commands if row.has_automation_route),
            "commands_needing_observed_schema": sum(1 for row in self.commands if row.needs_observed_schema),
            "readiness_bucket_counts": dict(sorted(self.bucket_counts.items())),
            "priority_counts": dict(sorted(priority_counts.items())),
            "probe_kind_counts": dict(sorted(probe_kind_counts.items())),
            "fixture_counts": dict(sorted(fixture_counts.items())),
            "static_mapping_status_counts": dict(sorted(self.static_mapping_status_counts.items())),
            "goal_requirement_status_counts": dict(sorted(self.goal_requirement_status_counts.items())),
            "format_family_count": len(self.format_families),
        }


class PlasticityParameterTemplate(FrozenModel):
    name: str = Field(min_length=1)
    type: str = ""
    description: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityParameterTemplate":
        return cls(
            name=str(row["name"]),
            type=str(row.get("type") or ""),
            description=str(row.get("description") or ""),
        )


class PlasticityCommandTemplate(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    schema_status: str = ""
    reachability: str = ""
    priority: str = ""
    probe_kind: str = ""
    fixture: str = ""
    parameters_to_observe: tuple[PlasticityParameterTemplate, ...] = ()
    validation_checks: tuple[str, ...] = ()
    expected_state_effects: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    invocation_candidates: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    evidence_screenshots: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityCommandTemplate":
        return cls(
            command_id=str(row["command_id"]),
            label=str(row.get("label") or ""),
            schema_status=str(row.get("schema_status") or ""),
            reachability=str(row.get("reachability") or ""),
            priority=str(row.get("priority") or ""),
            probe_kind=str(row.get("probe_kind") or ""),
            fixture=str(row.get("fixture") or ""),
            parameters_to_observe=tuple(
                PlasticityParameterTemplate.from_row(param)
                for param in row.get("parameters_to_observe", ())
                if isinstance(param, dict) and "name" in param
            ),
            validation_checks=tuple(str(value) for value in row.get("validation_checks", ())),
            expected_state_effects=tuple(str(value) for value in row.get("expected_state_effects", ())),
            preconditions=tuple(str(value) for value in row.get("preconditions", ())),
            invocation_candidates=dict(row.get("invocation_candidates", {})),
            safety=dict(row.get("safety", {})),
            evidence_screenshots=tuple(str(value) for value in row.get("evidence_screenshots", ())),
        )


class PlasticityCommandObservationStatus(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    schema_status: str = ""
    priority: str = ""
    probe_kind: str = ""
    fixture: str = ""
    observed_parameter_count: int = 0
    template_parameter_count: int = 0
    missing_template_parameters: tuple[str, ...] = ()
    evidence_screenshots: tuple[str, ...] = ()
    reset_verified: bool = False

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityCommandObservationStatus":
        return cls(
            command_id=str(row["command_id"]),
            label=str(row.get("label") or ""),
            schema_status=str(row.get("schema_status") or ""),
            priority=str(row.get("priority") or ""),
            probe_kind=str(row.get("probe_kind") or ""),
            fixture=str(row.get("fixture") or ""),
            observed_parameter_count=int(row.get("observed_parameter_count") or 0),
            template_parameter_count=int(row.get("template_parameter_count") or 0),
            missing_template_parameters=tuple(str(value) for value in row.get("missing_template_parameters", ())),
            evidence_screenshots=tuple(str(value) for value in row.get("evidence_screenshots", ())),
            reset_verified=bool(row.get("reset_verified", False)),
        )

    @property
    def is_observed_schema(self) -> bool:
        return self.schema_status == "observed_schema"

    @property
    def is_template_only(self) -> bool:
        return self.schema_status == "template_inferred_needs_probe"


class PlasticityLatestProbeSession(FrozenModel):
    command_id: str = ""
    mode: str = ""
    executed: bool = False
    generated_utc: str = ""
    parameter_names_to_resolve: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    validation_checks: tuple[str, ...] = ()
    reset_steps: tuple[str, ...] = ()
    session_path: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "PlasticityLatestProbeSession":
        package = payload.get("package", {})
        evidence_plan = package.get("evidence_capture_plan", {}) if isinstance(package, dict) else {}
        invocation_plan = package.get("invocation_plan", {}) if isinstance(package, dict) else {}
        artifacts = payload.get("artifacts", {})
        return cls(
            command_id=str(payload.get("command_id") or package.get("command_id") or ""),
            mode=str(payload.get("mode") or ""),
            executed=bool(payload.get("executed", False)),
            generated_utc=str(payload.get("generated_utc") or ""),
            parameter_names_to_resolve=tuple(str(value) for value in evidence_plan.get("parameter_names_to_resolve", ())),
            required_evidence=tuple(str(value) for value in evidence_plan.get("required_evidence", ())),
            validation_checks=tuple(str(value) for value in evidence_plan.get("validation_checks", ())),
            reset_steps=tuple(str(value) for value in invocation_plan.get("reset_steps", ())),
            session_path=str(artifacts.get("session_path") or ""),
        )


class PlasticityProbeParameterSlot(FrozenModel):
    name: str = Field(min_length=1)
    type: str = ""
    observed_control: str = ""
    confidence: str = ""
    value_or_options: Any = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityProbeParameterSlot":
        return cls(
            name=str(row["name"]),
            type=str(row.get("type") or ""),
            observed_control=str(row.get("observed_control") or ""),
            confidence=str(row.get("confidence") or ""),
            value_or_options=row.get("value_or_options"),
        )


class PlasticityProbeValidationCheck(FrozenModel):
    check: str = Field(min_length=1)
    passed: bool = False
    evidence: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityProbeValidationCheck":
        return cls(
            check=str(row["check"]),
            passed=bool(row.get("passed", False)),
            evidence=str(row.get("evidence") or ""),
        )


class PlasticityProbeFixturePlan(FrozenModel):
    fixture: str = ""
    purpose: str = ""
    assets: tuple[str, ...] = ()
    setup_steps: tuple[str, ...] = ()
    reset_steps: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()
    state_requirements: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityProbeFixturePlan":
        return cls(
            fixture=str(row.get("fixture") or ""),
            purpose=str(row.get("purpose") or ""),
            assets=tuple(str(value) for value in row.get("assets", ())),
            setup_steps=tuple(str(value) for value in row.get("setup_steps", ())),
            reset_steps=tuple(str(value) for value in row.get("reset_steps", ())),
            safety_notes=tuple(str(value) for value in row.get("safety_notes", ())),
            state_requirements=tuple(str(value) for value in row.get("state_requirements", ())),
        )


class PlasticityProbePackage(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    generated_utc: str = ""
    fixture: PlasticityProbeFixturePlan = Field(default_factory=PlasticityProbeFixturePlan)
    parameter_names_to_resolve: tuple[str, ...] = ()
    required_evidence: tuple[str, ...] = ()
    validation_checks: tuple[str, ...] = ()
    completion_definition: tuple[str, ...] = ()
    palette_queries: tuple[str, ...] = ()
    preferred_invocation: str = ""
    setup_steps: tuple[str, ...] = ()
    probe_steps: tuple[str, ...] = ()
    reset_steps: tuple[str, ...] = ()
    observed_parameter_slots: tuple[PlasticityProbeParameterSlot, ...] = ()
    observation_validation_results: tuple[PlasticityProbeValidationCheck, ...] = ()
    observation_schema_status: str = ""
    observation_reset_verified: bool = False
    side_effects_observed: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "PlasticityProbePackage":
        evidence_plan = row.get("evidence_capture_plan", {})
        invocation_plan = row.get("invocation_plan", {})
        observation = row.get("observation_record_template", {})
        return cls(
            command_id=str(row["command_id"]),
            label=str(row.get("label") or ""),
            generated_utc=str(row.get("generated_utc") or ""),
            fixture=PlasticityProbeFixturePlan.from_row(row.get("fixture", {})),
            parameter_names_to_resolve=tuple(str(value) for value in evidence_plan.get("parameter_names_to_resolve", ())),
            required_evidence=tuple(str(value) for value in evidence_plan.get("required_evidence", ())),
            validation_checks=tuple(str(value) for value in evidence_plan.get("validation_checks", ())),
            completion_definition=tuple(str(value) for value in row.get("completion_definition", ())),
            palette_queries=tuple(str(value) for value in invocation_plan.get("palette_queries", ())),
            preferred_invocation=str(invocation_plan.get("preferred_invocation") or ""),
            setup_steps=tuple(str(value) for value in invocation_plan.get("setup_steps", ())),
            probe_steps=tuple(str(value) for value in invocation_plan.get("probe_steps", ())),
            reset_steps=tuple(str(value) for value in invocation_plan.get("reset_steps", ())),
            observed_parameter_slots=tuple(
                PlasticityProbeParameterSlot.from_row(param)
                for param in observation.get("observed_parameters", ())
                if isinstance(param, dict) and "name" in param
            ),
            observation_validation_results=tuple(
                PlasticityProbeValidationCheck.from_row(check)
                for check in observation.get("validation_results", ())
                if isinstance(check, dict) and "check" in check
            ),
            observation_schema_status=str(observation.get("schema_status") or ""),
            observation_reset_verified=bool(observation.get("reset_verified", False)),
            side_effects_observed=tuple(str(value) for value in observation.get("side_effects_observed", ())),
        )

    @computed_field
    @property
    def has_workspace_safety_gate(self) -> bool:
        return any("workspace" in note.lower() or "knowledge_base/fixtures" in note for note in self.fixture.safety_notes + self.fixture.reset_steps)


class PlasticityProbePackageSnapshot(FrozenModel):
    kb_root: str
    generated_utc: str = ""
    source_files: dict[str, bool] = Field(default_factory=dict)
    basis: dict[str, Any] = Field(default_factory=dict)
    packages: tuple[PlasticityProbePackage, ...] = ()

    def package(self, command_id: str) -> PlasticityProbePackage:
        for package in self.packages:
            if package.command_id == command_id:
                return package
        raise KeyError(command_id)

    def package_summary(self) -> dict[str, Any]:
        return {
            "package_count": len(self.packages),
            "packages_with_workspace_safety_gate": sum(1 for package in self.packages if package.has_workspace_safety_gate),
            "packages_with_observation_template": sum(1 for package in self.packages if package.observed_parameter_slots),
            "packages_requiring_file_evidence": sum(
                1
                for package in self.packages
                if any("file" in evidence for evidence in package.required_evidence)
            ),
            "commands": [package.command_id for package in self.packages],
        }


class PlasticityObservationEvidenceSnapshot(FrozenModel):
    kb_root: str
    generated_utc: str = ""
    source_files: dict[str, bool] = Field(default_factory=dict)
    ledger_basis: dict[str, Any] = Field(default_factory=dict)
    template_basis: dict[str, Any] = Field(default_factory=dict)
    ledger_schema_status_counts: dict[str, int] = Field(default_factory=dict)
    template_schema_status_counts: dict[str, int] = Field(default_factory=dict)
    template_groups: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    fixture_counts: dict[str, int] = Field(default_factory=dict)
    probe_kind_counts: dict[str, int] = Field(default_factory=dict)
    commands: tuple[PlasticityCommandObservationStatus, ...] = ()
    templates: tuple[PlasticityCommandTemplate, ...] = ()
    latest_session: PlasticityLatestProbeSession | None = None

    def command_status(self, command_id: str) -> PlasticityCommandObservationStatus:
        for command in self.commands:
            if command.command_id == command_id:
                return command
        raise KeyError(command_id)

    def command_template(self, command_id: str) -> PlasticityCommandTemplate:
        for template in self.templates:
            if template.command_id == command_id:
                return template
        raise KeyError(command_id)

    def observation_summary(self) -> dict[str, Any]:
        return {
            "ledger_command_count": len(self.commands),
            "template_command_count": len(self.templates),
            "observed_schema_count": sum(1 for command in self.commands if command.is_observed_schema),
            "template_only_count": sum(1 for command in self.commands if command.is_template_only),
            "commands_with_reset_verified": sum(1 for command in self.commands if command.reset_verified),
            "commands_with_evidence_screenshots": sum(1 for command in self.commands if command.evidence_screenshots),
            "ledger_schema_status_counts": dict(sorted(self.ledger_schema_status_counts.items())),
            "template_schema_status_counts": dict(sorted(self.template_schema_status_counts.items())),
            "fixture_counts": dict(sorted(self.fixture_counts.items())),
            "probe_kind_counts": dict(sorted(self.probe_kind_counts.items())),
            "latest_session_command_id": self.latest_session.command_id if self.latest_session else None,
            "latest_session_executed": self.latest_session.executed if self.latest_session else None,
        }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _status_counts(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "<missing>")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _flatten_readiness_rows(readiness: dict[str, Any]) -> list[PlasticityReconCommandCoverage]:
    rows_by_command: dict[str, PlasticityReconCommandCoverage] = {}
    all_rows = readiness.get("rows", [])
    if isinstance(all_rows, list):
        for row in all_rows:
            if not isinstance(row, dict) or "command_id" not in row:
                continue
            coverage = PlasticityReconCommandCoverage.from_row(row)
            rows_by_command.setdefault(coverage.command_id, coverage)
    if rows_by_command:
        return [rows_by_command[key] for key in sorted(rows_by_command)]

    batches = readiness.get("recommended_batches", {})
    for bucket, rows in batches.items():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or "command_id" not in row:
                continue
            coverage = PlasticityReconCommandCoverage.from_row(row, fallback_bucket=str(bucket))
            rows_by_command.setdefault(coverage.command_id, coverage)
    return [rows_by_command[key] for key in sorted(rows_by_command)]


def _goal_requirement_status_counts(goal_audit: dict[str, Any]) -> dict[str, int]:
    requirements = goal_audit.get("requirements", [])
    if not isinstance(requirements, list):
        return {}
    return _status_counts([row for row in requirements if isinstance(row, dict)], "status")


def _tuple_groups(groups: dict[str, Any]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for key, value in groups.items():
        if isinstance(value, list):
            result[str(key)] = tuple(str(item) for item in value)
    return result


def load_plasticity_recon_coverage(
    kb_root: str | Path | None = None,
) -> PlasticityReconCoverageSnapshot:
    root = Path(kb_root) if kb_root is not None else DEFAULT_PLASTICITY_KB_ROOT
    paths = {
        "parameter_observation_readiness": root / "parameter_observation_readiness.json",
        "static_command_mapping_review": root / "static_command_mapping_review.json",
        "plasticity_file_format_map": root / "plasticity_file_format_map.json",
        "goal_progress_audit": root / "goal_progress_audit.json",
    }
    exists = {name: path.exists() for name, path in paths.items()}

    readiness = _read_json(paths["parameter_observation_readiness"]) if exists["parameter_observation_readiness"] else {}
    static_review = _read_json(paths["static_command_mapping_review"]) if exists["static_command_mapping_review"] else {}
    format_map = _read_json(paths["plasticity_file_format_map"]) if exists["plasticity_file_format_map"] else {}
    goal_audit = _read_json(paths["goal_progress_audit"]) if exists["goal_progress_audit"] else {}

    commands = tuple(_flatten_readiness_rows(readiness))
    formats = format_map.get("formats", {})
    return PlasticityReconCoverageSnapshot(
        kb_root=str(root),
        generated_utc=str(readiness.get("generated_utc") or goal_audit.get("generated_utc") or ""),
        source_files=exists,
        basis=dict(readiness.get("basis", {})),
        summary=dict(readiness.get("summary", {})),
        bucket_counts={str(key): int(value) for key, value in readiness.get("bucket_counts", {}).items()},
        operating_sequence=tuple(str(step) for step in readiness.get("operating_sequence", ())),
        goal_requirement_status_counts=_goal_requirement_status_counts(goal_audit),
        static_mapping_status_counts={
            str(key): int(value)
            for key, value in static_review.get("status_counts", {}).items()
        },
        format_families=tuple(sorted(str(key) for key in formats)),
        commands=commands,
    )


def load_plasticity_observation_evidence(
    kb_root: str | Path | None = None,
) -> PlasticityObservationEvidenceSnapshot:
    root = Path(kb_root) if kb_root is not None else DEFAULT_PLASTICITY_KB_ROOT
    paths = {
        "parameter_observation_ledger": root / "parameter_observation_ledger.json",
        "parameter_schema_templates": root / "parameter_schema_templates.json",
        "parameter_probe_session_last": root / "parameter_probe_session_last.json",
    }
    exists = {name: path.exists() for name, path in paths.items()}

    ledger = _read_json(paths["parameter_observation_ledger"]) if exists["parameter_observation_ledger"] else {}
    templates_payload = _read_json(paths["parameter_schema_templates"]) if exists["parameter_schema_templates"] else {}
    latest_payload = _read_json(paths["parameter_probe_session_last"]) if exists["parameter_probe_session_last"] else {}

    ledger_commands = [
        PlasticityCommandObservationStatus.from_row(row)
        for row in ledger.get("commands", ())
        if isinstance(row, dict) and "command_id" in row
    ]
    templates = [
        PlasticityCommandTemplate.from_row(row)
        for row in templates_payload.get("templates", ())
        if isinstance(row, dict) and "command_id" in row
    ]

    latest_session = (
        PlasticityLatestProbeSession.from_payload(latest_payload)
        if latest_payload
        else None
    )

    return PlasticityObservationEvidenceSnapshot(
        kb_root=str(root),
        generated_utc=str(templates_payload.get("generated_utc") or latest_payload.get("generated_utc") or ""),
        source_files=exists,
        ledger_basis=dict(ledger.get("basis", {})),
        template_basis=dict(templates_payload.get("basis", {})),
        ledger_schema_status_counts=_status_counts(
            [row for row in ledger.get("commands", ()) if isinstance(row, dict)],
            "schema_status",
        ),
        template_schema_status_counts={
            str(key): int(value)
            for key, value in templates_payload.get("schema_status_counts", {}).items()
        },
        template_groups=_tuple_groups(templates_payload.get("template_groups", {})),
        fixture_counts={
            str(key): int(value)
            for key, value in templates_payload.get("fixture_counts", {}).items()
        },
        probe_kind_counts={
            str(key): int(value)
            for key, value in templates_payload.get("probe_kind_counts", {}).items()
        },
        commands=tuple(sorted(ledger_commands, key=lambda row: row.command_id)),
        templates=tuple(sorted(templates, key=lambda row: row.command_id)),
        latest_session=latest_session,
    )


def load_plasticity_probe_packages(
    kb_root: str | Path | None = None,
) -> PlasticityProbePackageSnapshot:
    root = Path(kb_root) if kb_root is not None else DEFAULT_PLASTICITY_KB_ROOT
    paths = {
        "parameter_probe_packages": root / "parameter_probe_packages.json",
        "parameter_probe_session_last": root / "parameter_probe_session_last.json",
    }
    exists = {name: path.exists() for name, path in paths.items()}
    packages_payload = _read_json(paths["parameter_probe_packages"]) if exists["parameter_probe_packages"] else {}
    last_session = _read_json(paths["parameter_probe_session_last"]) if exists["parameter_probe_session_last"] else {}

    packages = [
        PlasticityProbePackage.from_row(row)
        for row in packages_payload.get("packages", ())
        if isinstance(row, dict) and "command_id" in row
    ]
    if last_session and isinstance(last_session.get("package"), dict):
        package = PlasticityProbePackage.from_row(last_session["package"])
        if all(existing.command_id != package.command_id for existing in packages):
            packages.append(package)

    return PlasticityProbePackageSnapshot(
        kb_root=str(root),
        generated_utc=str(packages_payload.get("generated_utc") or last_session.get("generated_utc") or ""),
        source_files=exists,
        basis=dict(packages_payload.get("basis", {})),
        packages=tuple(sorted(packages, key=lambda row: row.command_id)),
    )


__all__ = [
    "DEFAULT_PLASTICITY_KB_ROOT",
    "PlasticityCommandObservationStatus",
    "PlasticityCommandTemplate",
    "PlasticityLatestProbeSession",
    "PlasticityObservationEvidenceSnapshot",
    "PlasticityParameterTemplate",
    "PlasticityProbeFixturePlan",
    "PlasticityProbePackage",
    "PlasticityProbePackageSnapshot",
    "PlasticityProbeParameterSlot",
    "PlasticityProbeValidationCheck",
    "PlasticityReconCommandCoverage",
    "PlasticityReconCoverageSnapshot",
    "load_plasticity_observation_evidence",
    "load_plasticity_probe_packages",
    "load_plasticity_recon_coverage",
]
