from __future__ import annotations

from ghostforge_core.cad import build_default_cad_registry


def test_default_cad_registry_contains_plasticity_inspired_contracts() -> None:
    registry = build_default_cad_registry()

    assert registry.has("extrude")
    assert registry.has("fillet")
    assert registry.has("export_mesh")
    assert registry.has("face_change_grow")
    assert registry.has("xnurbs_boundary")

    extrude = registry.get("extrude")
    assert extrude.status == "planned"
    assert extrude.family == "solid"
    assert {param.name for param in extrude.parameter_schema} >= {
        "distance",
        "direction",
        "operation",
        "draft_angle_deg",
    }
    assert "face" in extrude.selection_contract.subobject_kinds
    assert "cad.topology_delta" in extrude.manifest_effect


def test_implemented_mesh_commands_have_automation_and_fixture_gates() -> None:
    registry = build_default_cad_registry()
    implemented = [
        command
        for command in registry.all()
        if command.status in {"implemented", "implemented_mesh"}
    ]

    assert implemented
    for command in implemented:
        assert command.source_operation
        assert command.selection_contract.min_count >= 1
        assert command.fixture_tests
        assert command.failure_modes
        assert command.undo_contract.reversible is True
        assert command.mcp_surface.get("resource")
        assert command.qt_surface.get("action")
        assert "parameter_schema_exists" in command.acceptance_gates


def test_static_asset_uncertainty_is_represented_as_relationships() -> None:
    registry = build_default_cad_registry()

    face_change = registry.get("face_change_grow")
    assert face_change.status == "option"
    assert face_change.option_of == "match_face"
    assert face_change.plasticity_reference["mapping_review"] == "likely_option_or_alias"

    xnurbs = registry.get("xnurbs_boundary")
    assert xnurbs.status == "contextual_mode"
    assert xnurbs.contextual_mode_of == "surface_patch"
    assert {param.name for param in xnurbs.option_panel_schema} == {
        "boundary_mode",
        "continuity",
    }


def test_export_mesh_tracks_format_specific_options_from_recon() -> None:
    registry = build_default_cad_registry()
    export_mesh = registry.get("export_mesh")

    assert export_mesh.status == "controlled_probe_needed"
    assert export_mesh.family == "export"
    assert {option.name for option in export_mesh.format_options} == {
        "angle_tolerance",
        "inflect",
        "max_width",
    }
    assert {param.name for param in export_mesh.parameter_schema} >= {
        "format",
        "target_path",
        "axis_preset",
    }
