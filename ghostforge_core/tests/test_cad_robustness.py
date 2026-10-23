from __future__ import annotations

import json

from ghostforge_core.cad import build_cad_robustness_catalog


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_selection_artifacts(tmp_path) -> None:
    commands = [
        ("selection_mode_set_edge", "Selection mode: set edge", ["selection_modes"], "selection_or_snapping_state_probe"),
        ("selection_convert_to_faces", "Selection: convert to faces", ["selection_modes"], "selection_or_snapping_state_probe"),
        ("select_adjacent", "Select Adjacent", ["selection_modes"], "selection_or_snapping_state_probe"),
        ("grid_toggle_grid_snapping", "Grid: toggle grid snapping", ["snapping_planes"], "selection_or_snapping_state_probe"),
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
    rows = [
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
    _write_json(tmp_path / "parameter_observation_readiness.json", {"rows": rows})
    _write_json(
        tmp_path / "parameter_observation_ledger.json",
        {
            "commands": [
                {
                    **row,
                    "schema_status": "template_inferred_needs_probe",
                    "observed_parameter_count": 0,
                    "template_parameter_count": 3,
                    "missing_template_parameters": ["selection_filter", "selection_scope", "active_plane"],
                    "reset_verified": False,
                }
                for row in rows
            ]
        },
    )
    _write_json(
        tmp_path / "parameter_schema_templates.json",
        {
            "templates": [
                {
                    "command_id": row["command_id"],
                    "label": row["label"],
                    "schema_status": "template_inferred_needs_probe",
                    "probe_kind": row["probe_kind"],
                    "fixture": row["fixture"],
                    "parameters_to_observe": [
                        {"name": "selection_filter", "type": "enum"},
                        {"name": "selection_scope", "type": "enum"},
                        {"name": "active_plane", "type": "object"},
                    ],
                }
                for row in rows
            ]
        },
    )
    _write_json(tmp_path / "parameter_probe_packages.json", {"packages": []})
    _write_json(tmp_path / "static_command_mapping_review.json", {"recommended_batches": {}})
    _write_json(tmp_path / "plasticity_file_format_map.json", {"formats": {}})
    _write_json(tmp_path / "goal_progress_audit.json", {"requirements": []})


def test_robustness_catalog_summarizes_native_topology_tolerance_and_failure_contracts(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_robustness_catalog(tmp_path)
    summary = catalog.summary()

    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["topology_policy_count"] >= 8
    assert summary["subject_type_counts"]["cad_command"] >= 10
    assert summary["subject_type_counts"]["selection_command"] >= 5
    assert summary["subject_type_counts"]["interop_format"] >= 6
    assert summary["failure_contract_count"] >= 20
    assert summary["tolerance_contract_count"] >= 10


def test_fillet_contract_records_blend_lineage_tolerance_and_failure_modes(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_robustness_catalog(tmp_path)
    fillet = catalog.get_contract("fillet")

    assert fillet.contract_id == "command:fillet"
    assert "face_identity" in fillet.topology_policy_ids
    assert "edge_boundary_identity" in fillet.topology_policy_ids
    assert any("E_top_front:deleted" in relation for relation in fillet.lineage_relations)
    assert "fillet.radius_too_large" in fillet.failure_codes
    assert "plasticity_evidence:needs_fixture_behavior_probe" in fillet.promotion_blockers

    tolerance = catalog.tolerance_contracts[fillet.tolerance_contract_ids[0]]
    assert "fillet.radius_too_large" in tolerance.failure_codes
    assert tolerance.verification_evidence


def test_selection_conversion_contract_keeps_source_and_result_ids_visible(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_robustness_catalog(tmp_path)
    convert = catalog.get_contract("selection_convert_to_faces")

    assert convert.contract_id == "selection:selection_convert_to_faces"
    assert convert.subject_type == "selection_command"
    assert "selection_identity" in convert.topology_policy_ids
    assert "selection_source_ids->selection_result_ids" in convert.lineage_relations
    assert "selection.conversion_no_result" in convert.failure_codes
    assert "source_selection_ids" in convert.verification_gates


def test_interop_contract_captures_file_safety_and_translator_failures(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_robustness_catalog(tmp_path)
    step = catalog.get_contract("step_stp")
    mesh = catalog.get_contract("mesh_export")

    assert step.contract_id == "format:step_stp"
    assert "artifact_identity" in step.topology_policy_ids
    assert "brep.healing_failed" in step.failure_codes
    assert "format_fixture_verification_required" in step.promotion_blockers

    assert mesh.subject_type == "interop_format"
    assert "path.permission_denied" in mesh.failure_codes
    assert "artifact_manifest_record" in mesh.verification_gates


def test_static_context_entries_remain_blocked_until_owner_evidence_exists(tmp_path) -> None:
    _write_selection_artifacts(tmp_path)

    catalog = build_cad_robustness_catalog(tmp_path)
    face_change = catalog.get_contract("face_change_grow")
    xnurbs = catalog.get_contract("xnurbs_boundary")

    assert face_change.subject_type == "cad_command"
    assert "descriptor_status:option" in face_change.promotion_blockers
    assert "relationship.owner_required" in face_change.failure_codes
    assert "plasticity_evidence:needs_static_asset_owner_probe" in face_change.promotion_blockers

    assert xnurbs.subject_type == "cad_command"
    assert "descriptor_status:contextual_mode" in xnurbs.promotion_blockers
    assert "surface_patch.open_boundary" in xnurbs.failure_codes
    assert "plasticity_evidence:needs_static_asset_owner_probe" in xnurbs.promotion_blockers


def test_robustness_catalog_real_data_includes_selection_and_interop_recon() -> None:
    catalog = build_cad_robustness_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["subject_type_counts"]["selection_command"] >= 30
    assert summary["subject_type_counts"]["interop_format"] == 6
    assert catalog.get_contract("selection_mode_set_edge").subject_type == "selection_command"
    assert catalog.get_contract("export_mesh").subject_type == "cad_command"
