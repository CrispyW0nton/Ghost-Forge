from __future__ import annotations

import json

from ghostforge_core.cad import (
    load_plasticity_observation_evidence,
    load_plasticity_probe_packages,
    load_plasticity_recon_coverage,
)


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_plasticity_recon_coverage_flattens_command_readiness_rows(tmp_path) -> None:
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "basis": {"command_count": 3, "matrix_full_ready_count": 0},
            "bucket_counts": {
                "fixture_required": 1,
                "palette_confirmation": 1,
                "safe_parameter_session": 1,
            },
            "summary": {"command_count": 3, "already_ready_count": 0},
            "operating_sequence": ["Confirm static-only commands.", "Record observations."],
            "recommended_batches": {
                "fixture_required": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "readiness_bucket": "fixture_required",
                        "stage": "palette_reachable_needs_parameter_probe",
                        "priority": "high",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_document_with_solid_sheet_curve_edge_and_face_selection_sets",
                        "preferred_query": "fillet",
                        "next_tool": "parameter_probe_session",
                        "next_action": "prepare_disposable_fixture_and_run_parameter_probe_session_in_plan_mode_first",
                        "missing_parameter_count": 9,
                        "observed_parameter_count": 0,
                        "template_parameter_count": 9,
                        "gaps": ["parameter schema is not fully observed"],
                        "mcp_route": [
                            {
                                "tool": "parameter_probe_session",
                                "arguments": {"command_id": "fillet", "mode": "plan"},
                            }
                        ],
                    }
                ],
                "palette_confirmation": [
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
                        "mcp_route": [
                            {
                                "tool": "plasticity_palette_search_probe",
                                "arguments": {"query": "Export Mesh"},
                            }
                        ],
                    }
                ],
                "safe_parameter_session": [
                    {
                        "command_id": "project",
                        "label": "Project",
                        "readiness_bucket": "safe_parameter_session",
                        "stage": "palette_confirmed_needs_parameter_probe",
                        "priority": "high",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_sheet_patch",
                        "missing_parameter_count": 4,
                        "mcp_route": [
                            {
                                "tool": "parameter_schema_observation_record",
                                "arguments": {"command_id": "project"},
                            }
                        ],
                    }
                ],
            },
        },
    )
    _write_json(
        tmp_path / "static_command_mapping_review.json",
        {"status_counts": {"controlled_probe_needed": 2, "likely_option_or_alias": 2}},
    )
    _write_json(
        tmp_path / "plasticity_file_format_map.json",
        {"formats": {"step_stp": {}, "mesh_export": {}}},
    )
    _write_json(
        tmp_path / "goal_progress_audit.json",
        {
            "requirements": [
                {"id": "a", "status": "complete"},
                {"id": "b", "status": "partial"},
                {"id": "c", "status": "partial"},
            ]
        },
    )

    snapshot = load_plasticity_recon_coverage(tmp_path)

    assert snapshot.source_files == {
        "parameter_observation_readiness": True,
        "static_command_mapping_review": True,
        "plasticity_file_format_map": True,
        "goal_progress_audit": True,
    }
    assert snapshot.command("export_mesh").next_tool == "plasticity_palette_search_probe"
    assert snapshot.command("fillet").has_automation_route is True
    assert snapshot.commands_by_bucket("safe_parameter_session")[0].command_id == "project"

    summary = snapshot.coverage_summary()
    assert summary["loaded_command_count"] == 3
    assert summary["commands_with_automation_routes"] == 3
    assert summary["commands_needing_observed_schema"] == 3
    assert summary["static_mapping_status_counts"] == {
        "controlled_probe_needed": 2,
        "likely_option_or_alias": 2,
    }
    assert summary["goal_requirement_status_counts"] == {"complete": 1, "partial": 2}
    assert summary["format_family_count"] == 2


def test_load_plasticity_recon_coverage_handles_missing_files(tmp_path) -> None:
    snapshot = load_plasticity_recon_coverage(tmp_path)

    assert snapshot.commands == ()
    assert snapshot.coverage_summary()["loaded_command_count"] == 0
    assert snapshot.source_files["parameter_observation_readiness"] is False


def test_load_plasticity_recon_coverage_prefers_authoritative_rows(tmp_path) -> None:
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "bucket_counts": {"safe_parameter_session": 2},
            "rows": [
                {
                    "command_id": "alpha",
                    "label": "Alpha",
                    "readiness_bucket": "safe_parameter_session",
                    "stage": "palette_reachable_needs_parameter_probe",
                    "missing_parameter_count": 1,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
                },
                {
                    "command_id": "beta",
                    "label": "Beta",
                    "readiness_bucket": "safe_parameter_session",
                    "stage": "palette_reachable_needs_parameter_probe",
                    "missing_parameter_count": 1,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
                },
            ],
            "recommended_batches": {
                "safe_parameter_session": [
                    {
                        "command_id": "alpha",
                        "label": "Alpha batch-only duplicate",
                        "readiness_bucket": "safe_parameter_session",
                    }
                ]
            },
        },
    )

    snapshot = load_plasticity_recon_coverage(tmp_path)

    assert [row.command_id for row in snapshot.commands] == ["alpha", "beta"]
    assert snapshot.command("alpha").label == "Alpha"


