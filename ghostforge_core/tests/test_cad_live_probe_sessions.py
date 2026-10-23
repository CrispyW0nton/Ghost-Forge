from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_live_probe_session_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_session_artifacts(tmp_path) -> None:
    commands = [
        ("export_mesh", "Export Mesh", ["file_io"], "file_dialog_or_export_options_probe", "temporary_export_output_path"),
        ("face_change", "Face Change", ["surface_modeling"], "geometry_operation_parameter_panel_probe", "neutral_document_session"),
    ]
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {"id": cid, "label": label, "categories": cats, "palette_queries": [label], "reachability": "observed_palette"}
                for cid, label, cats, _probe, _fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "rows": [
                {
                    "command_id": cid,
                    "label": label,
                    "priority": "critical",
                    "probe_kind": probe,
                    "fixture": fixture,
                    "destructive_or_file_touching": cid == "export_mesh",
                    "missing_parameter_count": 2,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": cid}}],
                }
                for cid, label, _cats, probe, fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "commands": [
                {
                    "command_id": cid,
                    "label": label,
                    "schema_status": "template_inferred_needs_probe",
                    "priority": "critical",
                    "probe_kind": probe,
                    "fixture": fixture,
                    "observed_parameter_count": 0,
                    "template_parameter_count": 2,
                    "missing_template_parameters": ["path", "format"] if cid == "export_mesh" else ["grow"],
                    "evidence_screenshots": [],
                    "reset_verified": False,
                }
                for cid, label, _cats, probe, fixture in commands
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {
            "templates": [
                {
                    "command_id": cid,
                    "label": label,
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": probe,
                    "fixture": fixture,
                    "parameters_to_observe": [
                        {"name": "path", "type": "filesystem_path"},
                        {"name": "format", "type": "enum"},
                    ]
                    if cid == "export_mesh"
                    else [{"name": "grow", "type": "bool"}],
                    "validation_checks": ["panel_captured"],
                }
                for cid, label, _cats, probe, fixture in commands
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


def test_live_probe_session_for_export_mesh_is_ready_and_ordered(tmp_path) -> None:
    _write_session_artifacts(tmp_path)

    session = build_cad_live_probe_session_catalog(tmp_path).get("export_mesh")

    assert session.session_mode == "ready_for_manual_live_capture"
    assert session.batch_id == "ready_live_capture:file_interop_packet"
    assert session.live_execution_allowed is True
    assert "workspace_controlled_path" in session.required_safety_gates
    assert "file_artifact" in session.required_sections
    assert [step.step_id for step in session.steps] == [
        "guard_preflight",
        "prepare_fixture",
        "capture_baseline",
        "invoke_command_panel",
        "capture_parameters",
        "capture_fixture_behavior",
        "capture_file_artifact",
        "verify_reset",
        "record_observation",
    ]
    assert any(step.touches_files for step in session.steps)


def test_live_probe_session_blocks_static_owner_until_classified(tmp_path) -> None:
    _write_session_artifacts(tmp_path)

    session = build_cad_live_probe_session_catalog(tmp_path).get("face_change")

    assert session.session_mode == "blocked"
    assert session.batch_id == "static_owner_resolution:static_owner_packet"
    assert session.steps[0].step_id == "resolve_blocker"
    assert session.steps[0].safety_gate == "automation.owner_command_resolution_missing"


def test_live_probe_session_real_data_counts() -> None:
    catalog = build_cad_live_probe_session_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["session_count"] == 141
    assert summary["manual_live_capture_ready_count"] == 21
    assert summary["blocked_session_count"] == 120
    assert summary["file_touching_session_count"] == 1
    assert catalog.get("export_mesh").session_mode == "ready_for_manual_live_capture"
