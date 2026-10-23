from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_probe_batch_plan


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_batch_artifacts(tmp_path) -> None:
    commands = [
        ("export_mesh", "Export Mesh", ["file_io"], "file_dialog_or_export_options_probe", "temporary_export_output_path"),
        ("file_import", "File Import", ["file_io"], "file_dialog_or_import_options_probe", "temporary_import_fixture"),
        ("face_change", "Face Change", ["surface_modeling"], "geometry_operation_parameter_panel_probe", "neutral_document_session"),
    ]
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {
                    "id": command_id,
                    "label": label,
                    "categories": categories,
                    "palette_queries": [label],
                    "reachability": "observed_palette",
                }
                for command_id, label, categories, _probe, _fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "rows": [
                {
                    "command_id": command_id,
                    "label": label,
                    "priority": "critical",
                    "probe_kind": probe_kind,
                    "fixture": fixture,
                    "destructive_or_file_touching": "file" in probe_kind,
                    "missing_parameter_count": 2,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": command_id}}],
                }
                for command_id, label, _categories, probe_kind, fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "commands": [
                {
                    "command_id": command_id,
                    "label": label,
                    "schema_status": "template_inferred_needs_probe",
                    "priority": "critical",
                    "probe_kind": probe_kind,
                    "fixture": fixture,
                    "observed_parameter_count": 0,
                    "template_parameter_count": 2,
                    "missing_template_parameters": ["path", "format"] if "file" in probe_kind else ["grow"],
                    "evidence_screenshots": [],
                    "reset_verified": False,
                }
                for command_id, label, _categories, probe_kind, fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {
            "templates": [
                {
                    "command_id": command_id,
                    "label": label,
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": probe_kind,
                    "fixture": fixture,
                    "parameters_to_observe": [
                        {"name": "path", "type": "filesystem_path"},
                        {"name": "format", "type": "enum"},
                    ]
                    if "file" in probe_kind
                    else [{"name": "grow", "type": "bool"}],
                    "validation_checks": ["panel_captured"],
                }
                for command_id, label, _categories, probe_kind, fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_probe_packages.json",
        {
            "packages": [
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["path", "format"],
                        "required_evidence": ["file_dialog_or_options_screenshot", "workspace_path_file_record"],
                        "validation_checks": ["workspace_controlled_path_used"],
                    },
                    "fixture": {
                        "fixture": "temporary_export_output_path",
                        "setup_steps": ["Use disposable export fixture."],
                        "reset_steps": ["Remove only files inside knowledge_base/fixtures/exports."],
                        "safety_notes": ["Use workspace-controlled paths."],
                    },
                    "observation_record_template": {
                        "observed_parameters": [{"name": "path", "type": "filesystem_path"}],
                        "validation_results": [{"check": "workspace_controlled_path_used", "passed": False, "evidence": ""}],
                    },
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "fixture": {"fixture": "neutral_document_session"},
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["grow"],
                        "required_evidence": ["negative_palette_screenshot", "candidate_owner_panel_screenshots"],
                        "validation_checks": ["owner_command_panel_detected"],
                    },
                    "observation_record_template": {
                        "observed_parameters": [{"name": "grow", "type": "bool"}],
                        "validation_results": [{"check": "owner_command_panel_detected", "passed": False, "evidence": ""}],
                    },
                },
            ]
        },
    )
    _write_json(
        tmp_path / "static_command_mapping_review.json",
        {
            "recommended_batches": {
                "review_as_option_or_alias": [
                    {
                        "command_id": "face_change",
                        "mapping_status": "likely_option_or_alias",
                        "candidate_existing_commands": [{"command_id": "match_face"}],
                    }
                ]
            }
        },
    )
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_probe_batch_plan_groups_ready_missing_package_and_static_owner(tmp_path) -> None:
    _write_batch_artifacts(tmp_path)

    plan = build_cad_probe_batch_plan(tmp_path)
    summary = plan.summary()

    assert summary["command_count"] == 3
    assert summary["command_kind_counts"]["ready_live_capture"] == 1
    assert summary["command_kind_counts"]["probe_package_generation"] == 1
    assert summary["command_kind_counts"]["static_owner_resolution"] == 1
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"


def test_ready_live_capture_batch_prioritizes_export_mesh(tmp_path) -> None:
    _write_batch_artifacts(tmp_path)

    batch = build_cad_probe_batch_plan(tmp_path).get("ready_live_capture:file_interop_packet")

    assert batch.live_execution_allowed is True
    assert batch.commands[0].command_id == "export_mesh"
    assert "workspace_write_scope" in batch.required_safety_gates
    assert "file_artifact_record" in batch.required_outputs
    assert batch.next_action == "capture evidence packet for export_mesh"


def test_static_owner_batch_keeps_face_change_out_of_live_capture(tmp_path) -> None:
    _write_batch_artifacts(tmp_path)

    batch = build_cad_probe_batch_plan(tmp_path).get("static_owner_resolution:static_owner_packet")

    assert batch.live_execution_allowed is False
    assert batch.commands[0].command_id == "face_change"
    assert batch.commands[0].static_owner_required is True
    assert "owner_command_resolution" in batch.required_safety_gates
    assert "owner_classification" in batch.required_outputs


def test_probe_batch_real_data_counts_match_current_recon() -> None:
    plan = build_cad_probe_batch_plan(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = plan.summary()

    assert summary["command_count"] == 141
    assert summary["command_kind_counts"]["ready_live_capture"] == 21
    assert summary["command_kind_counts"]["probe_package_generation"] == 116
    assert summary["command_kind_counts"]["static_owner_resolution"] == 2
    assert summary["command_kind_counts"]["safety_gate_repair"] == 2
    assert summary["file_artifact_command_count"] == 23
    assert summary["static_owner_command_count"] == 2
