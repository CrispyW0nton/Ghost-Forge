"""Draft native Ghost Forge CAD command schemas from recon templates.

PlasticityMCP currently provides inferred parameter templates, not observed
schemas.  This module converts those templates into Ghost Forge-owned draft
schemas: typed parameter candidates, option-panel grouping, UI control hints,
validation gaps, and promotion blockers.  These drafts are planning inputs for
native descriptors and Qt panels, not runtime Plasticity adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .development_queue import (
    GhostForgeCadDevelopmentTask,
    build_ghostforge_cad_development_queue,
)
from .plasticity_recon import (
    PlasticityCommandTemplate,
    PlasticityParameterTemplate,
    load_plasticity_observation_evidence,
)
from .schema import ParameterSpec


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


SchemaDraftStatus = Literal[
    "template_inferred",
    "observed_partial",
    "observed_schema",
]


class CadParameterDraft(FrozenModel):
    name: str = Field(min_length=1)
    source_type: str = ""
    ghostforge_type: str = Field(min_length=1)
    panel_group: str = "options"
    ui_control: str = "field"
    required: bool = False
    default: Any = None
    values: tuple[Any, ...] = ()
    unit: str | None = None
    description: str = ""
    validation_rules: tuple[str, ...] = ()
    promotion_blockers: tuple[str, ...] = ()

    def to_parameter_spec(self) -> ParameterSpec:
        return ParameterSpec(
            name=self.name,
            type=self.ghostforge_type,
            required=self.required,
            default=self.default,
            values=self.values,
            unit=self.unit,
            description=self.description,
            ui={
                "control": self.ui_control,
                "panel_group": self.panel_group,
                "draft_status": "inferred_from_recon_template",
            },
        )


class CadOptionPanelDraft(FrozenModel):
    group_id: str = Field(min_length=1)
    label: str
    parameters: tuple[str, ...] = ()
    purpose: str = ""


class CadCommandSchemaDraft(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    implementation_track: str = ""
    status: SchemaDraftStatus = "template_inferred"
    reachability: str = ""
    fixture: str = ""
    probe_kind: str = ""
    template_parameters: tuple[str, ...] = ()
    missing_parameters: tuple[str, ...] = ()
    parameter_drafts: tuple[CadParameterDraft, ...] = ()
    option_panel_groups: tuple[CadOptionPanelDraft, ...] = ()
    validation_checks: tuple[str, ...] = ()
    expected_state_effects: tuple[str, ...] = ()
    promotion_blockers: tuple[str, ...] = ()
    next_action: str = ""

    @property
    def ready_for_descriptor_promotion(self) -> bool:
        return self.status == "observed_schema" and not self.promotion_blockers

    def parameter_specs(self) -> tuple[ParameterSpec, ...]:
        return tuple(draft.to_parameter_spec() for draft in self.parameter_drafts)


@dataclass(frozen=True)
class CadSchemaDraftCatalog:
    drafts: dict[str, CadCommandSchemaDraft]
    kb_root: str
    generated_utc: str = ""

    def get(self, command_id: str) -> CadCommandSchemaDraft:
        return self.drafts[command_id]

    def all_drafts(self) -> list[CadCommandSchemaDraft]:
        return [self.drafts[key] for key in sorted(self.drafts)]

    def by_track(self, implementation_track: str) -> list[CadCommandSchemaDraft]:
        return [draft for draft in self.all_drafts() if draft.implementation_track == implementation_track]

    def summary(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        track_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        control_counts: dict[str, int] = {}
        for draft in self.drafts.values():
            status_counts[draft.status] = status_counts.get(draft.status, 0) + 1
            track_counts[draft.implementation_track or "<missing>"] = track_counts.get(draft.implementation_track or "<missing>", 0) + 1
            for blocker in draft.promotion_blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
            for parameter in draft.parameter_drafts:
                control_counts[parameter.ui_control] = control_counts.get(parameter.ui_control, 0) + 1
        return {
            "draft_count": len(self.drafts),
            "status_counts": dict(sorted(status_counts.items())),
            "track_counts": dict(sorted(track_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "ui_control_counts": dict(sorted(control_counts.items())),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_schema_draft_catalog(kb_root: str | Path | None = None) -> CadSchemaDraftCatalog:
    observation = load_plasticity_observation_evidence(kb_root)
    queue = build_ghostforge_cad_development_queue(kb_root)
    drafts: dict[str, CadCommandSchemaDraft] = {}
    for template in observation.templates:
        task = queue.tasks.get(template.command_id)
        drafts[template.command_id] = _draft_from_template(template, task)
    return CadSchemaDraftCatalog(
        drafts=drafts,
        kb_root=observation.kb_root,
        generated_utc=observation.generated_utc,
    )


def _draft_from_template(
    template: PlasticityCommandTemplate,
    task: GhostForgeCadDevelopmentTask | None,
) -> CadCommandSchemaDraft:
    status = _schema_status(template.schema_status)
    parameter_drafts = tuple(_parameter_draft(param, task) for param in template.parameters_to_observe)
    promotion_blockers = _promotion_blockers(template, task)
    groups = _option_panel_groups(parameter_drafts)
    return CadCommandSchemaDraft(
        command_id=template.command_id,
        label=template.label,
        implementation_track=task.implementation_track if task else "",
        status=status,
        reachability=template.reachability,
        fixture=template.fixture,
        probe_kind=template.probe_kind,
        template_parameters=tuple(param.name for param in template.parameters_to_observe),
        missing_parameters=task.missing_parameters if task else tuple(param.name for param in template.parameters_to_observe),
        parameter_drafts=parameter_drafts,
        option_panel_groups=groups,
        validation_checks=template.validation_checks,
        expected_state_effects=template.expected_state_effects,
        promotion_blockers=promotion_blockers,
        next_action=_next_schema_action(status, promotion_blockers, task),
    )


def _schema_status(value: str) -> SchemaDraftStatus:
    if value == "observed_schema":
        return "observed_schema"
    if value == "observed_partial":
        return "observed_partial"
    return "template_inferred"


def _parameter_draft(
    parameter: PlasticityParameterTemplate,
    task: GhostForgeCadDevelopmentTask | None,
) -> CadParameterDraft:
    ghostforge_type = _ghostforge_type(parameter)
    panel_group = _panel_group(parameter.name, parameter.type)
    ui_control = _ui_control(parameter.name, parameter.type, ghostforge_type)
    required = _is_required(parameter.name, parameter.type)
    values = _enum_values(parameter.name)
    default = _default_value(parameter.name, ghostforge_type, values)
    blockers = ["control_not_observed", "default_not_observed"]
    if values:
        blockers.append("enum_values_need_confirmation")
    if task and parameter.name not in task.missing_parameters and task.schema_status == "observed_schema":
        blockers = []
    return CadParameterDraft(
        name=parameter.name,
        source_type=parameter.type,
        ghostforge_type=ghostforge_type,
        panel_group=panel_group,
        ui_control=ui_control,
        required=required,
        default=default,
        values=values,
        unit=_unit(parameter.name, ghostforge_type),
        description=parameter.description,
        validation_rules=_validation_rules(parameter.name, ghostforge_type),
        promotion_blockers=tuple(blockers),
    )


def _ghostforge_type(parameter: PlasticityParameterTemplate) -> str:
    source_type = parameter.type.lower()
    name = parameter.name.lower()
    if source_type in {"selection_set", "selection"} or "selection" in name:
        return "selection_set"
    if source_type in {"number", "float", "integer"} or any(token in name for token in ("distance", "radius", "tolerance", "angle", "width", "scale")):
        return "float"
    if source_type in {"bool", "boolean"} or name.startswith(("include_", "trim_", "imprint_", "preserve_", "heal_", "toggle_")):
        return "bool"
    if source_type in {"filesystem_path", "path"} or "path" in name:
        return "path"
    if source_type in {"vector_or_axis", "vector"} or any(token in name for token in ("direction", "axis", "pivot", "normal")):
        return "vector_or_axis"
    if source_type in {"command_state"} or "preview" in name or "command_state" in name:
        return "command_state"
    if source_type in {"enum"} or any(token in name for token in ("mode", "operation", "continuity", "format", "scope", "units", "policy", "preset")):
        return "enum"
    if source_type in {"object"} or name == "options":
        return "object"
    return source_type or "string"


def _panel_group(name: str, source_type: str) -> str:
    lowered = name.lower()
    if "selection" in lowered:
        return "selection"
    if any(token in lowered for token in ("preview", "accept", "cancel", "command_state")) or source_type == "command_state":
        return "command_state"
    if any(token in lowered for token in ("tolerance", "quality", "continuity", "smoothing", "angle", "width")):
        return "advanced_options"
    if any(token in lowered for token in ("path", "format", "units", "overwrite", "scope", "axis_preset")):
        return "file_options"
    return "primary_parameters"


def _ui_control(name: str, source_type: str, ghostforge_type: str) -> str:
    lowered = name.lower()
    if ghostforge_type == "selection_set":
        return "selection_picker"
    if ghostforge_type == "bool":
        return "checkbox"
    if ghostforge_type == "enum":
        return "dropdown"
    if ghostforge_type == "float":
        return "numeric_input"
    if ghostforge_type == "path":
        return "file_picker"
    if ghostforge_type == "vector_or_axis":
        return "axis_vector_picker"
    if ghostforge_type == "command_state" or "preview" in lowered:
        return "command_state_controls"
    if source_type == "object" or lowered == "options":
        return "schema_group"
    return "text_input"


def _is_required(name: str, source_type: str) -> bool:
    lowered = name.lower()
    return (
        "selection" in lowered
        or lowered in {"path", "target_path", "format"}
        or any(token in lowered for token in ("distance", "radius"))
        or source_type == "selection_set"
    )


def _enum_values(name: str) -> tuple[Any, ...]:
    lowered = name.lower()
    if "continuity" in lowered:
        return ("g0", "g1", "g2")
    if "operation" in lowered:
        return ("new_body", "join", "cut", "intersect")
    if lowered == "mode" or lowered.endswith("_mode"):
        return ("individual", "chain", "body", "surface")
    if "format" in lowered:
        return ("glb", "obj", "stl", "fbx", "ply", "3mf", "step", "iges", "sat", "x_t", "dxf")
    if "scope" in lowered:
        return ("selection", "visible_scene", "whole_scene", "named_set")
    if "units" in lowered:
        return ("scene", "mm", "cm", "m", "inch", "foot")
    if "overwrite" in lowered:
        return ("fail_if_exists", "overwrite", "versioned_name")
    if "axis_preset" in lowered:
        return ("ghostforge", "unity", "unreal", "blender")
    return ()


def _default_value(name: str, ghostforge_type: str, values: tuple[Any, ...]) -> Any:
    lowered = name.lower()
    if values:
        return values[0]
    if ghostforge_type == "bool":
        return False
    if ghostforge_type == "float":
        if "tolerance" in lowered:
            return 1e-5
        if "angle" in lowered:
            return 0.0
        return None
    return None


def _unit(name: str, ghostforge_type: str) -> str | None:
    lowered = name.lower()
    if any(token in lowered for token in ("distance", "radius", "width", "tolerance")):
        return "scene_units"
    if "angle" in lowered:
        return "degrees"
    return None


def _validation_rules(name: str, ghostforge_type: str) -> tuple[str, ...]:
    rules = []
    lowered = name.lower()
    if ghostforge_type == "selection_set":
        rules.append("selection_contract_must_accept_items")
    if "radius" in lowered or "distance" in lowered or "width" in lowered:
        rules.append("value_must_be_nonzero_when_command_requires_extent")
    if "tolerance" in lowered:
        rules.append("tolerance_must_be_positive_and_recorded")
    if ghostforge_type == "path":
        rules.append("path_must_be_workspace_controlled_for_automation")
    if ghostforge_type == "enum":
        rules.append("value_must_match_observed_options")
    return tuple(rules)


def _promotion_blockers(
    template: PlasticityCommandTemplate,
    task: GhostForgeCadDevelopmentTask | None,
) -> tuple[str, ...]:
    blockers = []
    if template.schema_status != "observed_schema":
        blockers.append("plasticity.observed_schema_missing")
    if task and "plasticity.reset_not_verified" in task.blockers:
        blockers.append("plasticity.reset_not_verified")
    if task and "static_asset.owner_unresolved" in task.blockers:
        blockers.append("static_asset.owner_unresolved")
    if task and "automation.workspace_safety_gate_missing" in task.blockers:
        blockers.append("automation.workspace_safety_gate_missing")
    if not template.validation_checks:
        blockers.append("validation_checks_missing")
    return tuple(dict.fromkeys(blockers))


def _option_panel_groups(parameters: tuple[CadParameterDraft, ...]) -> tuple[CadOptionPanelDraft, ...]:
    labels = {
        "selection": "Selection",
        "primary_parameters": "Parameters",
        "advanced_options": "Advanced",
        "file_options": "File",
        "command_state": "Command",
    }
    purposes = {
        "selection": "Selection consumed or modified by the command.",
        "primary_parameters": "Core command values surfaced in the main panel.",
        "advanced_options": "Tolerance, continuity, quality, and less-common operation controls.",
        "file_options": "Import/export paths, formats, units, and overwrite policies.",
        "command_state": "Preview, accept, cancel, and transient command state.",
    }
    groups: list[CadOptionPanelDraft] = []
    for group_id in ("selection", "primary_parameters", "advanced_options", "file_options", "command_state"):
        names = tuple(parameter.name for parameter in parameters if parameter.panel_group == group_id)
        if names:
            groups.append(
                CadOptionPanelDraft(
                    group_id=group_id,
                    label=labels[group_id],
                    parameters=names,
                    purpose=purposes[group_id],
                )
            )
    return tuple(groups)


def _next_schema_action(
    status: SchemaDraftStatus,
    blockers: tuple[str, ...],
    task: GhostForgeCadDevelopmentTask | None,
) -> str:
    if "static_asset.owner_unresolved" in blockers:
        return "resolve_owner_command_before_promoting_option_panel_schema"
    if "automation.workspace_safety_gate_missing" in blockers:
        return "add_workspace_safety_gate_before_promoting_file_option_schema"
    if status != "observed_schema":
        return "use_draft_for_qt_mcp_panel_planning_but_wait_for_observed_schema"
    if task and task.implementation_track == "file_interop":
        return "promote_to_native_interop_descriptor_option_schema"
    return "promote_to_native_cad_command_descriptor_schema"


__all__ = [
    "CadCommandSchemaDraft",
    "CadOptionPanelDraft",
    "CadParameterDraft",
    "CadSchemaDraftCatalog",
    "SchemaDraftStatus",
    "build_cad_schema_draft_catalog",
]
