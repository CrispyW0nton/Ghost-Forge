from __future__ import annotations

import json

from ghostforge_core.cad import (
    CadCapturedEvidenceSection,
    CadFileArtifactObservation,
    CadLiveProbeObservationRecord,
    CadObservationValidationResult,
    CadObservedControl,
    CadStaticOwnerObservation,
    CadTopologyObservation,
    build_cad_observation_template_catalog,
    validate_cad_observation_record,
)


def _write_json(path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_observation_artifacts(tmp_path) -> None:
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
                    "observation_record_template": {
                        "observed_parameters": [{"name": "path", "type": "filesystem_path"}],
                        "validation_results": [{"check": "workspace_controlled_path_used", "passed": False, "evidence": ""}],
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
                    "observation_record_template": {
                        "observed_parameters": [{"name": "grow", "type": "bool"}],
                        "validation_results": [{"check": "owner_command_panel_detected", "passed": False, "evidence": ""}],
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


def test_observation_template_matches_live_session_required_sections(tmp_path) -> None:
    _write_observation_artifacts(tmp_path)

    template = build_cad_observation_template_catalog(tmp_path).get("export_mesh")

    assert template.command_id == "export_mesh"
    assert template.fixture == "temporary_export_output_path"
    assert {section.section_id for section in template.captured_sections} >= {
        "session_identity",
        "parameter_panel",
        "file_artifact",
        "reset_verification",
    }
    assert {control.maps_to_parameter for control in template.observed_controls} >= {"path", "format"}


def test_complete_export_mesh_observation_feeds_schema_behavior_and_interop(tmp_path) -> None:
    _write_observation_artifacts(tmp_path)
    template = build_cad_observation_template_catalog(tmp_path).get("export_mesh")
    required_sections = template.captured_sections
    record = CadLiveProbeObservationRecord(
        command_id="export_mesh",
        plasticity_version="26.1.3",
        fixture="temporary_export_output_path",
        session_mode="ready_for_manual_live_capture",
        captured_sections=tuple(
            CadCapturedEvidenceSection(
                section_id=section.section_id,
                status="captured",
                evidence_refs=(f"{section.section_id}.png",),
                fields={"captured": True},
            )
            for section in required_sections
        ),
        observed_controls=tuple(
            CadObservedControl(
                control_id=control.control_id,
                control_type="dropdown" if control.maps_to_parameter == "format" else "numeric_input",
                maps_to_parameter=control.maps_to_parameter,
                current_value="fixtures/exports/cube.glb" if control.maps_to_parameter in {"path", "target_path"} else 1,
                option_values=("glb", "obj", "stl") if control.maps_to_parameter == "format" else (),
                confidence="high",
                evidence_refs=("file_dialog_or_options_screenshot",),
            )
            for control in template.observed_controls
        ),
        validation_results=(
            CadObservationValidationResult(
                check_id="workspace_controlled_path_used",
                passed=True,
                evidence_refs=("workspace_path_file_record",),
            ),
            CadObservationValidationResult(
                check_id="format_options_detected",
                passed=True,
                evidence_refs=("file_dialog_or_options_screenshot",),
            ),
        ),
        topology_delta=CadTopologyObservation(
            before_counts={"objects": 1, "faces": 6},
            after_counts={"objects": 1, "faces": 6},
            modified_ids=("artifact:export_mesh",),
            evidence_refs=("topology_delta.png",),
        ),
        file_artifacts=(
            CadFileArtifactObservation(
                path="fixtures/exports/cube.glb",
                format_id="mesh_export",
                operation="export",
                source_topology_preserved=True,
                evidence_refs=("workspace_path_file_record",),
            ),
        ),
        reset_verified=True,
    )

    report = validate_cad_observation_record(record, tmp_path)

    assert report.status == "accepted_for_promotion"
    assert report.missing_sections == ()
    assert report.missing_parameters == ()
    assert "schema_promotion" in report.promotion_targets
    assert "fixture_behavior_parity" in report.promotion_targets
    assert "interop_contract" in report.promotion_targets


def test_incomplete_observation_reports_precise_missing_evidence(tmp_path) -> None:
    _write_observation_artifacts(tmp_path)
    record = CadLiveProbeObservationRecord(
        command_id="export_mesh",
        captured_sections=(
            CadCapturedEvidenceSection(
                section_id="session_identity",
                status="captured",
                evidence_refs=("session.json",),
            ),
        ),
        observed_controls=(
            CadObservedControl(
                control_id="export_mesh.path",
                control_type="file_picker",
                maps_to_parameter="path",
                evidence_refs=("file_dialog_or_options_screenshot",),
            ),
        ),
        validation_results=(
            CadObservationValidationResult(check_id="workspace_controlled_path_used", passed=False),
        ),
        reset_verified=False,
    )

    report = validate_cad_observation_record(record, tmp_path)

    assert report.status == "rejected_failed_checks"
    assert "validation.workspace_controlled_path_used.failed" in report.blockers
    assert "parameter.format.missing_observed_control" in report.blockers
    assert "file_artifact.missing" in report.blockers
    assert "reset_verification.missing" in report.blockers


def test_static_asset_observation_is_accepted_only_for_owner_classification(tmp_path) -> None:
    _write_observation_artifacts(tmp_path)
    record = CadLiveProbeObservationRecord(
        command_id="face_change",
        fixture="neutral_document_session",
        captured_sections=(
            CadCapturedEvidenceSection(
                section_id="static_owner_classification",
                status="captured",
                evidence_refs=("face_change_owner_panel.png",),
                fields={"owner_command_id": "match_face", "classification": "option"},
            ),
        ),
        static_owner_classification=CadStaticOwnerObservation(
            static_asset_id="face-change-grow.png",
            classification="option",
            owner_command_id="match_face",
            negative_palette_evidence_refs=("face_change_negative_palette.png",),
            owner_panel_evidence_refs=("face_change_owner_panel.png",),
        ),
        reset_verified=False,
    )

    report = validate_cad_observation_record(record, tmp_path)

    assert report.status == "accepted_for_static_owner"
    assert "registry_relationships" in report.promotion_targets
    assert "schema_promotion" not in report.promotion_targets
    assert "session.blocked" not in report.blockers


def test_observation_template_real_data_counts() -> None:
    catalog = build_cad_observation_template_catalog(
        r"C:\Users\NewAdmin\Documents\GDeveloper\Workspaces\PlasticityMCP\knowledge_base"
    )
    summary = catalog.summary()

    assert summary["template_count"] == 141
    assert catalog.get("export_mesh").captured_sections
    assert catalog.get("face_change").session_mode == "blocked"
