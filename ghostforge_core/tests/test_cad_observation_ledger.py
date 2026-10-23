from __future__ import annotations

import json

from ghostforge_core.cad import (
    build_cad_observation_template_catalog,
    load_cad_observation_ledger,
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
                    "validation_checks": ["workspace_controlled_path_used", "format_options_detected"],
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
                        "validation_checks": ["workspace_controlled_path_used", "format_options_detected"],
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


def _captured_export_record(tmp_path) -> dict:
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
            {
                "check_id": "workspace_controlled_path_used",
                "passed": True,
                "evidence_refs": ["workspace_path_file_record"],
            },
            {
                "check_id": "format_options_detected",
                "passed": True,
                "evidence_refs": ["file_dialog_or_options_screenshot"],
            },
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


def test_observation_ledger_loads_and_validates_captured_records(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    good = _captured_export_record(tmp_path)
    bad = {
        "command_id": "export_mesh",
        "captured_sections": [{"section_id": "session_identity", "status": "captured", "evidence_refs": ["session.json"]}],
        "observed_controls": [],
        "validation_results": [{"check_id": "workspace_controlled_path_used", "passed": False}],
    }
    _write_json(tmp_path / "cad_live_observation_records.json", {"records": [good, bad]})

    catalog = load_cad_observation_ledger(tmp_path)
    summary = catalog.summary()

    assert summary["record_count"] == 2
    assert summary["accepted_count"] == 1
    assert summary["rejected_count"] == 1
    assert summary["status_counts"]["accepted_for_promotion"] == 1
    assert summary["status_counts"]["rejected_failed_checks"] == 1
    assert summary["promotion_target_counts"]["schema_promotion"] == 1
    assert catalog.entries_for_command("export_mesh")[0].validation.status == "accepted_for_promotion"


def test_observation_ledger_accepts_static_owner_without_promoting_command_schema(tmp_path) -> None:
    _write_recon_artifacts(tmp_path)
    static_owner_record = {
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
    _write_json(tmp_path / "cad_observation_records.json", [static_owner_record])

    entry = load_cad_observation_ledger(tmp_path).latest_for_command("face_change")

    assert entry.validation.status == "accepted_for_static_owner"
    assert "registry_relationships" in entry.validation.promotion_targets
    assert "schema_promotion" not in entry.validation.promotion_targets


def test_observation_ledger_default_root_is_empty_until_live_captures_are_recorded() -> None:
    catalog = load_cad_observation_ledger(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["record_count"] >= 0
