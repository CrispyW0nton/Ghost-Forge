from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_evidence_packet_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_packet_artifacts(tmp_path) -> None:
    commands = [
        ("fillet", "Fillet", ["solid_modeling"], "geometry_operation_parameter_panel_probe", "fixture_cube_solid"),
        ("export_mesh", "Export Mesh", ["file_io"], "file_dialog_or_export_options_probe", "temporary_export_output_path"),
        ("face_change", "Face Change", ["surface_modeling"], "geometry_operation_parameter_panel_probe", "fixture_cube_solid"),
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
                    "priority": "high",
                    "probe_kind": probe_kind,
                    "fixture": fixture,
                    "destructive_or_file_touching": command_id == "export_mesh",
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
                    "priority": "high",
                    "probe_kind": probe_kind,
                    "fixture": fixture,
                    "observed_parameter_count": 0,
                    "template_parameter_count": 2,
                    "missing_template_parameters": ["radius", "continuity"]
                    if command_id == "fillet"
                    else ["path", "format"]
                    if command_id == "export_mesh"
                    else ["grow"],
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
                        {"name": "radius", "type": "number"},
                        {"name": "continuity", "type": "enum"},
                    ]
                    if command_id == "fillet"
                    else [
                        {"name": "path", "type": "filesystem_path"},
                        {"name": "format", "type": "enum"},
                    ]
                    if command_id == "export_mesh"
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
                    "command_id": "fillet",
                    "label": "Fillet",
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["radius", "continuity"],
                        "required_evidence": ["baseline_screenshot", "panel_screenshot"],
                        "validation_checks": ["panel_captured"],
                    },
                    "fixture": {
                        "fixture": "fixture_cube_solid",
                        "setup_steps": ["Open disposable cube."],
                        "reset_steps": ["Undo and verify cube."],
                    },
                    "observation_record_template": {
                        "observed_parameters": [
                            {"name": "radius", "type": "number", "observed_control": "", "confidence": ""}
                        ],
                        "validation_results": [{"check": "panel_captured", "passed": False, "evidence": ""}],
                    },
                },
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
                        "static_operation_evidence": {"inferred_options": ["grow"]},
                    }
                ]
            }
        },
    )
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_evidence_packet_catalog_builds_route_specific_packets(tmp_path) -> None:
    _write_packet_artifacts(tmp_path)

    catalog = build_cad_evidence_packet_catalog(tmp_path)
    summary = catalog.summary()

    assert summary["packet_count"] == 3
    assert summary["packet_kind_counts"]["fixture_mutation_packet"] == 1
    assert summary["packet_kind_counts"]["file_interop_packet"] == 1
    assert summary["packet_kind_counts"]["static_owner_packet"] == 1
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"


def test_file_interop_packet_requires_file_artifact_and_reset_sections(tmp_path) -> None:
    _write_packet_artifacts(tmp_path)

    packet = build_cad_evidence_packet_catalog(tmp_path).get("export_mesh")

    assert packet.packet_kind == "file_interop_packet"
    assert packet.file_artifact_required is True
    assert packet.live_execution_allowed is True
    assert "file_artifact" in packet.required_section_ids
    assert "workspace_path_file_record" in packet.required_evidence
    assert "source_document_snapshot_unchanged" in packet.reset_requirements
    assert "path" in packet.parameter_names
    assert "format" in packet.parameter_names


def test_fixture_mutation_packet_carries_topology_failure_and_tolerance_targets(tmp_path) -> None:
    _write_packet_artifacts(tmp_path)

    packet = build_cad_evidence_packet_catalog(tmp_path).get("fillet")

    assert packet.packet_kind == "fixture_mutation_packet"
    assert "topology_delta" in packet.required_section_ids
    assert "failure_tolerance" in packet.required_section_ids
    assert "fillet.radius_too_large" in packet.failure_targets
    assert "tolerance:fillet" in packet.tolerance_targets
    assert any("F_blend_top_front" in target for target in packet.topology_targets)


def test_static_owner_packet_stays_blocked_until_owner_classification(tmp_path) -> None:
    _write_packet_artifacts(tmp_path)

    packet = build_cad_evidence_packet_catalog(tmp_path).get("face_change")

    assert packet.packet_kind == "static_owner_packet"
    assert packet.static_owner_required is True
    assert packet.readiness == "waiting_for_static_owner"
    assert "static_owner_classification" in packet.required_section_ids
    assert "section.static_owner_classification.blocked" in packet.blockers


def test_evidence_packet_catalog_real_data_covers_all_recon_routes() -> None:
    catalog = build_cad_evidence_packet_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["packet_count"] == 141
    assert summary["packet_kind_counts"]["file_interop_packet"] == 23
    assert summary["packet_kind_counts"]["selection_state_packet"] == 33
    assert summary["packet_kind_counts"]["static_owner_packet"] == 2
    assert summary["live_execution_allowed_count"] == 21
    assert catalog.get("export_mesh").readiness == "ready_to_capture"
