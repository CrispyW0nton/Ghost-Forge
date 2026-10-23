"""Ghost Forge CAD development queue distilled from Plasticity recon evidence.

This module converts raw PlasticityMCP artifacts into implementation-facing
work for Ghost Forge.  Plasticity is still only a comparator/evidence source:
the output here says which native Ghost Forge subsystem should own a command,
what parameter/option evidence is missing, which fixture/probe is required, and
what blockers prevent implementation or product exposure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .plasticity_recon import (
    DEFAULT_PLASTICITY_KB_ROOT,
    PlasticityCommandObservationStatus,
    PlasticityCommandTemplate,
    PlasticityProbePackage,
    PlasticityReconCommandCoverage,
    load_plasticity_observation_evidence,
    load_plasticity_probe_packages,
    load_plasticity_recon_coverage,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


DevelopmentTrack = Literal[
    "solid_modeling_kernel",
    "surface_curve_kernel",
    "file_interop",
    "selection_state",
    "viewport_state",
    "transform_command",
    "command_state",
    "static_asset_resolution",
    "unknown",
]


class CommandReconIndexEntry(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    categories: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    palette_queries: tuple[str, ...] = ()
    shortcuts: tuple[str, ...] = ()
    visible_actions: tuple[str, ...] = ()
    reachability: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CommandReconIndexEntry":
        return cls(
            command_id=str(row.get("command_id") or row.get("id") or ""),
            label=str(row.get("label") or ""),
            categories=tuple(str(value) for value in row.get("categories", ())),
            sources=tuple(str(value) for value in row.get("sources", ())),
            palette_queries=tuple(str(value) for value in row.get("palette_queries", ())),
            shortcuts=tuple(str(value) for value in row.get("shortcuts", ())),
            visible_actions=tuple(str(value) for value in row.get("visible_actions", ())),
            reachability=str(row.get("reachability") or ""),
        )


class StaticMappingEvidence(FrozenModel):
    command_id: str = Field(min_length=1)
    mapping_status: str = ""
    next_action: str = ""
    safe_search_allowed: bool | None = None
    candidate_owner_commands: tuple[str, ...] = ()
    inferred_options: tuple[str, ...] = ()
    evidence_assets: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "StaticMappingEvidence":
        static_evidence = row.get("static_operation_evidence", {})
        candidate_rows = row.get("candidate_existing_commands", ())
        return cls(
            command_id=str(row.get("command_id") or row.get("operation_key") or ""),
            mapping_status=str(row.get("mapping_status") or ""),
            next_action=str(row.get("next_action") or ""),
            safe_search_allowed=row.get("safe_search_allowed"),
            candidate_owner_commands=tuple(
                str(candidate.get("command_id"))
                for candidate in candidate_rows
                if isinstance(candidate, dict) and candidate.get("command_id")
            ),
            inferred_options=tuple(
                str(value).replace(" ", "_")
                for value in static_evidence.get("inferred_options", ())
            ),
            evidence_assets=tuple(str(value) for value in static_evidence.get("evidence_assets", ())),
        )


class GhostForgeCadDevelopmentTask(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    categories: tuple[str, ...] = ()
    implementation_track: DevelopmentTrack = "unknown"
    priority: str = ""
    schema_status: str = ""
    readiness_bucket: str = ""
    probe_kind: str = ""
    fixture: str = ""
    reachability: str = ""
    template_parameters: tuple[str, ...] = ()
    missing_parameters: tuple[str, ...] = ()
    observed_parameter_count: int = 0
    template_parameter_count: int = 0
    validation_checks: tuple[str, ...] = ()
    expected_state_effects: tuple[str, ...] = ()
    palette_queries: tuple[str, ...] = ()
    shortcuts: tuple[str, ...] = ()
    visible_actions: tuple[str, ...] = ()
    evidence_screenshots: tuple[str, ...] = ()
    automation_tools: tuple[str, ...] = ()
    route_ready: bool = False
    package_available: bool = False
    required_evidence: tuple[str, ...] = ()
    parameter_names_to_resolve: tuple[str, ...] = ()
    file_touching: bool = False
    requires_disposable_fixture: bool = False
    workspace_safety_gate: bool = False
    static_mapping_status: str = ""
    inferred_static_options: tuple[str, ...] = ()
    candidate_owner_commands: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    next_plasticity_action: str = ""
    next_ghostforge_action: str = ""

    @property
    def ready_for_native_schema_promotion(self) -> bool:
        return not self.blockers and self.schema_status == "observed_schema"


@dataclass(frozen=True)
class GhostForgeCadDevelopmentQueue:
    tasks: dict[str, GhostForgeCadDevelopmentTask]
    kb_root: str
    generated_utc: str = ""
    source_files: dict[str, bool] | None = None

    def get(self, command_id: str) -> GhostForgeCadDevelopmentTask:
        return self.tasks[command_id]

    def all_tasks(self) -> list[GhostForgeCadDevelopmentTask]:
        return [self.tasks[key] for key in sorted(self.tasks)]

    def by_track(self, track: str) -> list[GhostForgeCadDevelopmentTask]:
        return [task for task in self.all_tasks() if task.implementation_track == track]

    def summary(self) -> dict[str, Any]:
        track_counts: dict[str, int] = {}
        priority_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        route_ready_count = 0
        package_count = 0
        file_touching_count = 0
        workspace_safety_count = 0
        for task in self.tasks.values():
            track_counts[task.implementation_track] = track_counts.get(task.implementation_track, 0) + 1
            priority_counts[task.priority or "<missing>"] = priority_counts.get(task.priority or "<missing>", 0) + 1
            if task.route_ready:
                route_ready_count += 1
            if task.package_available:
                package_count += 1
            if task.file_touching:
                file_touching_count += 1
            if task.workspace_safety_gate:
                workspace_safety_count += 1
            for blocker in task.blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "task_count": len(self.tasks),
            "track_counts": dict(sorted(track_counts.items())),
            "priority_counts": dict(sorted(priority_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "route_ready_count": route_ready_count,
            "probe_package_count": package_count,
            "file_touching_count": file_touching_count,
            "workspace_safety_gate_count": workspace_safety_count,
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_ghostforge_cad_development_queue(
    kb_root: str | Path | None = None,
) -> GhostForgeCadDevelopmentQueue:
    root = Path(kb_root) if kb_root is not None else DEFAULT_PLASTICITY_KB_ROOT
    coverage = load_plasticity_recon_coverage(root)
    observation = load_plasticity_observation_evidence(root)
    packages = load_plasticity_probe_packages(root)
    index = _load_command_recon_index(root)
    static_mapping = _load_static_mapping(root)

    command_ids = set(index) | {row.command_id for row in coverage.commands} | {row.command_id for row in observation.commands}
    command_ids |= {row.command_id for row in observation.templates} | {row.command_id for row in packages.packages} | set(static_mapping)

    tasks = {
        command_id: _build_task(
            command_id,
            index=index.get(command_id),
            coverage=_maybe_command(coverage.commands, command_id),
            status=_maybe_command(observation.commands, command_id),
            template=_maybe_template(observation.templates, command_id),
            package=_maybe_package(packages.packages, command_id),
            static_mapping=static_mapping.get(command_id),
        )
        for command_id in command_ids
    }
    return GhostForgeCadDevelopmentQueue(
        tasks=tasks,
        kb_root=str(root),
        generated_utc=observation.generated_utc or coverage.generated_utc or packages.generated_utc,
        source_files={
            "command_recon_index": (root / "command_recon_index.json").exists(),
            **coverage.source_files,
            **observation.source_files,
            **packages.source_files,
        },
    )


def _build_task(
    command_id: str,
    *,
    index: CommandReconIndexEntry | None,
    coverage: PlasticityReconCommandCoverage | None,
    status: PlasticityCommandObservationStatus | None,
    template: PlasticityCommandTemplate | None,
    package: PlasticityProbePackage | None,
    static_mapping: StaticMappingEvidence | None,
) -> GhostForgeCadDevelopmentTask:
    categories = index.categories if index else ()
    probe_kind = _first_nonempty(
        coverage.probe_kind if coverage else "",
        status.probe_kind if status else "",
        template.probe_kind if template else "",
    )
    fixture = _first_nonempty(
        coverage.fixture if coverage else "",
        status.fixture if status else "",
        template.fixture if template else "",
        package.fixture.fixture if package else "",
    )
    template_parameters = tuple(param.name for param in template.parameters_to_observe) if template else ()
    missing_parameters = status.missing_template_parameters if status else ()
    parameter_names_to_resolve = package.parameter_names_to_resolve if package else ()
    automation_tools = _automation_tools(coverage, package)
    file_touching = _is_file_touching(probe_kind, fixture, coverage, package)
    workspace_safety_gate = package.has_workspace_safety_gate if package else False
    implementation_track = _implementation_track(
        categories=categories,
        probe_kind=probe_kind,
        command_id=command_id,
        static_mapping=static_mapping,
    )
    blockers = _blockers(
        status=status,
        package=package,
        static_mapping=static_mapping,
        file_touching=file_touching,
        workspace_safety_gate=workspace_safety_gate,
    )
    return GhostForgeCadDevelopmentTask(
        command_id=command_id,
        label=_first_nonempty(
            index.label if index else "",
            coverage.label if coverage else "",
            status.label if status else "",
            template.label if template else "",
            package.label if package else "",
        ),
        categories=categories,
        implementation_track=implementation_track,
        priority=_first_nonempty(
            coverage.priority if coverage else "",
            status.priority if status else "",
            template.priority if template else "",
        ),
        schema_status=status.schema_status if status else (template.schema_status if template else ""),
        readiness_bucket=coverage.readiness_bucket if coverage else "",
        probe_kind=probe_kind,
        fixture=fixture,
        reachability=(index.reachability if index else "") or (template.reachability if template else ""),
        template_parameters=template_parameters,
        missing_parameters=missing_parameters,
        observed_parameter_count=status.observed_parameter_count if status else 0,
        template_parameter_count=status.template_parameter_count if status else len(template_parameters),
        validation_checks=template.validation_checks if template else (),
        expected_state_effects=template.expected_state_effects if template else (),
        palette_queries=(index.palette_queries if index else ()) or (package.palette_queries if package else ()),
        shortcuts=index.shortcuts if index else (),
        visible_actions=index.visible_actions if index else (),
        evidence_screenshots=(status.evidence_screenshots if status else ()) or (template.evidence_screenshots if template else ()),
        automation_tools=automation_tools,
        route_ready=bool(automation_tools),
        package_available=package is not None,
        required_evidence=package.required_evidence if package else (),
        parameter_names_to_resolve=parameter_names_to_resolve,
        file_touching=file_touching,
        requires_disposable_fixture=bool(
            package and (file_touching or package.fixture.fixture or package.fixture.setup_steps)
        )
        or any(step.get("requires_disposable_fixture") for step in (coverage.mcp_route if coverage else ())),
        workspace_safety_gate=workspace_safety_gate,
        static_mapping_status=static_mapping.mapping_status if static_mapping else "",
        inferred_static_options=static_mapping.inferred_options if static_mapping else (),
        candidate_owner_commands=static_mapping.candidate_owner_commands if static_mapping else (),
        blockers=blockers,
        next_plasticity_action=_next_plasticity_action(coverage, package, static_mapping),
        next_ghostforge_action=_next_ghostforge_action(implementation_track, blockers, template_parameters, parameter_names_to_resolve),
    )


def _load_command_recon_index(root: Path) -> dict[str, CommandReconIndexEntry]:
    path = root / "command_recon_index.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, CommandReconIndexEntry] = {}
    for row in payload.get("commands", ()):
        if not isinstance(row, dict):
            continue
        entry = CommandReconIndexEntry.from_row(row)
        if entry.command_id:
            entries[entry.command_id] = entry
    return entries


def _load_static_mapping(root: Path) -> dict[str, StaticMappingEvidence]:
    path = root / "static_command_mapping_review.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping: dict[str, StaticMappingEvidence] = {}
    for rows in payload.get("recommended_batches", {}).values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            evidence = StaticMappingEvidence.from_row(row)
            if evidence.command_id:
                mapping[evidence.command_id] = evidence
    return mapping


def _maybe_command(rows: tuple[Any, ...], command_id: str) -> Any | None:
    for row in rows:
        if row.command_id == command_id:
            return row
    return None


def _maybe_template(rows: tuple[PlasticityCommandTemplate, ...], command_id: str) -> PlasticityCommandTemplate | None:
    return _maybe_command(rows, command_id)


def _maybe_package(rows: tuple[PlasticityProbePackage, ...], command_id: str) -> PlasticityProbePackage | None:
    return _maybe_command(rows, command_id)


def _first_nonempty(*values: str) -> str:
    for value in values:
        if value:
            return value
    return ""


def _automation_tools(
    coverage: PlasticityReconCommandCoverage | None,
    package: PlasticityProbePackage | None,
) -> tuple[str, ...]:
    tools = []
    if coverage:
        tools.extend(str(step.get("tool")) for step in coverage.mcp_route if step.get("tool"))
    if package:
        tools.append("parameter_probe_package")
        if package.preferred_invocation:
            tools.append(package.preferred_invocation)
    return tuple(dict.fromkeys(tools))


def _is_file_touching(
    probe_kind: str,
    fixture: str,
    coverage: PlasticityReconCommandCoverage | None,
    package: PlasticityProbePackage | None,
) -> bool:
    if coverage and coverage.destructive_or_file_touching:
        return True
    text = " ".join(
        (
            probe_kind,
            fixture,
            " ".join(package.required_evidence if package else ()),
            " ".join(package.fixture.state_requirements if package else ()),
        )
    ).lower()
    return any(token in text for token in ("file", "export", "import", "output_path", "temporary_export"))


def _implementation_track(
    *,
    categories: tuple[str, ...],
    probe_kind: str,
    command_id: str,
    static_mapping: StaticMappingEvidence | None,
) -> DevelopmentTrack:
    if static_mapping and static_mapping.mapping_status in {"likely_option_or_alias", "controlled_probe_needed"}:
        return "static_asset_resolution" if static_mapping.mapping_status == "likely_option_or_alias" else _static_controlled_track(command_id, probe_kind)
    if "file" in probe_kind or any(category in categories for category in ("file_io", "cad_file_interop", "mesh_export_rendering")):
        return "file_interop"
    if any(category in categories for category in ("solid_modeling",)):
        return "solid_modeling_kernel"
    if any(category in categories for category in ("surface_modeling", "curve_sketch_modeling", "sketch_primitives")):
        return "surface_curve_kernel"
    if any(category in categories for category in ("selection_modes", "snapping_planes")) or "selection" in probe_kind:
        return "selection_state"
    if any(category in categories for category in ("viewport_camera", "viewport_interaction", "visibility_display")) or "viewport" in probe_kind:
        return "viewport_state"
    if any(category in categories for category in ("transform_duplication",)) or command_id in {"transform", "move", "rotate", "scale"}:
        return "transform_command"
    if "command_panel" in probe_kind:
        return "command_state"
    return "unknown"


def _static_controlled_track(command_id: str, probe_kind: str) -> DevelopmentTrack:
    if "export" in command_id or "file" in probe_kind:
        return "file_interop"
    if command_id == "transform":
        return "transform_command"
    return "static_asset_resolution"


def _blockers(
    *,
    status: PlasticityCommandObservationStatus | None,
    package: PlasticityProbePackage | None,
    static_mapping: StaticMappingEvidence | None,
    file_touching: bool,
    workspace_safety_gate: bool,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if status is None:
        blockers.append("plasticity.observation_status_missing")
    elif not status.is_observed_schema:
        blockers.append("plasticity.observed_schema_missing")
    if status and not status.reset_verified:
        blockers.append("plasticity.reset_not_verified")
    if package is None:
        blockers.append("plasticity.probe_package_missing")
    if file_touching and not workspace_safety_gate:
        blockers.append("automation.workspace_safety_gate_missing")
    if static_mapping and static_mapping.mapping_status == "likely_option_or_alias":
        blockers.append("static_asset.owner_unresolved")
    if static_mapping and static_mapping.mapping_status == "controlled_probe_needed":
        blockers.append("static_asset.controlled_probe_needed")
    return tuple(dict.fromkeys(blockers))


def _next_plasticity_action(
    coverage: PlasticityReconCommandCoverage | None,
    package: PlasticityProbePackage | None,
    static_mapping: StaticMappingEvidence | None,
) -> str:
    if static_mapping and static_mapping.next_action:
        return static_mapping.next_action
    if package:
        return "run_probe_package_and_record_observation"
    if coverage and coverage.next_action:
        return coverage.next_action
    if coverage and coverage.next_tool:
        return f"run_{coverage.next_tool}"
    return "create_probe_package_from_template"


def _next_ghostforge_action(
    track: DevelopmentTrack,
    blockers: tuple[str, ...],
    template_parameters: tuple[str, ...],
    parameter_names_to_resolve: tuple[str, ...],
) -> str:
    if "static_asset.owner_unresolved" in blockers:
        return "keep_relationship_descriptor_blocked_until_owner_command_is_verified"
    if "automation.workspace_safety_gate_missing" in blockers:
        return "add_workspace_controlled_file_fixture_before_any_file_probe"
    if "plasticity.observed_schema_missing" in blockers:
        return "use_inferred_template_to_draft_schema_then_wait_for_live_observation"
    if track in {"solid_modeling_kernel", "surface_curve_kernel"}:
        return "promote_observed_schema_into_native_kernel_command_descriptor_and_fixture_behavior_case"
    if track == "file_interop":
        return "promote_observed_options_into_native_interop_format_descriptor"
    if track == "selection_state":
        return "promote_selection_behavior_into_core_selection_state_contract"
    if track == "viewport_state":
        return "promote_state_changes_into_queryable_viewport_state_contract"
    if template_parameters or parameter_names_to_resolve:
        return "promote_parameters_into_native_command_schema"
    return "classify_command_and_assign_native_owner"


__all__ = [
    "CommandReconIndexEntry",
    "DevelopmentTrack",
    "GhostForgeCadDevelopmentQueue",
    "GhostForgeCadDevelopmentTask",
    "StaticMappingEvidence",
    "build_ghostforge_cad_development_queue",
]
