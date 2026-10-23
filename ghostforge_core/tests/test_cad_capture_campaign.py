from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_capture_campaign_catalog, build_cad_observation_template_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_recon_artifacts(tmp_path) -> None:
    commands = [
        ("export_mesh", "Export Mesh", ["file_io"], "file_dialog_or_export_options_probe", "temporary_export_output_path"),
        ("face_change", "Face Change", ["surface_modeling"], "geometry_operation_parameter_panel_probe", "neutral_document_session"),
        ("fillet", "Fillet", ["solid_modeling"], "geometry_operation_parameter_panel_probe", "fixture_cube_solid"),
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
                    "priority": "critical" if cid != "fillet" else "high",
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
                    "missing_template_parameters": ["path", "format"] if cid == "export_mesh" else ["radius", "continuity"],
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
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "parameters_to_observe": [{"name": "path", "type": "filesystem_path"}, {"name": "format", "type": "enum"}],
                    "validation_checks": ["workspace_controlled_path_used"],
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "neutral_document_session",
                    "parameters_to_observe": [{"name": "grow", "type": "bool"}],
                    "validation_checks": ["owner_command_panel_detected"],
                },
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [{"name": "radius", "type": "number"}, {"name": "continuity", "type": "enum"}],
                    "validation_checks": ["panel_captured"],
                },
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


def _accepted_export_record(tmp_path) -> dict:
    template = build_cad_observation_template_catalog(tmp_path).get("export_mesh")
    return {
        **template.model_dump(mode="json"),
        "captured_sections": [
            {
                **section.model_dump(mode="json"),
                "status": "captured",
                "evidence_refs": [f"{section.section_id}.png"],
                "fields": {"captured": True},
            }
            for section in template.captured_sections
        ],
        "observed_controls": [
            {
                **control.model_dump(mode="json"),
                "control_type": "dropdown",
                "current_value": "captured",
                "confidence": "high",
                "evidence_refs": ["file_dialog_or_options_screenshot"],
            }
            for control in template.observed_controls
        ],
        "validation_results": [{"check_id": "workspace_controlled_path_used", "passed": True, "evidence_refs": ["workspace_path_file_record"]}],
        "topology_delta": {"after_counts": {"objects": 1}, "modified_ids": ["artifact:export_mesh"], "evidence_refs": ["topology_delta.png"]},
        "file_artifacts": [
            {
                "path": "fixtures/exports/cube.glb",
                "format_id": "mesh_export",
                "operation": "export",
                "source_topology_preserved": True,
                "evidence_refs": ["workspace_path_file_record"],
            }
        ],
        "reset_verified": True,
    }


def test_capture_campaign_prioritizes_ready_capture_without_ledger(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)

    item = build_cad_capture_campaign_catalog(tmp_path).get("export_mesh")

    assert item.status == "ready_to_capture"
    assert item.ledger_filename == "cad_live_observation_records.json"
    assert item.file_touching is True
    assert "workspace_controlled_path" in item.required_safety_gates
    assert item.next_action == "run live session and append record to cad_live_observation_records.json"


def test_capture_campaign_marks_accepted_observation_as_handoff_ready(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    _write_json(tmp_path / "cad_live_observation_records.json", {"records": [_accepted_export_record(tmp_path)]})

    item = build_cad_capture_campaign_catalog(tmp_path).get("export_mesh")

    assert item.status == "handoff_ready"
    assert item.latest_handoff_status == "ready_for_native_application"
    assert "schema_promotion" in item.handoff_targets
    assert "native_handoff_applied" in item.required_outputs


def test_capture_campaign_requires_recapture_for_rejected_ledger_entry(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    _write_json(
        tmp_path / "cad_live_observation_records.json",
        {
            "records": [
                {
                    "command_id": "export_mesh",
                    "captured_sections": [{"section_id": "session_identity", "status": "captured", "evidence_refs": ["session.json"]}],
                    "validation_results": [{"check_id": "workspace_controlled_path_used", "passed": False}],
                }
            ]
        },
    )

    item = build_cad_capture_campaign_catalog(tmp_path).get("export_mesh")

    assert item.status == "recapture_required"
    assert "validation.workspace_controlled_path_used.failed" in item.blockers
    assert item.next_action == "recapture export_mesh and replace rejected ledger evidence"


def test_capture_campaign_keeps_static_owner_blocked_until_owner_evidence(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)

    item = build_cad_capture_campaign_catalog(tmp_path).get("face_change")

    assert item.status == "blocked_static_owner_resolution"
    assert item.ledger_filename == "cad_observation_records.json"
    assert "owner_classification" in item.required_outputs


def test_capture_campaign_real_data_counts() -> None:
    catalog = build_cad_capture_campaign_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["item_count"] == 141
    assert summary["ready_to_capture_count"] == 21
    assert catalog.get("export_mesh").status == "ready_to_capture"
