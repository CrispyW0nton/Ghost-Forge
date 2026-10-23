from __future__ import annotations

from ghostforge_core.cad import (
    build_default_behavior_matrix,
    build_default_cad_registry,
    build_default_fixture_catalog,
)


def test_behavior_matrix_covers_every_default_cad_command() -> None:
    registry = build_default_cad_registry()
    fixture_catalog = build_default_fixture_catalog()
    matrix = build_default_behavior_matrix()
    summary = matrix.summary()

    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert {command.command_id for command in registry.all()} <= set(summary["covered_command_ids"])
    assert summary["result_state_counts"]["commit_allowed"] >= 5
    assert summary["result_state_counts"]["relationship_owner_required"] == 2
    assert summary["cases_needing_live_plasticity_evidence"] >= 5
    assert {case.fixture_id for case in matrix.all_cases()} <= set(fixture_catalog.fixtures)


def test_extrude_behavior_records_parameters_options_lineage_and_failure_probes() -> None:
    matrix = build_default_behavior_matrix()
    case = matrix.get("extrude_top_face_new_body_lineage")

    assert case.command_id == "extrude"
    assert case.result_state == "preview_only_until_kernel_handler"
    assert case.selection.selection_id == "top_face"
    assert case.selection.topology_ids == ("F_top",)
    assert case.parameters["operation"] == "new_body"
    assert case.option_panel_state["extent_type"] == "distance"
    assert case.expected_count_deltas["bodies"] == "+1"
    transitions = {(transition.source, transition.relation, transition.results) for transition in case.topology_transitions}
    assert ("F_top", "created", ("F_extrude_cap",)) in transitions
    assert any("profile closure tolerance" in assertion for assertion in case.tolerance_assertions)
    assert {"extrude.open_profile", "extrude.zero_distance", "operation.self_intersection"} <= {
        probe.expected_failure_code for probe in case.failure_probes
    }
    assert "observed_parameter_schema" in case.automation.required_evidence


def test_fillet_behavior_tracks_blend_face_lineage_and_radius_failures() -> None:
    case = build_default_behavior_matrix().get("fillet_top_front_edge_blend_lineage")

    assert case.selection.selection_id == "top_front_edge"
    assert case.parameters["radius"] == 0.05
    assert case.option_panel_state["chain_selection"] is True
    assert any(
        transition.source == "E_top_front"
        and transition.relation == "created"
        and transition.results == ("F_blend_top_front",)
        for transition in case.topology_transitions
    )
    assert "radius_too_large" in {probe.probe_id for probe in case.failure_probes}
    assert any(probe.tolerance_sensitive for probe in case.failure_probes)
    assert "blend face id is created" in case.topology_naming_assertions


def test_project_behavior_requires_ordered_selection_and_preserves_target_when_not_imprinting() -> None:
    case = build_default_behavior_matrix().get("project_curve_to_sheet_without_imprint")

    assert case.command_id == "project"
    assert case.selection.ordered is True
    assert case.parameters["imprint_result"] is False
    assert case.expected_count_deltas == {"surfaces": "0", "curves": ">0"}
    assert any(
        transition.source == "S_patch"
        and transition.relation == "preserved"
        for transition in case.topology_transitions
    )
    assert "ordered_selection_record" in case.automation.required_evidence


def test_export_behavior_is_file_safe_and_source_topology_preserving() -> None:
    case = build_default_behavior_matrix().get("export_mesh_cube_glb_preserves_source")

    assert case.result_state == "controlled_probe_required"
    assert case.plasticity_evidence_status == "needs_file_dialog_probe"
    assert case.selection.active_object_required is False
    assert case.parameters["target_path"].startswith("knowledge_base/fixtures/exports/")
    assert {"angle_tolerance", "max_width", "inflect", "overwrite_policy"} <= set(case.option_panel_state)
    assert case.automation.file_touching is True
    assert case.automation.disposable_fixture_required is True
    assert "remove_only_workspace_export_artifact" in case.automation.reset_verification
    assert any(
        transition.source == "mesh_cube"
        and transition.relation == "preserved"
        for transition in case.topology_transitions
    )


def test_static_asset_behavior_cases_require_owner_before_top_level_command() -> None:
    matrix = build_default_behavior_matrix()
    face_change = matrix.get("face_change_grow_relationship_owner_probe")
    xnurbs = matrix.get("xnurbs_boundary_contextual_surface_probe")

    assert face_change.result_state == "relationship_owner_required"
    assert face_change.plasticity_evidence_status == "needs_static_asset_owner_probe"
    assert "negative_palette_screenshot" in face_change.automation.required_evidence
    assert "relationship.owner_required" in {
        probe.expected_failure_code for probe in face_change.failure_probes
    }

    assert xnurbs.result_state == "relationship_owner_required"
    assert "surface fitting" in xnurbs.tolerance_assertions[0]
    assert {"surface_patch.open_boundary", "surface_patch.wrong_side_count"} <= {
        probe.expected_failure_code for probe in xnurbs.failure_probes
    }
