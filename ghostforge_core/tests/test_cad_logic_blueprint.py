from __future__ import annotations

from ghostforge_core.cad import build_default_logic_blueprint


def test_logic_blueprint_is_native_ghostforge_logic_not_runtime_plasticity_mcp() -> None:
    blueprint = build_default_logic_blueprint()
    summary = blueprint.summary()

    assert summary["pattern_count"] >= 4
    pipeline = blueprint.get("descriptor_driven_command_pipeline")
    assert "Plasticity observations are used as comparator evidence, not runtime dependencies." in pipeline.verification_logic
    assert any(stage.stage_id == "commit_transaction" for stage in pipeline.command_pipeline)
    assert "Manifest provenance is emitted by core command execution, not by Qt or MCP wrappers." in pipeline.undo_manifest_logic


def test_topology_identity_pattern_captures_lineage_and_stable_id_rules() -> None:
    blueprint = build_default_logic_blueprint()
    topology = blueprint.get("topology_identity_and_lineage")

    assert "extrude" in topology.applies_to
    assert "fillet" in topology.applies_to
    assert any(stage.stage_id == "assign_result_ids" for stage in topology.command_pipeline)
    assert "Record split, merge, delete, replace, and create relationships." in topology.topology_logic
    assert "Undo restores both geometry and stable topology ids where possible." in topology.undo_manifest_logic


def test_export_import_pattern_makes_format_options_first_class() -> None:
    blueprint = build_default_logic_blueprint()
    interop = blueprint.get("export_import_format_pipeline")

    assert {"export_mesh", "step_stp", "iges_igs", "dwg_dxf"}.issubset(set(interop.applies_to))
    assert any(stage.stage_id == "resolve_format_options" for stage in interop.command_pipeline)
    assert any("angle tolerance" in rule for rule in interop.parameter_logic)
    assert any("workspace-controlled temporary paths" in rule for rule in interop.verification_logic)


def test_static_asset_classification_keeps_face_change_and_xnurbs_as_evidence_candidates() -> None:
    blueprint = build_default_logic_blueprint()
    static_assets = blueprint.get("static_asset_classification")

    assert {"face_change_grow", "xnurbs_boundary"}.issubset(set(static_assets.applies_to))
    assert "Static assets become evidence candidates, not automatic top-level commands." == static_assets.intent
    assert any("owner command panels" in rule for rule in static_assets.option_panel_logic)
    assert "Unverified ownership blocks top-level exposure." in static_assets.failure_logic


def test_patterns_for_command_returns_all_relevant_logic() -> None:
    blueprint = build_default_logic_blueprint()

    export_patterns = {pattern.pattern_id for pattern in blueprint.patterns_for_command("export_mesh")}
    assert {
        "descriptor_driven_command_pipeline",
        "export_import_format_pipeline",
        "static_asset_classification",
    }.issubset(export_patterns)
