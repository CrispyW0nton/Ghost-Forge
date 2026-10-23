"""Typed CAD command descriptors for Ghost Forge.

These contracts are deliberately richer than the current authoring
``OperationDescriptor``.  Plasticity recon showed that a modeling command is
not ready for artists or agents until selection rules, parameters, topology
effects, tolerances, failures, undo, fixtures, and automation surfaces are all
inspectable.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CadCommandStatus = Literal[
    "implemented",
    "implemented_mesh",
    "planned",
    "alias",
    "option",
    "contextual_mode",
    "controlled_probe_needed",
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ParameterSpec(FrozenModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    required: bool = False
    default: Any = None
    values: tuple[Any, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    description: str = ""
    ui: dict[str, Any] = Field(default_factory=dict)


class FormatOption(FrozenModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    default: Any = None
    applies_to: tuple[str, ...] = ()
    description: str = ""


class SelectionContract(FrozenModel):
    object_kinds: tuple[str, ...] = ("mesh",)
    subobject_kinds: tuple[str, ...] = ()
    min_count: int = 0
    max_count: int | None = None
    ordered: bool = False
    requires_active_object: bool = True
    active_plane_required: bool = False
    notes: tuple[str, ...] = ()


class TopologyEffects(FrozenModel):
    creates: tuple[str, ...] = ()
    deletes: tuple[str, ...] = ()
    modifies: tuple[str, ...] = ()
    preserves: tuple[str, ...] = ()
    id_policy: str = "stable_where_possible"
    result_summary_fields: tuple[str, ...] = (
        "vertex_count",
        "edge_count",
        "face_count",
        "component_count",
        "bounds",
    )


class TolerancePolicy(FrozenModel):
    linear: float | None = None
    angular_degrees: float | None = None
    unit: str = "scene_units"
    description: str = ""


class FailureMode(FrozenModel):
    code: str = Field(min_length=1)
    message: str
    recovery: str = ""


class UndoContract(FrozenModel):
    transaction_name: str
    reversible: bool = True
    delta_kind: str = "mesh_delta"
    notes: tuple[str, ...] = ()


class CadCommandDescriptor(FrozenModel):
    command_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    family: str = Field(min_length=1)
    status: CadCommandStatus = "planned"
    implementation_kind: str = "none"
    source_operation: str | None = None
    alias_of: str | None = None
    option_of: str | None = None
    contextual_mode_of: str | None = None
    plasticity_reference: dict[str, Any] = Field(default_factory=dict)
    selection_contract: SelectionContract = Field(default_factory=SelectionContract)
    parameter_schema: tuple[ParameterSpec, ...] = ()
    option_panel_schema: tuple[ParameterSpec, ...] = ()
    format_options: tuple[FormatOption, ...] = ()
    preview_contract: tuple[str, ...] = ()
    topology_effects: TopologyEffects = Field(default_factory=TopologyEffects)
    tolerance_policy: TolerancePolicy = Field(default_factory=TolerancePolicy)
    failure_modes: tuple[FailureMode, ...] = ()
    undo_contract: UndoContract
    fixture_tests: tuple[str, ...] = ()
    manifest_effect: tuple[str, ...] = ()
    mcp_surface: dict[str, Any] = Field(default_factory=dict)
    qt_surface: dict[str, Any] = Field(default_factory=dict)
    acceptance_gates: tuple[str, ...] = ()

    @property
    def is_top_level_command(self) -> bool:
        return self.status not in {"alias", "option", "contextual_mode"}


__all__ = [
    "CadCommandDescriptor",
    "CadCommandStatus",
    "FailureMode",
    "FormatOption",
    "ParameterSpec",
    "SelectionContract",
    "TolerancePolicy",
    "TopologyEffects",
    "UndoContract",
]
