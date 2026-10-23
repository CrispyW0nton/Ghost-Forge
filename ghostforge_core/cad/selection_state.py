"""Native CAD selection-state contracts for Ghost Forge.

Plasticity recon shows many selection, snapping, grouping, and construction
plane commands.  Ghost Forge needs those behaviors as queryable state, not
hidden viewport state.  This module defines selection modes, topology id
policies, command-level state transitions, failure cases, and automation
evidence required before a command can drive the native picker/preflight path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .development_queue import GhostForgeCadDevelopmentTask, build_ghostforge_cad_development_queue


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


SelectionOperationKind = Literal[
    "set_mode",
    "toggle_mode",
    "convert_selection",
    "select_query",
    "selection_set_mutation",
    "snapping_or_plane_state",
    "lock_group_state",
    "face_context_tool",
    "unknown",
]


class CadSelectionModeDescriptor(FrozenModel):
    mode_id: str = Field(min_length=1)
    label: str
    selection_kinds: tuple[str, ...] = ()
    object_kinds: tuple[str, ...] = ()
    topology_id_prefixes: tuple[str, ...] = ()
    hit_test_priority: tuple[str, ...] = ()
    requires_active_plane: bool = False
    notes: tuple[str, ...] = ()


class CadSelectionCommandContract(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = ""
    operation_kind: SelectionOperationKind = "unknown"
    implementation_track: str = ""
    source_probe_kind: str = ""
    input_modes: tuple[str, ...] = ()
    output_modes: tuple[str, ...] = ()
    modifies_selection: bool = True
    modifies_document_state: bool = False
    preserves_order: bool = False
    active_plane_policy: str = "preserve_current"
    topology_naming_policy: tuple[str, ...] = ()
    expected_state_delta: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    automation_evidence: tuple[str, ...] = ()
    promotion_blockers: tuple[str, ...] = ()
    next_action: str = ""


DEFAULT_SELECTION_MODES: tuple[CadSelectionModeDescriptor, ...] = (
    CadSelectionModeDescriptor(
        mode_id="object",
        label="Object",
        selection_kinds=("object",),
        object_kinds=("mesh", "solid", "surface", "curve", "scene"),
        topology_id_prefixes=("O_", "mesh_", "body_", "scene_"),
        hit_test_priority=("object", "body", "mesh"),
        notes=("Object mode selects whole entities and is the default safe command context.",),
    ),
    CadSelectionModeDescriptor(
        mode_id="solid",
        label="Solid",
        selection_kinds=("solid", "object"),
        object_kinds=("solid", "mesh"),
        topology_id_prefixes=("B_", "body_", "solid_"),
        hit_test_priority=("solid", "body", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="surface",
        label="Surface",
        selection_kinds=("surface", "face"),
        object_kinds=("surface", "solid", "mesh"),
        topology_id_prefixes=("S_", "F_"),
        hit_test_priority=("surface", "face", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="face",
        label="Face",
        selection_kinds=("face",),
        object_kinds=("mesh", "solid", "surface"),
        topology_id_prefixes=("F_", "face_"),
        hit_test_priority=("face", "surface", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="edge",
        label="Edge",
        selection_kinds=("edge",),
        object_kinds=("mesh", "solid", "surface", "curve"),
        topology_id_prefixes=("E_", "edge_", "B_"),
        hit_test_priority=("edge", "boundary", "curve", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="vertex",
        label="Vertex",
        selection_kinds=("vertex",),
        object_kinds=("mesh", "curve"),
        topology_id_prefixes=("V_", "vertex_"),
        hit_test_priority=("vertex", "edge", "face", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="curve",
        label="Curve",
        selection_kinds=("curve",),
        object_kinds=("curve", "surface"),
        topology_id_prefixes=("C_", "curve_"),
        hit_test_priority=("curve", "edge", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="group",
        label="Group",
        selection_kinds=("object", "group"),
        object_kinds=("group", "mesh", "solid", "surface", "curve"),
        topology_id_prefixes=("G_", "group_"),
        hit_test_priority=("group", "object"),
    ),
    CadSelectionModeDescriptor(
        mode_id="all",
        label="All",
        selection_kinds=("object", "solid", "surface", "curve", "face", "edge", "vertex", "group"),
        object_kinds=("mesh", "solid", "surface", "curve", "group", "scene"),
        topology_id_prefixes=("O_", "B_", "S_", "C_", "F_", "E_", "V_", "G_"),
        hit_test_priority=("vertex", "edge", "face", "curve", "surface", "solid", "object", "group"),
    ),
)


@dataclass(frozen=True)
class CadSelectionContractCatalog:
    modes: dict[str, CadSelectionModeDescriptor]
    command_contracts: dict[str, CadSelectionCommandContract]
    kb_root: str
    generated_utc: str = ""

    def get_mode(self, mode_id: str) -> CadSelectionModeDescriptor:
        return self.modes[mode_id]

    def get_command(self, command_id: str) -> CadSelectionCommandContract:
        return self.command_contracts[command_id]

    def all_modes(self) -> list[CadSelectionModeDescriptor]:
        return [self.modes[key] for key in sorted(self.modes)]

    def all_commands(self) -> list[CadSelectionCommandContract]:
        return [self.command_contracts[key] for key in sorted(self.command_contracts)]

    def summary(self) -> dict[str, Any]:
        operation_counts: dict[str, int] = {}
        blocker_counts: dict[str, int] = {}
        for contract in self.command_contracts.values():
            operation_counts[contract.operation_kind] = operation_counts.get(contract.operation_kind, 0) + 1
            for blocker in contract.promotion_blockers:
                blocker_counts[blocker] = blocker_counts.get(blocker, 0) + 1
        return {
            "mode_count": len(self.modes),
            "command_contract_count": len(self.command_contracts),
            "operation_kind_counts": dict(sorted(operation_counts.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "runtime_dependency": "none",
            "plasticity_role": "development_evidence_only",
        }


def build_cad_selection_contract_catalog(kb_root: str | Path | None = None) -> CadSelectionContractCatalog:
    queue = build_ghostforge_cad_development_queue(kb_root)
    tasks = [
        task
        for task in queue.all_tasks()
        if task.implementation_track == "selection_state"
        or task.command_id.startswith(("select_", "selection_"))
        or task.command_id in {"group_selected", "ungroup_selected", "lock_selected", "unlock_all", "match_face", "push_face"}
    ]
    contracts = {task.command_id: _contract_from_task(task) for task in tasks}
    return CadSelectionContractCatalog(
        modes={mode.mode_id: mode for mode in DEFAULT_SELECTION_MODES},
        command_contracts=contracts,
        kb_root=queue.kb_root,
        generated_utc=queue.generated_utc,
    )


def _contract_from_task(task: GhostForgeCadDevelopmentTask) -> CadSelectionCommandContract:
    operation_kind = _operation_kind(task.command_id)
    input_modes, output_modes = _selection_modes(task.command_id, operation_kind)
    modifies_document_state = operation_kind in {"lock_group_state", "snapping_or_plane_state", "face_context_tool"}
    return CadSelectionCommandContract(
        command_id=task.command_id,
        label=task.label,
        operation_kind=operation_kind,
        implementation_track=task.implementation_track,
        source_probe_kind=task.probe_kind,
        input_modes=input_modes,
        output_modes=output_modes,
        modifies_selection=operation_kind not in {"snapping_or_plane_state"},
        modifies_document_state=modifies_document_state,
        preserves_order=operation_kind in {"convert_selection", "face_context_tool"},
        active_plane_policy=_active_plane_policy(task.command_id, operation_kind),
        topology_naming_policy=_topology_naming_policy(operation_kind, output_modes),
        expected_state_delta=_expected_state_delta(task.command_id, operation_kind, output_modes),
        failure_modes=_failure_modes(operation_kind),
        automation_evidence=_automation_evidence(operation_kind),
        promotion_blockers=_promotion_blockers(task),
        next_action=_next_action(task, operation_kind),
    )


def _operation_kind(command_id: str) -> SelectionOperationKind:
    if command_id.startswith("selection_mode_set_"):
        return "set_mode"
    if command_id.startswith("selection_toggle_") or command_id.startswith("viewport_toggle_"):
        return "toggle_mode"
    if command_id.startswith("selection_convert_to_"):
        return "convert_selection"
    if command_id.startswith("select_") or command_id in {"find_boundary_edges", "complete_edge"}:
        return "select_query"
    if command_id in {"group_selected", "ungroup_selected", "lock_selected", "unlock_all"}:
        return "lock_group_state"
    if "grid_" in command_id or "construction_plane" in command_id:
        return "snapping_or_plane_state"
    if command_id in {"match_face", "push_face", "unwrap_face"}:
        return "face_context_tool"
    return "selection_set_mutation"


def _selection_modes(command_id: str, operation_kind: SelectionOperationKind) -> tuple[tuple[str, ...], tuple[str, ...]]:
    lowered = command_id.lower()
    if "edge" in lowered:
        output = ("edge",)
    elif "face" in lowered:
        output = ("face",)
    elif "solid" in lowered:
        output = ("solid",)
    elif "curve" in lowered:
        output = ("curve",)
    elif "group" in lowered:
        output = ("group",)
    elif lowered.endswith("_all") or "set_all" in lowered or lowered == "select_all":
        output = ("all",)
    else:
        output = ("object",)

    if operation_kind == "convert_selection":
        return (("object", "face", "edge", "curve", "solid", "surface"), output)
    if operation_kind in {"set_mode", "toggle_mode"}:
        return (("all",), output)
    if operation_kind == "select_query":
        return (("all",), output)
    if operation_kind == "face_context_tool":
        return (("face", "surface"), ("face",))
    if operation_kind == "lock_group_state":
        return (("object", "group"), ("object", "group"))
    return (("all",), output)


def _active_plane_policy(command_id: str, operation_kind: SelectionOperationKind) -> str:
    if "construction_plane" in command_id:
        return "sets_or_resets_active_plane"
    if operation_kind == "snapping_or_plane_state":
        return "may_read_active_plane"
    if operation_kind == "face_context_tool":
        return "uses_selected_face_or_active_plane"
    return "preserve_current"


def _topology_naming_policy(operation_kind: SelectionOperationKind, output_modes: tuple[str, ...]) -> tuple[str, ...]:
    policies = ["selected items must carry stable object_id and topology_id where applicable"]
    if "face" in output_modes:
        policies.append("face selections use F_ or face_ topology ids")
    if "edge" in output_modes:
        policies.append("edge selections use E_ or edge_ topology ids")
    if "vertex" in output_modes:
        policies.append("vertex selections use V_ or vertex_ topology ids")
    if operation_kind == "convert_selection":
        policies.append("conversion records source topology ids and resulting topology ids")
    if operation_kind == "select_query":
        policies.append("query selections record why each hit was selected or filtered")
    return tuple(policies)


def _expected_state_delta(command_id: str, operation_kind: SelectionOperationKind, output_modes: tuple[str, ...]) -> tuple[str, ...]:
    if operation_kind == "set_mode":
        return (f"selection_filter.mode={output_modes[0]}", "selection remains valid or is pruned with filter reasons")
    if operation_kind == "toggle_mode":
        return (f"selection_filter.toggle={output_modes[0]}", "visible selection affordances update")
    if operation_kind == "convert_selection":
        return (f"selection converted to {output_modes[0]}", "source selection lineage recorded")
    if operation_kind == "select_query":
        return ("selection set replaced or extended by query result", "hit/filter reasons recorded")
    if operation_kind == "lock_group_state":
        return ("object/group lock or grouping metadata changes", "selection ids preserved where possible")
    if operation_kind == "snapping_or_plane_state":
        return ("active plane, grid, or snapping settings change", "selection set is preserved")
    if operation_kind == "face_context_tool":
        return ("face-context selection/option state changes", "owner modeling command must record topology effects")
    return ("selection set changes",)


def _failure_modes(operation_kind: SelectionOperationKind) -> tuple[str, ...]:
    base = ["selection.empty", "selection.filtered_out"]
    if operation_kind == "convert_selection":
        base.append("selection.conversion_no_result")
    if operation_kind == "face_context_tool":
        base.extend(("selection.face_required", "relationship.owner_required"))
    if operation_kind == "snapping_or_plane_state":
        base.append("active_plane.invalid")
    return tuple(base)


def _automation_evidence(operation_kind: SelectionOperationKind) -> tuple[str, ...]:
    evidence = ["before_selection_state", "after_selection_state", "selection_filter_state"]
    if operation_kind in {"set_mode", "toggle_mode"}:
        evidence.append("mode_toggle_visual_or_state_record")
    if operation_kind == "convert_selection":
        evidence.extend(("source_selection_ids", "result_selection_ids"))
    if operation_kind == "select_query":
        evidence.append("hit_filter_reason_record")
    if operation_kind == "snapping_or_plane_state":
        evidence.extend(("active_plane_before_after", "grid_or_snap_state"))
    if operation_kind == "face_context_tool":
        evidence.extend(("candidate_owner_panel_screenshot", "face_selection_fixture"))
    return tuple(evidence)


def _promotion_blockers(task: GhostForgeCadDevelopmentTask) -> tuple[str, ...]:
    blockers = ["selection_state_observation_missing"]
    for blocker in task.blockers:
        if blocker in {"plasticity.observed_schema_missing", "plasticity.reset_not_verified", "static_asset.owner_unresolved"}:
            blockers.append(blocker)
    return tuple(dict.fromkeys(blockers))


def _next_action(task: GhostForgeCadDevelopmentTask, operation_kind: SelectionOperationKind) -> str:
    if operation_kind == "face_context_tool" or "static_asset.owner_unresolved" in task.blockers:
        return "record_face_selection_owner_and_option_panel_before_native_promotion"
    if operation_kind == "snapping_or_plane_state":
        return "promote_into_queryable_viewport_and_construction_plane_state"
    if operation_kind in {"set_mode", "toggle_mode", "convert_selection", "select_query"}:
        return "promote_into_core_selection_filter_and_conversion_api_after_observation"
    return "record_selection_state_delta_and_reset_verification"


__all__ = [
    "CadSelectionCommandContract",
    "CadSelectionContractCatalog",
    "CadSelectionModeDescriptor",
    "DEFAULT_SELECTION_MODES",
    "SelectionOperationKind",
    "build_cad_selection_contract_catalog",
]
