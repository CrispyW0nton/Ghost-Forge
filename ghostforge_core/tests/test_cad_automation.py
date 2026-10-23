from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_automation_runbook


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_minimal_queue_artifacts(tmp_path) -> None:
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {"id": "fillet", "label": "Fillet", "categories": ["solid_modeling"], "palette_queries": ["fillet"]},
                {"id": "export_mesh", "label": "Export Mesh", "categories": ["file_io", "mesh_export_rendering"], "palette_queries": ["Export Mesh"]},
                {"id": "face_change", "label": "Face Change", "categories": ["surface_modeling"]},
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
                    "readiness_bucket": "fixture_required",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "missing_parameter_count": 2,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "fillet"}}],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "readiness_bucket": "palette_confirmation",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "destructive_or_file_touching": True,
                    "missing_parameter_count": 3,
                    "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {"query": "Export Mesh"}}],
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
                    "schema_status": "template_inferred_needs_probe",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 2,
                    "missing_template_parameters": ["radius", "continuity"],
                    "reset_verified": False,
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
                    "reset_verified": False,
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "priority": "critical",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 1,
                    "missing_template_parameters": ["grow"],
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
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [{"name": "radius", "type": "float"}, {"name": "continuity", "type": "enum"}],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "parameters_to_observe": [{"name": "path", "type": "filesystem_path"}, {"name": "format", "type": "enum"}],
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [{"name": "grow", "type": "bool"}],
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
                        "parameter_names_to_resolve": ["path", "format", "tolerance"],
                        "required_evidence": ["file_dialog_or_options_screenshot", "workspace_path_file_record"],
                    },
                    "fixture": {
                        "fixture": "temporary_export_output_path",
                        "setup_steps": ["Choose knowledge_base/fixtures/exports."],
                        "reset_steps": ["Remove only files inside knowledge_base/fixtures/exports."],
                        "safety_notes": ["Use workspace-controlled paths."],
                        "state_requirements": ["document_session", "output_path"],
                    },
                    "invocation_plan": {"palette_queries": ["Export Mesh"], "preferred_invocation": "requires_runtime_probe"},
                    "observation_record_template": {"observed_parameters": [{"name": "path", "type": "filesystem_path"}]},
                }
            ]
        },
    )
    _write_json(
        tmp_path / "static_command_mapping_review.json",
        {
            "recommended_batches": {
                "prepare_controlled_probe": [
                    {"command_id": "export_mesh", "mapping_status": "controlled_probe_needed"}
                ],
                "review_as_option_or_alias": [
                    {
                        "command_id": "face_change",
                        "mapping_status": "likely_option_or_alias",
                        "candidate_existing_commands": [{"command_id": "match_face"}],
                        "static_operation_evidence": {"inferred_options": ["grow"]},
                    }
                ],
            }
        },
    )
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_automation_runbook_covers_queue_and_summarizes_route_kinds(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    runbook = build_cad_automation_runbook(tmp_path)
    summary = runbook.summary()

    assert summary["route_count"] == 3
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["route_kind_counts"] == {
        "file_interop_probe": 1,
        "fixture_mutation_probe": 1,
        "static_owner_probe": 1,
    }
    assert summary["package_available_count"] == 1
    assert summary["file_touching_route_count"] == 1


def test_file_interop_route_requires_workspace_scope_and_artifact_evidence(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    route = build_cad_automation_runbook(tmp_path).get("export_mesh")

    assert route.route_kind == "file_interop_probe"
    assert route.live_execution_allowed is True
    assert route.workspace_write_scope == "workspace_controlled_fixture_exports_only"
    gate_status = {gate.gate_id: gate.status for gate in route.safety_gates}
    assert gate_status["workspace_write_scope"] == "satisfied"
    assert "workspace_path_file_record" in route.evidence.required
    assert "artifact_or_translator_diagnostics" in route.evidence.required
    assert route.evidence.reset_verification == (
        "remove_only_workspace_artifacts",
        "source_document_snapshot_unchanged",
    )
    assert route.native_consumer == "ghostforge_core.cad.interop"


def test_geometry_mutation_route_is_blocked_until_probe_package_exists(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    route = build_cad_automation_runbook(tmp_path).get("fillet")

    assert route.route_kind == "fixture_mutation_probe"
    assert route.live_execution_allowed is False
    assert route.missing_required_gates == ("probe_package", "disposable_fixture")
    assert "observed_parameter_schema" in route.evidence.required
    assert "fixture_topology_delta" in route.evidence.required
    assert route.next_action == "create_probe_package_with_fixture_setup_evidence_and_reset_steps"
    assert route.native_consumer == "ghostforge_core.cad.behavior + future kernel handler"


def test_static_asset_route_never_executes_until_owner_is_resolved(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    route = build_cad_automation_runbook(tmp_path).get("face_change")

    assert route.route_kind == "static_owner_probe"
    assert route.live_execution_allowed is False
    assert "owner_command_resolution" in route.missing_required_gates
    assert "negative_palette_screenshot" in route.evidence.required
    assert "candidate_owner_panel_screenshots" in route.evidence.required
    assert route.next_action == "probe_candidate_owner_commands_without_promoting_static_asset"
    assert route.native_consumer == "ghostforge_core.cad.registry relationship descriptor"
