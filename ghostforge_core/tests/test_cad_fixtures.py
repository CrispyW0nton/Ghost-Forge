from __future__ import annotations

from ghostforge_core.cad import (
    build_default_cad_registry,
    build_default_fixture_catalog,
    fixture_ids,
)


def test_fixture_catalog_exposes_named_topology_and_selection_sets() -> None:
    catalog = build_default_fixture_catalog()

    cube = catalog.get_fixture("fixture_cube_mesh")
    assert cube.geometry_kind == "mesh"
    assert cube.named_topology["faces"]["top"] == 0
    assert {"object", "top_face", "vertical_edge"}.issubset(
        {selection.selection_id for selection in cube.selection_sets}
    )

    solid = catalog.get_fixture("fixture_cube_solid")
    assert solid.named_topology["faces"]["top"] == "F_top"
    assert any("topology naming" in purpose for purpose in solid.purpose)


def test_every_cad_command_has_a_fixture_expectation_contract() -> None:
    registry = build_default_cad_registry()
    catalog = build_default_fixture_catalog()

    assert {command.command_id for command in registry.all()} <= catalog.expectation_commands()
    assert fixture_ids().issuperset(
        {expectation.fixture_id for expectation in catalog.expectations}
    )


def test_mesh_command_expectations_capture_topology_preservation_and_failures() -> None:
    catalog = build_default_fixture_catalog()

    transform = catalog.expectations_for_command("transform")[0]
    assert transform.selection_id == "object"
    assert transform.expected_topology.expected_count_deltas == {
        "vertices": "0",
        "faces": "0",
        "components": "0",
    }
    assert "face_ids" in transform.expected_topology.preserves

    delete = catalog.expectations_for_command("delete_selection")[0]
    assert delete.selection_id == "top_face"
    assert "delete.all_geometry" in delete.expected_failures
    assert delete.expected_topology.expected_count_deltas["faces"] == "<0"

    weld = catalog.expectations_for_command("weld")[0]
    assert weld.fixture_id == "fixture_degenerate_mesh"
    assert "weld.collapsed_all_faces" in weld.expected_failures


def test_plasticity_uncertainty_expectations_do_not_claim_standalone_commands() -> None:
    catalog = build_default_fixture_catalog()

    face_change = catalog.expectations_for_command("face_change_grow")[0]
    assert face_change.fixture_id == "fixture_command_option_mapping"
    assert face_change.verification_status == "relationship_mapping"
    assert "option relationship" in face_change.expected_topology.notes[0]

    xnurbs = catalog.expectations_for_command("xnurbs_boundary")[0]
    assert xnurbs.verification_status == "relationship_mapping"
    assert "contextual_surface_patch_mode" in xnurbs.expected_topology.modifies


def test_export_mesh_expectation_preserves_source_geometry_until_probe() -> None:
    catalog = build_default_fixture_catalog()

    export_mesh = catalog.expectations_for_command("export_mesh")[0]
    assert export_mesh.verification_status == "controlled_probe_needed"
    assert export_mesh.parameters["format"] == "glb"
    assert export_mesh.expected_topology.expected_count_deltas == {
        "source_vertices": "0",
        "source_faces": "0",
    }
    assert "scene_geometry" in export_mesh.expected_topology.preserves
