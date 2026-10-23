from __future__ import annotations

import json

from ghostforge_core.cad import build_ghostforge_cad_development_queue


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_minimal_queue_artifacts(tmp_path) -> None:
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {
                    "id": "fillet",
                    "label": "Fillet",
                    "categories": ["solid_modeling"],
                    "sources": ["command_palette_filtered"],
                    "palette_queries": ["fillet"],
                    "shortcuts": ["F"],
                    "reachability": "observed_palette",
                },
                {
                    "id": "export_mesh",
                    "label": "Export Mesh",
                    "categories": ["file_io", "mesh_export_rendering"],
                    "sources": ["static_operation_asset"],
                    "palette_queries": ["Export Mesh"],
                    "reachability": "static_inferred",
                },
                {
                    "id": "face_change",
                    "label": "Face Change",
                    "categories": ["surface_modeling"],
                    "sources": ["static_operation_asset"],
                    "reachability": "reviewed_no_visible_match",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_observation_readiness.json",
        {
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "bucket_counts": {"fixture_required": 1, "palette_confirmation": 2},
            "rows": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "readiness_bucket": "fixture_required",
                    "stage": "palette_reachable_needs_parameter_probe",
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_document_with_solid_sheet_curve_edge_and_face_selection_sets",
                    "missing_parameter_count": 3,
                    "mcp_route": [
                        {"tool": "parameter_probe_session", "arguments": {"command_id": "fillet"}}
                    ],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "readiness_bucket": "palette_confirmation",
                    "stage": "static_inferred_needs_palette_confirmation",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "destructive_or_file_touching": True,
                    "missing_parameter_count": 4,
                    "mcp_route": [
                        {"tool": "plasticity_palette_search_probe", "arguments": {"query": "Export Mesh"}}
                    ],
                },
            ],
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
                    "template_parameter_count": 3,
                    "missing_template_parameters": ["radius", "continuity", "tolerance"],
                    "evidence_screenshots": ["evidence/fillet.png"],
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
                    "template_parameter_count": 4,
                    "missing_template_parameters": ["path", "format", "tolerance", "overwrite_policy"],
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
            "generated_utc": "2026-06-01T14:08:16+00:00",
            "schema_status_counts": {"template_inferred_needs_probe": 3},
            "templates": [
                {
                    "command_id": "fillet",
                    "label": "Fillet",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [
                        {"name": "radius", "type": "float"},
                        {"name": "continuity", "type": "enum"},
                        {"name": "tolerance", "type": "float"},
                    ],
                    "validation_checks": ["before_screenshot_captured"],
                    "expected_state_effects": ["geometry_topology_or_transform_change"],
                    "evidence_screenshots": ["evidence/fillet.png"],
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
                        {"name": "tolerance", "type": "float"},
                        {"name": "overwrite_policy", "type": "enum"},
                    ],
                },
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [{"name": "grow", "type": "bool"}],
                },
            ],
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
                        "validation_checks": ["workspace_controlled_path_used"],
                    },
                    "fixture": {
                        "fixture": "temporary_export_output_path",
                        "setup_steps": ["Choose knowledge_base/fixtures/exports."],
                        "reset_steps": ["Remove only files inside knowledge_base/fixtures/exports."],
                        "safety_notes": ["Use workspace-controlled paths."],
                        "state_requirements": ["document_session", "output_path"],
                    },
                    "invocation_plan": {
                        "palette_queries": ["Export Mesh"],
                        "preferred_invocation": "requires_runtime_probe",
                    },
                    "observation_record_template": {
                        "observed_parameters": [
                            {"name": "path", "type": "filesystem_path"},
                            {"name": "format", "type": "enum"},
                        ]
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "static_command_mapping_review.json",
        {
            "recommended_batches": {
                "prepare_controlled_probe": [
                    {
                        "command_id": "export_mesh",
                        "mapping_status": "controlled_probe_needed",
                        "next_action": "prepare disposable export probe",
                        "static_operation_evidence": {
                            "inferred_options": ["angle tolerance", "inflect", "max width"],
                            "evidence_assets": ["export-mesh-angle-tolerance.png"],
                        },
                    }
                ],
                "review_as_option_or_alias": [
                    {
                        "command_id": "face_change",
                        "mapping_status": "likely_option_or_alias",
                        "next_action": "probe likely owner commands",
                        "candidate_existing_commands": [
                            {"command_id": "match_face"},
                            {"command_id": "draft_face"},
                        ],
                        "static_operation_evidence": {
                            "inferred_options": ["grow"],
                            "evidence_assets": ["face-change-grow.png"],
                        },
                    }
                ],
            }
        },
    )
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {"mesh_export": {}}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_development_queue_joins_recon_templates_packages_and_static_mapping(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    queue = build_ghostforge_cad_development_queue(tmp_path)
    summary = queue.summary()

    assert summary["task_count"] == 3
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["track_counts"]["solid_modeling_kernel"] == 1
    assert summary["track_counts"]["file_interop"] == 1
    assert summary["track_counts"]["static_asset_resolution"] == 1
    assert summary["route_ready_count"] == 2
    assert summary["probe_package_count"] == 1
    assert summary["workspace_safety_gate_count"] == 1


def test_development_queue_tracks_geometry_command_schema_and_fixture_blockers(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    fillet = build_ghostforge_cad_development_queue(tmp_path).get("fillet")

    assert fillet.implementation_track == "solid_modeling_kernel"
    assert fillet.template_parameters == ("radius", "continuity", "tolerance")
    assert fillet.missing_parameters == ("radius", "continuity", "tolerance")
    assert "parameter_probe_session" in fillet.automation_tools
    assert "plasticity.observed_schema_missing" in fillet.blockers
    assert "plasticity.reset_not_verified" in fillet.blockers
    assert "plasticity.probe_package_missing" in fillet.blockers
    assert fillet.next_ghostforge_action == "use_inferred_template_to_draft_schema_then_wait_for_live_observation"


def test_development_queue_preserves_file_safety_and_static_export_options(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    export_mesh = build_ghostforge_cad_development_queue(tmp_path).get("export_mesh")

    assert export_mesh.implementation_track == "file_interop"
    assert export_mesh.file_touching is True
    assert export_mesh.workspace_safety_gate is True
    assert export_mesh.package_available is True
    assert export_mesh.parameter_names_to_resolve == ("path", "format", "tolerance")
    assert {"angle_tolerance", "inflect", "max_width"} <= set(export_mesh.inferred_static_options)
    assert "static_asset.controlled_probe_needed" in export_mesh.blockers
    assert export_mesh.next_plasticity_action == "prepare disposable export probe"


def test_development_queue_blocks_static_assets_until_owner_is_verified(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    face_change = build_ghostforge_cad_development_queue(tmp_path).get("face_change")

    assert face_change.implementation_track == "static_asset_resolution"
    assert face_change.static_mapping_status == "likely_option_or_alias"
    assert face_change.inferred_static_options == ("grow",)
    assert face_change.candidate_owner_commands == ("match_face", "draft_face")
    assert "static_asset.owner_unresolved" in face_change.blockers
    assert face_change.next_ghostforge_action == "keep_relationship_descriptor_blocked_until_owner_command_is_verified"
