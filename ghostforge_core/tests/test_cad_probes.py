from __future__ import annotations

from ghostforge_core.cad import (
    build_default_cad_registry,
    build_default_fixture_catalog,
    build_default_probe_matrix,
)


def test_probe_matrix_summarizes_current_plasticity_recon_gaps() -> None:
    matrix = build_default_probe_matrix()
    summary = matrix.summary()

    assert summary["command_plan_count"] >= 11
    assert summary["format_plan_count"] == 6
    assert summary["static_asset_plan_count"] == 4
    assert summary["command_readiness_bucket_counts"]["palette_confirmation"] == 2
    assert summary["command_readiness_bucket_counts"]["review_as_option_or_alias"] == 2
    assert summary["commands_needing_live_plasticity_probe"] >= 5


def test_every_default_cad_command_has_probe_or_internal_contract_plan() -> None:
    registry = build_default_cad_registry()
    matrix = build_default_probe_matrix()

    assert {command.command_id for command in registry.all()} <= set(matrix.command_plans)


def test_probe_plans_reference_known_fixture_contracts() -> None:
    fixture_catalog = build_default_fixture_catalog()
    matrix = build_default_probe_matrix()
    known_fixture_ids = set(fixture_catalog.fixtures)

    for plan in matrix.all_command_plans():
        assert plan.fixture_ids
        assert set(plan.fixture_ids) <= known_fixture_ids

    for plan in matrix.all_format_plans():
        assert plan.fixture_ids
        assert set(plan.fixture_ids) <= known_fixture_ids


def test_export_mesh_probe_tracks_format_specific_options_and_file_io_route() -> None:
    matrix = build_default_probe_matrix()

    export_mesh = matrix.get_command_plan("export_mesh")
    assert export_mesh.priority == "critical"
    assert export_mesh.readiness_bucket == "palette_confirmation"
    assert {"angle_tolerance", "inflect", "max_width"}.issubset(
        set(export_mesh.option_panel_targets)
    )
    assert "mesh_export" in export_mesh.import_export_targets
    assert any(step.requires_disposable_fixture for step in export_mesh.automation_route)

    mesh_format = matrix.format_plans["mesh_export"]
    assert {"angle_tolerance", "inflect", "max_width"}.issubset(
        set(mesh_format.option_targets)
    )


def test_static_asset_probe_plans_keep_face_change_and_xnurbs_unpromoted() -> None:
    matrix = build_default_probe_matrix()

    face_change = matrix.static_asset_plans["face_change"]
    assert face_change.mapping_status == "likely_option_or_alias"
    assert "match_face" in face_change.candidate_owner_commands
    assert face_change.ghostforge_mapping.startswith("option_of:")

    xnurbs = matrix.static_asset_plans["xnurbs"]
    assert "xnurbs-boundary.png" in xnurbs.evidence_assets
    assert "surface_patch" in xnurbs.candidate_owner_commands
    assert xnurbs.ghostforge_mapping.startswith("contextual_mode_of:")


def test_modeling_probe_plans_capture_topology_tolerance_and_failure_targets() -> None:
    matrix = build_default_probe_matrix()

    fillet = matrix.get_command_plan("fillet")
    assert "blend_face_ids" in fillet.topology_naming_targets
    assert "radius_too_large" in fillet.failure_mode_targets
    assert "blend_tolerance" in fillet.tolerance_targets

    project = matrix.get_command_plan("project")
    assert "ordered_selection" in project.selection_rule_targets
    assert "curve_projection_tolerance" in project.tolerance_targets
