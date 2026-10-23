from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_schema_draft_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_minimal_queue_artifacts(tmp_path) -> None:
    _write_json(
        tmp_path / "command_recon_index.json",
        {
            "commands": [
                {"id": "fillet", "label": "Fillet", "categories": ["solid_modeling"]},
                {"id": "export_mesh", "label": "Export Mesh", "categories": ["file_io"]},
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
                    "priority": "high",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "missing_parameter_count": 3,
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
                },
                {
                    "command_id": "export_mesh",
                    "label": "Export Mesh",
                    "priority": "critical",
                    "probe_kind": "file_dialog_or_export_options_probe",
                    "fixture": "temporary_export_output_path",
                    "destructive_or_file_touching": True,
                    "missing_parameter_count": 3,
                    "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {}}],
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
                    "template_parameter_count": 3,
                    "missing_template_parameters": ["radius", "continuity", "tolerance"],
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
                    "reachability": "observed_palette",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
                    "parameters_to_observe": [
                        {"name": "radius", "type": "number"},
                        {"name": "continuity", "type": "enum"},
                        {"name": "tolerance", "type": "number"},
                    ],
                    "validation_checks": ["before_screenshot_captured"],
                    "expected_state_effects": ["geometry_topology_or_transform_change"],
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
                {
                    "command_id": "face_change",
                    "label": "Face Change",
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": "geometry_operation_parameter_panel_probe",
                    "fixture": "fixture_cube_solid",
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
                    "evidence_capture_plan": {"parameter_names_to_resolve": ["path", "format"]},
                    "fixture": {
                        "fixture": "temporary_export_output_path",
                        "reset_steps": ["Remove only files inside knowledge_base/fixtures/exports."],
                        "safety_notes": ["Use workspace-controlled paths."],
                    },
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


def test_schema_draft_catalog_builds_from_recon_templates(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    catalog = build_cad_schema_draft_catalog(tmp_path)
    summary = catalog.summary()

    assert summary["draft_count"] == 3
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["status_counts"] == {"template_inferred": 3}
    assert summary["track_counts"]["solid_modeling_kernel"] == 1
    assert summary["track_counts"]["file_interop"] == 1
    assert summary["track_counts"]["static_asset_resolution"] == 1
    assert summary["blocker_counts"]["plasticity.observed_schema_missing"] == 3


def test_geometry_template_becomes_parameter_and_option_panel_draft(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    fillet = build_cad_schema_draft_catalog(tmp_path).get("fillet")

    assert fillet.status == "template_inferred"
    assert fillet.template_parameters == ("radius", "continuity", "tolerance")
    assert fillet.missing_parameters == ("radius", "continuity", "tolerance")
    assert {group.group_id for group in fillet.option_panel_groups} == {
        "primary_parameters",
        "advanced_options",
    }
    radius = next(parameter for parameter in fillet.parameter_drafts if parameter.name == "radius")
    assert radius.ghostforge_type == "float"
    assert radius.ui_control == "numeric_input"
    assert radius.required is True
    assert radius.unit == "scene_units"
    assert "value_must_be_nonzero_when_command_requires_extent" in radius.validation_rules

    continuity = next(parameter for parameter in fillet.parameter_drafts if parameter.name == "continuity")
    assert continuity.ui_control == "dropdown"
    assert continuity.values == ("g0", "g1", "g2")
    assert "enum_values_need_confirmation" in continuity.promotion_blockers


def test_file_template_becomes_file_option_panel_schema_draft(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    export_mesh = build_cad_schema_draft_catalog(tmp_path).get("export_mesh")

    assert export_mesh.implementation_track == "file_interop"
    assert {group.group_id for group in export_mesh.option_panel_groups} == {"file_options", "advanced_options"}
    path = next(parameter for parameter in export_mesh.parameter_drafts if parameter.name == "path")
    assert path.ghostforge_type == "path"
    assert path.ui_control == "file_picker"
    assert path.required is True
    assert "path_must_be_workspace_controlled_for_automation" in path.validation_rules
    tolerance = next(parameter for parameter in export_mesh.parameter_drafts if parameter.name == "tolerance")
    assert tolerance.default == 1e-5
    assert tolerance.panel_group == "advanced_options"


def test_static_asset_schema_draft_remains_blocked_until_owner_resolution(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    face_change = build_cad_schema_draft_catalog(tmp_path).get("face_change")

    assert face_change.implementation_track == "static_asset_resolution"
    assert "static_asset.owner_unresolved" in face_change.promotion_blockers
    assert face_change.next_action == "resolve_owner_command_before_promoting_option_panel_schema"
    grow = face_change.parameter_drafts[0]
    assert grow.name == "grow"
    assert grow.ghostforge_type == "bool"
    assert grow.ui_control == "checkbox"


def test_parameter_draft_exports_descriptor_parameter_spec(tmp_path) -> None:
    _write_minimal_queue_artifacts(tmp_path)

    spec = build_cad_schema_draft_catalog(tmp_path).get("fillet").parameter_specs()[0]

    assert spec.name == "radius"
    assert spec.type == "float"
    assert spec.required is True
    assert spec.ui["control"] == "numeric_input"
    assert spec.ui["draft_status"] == "inferred_from_recon_template"
