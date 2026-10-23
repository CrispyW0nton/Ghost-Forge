from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_schema_promotion_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_promotion_artifacts(tmp_path) -> None:
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {
                    "id": "fillet",
                    "label": "Fillet",
                    "categories": ["solid_modeling"],
                    "palette_queries": ["Fillet"],
                    "reachability": "observed_palette",
                },
                {
                    "id": "export_mesh",
                    "label": "Export Mesh",
                    "categories": ["file_io"],
                    "palette_queries": ["Export Mesh"],
                    "reachability": "static_inferred",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "rows": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "missing_parameter_count": 0,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "fillet"}}],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "destructive_or_file_touching": True,
                    "missing_parameter_count": 3,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "export_mesh"}}],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "commands": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "observed_schema",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "observed_parameter_count": 2,
                    "template_parameter_count": 2,
                    "missing_template_parameters": [],
                    "evidence_screenshots": [
                        "baseline_screenshot",
                        "panel_screenshot",
                        "reset_screenshot",
                    ],
                    "reset_verified": True,
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 3,
                    "missing_template_parameters": ["path", "format", "tolerance"],
                    "evidence_screenshots": [],
                    "reset_verified": False,
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {
            "templates": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "observed_schema",
                    "reachability": "observed_palette",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [
                        {"name": "radius", "type": "number"},
                        {"name": "continuity", "type": "enum"},
                    ],
                    "validation_checks": ["before_screenshot_captured", "panel_controls_mapped"],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "parameters_to_observe": [
                        {"name": "path", "type": "filesystem_path"},
                        {"name": "format", "type": "enum"},
                        {"name": "tolerance", "type": "number"},
                    ],
                    "validation_checks": ["workspace_controlled_path_used"],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_probe_packages.json",
        {
            "packages": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["radius", "continuity"],
                        "required_evidence": ["baseline_screenshot", "panel_screenshot", "reset_screenshot"],
                        "validation_checks": ["before_screenshot_captured", "panel_controls_mapped"],
                    },
                    "fixture": {
                        "fixture": "fixture_cube_solid",
                        "setup_steps": ["Open disposable cube solid fixture."],
                        "reset_steps": ["Undo fillet and verify cube snapshot."],
                        "safety_notes": ["Use disposable fixture geometry."],
                    },
                    "invocation_plan": {
                        "palette_queries": ["Fillet"],
                        "preferred_invocation": "command_palette",
                    },
                    "observation_record_template": {
                        "observed_parameters": [
                            {
                                "name": "radius",
                                "type": "number",
                                "observed_control": "numeric_input",
                                "confidence": "high",
                                "value_or_options": 0.05,
                            },
                            {
                                "name": "continuity",
                                "type": "enum",
                                "observed_control": "dropdown",
                                "confidence": "high",
                                "value_or_options": ["g1", "g2"],
                            },
                        ],
                        "validation_results": [
                            {
                                "check": "before_screenshot_captured",
                                "passed": True,
                                "evidence": "baseline_screenshot",
                            },
                            {
                                "check": "panel_controls_mapped",
                                "passed": True,
                                "evidence": "panel_screenshot",
                            },
                        ],
                        "schema_status": "observed_schema",
                        "reset_verified": True,
                    },
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["path", "format", "tolerance"],
                        "required_evidence": ["file_dialog_or_options_screenshot", "workspace_path_file_record"],
                        "validation_checks": ["workspace_controlled_path_used"],
                    },
                    "fixture": {
                        "fixture": "temporary_export_output_path",
                        "setup_steps": ["Use disposable export fixture."],
                        "reset_steps": ["Remove or overwrite only files inside knowledge_base/fixtures/exports."],
                        "safety_notes": ["Use workspace-controlled paths."],
                    },
                    "observation_record_template": {
                        "observed_parameters": [
                            {"name": "path", "type": "filesystem_path", "observed_control": "", "confidence": "medium"}
                        ],
                        "validation_results": [
                            {"check": "workspace_controlled_path_used", "passed": False, "evidence": ""}
                        ],
                        "schema_status": "observed_partial",
                        "reset_verified": False,
                    },
                },
            ]
        },
    )
    _write_json(tmp_path / "static_command_mapping_review.json", {"recommended_batches": {}})
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_schema_promotion_catalog_distinguishes_observed_schema_from_templates(tmp_path) -> None:
    _write_promotion_artifacts(tmp_path)

    catalog = build_cad_schema_promotion_catalog(tmp_path)
    summary = catalog.summary()

    assert summary["candidate_count"] == 2
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["promotion_status_counts"]["promotable_to_descriptor"] == 1
    assert summary["promotion_status_counts"]["template_only_blocked"] == 1
    assert summary["observed_parameter_count"] == 2


def test_promotable_schema_exports_descriptor_parameter_specs(tmp_path) -> None:
    _write_promotion_artifacts(tmp_path)

    fillet = build_cad_schema_promotion_catalog(tmp_path).get("fillet")

    assert fillet.promotion_status == "promotable_to_descriptor"
    assert fillet.ready_for_native_descriptor is True
    assert {gate.gate_id: gate.status for gate in fillet.gates}["reset_verified"] == "passed"
    assert fillet.blockers == ()
    specs = fillet.parameter_specs()
    assert {spec.name for spec in specs} == {"radius", "continuity"}
    continuity = next(spec for spec in specs if spec.name == "continuity")
    assert continuity.type == "enum"
    assert continuity.values == ("g1", "g2")
    assert continuity.ui["source"] == "plasticity_observed_schema"


def test_template_only_command_reports_exact_evidence_blockers(tmp_path) -> None:
    _write_promotion_artifacts(tmp_path)

    export_mesh = build_cad_schema_promotion_catalog(tmp_path).get("export_mesh")

    assert export_mesh.promotion_status == "template_only_blocked"
    assert "parameter_controls_observed:missing" in export_mesh.blockers
    assert "required_evidence_referenced:missing" in export_mesh.blockers
    assert "validation_checks_passed:failed" in export_mesh.blockers
    assert "reset_verified:missing" in export_mesh.blockers
    assert "ledger.template_only" in export_mesh.blockers
    assert export_mesh.next_action == "run the package and record observed controls for each visible option"


def test_schema_promotion_real_data_keeps_all_current_rows_blocked() -> None:
    catalog = build_cad_schema_promotion_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["candidate_count"] == 141
    assert summary["promotable_to_descriptor_count"] == 0
    assert summary["promotion_status_counts"]["template_only_blocked"] == 141
    assert summary["reset_verified_count"] == 0
    export_mesh = catalog.get("export_mesh")
    assert export_mesh.required_evidence
    assert "parameter_controls_observed:missing" in export_mesh.blockers
