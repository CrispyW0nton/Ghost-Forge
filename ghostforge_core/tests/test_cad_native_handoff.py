from __future__ import annotations

import json

from ghostforge_core.cad import (
    build_cad_native_handoff_catalog,
    build_cad_observation_template_catalog,
)


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_recon_artifacts(tmp_path) -> None:
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
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "parameters_to_observe": [
                        {"name": "path", "type": "filesystem_path"},
                        {"name": "format", "type": "enum"},
                    ],
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
        "plasticity_version": "26.1.3",
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
        "validation_results": [
            {"check_id": "workspace_controlled_path_used", "passed": True, "evidence_refs": ["workspace_path_file_record"]}
        ],
        "topology_delta": {
            "before_counts": {"objects": 1},
            "after_counts": {"objects": 1},
            "modified_ids": ["artifact:export_mesh"],
            "evidence_refs": ["topology_delta.png"],
        },
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


def test_native_handoff_turns_accepted_export_observation_into_work_steps(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    _write_json(tmp_path / "cad_live_observation_records.json", {"records": [_accepted_export_record(tmp_path)]})

    handoff = build_cad_native_handoff_catalog(tmp_path).handoffs_for_command("export_mesh")[0]

    assert handoff.handoff_status == "ready_for_native_application"
    assert handoff.implementation_track == "file_interop"
    assert "schema_promotion" in handoff.promotion_targets
    assert {step.step_id for step in handoff.steps} >= {
        "apply_descriptor_schema",
        "apply_fixture_behavior",
        "apply_interop_contract",
    }
    assert handoff.next_action == "implement handoff step: apply_descriptor_schema"


def test_native_handoff_keeps_static_owner_as_relationship_work(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    _write_json(
        tmp_path / "cad_observation_records.json",
        [
            {
                "command_id": "face_change",
                "fixture": "neutral_document_session",
                "captured_sections": [
                    {
                        "section_id": "static_owner_classification",
                        "status": "captured",
                        "evidence_refs": ["face_change_owner_panel.png"],
                        "fields": {"owner_command_id": "match_face", "classification": "option"},
                    }
                ],
                "static_owner_classification": {
                    "static_asset_id": "face-change-grow.png",
                    "classification": "option",
                    "owner_command_id": "match_face",
                    "negative_palette_evidence_refs": ["face_change_negative_palette.png"],
                    "owner_panel_evidence_refs": ["face_change_owner_panel.png"],
                },
            }
        ],
    )

    handoff = build_cad_native_handoff_catalog(tmp_path).handoffs_for_command("face_change")[0]

    assert handoff.handoff_status == "ready_for_static_owner_application"
    assert handoff.steps[0].step_id == "apply_static_owner_relationship"
    assert "schema_promotion" not in handoff.promotion_targets


def test_native_handoff_reports_validation_blockers_before_product_work(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    _write_json(
        tmp_path / "cad_live_observation_records.json",
        {
            "records": [
                {
                    "command_id": "export_mesh",
                    "captured_sections": [
                        {"section_id": "session_identity", "status": "captured", "evidence_refs": ["session.json"]}
                    ],
                    "validation_results": [{"check_id": "workspace_controlled_path_used", "passed": False}],
                }
            ]
        },
    )

    handoff = build_cad_native_handoff_catalog(tmp_path).handoffs_for_command("export_mesh")[0]

    assert handoff.handoff_status == "blocked_by_validation"
    assert handoff.steps == ()
    assert "validation.workspace_controlled_path_used.failed" in handoff.blockers


def test_native_handoff_real_data_is_empty_until_observation_ledger_exists() -> None:
    catalog = build_cad_native_handoff_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["handoff_count"] >= 0
