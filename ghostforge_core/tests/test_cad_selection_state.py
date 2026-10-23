from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_selection_contract_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_selection_artifacts(tmp_path) -> None:
    commands = [
        ("selection_mode_set_edge", "Selection mode: set edge", ["selection_modes"], "viewport_state_before_after_probe"),
        ("selection_convert_to_faces", "Selection: convert to faces", ["selection_modes"], "viewport_state_before_after_probe"),
        ("select_adjacent", "Select Adjacent", ["selection_modes"], "selection_or_snapping_state_probe"),
        ("grid_toggle_grid_snapping", "Grid: toggle grid snapping", ["snapping_planes"], "selection_or_snapping_state_probe"),
        ("group_selected", "Group Selected", ["selection_modes"], "selection_or_snapping_state_probe"),
        ("match_face", "Match Face", ["surface_modeling"], "selection_or_snapping_state_probe"),
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
                for command_id, label, categories, _probe_kind in commands
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
                    "priority": "medium",
                    "probe_kind": probe_kind,
                    "fixture": "neutral_document_session",
                    "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": command_id}}],
                }
                for command_id, label, _categories, probe_kind in commands
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
                    "priority": "medium",
                    "probe_kind": probe_kind,
                    "fixture": "neutral_document_session",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 5,
                    "missing_template_parameters": ["selection_filter", "selection_count", "selection_scope", "snap_targets", "active_plane"],
                    "reset_verified": False,
                }
                for command_id, label, _categories, probe_kind in commands
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
                    "fixture": "neutral_document_session",
                    "parameters_to_observe": [
                        {"name": "selection_filter", "type": "enum"},
                        {"name": "selection_count", "type": "number"},
                        {"name": "selection_scope", "type": "enum"},
                        {"name": "snap_targets", "type": "object"},
                        {"name": "active_plane", "type": "object"},
                    ],
                    "validation_checks": ["selection_state_captured"],
                }
                for command_id, label, _categories, probe_kind in commands
            ]
        },
    )
    _write_json(tmp_path / "parameter_probe_packages.json", {"packages": []})
    _write_json(tmp_path / "static_command_mapping_review.json", {"recommended_batches": {}})
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_selection_catalog_exposes_native_modes_and_topology_prefixes(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_selection_contract_catalog(tmp_path)
    summary = catalog.summary()

    assert summary["mode_count"] >= 9
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    face = catalog.get_mode("face")
    assert face.selection_kinds == ("face",)
    assert "F_" in face.topology_id_prefixes
    assert face.hit_test_priority[0] == "face"


def test_selection_mode_and_conversion_contracts_capture_state_deltas(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)
    catalog = build_cad_selection_contract_catalog(tmp_path)

    set_edge = catalog.get_command("selection_mode_set_edge")
    assert set_edge.operation_kind == "set_mode"
    assert set_edge.output_modes == ("edge",)
    assert "selection_filter.mode=edge" in set_edge.expected_state_delta
    assert "edge selections use E_ or edge_ topology ids" in set_edge.topology_naming_policy

    convert_faces = catalog.get_command("selection_convert_to_faces")
    assert convert_faces.operation_kind == "convert_selection"
    assert convert_faces.preserves_order is True
    assert convert_faces.input_modes == ("object", "face", "edge", "curve", "solid", "surface")
    assert "source_selection_ids" in convert_faces.automation_evidence
    assert "selection.conversion_no_result" in convert_faces.failure_modes


def test_query_grid_group_and_face_context_contracts_are_distinct(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)
    catalog = build_cad_selection_contract_catalog(tmp_path)

    adjacent = catalog.get_command("select_adjacent")
    assert adjacent.operation_kind == "select_query"
    assert "hit_filter_reason_record" in adjacent.automation_evidence

    grid = catalog.get_command("grid_toggle_grid_snapping")
    assert grid.operation_kind == "snapping_or_plane_state"
    assert grid.modifies_selection is False
    assert grid.active_plane_policy == "may_read_active_plane"

    group = catalog.get_command("group_selected")
    assert group.operation_kind == "lock_group_state"
    assert group.modifies_document_state is True

    match_face = catalog.get_command("match_face")
    assert match_face.operation_kind == "face_context_tool"
    assert match_face.input_modes == ("face", "surface")
    assert "relationship.owner_required" in match_face.failure_modes


def test_selection_catalog_real_data_covers_selection_recon_tasks() -> None:
    catalog = build_cad_selection_contract_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["command_contract_count"] >= 30
    assert summary["operation_kind_counts"]["set_mode"] >= 1
    assert summary["operation_kind_counts"]["toggle_mode"] >= 1
    assert summary["operation_kind_counts"]["select_query"] >= 1
    assert "selection_mode_set_edge" in {contract.command_id for contract in catalog.all_commands()}
