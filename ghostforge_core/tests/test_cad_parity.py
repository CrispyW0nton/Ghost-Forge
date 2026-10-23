from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_parity_report


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_minimal_recon_artifacts(tmp_path) -> None:
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "bucket_counts": {"palette_confirmation": 2, "fixture_required": 1},
            "rows": [
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "readiness_bucket": "palette_confirmation",
                    "stage": "static_inferred_needs_palette_confirmation",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "next_tool": "plasticity_palette_search_probe",
                    "missing_parameter_count": 6,
                    "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {"query": "Export Mesh"}}],
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "readiness_bucket": "palette_confirmation",
                    "stage": "static_inferred_needs_palette_confirmation",
                    "priority": "critical",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "next_tool": "plasticity_palette_search_probe",
                    "missing_parameter_count": 1,
                    "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {"query": "Face Change"}}],
                },
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "readiness_bucket": "fixture_required",
                    "stage": "palette_reachable_needs_parameter_probe",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "next_tool": "parameter_probe_session",
                    "missing_parameter_count": 3,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "fillet"}}],
                },
            ],
        },
    )
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "commands": [
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 6,
                    "missing_template_parameters": ["path", "format", "scope", "units", "tolerance", "overwrite_policy"],
                    "reset_verified": False,
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 1,
                    "missing_template_parameters": ["grow"],
                    "reset_verified": False,
                },
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "observed_schema",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "observed_parameter_count": 3,
                    "template_parameter_count": 3,
                    "missing_template_parameters": [],
                    "reset_verified": True,
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {"templates": [], "schema_status_counts": {"template_inferred_needs_probe": 2}},
    )
    _write_json(
        tmp_path / "parameter_probe_session_last.json",
        {"command_id": "export_mesh", "mode": "plan", "executed": False},
    )
    _write_json(tmp_path / "static_command_mapping_review.json", {"status_counts": {"controlled_probe_needed": 2}})
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {"mesh_export": {}}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_cad_parity_report_joins_descriptors_routes_and_observation_evidence(tmp_path) -> None:
    _write_minimal_recon_artifacts(tmp_path)

    report = build_cad_parity_report(tmp_path)
    export_mesh = report.command("export_mesh")

    assert report.summary["command_count"] >= 11
    assert report.summary["latest_session_command_id"] == "export_mesh"
    assert export_mesh.plasticity_command_id == "export_mesh"
    assert export_mesh.plasticity_route_ready is True
    assert export_mesh.latest_session_command is True
    assert export_mesh.missing_parameters == (
        "path",
        "format",
        "scope",
        "units",
        "tolerance",
        "overwrite_policy",
    )
    assert "ghostforge.implementation_controlled_probe_needed" in export_mesh.blockers
    assert "plasticity.observed_schema_missing" in export_mesh.blockers
    assert export_mesh.recommended_ghostforge_action == "implement_or_gate_ghostforge_handler"


def test_cad_parity_report_maps_static_asset_relationships_to_plasticity_rows(tmp_path) -> None:
    _write_minimal_recon_artifacts(tmp_path)

    report = build_cad_parity_report(tmp_path)
    face_change = report.command("face_change_grow")

    assert face_change.plasticity_command_id == "face_change"
    assert face_change.plasticity_route_ready is True
    assert "plasticity.relationship_owner_unverified" in face_change.blockers
    assert face_change.recommended_ghostforge_action == "resolve_static_asset_ownership"
    assert any("owner commands" in action for action in face_change.next_actions)


def test_cad_parity_report_recognizes_observed_schema_but_keeps_kernel_blocker(tmp_path) -> None:
    _write_minimal_recon_artifacts(tmp_path)

    report = build_cad_parity_report(tmp_path)
    fillet = report.command("fillet")

    assert fillet.plasticity_schema_status == "observed_schema"
    assert fillet.reset_verified is True
    assert "plasticity.observed_schema_missing" not in fillet.blockers
    assert "plasticity.reset_not_verified" not in fillet.blockers
    assert "ghostforge.implementation_planned" in fillet.blockers