def test_load_plasticity_observation_evidence_separates_templates_and_ledger(tmp_path) -> None:
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "basis": {"observation_count": 0, "template_count": 2},
            "commands": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "template_inferred_needs_probe",
                    "fixture": "fixture_cube_solid",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "priority": "high",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 3,
                    "missing_template_parameters": ["radius", "continuity", "tolerance"],
                    "evidence_screenshots": ["evidence/fillet.png"],
                    "reset_verified": False,
                },
                {
                    "command_id": "project",
                    "label": "Project",
                    "schema_status": "observed_schema",
                    "observed_parameter_count": 2,
                    "template_parameter_count": 2,
                    "missing_template_parameters": [],
                    "reset_verified": True,
                },
            ],
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "basis": {"command_count": 2},
            "schema_status_counts": {"template_inferred_needs_probe": 2},
            "template_groups": {"geometry_parameter_panels": ["fillet", "project"]},
            "fixture_counts": {"fixture_cube_solid": 1},
            "probe_kind_counts": {"geometry_operation_parameter_panel_probe": 2},
            "templates": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "template_inferred_needs_probe",
                    "reachability": "observed_palette",
                    "fixture": "fixture_cube_solid",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "parameters_to_observe": [
                        {"name": "radius", "type": "float", "description": "Blend radius."},
                        {"name": "continuity", "type": "enum"},
                    ],
                    "validation_checks": ["before_screenshot_captured"],
                    "expected_state_effects": ["geometry_topology_or_transform_change"],
                    "preconditions": ["document_session"],
                    "invocation_candidates": {"palette_queries": ["fillet"]},
                    "safety": {"requires_workspace_fixture": True},
                    "evidence_screenshots": ["evidence/fillet.png"],
                }
            ],
        },
    )
    _write_json(
        tmp_path / "parameter_probe_session_last.json",
        {
            "command_id": "fillet",
            "mode": "plan",
            "executed": False,
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "artifacts": {"session_path": "parameter_probe_session_fillet.json"},
            "package": {
                "command_id": "fillet",
                "evidence_capture_plan": {
                    "parameter_names_to_resolve": ["radius", "continuity"],
                    "required_evidence": ["baseline_screenshot"],
                    "validation_checks": ["before_screenshot_captured"],
                },
                "invocation_plan": {"reset_steps": ["Escape"]},
            },
        },
    )

    snapshot = load_plasticity_observation_evidence(tmp_path)

    assert snapshot.command_status("fillet").is_template_only is True
    assert snapshot.command_status("project").is_observed_schema is True
    assert snapshot.command_template("fillet").parameters_to_observe[0].name == "radius"
    assert snapshot.latest_session is not None
    assert snapshot.latest_session.parameter_names_to_resolve == ("radius", "continuity")
    assert snapshot.template_groups["geometry_parameter_panels"] == ("fillet", "project")

    summary = snapshot.observation_summary()
    assert summary["ledger_command_count"] == 2
    assert summary["template_command_count"] == 1
    assert summary["observed_schema_count"] == 1
    assert summary["template_only_count"] == 1
    assert summary["latest_session_command_id"] == "fillet"


def test_load_plasticity_probe_packages_captures_executable_evidence_unit(tmp_path) -> None:
    package = {
        "command_id": "export_mesh",
        "label": "Export Mesh",
        "generated_utc": "2026-06-01T14:08:16+00:00",
        "completion_definition": ["All required evidence screenshots are referenced."],
        "evidence_capture_plan": {
            "parameter_names_to_resolve": ["path", "format", "tolerance"],
            "required_evidence": ["baseline_screenshot", "file_dialog_or_options_screenshot", "workspace_path_file_record"],
            "validation_checks": ["workspace_controlled_path_used", "format_options_detected"],
        },
        "fixture": {
            "fixture": "temporary_export_output_path",
            "purpose": "Exercise export options into workspace-controlled temporary paths.",
            "assets": [],
            "setup_steps": ["Choose knowledge_base/fixtures/exports as the export destination."],
            "reset_steps": ["Remove or overwrite only files inside knowledge_base/fixtures/exports."],
            "safety_notes": ["Never export into source folders."],
            "state_requirements": ["document_session", "output_path"],
        },
        "invocation_plan": {
            "palette_queries": ["Export Mesh"],
            "preferred_invocation": "requires_runtime_probe",
            "setup_steps": ["Use a disposable document."],
            "probe_steps": ["Open the command palette.", "Capture visible options."],
            "reset_steps": ["Remove or overwrite only files inside knowledge_base/fixtures/exports."],
        },
        "observation_record_template": {
            "schema_status": "observed_partial",
            "reset_verified": False,
            "side_effects_observed": ["file_system_or_document_io"],
            "observed_parameters": [
                {"name": "path", "type": "filesystem_path", "observed_control": "", "confidence": "medium"},
                {"name": "format", "type": "enum", "observed_control": "", "confidence": "medium"},
            ],
            "validation_results": [
                {"check": "workspace_controlled_path_used", "passed": False, "evidence": ""},
                {"check": "format_options_detected", "passed": False, "evidence": ""},
            ],
        },
    }
    _write_json(
        tmp_path / "parameter_probe_packages.json",
        {
            "basis": {"selected_count": 1},
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "packages": [package],
        },
    )

    snapshot = load_plasticity_probe_packages(tmp_path)
    export_mesh = snapshot.package("export_mesh")

    assert snapshot.package_summary()["package_count"] == 1
    assert snapshot.package_summary()["packages_requiring_file_evidence"] == 1
    assert export_mesh.parameter_names_to_resolve == ("path", "format", "tolerance")
    assert export_mesh.required_evidence[-1] == "workspace_path_file_record"
    assert export_mesh.fixture.fixture == "temporary_export_output_path"
    assert export_mesh.has_workspace_safety_gate is True
    assert export_mesh.observed_parameter_slots[0].name == "path"
    assert export_mesh.observation_validation_results[1].check == "format_options_detected"
