"""CAD fixture and behavior contracts.

Plasticity recon made one point painfully clear: command names alone are not
enough.  To build a better Ghost Forge command system we need deterministic
fixtures, named topology, expected parameter sets, and expected topology deltas.
These models are intentionally inspectable by tests, Qt, and MCP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NamedSelection(FrozenModel):
    selection_id: str = Field(min_length=1)
    label: str
    mode: str
    vertices: tuple[int, ...] = ()
    edges: tuple[tuple[int, int], ...] = ()
    faces: tuple[int, ...] = ()
    elements: tuple[int, ...] = ()
    description: str = ""


class CadFixture(FrozenModel):
    fixture_id: str = Field(min_length=1)
    label: str
    geometry_kind: str
    primitive_recipe: dict[str, Any] = Field(default_factory=dict)
    named_topology: dict[str, Any] = Field(default_factory=dict)
    selection_sets: tuple[NamedSelection, ...] = ()
    tolerance_notes: tuple[str, ...] = ()
    purpose: tuple[str, ...] = ()


class TopologyExpectation(FrozenModel):
    preserves: tuple[str, ...] = ()
    creates: tuple[str, ...] = ()
    deletes: tuple[str, ...] = ()
    modifies: tuple[str, ...] = ()
    expected_count_deltas: dict[str, str] = Field(default_factory=dict)
    stable_id_expectation: str = "stable_where_possible"
    notes: tuple[str, ...] = ()


class CommandFixtureExpectation(FrozenModel):
    command_id: str
    fixture_id: str
    selection_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_topology: TopologyExpectation
    expected_failures: tuple[str, ...] = ()
    verification_status: str = "contract_defined"
    notes: tuple[str, ...] = ()


DEFAULT_CAD_FIXTURES: tuple[CadFixture, ...] = (
    CadFixture(
        fixture_id="fixture_cube_mesh",
        label="Named cube mesh",
        geometry_kind="mesh",
        primitive_recipe={"type": "box", "extents": [1.0, 1.0, 1.0], "units": "scene_units"},
        named_topology={
            "faces": {
                "top": 0,
                "bottom": 1,
                "front": 2,
                "back": 3,
                "right": 4,
                "left": 5,
            },
            "edges": {
                "top_front": [0, 1],
                "top_right": [1, 2],
                "vertical_front_right": [2, 6],
            },
        },
        selection_sets=(
            NamedSelection(selection_id="object", label="Whole cube", mode="object", description="One selected mesh object."),
            NamedSelection(selection_id="top_face", label="Top face", mode="face", faces=(0,)),
            NamedSelection(selection_id="vertical_edge", label="Vertical edge", mode="edge", edges=((2, 6),)),
            NamedSelection(selection_id="two_vertices", label="Two vertices", mode="vertex", vertices=(0, 1)),
        ),
        tolerance_notes=("Unit cube should avoid tiny-feature tolerance ambiguity.",),
        purpose=("basic topology count deltas", "selection contracts", "transform and cleanup operations"),
    ),
    CadFixture(
        fixture_id="fixture_degenerate_mesh",
        label="Degenerate mesh",
        geometry_kind="mesh",
        primitive_recipe={
            "type": "custom",
            "vertices": [[0, 0, 0], [1, 0, 0], [1, 0, 0], [0, 0, 0]],
            "faces": [[0, 1, 2], [0, 2, 3]],
        },
        named_topology={"issues": ["duplicate_vertices", "zero_area_faces"]},
        selection_sets=(NamedSelection(selection_id="object", label="Whole degenerate mesh", mode="object"),),
        tolerance_notes=("Used to prove failure modes and repair preflight.",),
        purpose=("failure modes", "tolerance preflight", "validation recovery"),
    ),
    CadFixture(
        fixture_id="fixture_cube_solid",
        label="Named cube solid",
        geometry_kind="future_brep_solid",
        primitive_recipe={"type": "solid_box", "extents": [1.0, 1.0, 1.0], "units": "scene_units"},
        named_topology={
            "faces": {"top": "F_top", "bottom": "F_bottom", "front": "F_front", "back": "F_back"},
            "edges": {"top_front": "E_top_front", "vertical_front_right": "E_vertical_front_right"},
        },
        selection_sets=(
            NamedSelection(selection_id="top_face", label="Top B-rep face", mode="face", description="Stable face id F_top."),
            NamedSelection(selection_id="top_front_edge", label="Top/front B-rep edge", mode="edge", description="Stable edge id E_top_front."),
        ),
        tolerance_notes=("B-rep fixture should preserve named topology across reversible commands where possible.",),
        purpose=("future kernel extrude", "future kernel fillet", "topology naming"),
    ),
    CadFixture(
        fixture_id="fixture_sheet_patch",
        label="Open sheet patch",
        geometry_kind="future_surface",
        primitive_recipe={"type": "plane_patch", "size": [1.0, 1.0], "u_spans": 1, "v_spans": 1},
        named_topology={"boundaries": {"outer": "B_outer"}, "surface": "S_patch"},
        selection_sets=(
            NamedSelection(selection_id="outer_boundary", label="Outer boundary", mode="edge", description="Closed patch boundary."),
            NamedSelection(selection_id="surface", label="Patch surface", mode="face", description="Surface id S_patch."),
        ),
        tolerance_notes=("Surface fixture is for trim/project/extend/patch continuity contracts.",),
        purpose=("surface modeling", "project/imprint", "XNURBS contextual options"),
    ),
    CadFixture(
        fixture_id="fixture_curve_profile",
        label="Closed square curve profile",
        geometry_kind="future_curve",
        primitive_recipe={"type": "polyline", "closed": True, "points": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]]},
        named_topology={"curve": "C_square", "segments": ["C0", "C1", "C2", "C3"]},
        selection_sets=(NamedSelection(selection_id="profile", label="Closed profile", mode="curve", description="Closed square curve."),),
        tolerance_notes=("Closed profile should reject gaps larger than profile closure tolerance.",),
        purpose=("extrude profile", "project curve", "selection ordering"),
    ),
    CadFixture(
        fixture_id="fixture_command_option_mapping",
        label="Command option mapping fixture",
        geometry_kind="metadata",
        primitive_recipe={"type": "no_geometry", "purpose": "alias/option/contextual-mode review"},
        named_topology={},
        selection_sets=(),
        purpose=("static asset mapping", "option ownership", "contextual command review"),
    ),
)


DEFAULT_COMMAND_FIXTURE_EXPECTATIONS: tuple[CommandFixtureExpectation, ...] = (
    CommandFixtureExpectation(
        command_id="transform",
        fixture_id="fixture_cube_mesh",
        selection_id="object",
        parameters={"translate": [1.0, 0.0, 0.0], "rotate_euler_deg": [0.0, 0.0, 0.0], "scale": 1.0},
        expected_topology=TopologyExpectation(
            preserves=("vertex_count", "edge_count", "face_count", "face_ids", "material_slots"),
            modifies=("bounds", "vertex_positions"),
            expected_count_deltas={"vertices": "0", "faces": "0", "components": "0"},
            notes=("Transform should not renumber topology.",),
        ),
    ),
    CommandFixtureExpectation(
        command_id="normalize_scale",
        fixture_id="fixture_cube_mesh",
        selection_id="object",
        parameters={"target_extent": 1.0},
        expected_topology=TopologyExpectation(
            preserves=("vertex_count", "edge_count", "face_count", "face_ids"),
            modifies=("bounds", "vertex_positions"),
            expected_count_deltas={"vertices": "0", "faces": "0"},
        ),
    ),
    CommandFixtureExpectation(
        command_id="recompute_normals",
        fixture_id="fixture_cube_mesh",
        selection_id="object",
        expected_topology=TopologyExpectation(
            preserves=("vertex_count", "edge_count", "face_count", "vertex_positions", "face_ids"),
            modifies=("normals",),
            expected_count_deltas={"vertices": "0", "faces": "0"},
        ),
    ),
    CommandFixtureExpectation(
        command_id="delete_selection",
        fixture_id="fixture_cube_mesh",
        selection_id="top_face",
        expected_topology=TopologyExpectation(
            preserves=("unselected_face_ids",),
            deletes=("selected_faces", "unreferenced_vertices"),
            modifies=("connectivity", "normals"),
            expected_count_deltas={"faces": "<0", "vertices": "<=0"},
            notes=("Deleting all faces must fail; deleting one face should leave a valid open mesh.",),
        ),
        expected_failures=("delete.all_geometry",),
    ),
    CommandFixtureExpectation(
        command_id="weld",
        fixture_id="fixture_degenerate_mesh",
        selection_id="object",
        parameters={"tolerance": 1e-6},
        expected_topology=TopologyExpectation(
            deletes=("duplicate_vertices", "collapsed_faces"),
            modifies=("vertices", "faces", "normals"),
            expected_count_deltas={"vertices": "<0", "faces": "<=0"},
        ),
        expected_failures=("weld.collapsed_all_faces",),
    ),
    CommandFixtureExpectation(
        command_id="extrude",
        fixture_id="fixture_cube_solid",
        selection_id="top_face",
        parameters={"distance": 1.0, "direction": "normal", "operation": "new_body", "draft_angle_deg": 0.0},
        expected_topology=TopologyExpectation(
            creates=("side_faces", "cap_face", "new_body_or_joined_volume"),
            modifies=("selected_profile",),
            expected_count_deltas={"faces": ">0", "edges": ">0", "solids": ">=0"},
            stable_id_expectation="source_face_lineage_recorded",
        ),
        verification_status="planned_until_kernel_exists",
    ),
    CommandFixtureExpectation(
        command_id="fillet",
        fixture_id="fixture_cube_solid",
        selection_id="top_front_edge",
        parameters={"radius": 0.05, "continuity": "g1", "setback": False},
        expected_topology=TopologyExpectation(
            creates=("blend_faces",),
            deletes=("sharp_edge",),
            modifies=("adjacent_faces",),
            expected_count_deltas={"faces": ">0", "edges": ">=0"},
            stable_id_expectation="adjacent_face_lineage_recorded",
        ),
        verification_status="planned_until_kernel_exists",
    ),
    CommandFixtureExpectation(
        command_id="project",
        fixture_id="fixture_sheet_patch",
        selection_id="surface",
        parameters={"projection_mode": "normal", "imprint_result": False, "trim_to_target": False},
        expected_topology=TopologyExpectation(
            creates=("projected_curves",),
            preserves=("target_surface",),
            expected_count_deltas={"curves": ">0", "surfaces": "0"},
        ),
        verification_status="planned_until_kernel_exists",
    ),
    CommandFixtureExpectation(
        command_id="export_mesh",
        fixture_id="fixture_cube_mesh",
        selection_id="object",
        parameters={"format": "glb", "include_materials": True, "axis_preset": "unity"},
        expected_topology=TopologyExpectation(
            preserves=("scene_geometry", "source_manifest"),
            expected_count_deltas={"source_vertices": "0", "source_faces": "0"},
            notes=("Export creates a file artifact and must not mutate scene topology.",),
        ),
        verification_status="controlled_probe_needed",
    ),
    CommandFixtureExpectation(
        command_id="face_change_grow",
        fixture_id="fixture_command_option_mapping",
        parameters={"grow": True},
        expected_topology=TopologyExpectation(
            preserves=("source_geometry",),
            modifies=("option_panel_state",),
            notes=("Plasticity evidence suggests this is an option relationship, not a standalone command.",),
        ),
        verification_status="relationship_mapping",
    ),
    CommandFixtureExpectation(
        command_id="xnurbs_boundary",
        fixture_id="fixture_command_option_mapping",
        parameters={"boundary_mode": "boundary", "continuity": "g1"},
        expected_topology=TopologyExpectation(
            preserves=("source_geometry",),
            modifies=("contextual_surface_patch_mode",),
            notes=("Plasticity evidence suggests contextual surface/NURBS option behavior.",),
        ),
        verification_status="relationship_mapping",
    ),
)


@dataclass(frozen=True)
class CadFixtureCatalog:
    fixtures: dict[str, CadFixture]
    expectations: tuple[CommandFixtureExpectation, ...]

    @classmethod
    def from_defaults(cls) -> "CadFixtureCatalog":
        return cls(
            fixtures={fixture.fixture_id: fixture for fixture in DEFAULT_CAD_FIXTURES},
            expectations=DEFAULT_COMMAND_FIXTURE_EXPECTATIONS,
        )

    def get_fixture(self, fixture_id: str) -> CadFixture:
        return self.fixtures[fixture_id]

    def all_fixtures(self) -> list[CadFixture]:
        return [self.fixtures[key] for key in sorted(self.fixtures)]

    def expectations_for_command(self, command_id: str) -> list[CommandFixtureExpectation]:
        return [expectation for expectation in self.expectations if expectation.command_id == command_id]

    def expectation_commands(self) -> set[str]:
        return {expectation.command_id for expectation in self.expectations}


def build_default_fixture_catalog() -> CadFixtureCatalog:
    return CadFixtureCatalog.from_defaults()


def expectations_for_command(command_id: str) -> list[CommandFixtureExpectation]:
    return build_default_fixture_catalog().expectations_for_command(command_id)


def fixture_ids(fixtures: Iterable[CadFixture] | None = None) -> set[str]:
    return {fixture.fixture_id for fixture in (fixtures or DEFAULT_CAD_FIXTURES)}


__all__ = [
    "CadFixture",
    "CadFixtureCatalog",
    "CommandFixtureExpectation",
    "DEFAULT_CAD_FIXTURES",
    "DEFAULT_COMMAND_FIXTURE_EXPECTATIONS",
    "NamedSelection",
    "TopologyExpectation",
    "build_default_fixture_catalog",
    "expectations_for_command",
    "fixture_ids",
]
