from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _unwrap(value):
    if (
        isinstance(value, dict)
        and set(value.keys()) == {"result"}
        and not isinstance(value["result"], dict)
    ):
        return value["result"]
    return value


def _payload(result):
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, (dict, list)):
            return _unwrap(structured)
        for item in content:
            text = getattr(item, "text", None)
            if text is None:
                continue
            return _unwrap(json.loads(text))
    for item in result:
        text = getattr(item, "text", None)
        if text is None:
            continue
        return _unwrap(json.loads(text))
    raise AssertionError(f"no payload in {result!r}")


@pytest.fixture(autouse=True)
def isolated_data_root(monkeypatch, tmp_path):
    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "0")

    from ghostforge_mcp import server as server_mod

    server_mod.reset_context_for_tests()
    yield
    server_mod.reset_context_for_tests()


def _server():
    from ghostforge_mcp.server import build_server

    return build_server()


def _call(server, name, args=None):
    return _payload(asyncio.run(server.call_tool(name, args or {})))


def _resource_payload(result):
    content = result[0].content if isinstance(result, list) else result.content
    return json.loads(content)


def _transform_graph_payload(*, parameters=None):
    return {
        "graph_id": "mcp_cad_graph_transform",
        "document_units": "meters",
        "nodes": [
            {
                "node_id": "n_transform",
                "command_id": "transform",
                "parameters": parameters or {"translate": [1.0, 0.0, 0.0], "scale": 1.0},
                "selection": {
                    "items": [
                        {
                            "object_id": "mesh_cube",
                            "object_kind": "mesh",
                            "selection_kind": "object",
                            "topology_id": "mesh_cube",
                        }
                    ],
                    "active_object_id": "mesh_cube",
                },
                "inputs": [{"ref_id": "mesh_in", "entity_id": "mesh_cube", "role": "input"}],
                "outputs": [{"ref_id": "mesh_out", "entity_id": "mesh_cube", "role": "output"}],
            }
        ],
        "entity_table": {"mesh_cube": {"entity_id": "mesh_cube", "kind": "mesh"}},
    }


def _create_box_graph_payload(*, parameters=None):
    return {
        "graph_id": "mcp_cad_graph_box",
        "document_units": "meters",
        "nodes": [
            {
                "node_id": "n_box",
                "command_id": "create_box",
                "parameters": parameters or {"extents": [2.0, 3.0, 4.0], "center": [1.0, 2.0, 3.0]},
                "outputs": [{"ref_id": "box_out", "entity_id": "box_mesh", "role": "output"}],
            }
        ],
    }


def _cube_mesh(path: Path) -> Path:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.export(str(path))
    return path


def test_cad_command_tools_and_resources_registered():
    server = _server()
    tools = asyncio.run(server.list_tools())
    tool_names = {tool.name for tool in tools}
    resources = asyncio.run(server.list_resources())
    resource_uris = {str(resource.uri) for resource in resources}
    templates = asyncio.run(server.list_resource_templates())
    template_uris = {template.uriTemplate for template in templates}

    assert {
        "list_cad_commands",
        "get_cad_command",
        "preflight_cad_command",
        "validate_cad_operation_graph",
        "execute_cad_operation_graph",
        "list_cad_fixtures",
        "get_cad_fixture",
        "list_cad_command_fixture_expectations",
        "list_cad_behavior_cases",
        "get_cad_behavior_case",
        "list_cad_probe_matrix",
        "get_cad_command_probe_plan",
        "list_cad_logic_blueprint",
        "get_cad_logic_pattern",
        "list_cad_interop_formats",
        "get_cad_interop_format",
        "list_cad_development_queue",
        "get_cad_development_task",
        "list_cad_automation_runbook",
        "get_cad_automation_route",
        "list_cad_schema_drafts",
        "get_cad_schema_draft",
        "list_cad_schema_promotions",
        "get_cad_schema_promotion",
        "list_cad_evidence_packets",
        "get_cad_evidence_packet",
        "list_cad_probe_batches",
        "get_cad_probe_batch",
        "list_cad_live_probe_sessions",
        "get_cad_live_probe_session",
        "list_cad_observation_templates",
        "get_cad_observation_template",
        "validate_cad_observation_record",
        "list_cad_observation_ledger",
        "get_cad_observation_ledger_command",
        "list_cad_native_handoffs",
        "get_cad_native_handoff_command",
        "list_cad_capture_campaign",
        "get_cad_capture_campaign_command",
        "list_cad_selection_contracts",
        "get_cad_selection_command",
        "list_cad_robustness_contracts",
        "get_cad_robustness_contract",
        "list_plasticity_recon_coverage",
        "get_plasticity_recon_command",
        "list_plasticity_observation_evidence",
        "get_plasticity_observation_command",
        "list_plasticity_probe_packages",
        "get_plasticity_probe_package",
        "list_cad_parity_report",
        "get_cad_parity_command",
    }.issubset(tool_names)
    assert "ghostforge://cad/commands" in resource_uris
    assert "ghostforge://cad/execution-contract" in resource_uris
    assert "ghostforge://cad/operation-graph-contract" in resource_uris
    assert "ghostforge://cad/fixtures" in resource_uris
    assert "ghostforge://cad/command-fixtures" in resource_uris
    assert "ghostforge://cad/behavior-cases" in resource_uris
    assert "ghostforge://cad/probe-matrix" in resource_uris
    assert "ghostforge://cad/logic-blueprint" in resource_uris
    assert "ghostforge://cad/interop-formats" in resource_uris
    assert "ghostforge://cad/development-queue" in resource_uris
    assert "ghostforge://cad/automation-runbook" in resource_uris
    assert "ghostforge://cad/schema-drafts" in resource_uris
    assert "ghostforge://cad/schema-promotions" in resource_uris
    assert "ghostforge://cad/evidence-packets" in resource_uris
    assert "ghostforge://cad/probe-batches" in resource_uris
    assert "ghostforge://cad/live-probe-sessions" in resource_uris
    assert "ghostforge://cad/observation-templates" in resource_uris
    assert "ghostforge://cad/observation-ledger" in resource_uris
    assert "ghostforge://cad/native-handoffs" in resource_uris
    assert "ghostforge://cad/capture-campaign" in resource_uris
    assert "ghostforge://cad/selection-contracts" in resource_uris
    assert "ghostforge://cad/robustness-contracts" in resource_uris
    assert "ghostforge://cad/plasticity-recon-coverage" in resource_uris
    assert "ghostforge://cad/plasticity-observation-evidence" in resource_uris
    assert "ghostforge://cad/plasticity-probe-packages" in resource_uris
    assert "ghostforge://cad/parity-report" in resource_uris
    assert "ghostforge://cad/commands/{command_id}" in template_uris
    assert "ghostforge://cad/fixtures/{fixture_id}" in template_uris
    assert "ghostforge://cad/behavior-cases/{case_id}" in template_uris
    assert "ghostforge://cad/probe-matrix/{command_id}" in template_uris
    assert "ghostforge://cad/logic-blueprint/{pattern_id}" in template_uris
    assert "ghostforge://cad/interop-formats/{format_id}" in template_uris
    assert "ghostforge://cad/development-queue/{command_id}" in template_uris
    assert "ghostforge://cad/automation-runbook/{command_id}" in template_uris
    assert "ghostforge://cad/schema-drafts/{command_id}" in template_uris
    assert "ghostforge://cad/schema-promotions/{command_id}" in template_uris
    assert "ghostforge://cad/evidence-packets/{command_id}" in template_uris
    assert "ghostforge://cad/probe-batches/{batch_id}" in template_uris
    assert "ghostforge://cad/live-probe-sessions/{command_id}" in template_uris
    assert "ghostforge://cad/observation-templates/{command_id}" in template_uris
    assert "ghostforge://cad/observation-ledger/{command_id}" in template_uris
    assert "ghostforge://cad/native-handoffs/{command_id}" in template_uris
    assert "ghostforge://cad/capture-campaign/{command_id}" in template_uris
    assert "ghostforge://cad/selection-contracts/{command_id}" in template_uris
    assert "ghostforge://cad/robustness-contracts/{contract_id}" in template_uris
    assert "ghostforge://cad/plasticity-recon-coverage/{command_id}" in template_uris
    assert "ghostforge://cad/plasticity-observation-evidence/{command_id}" in template_uris
    assert "ghostforge://cad/plasticity-probe-packages/{command_id}" in template_uris
    assert "ghostforge://cad/parity-report/{command_id}" in template_uris


def test_list_cad_commands_exposes_contract_fields_and_filters():
    server = _server()

    payload = _call(server, "list_cad_commands", {"family": "solid"})
    assert payload["summary"]["command_count"] >= 2
    command_ids = {command["command_id"] for command in payload["commands"]}
    assert {"extrude", "fillet"}.issubset(command_ids)
    extrude = next(command for command in payload["commands"] if command["command_id"] == "extrude")
    assert extrude["selection_contract"]["subobject_kinds"]
    assert {param["name"] for param in extrude["parameter_schema"]} >= {"distance", "operation"}
    assert extrude["topology_effects"]["creates"]
    assert extrude["failure_modes"]
    assert extrude["undo_contract"]["delta_kind"] == "cad_topology_delta"

    top_level = _call(server, "list_cad_commands", {"include_relationships": False})
    assert all(
        not (command.get("alias_of") or command.get("option_of") or command.get("contextual_mode_of"))
        for command in top_level["commands"]
    )


def test_get_cad_command_and_resource_preserve_static_asset_uncertainty():
    server = _server()

    face_change = _call(server, "get_cad_command", {"command_id": "face_change_grow"})
    assert face_change["status"] == "option"
    assert face_change["option_of"] == "match_face"
    assert face_change["plasticity_reference"]["mapping_review"] == "likely_option_or_alias"

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/commands/export_mesh")))
    assert resource["command_id"] == "export_mesh"
    assert resource["status"] == "controlled_probe_needed"
    assert {option["name"] for option in resource["format_options"]} == {
        "angle_tolerance",
        "inflect",
        "max_width",
    }


def test_cad_preflight_tool_exposes_native_execution_contract():
    server = _server()

    payload = _call(
        server,
        "preflight_cad_command",
        {
            "command_id": "transform",
            "selection_items": [
                {
                    "object_id": "mesh_cube",
                    "object_kind": "mesh",
                    "selection_kind": "object",
                    "topology_id": "mesh_cube",
                }
            ],
            "active_object_id": "mesh_cube",
        },
    )
    assert payload["runtime_dependency"] == "none"
    assert payload["plasticity_role"] == "development_evidence_only"
    assert payload["preflight"]["ok"] is True
    assert payload["preview_result"]["status"] == "preview_ready"
    assert payload["context"]["parameters"][2]["name"] == "scale"

    blocked = _call(
        server,
        "preflight_cad_command",
        {"command_id": "extrude", "selection_items": [], "active_object_id": None},
    )
    assert blocked["preflight"]["ok"] is False
    assert "selection.count_below_minimum" in {
        failure["code"] for failure in blocked["preflight"]["failures"]
    }
    assert "parameter.distance.required" in {
        failure["code"] for failure in blocked["preflight"]["failures"]
    }

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/execution-contract")))
    assert "record_topology_delta_undo_and_manifest" in resource["stages"]
    assert resource["runtime_dependency"] == "none"


def test_cad_operation_graph_validation_tool_accepts_descriptor_backed_graph():
    server = _server()

    payload = _call(
        server,
        "validate_cad_operation_graph",
        {"graph": _transform_graph_payload()},
    )

    assert payload["runtime_dependency"] == "none"
    assert payload["plasticity_role"] == "development_evidence_only"
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["status"] == "valid"
    assert payload["summary"]["replay_step_count"] == 1
    assert payload["validation"]["replay_plan"][0]["node_id"] == "n_transform"
    assert payload["validation"]["replay_plan"][0]["parameter_snapshot"]["translate"] == [1.0, 0.0, 0.0]

    contract = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/operation-graph-contract"))
    )
    assert contract["runtime_dependency"] == "none"
    assert contract["input_contract"]["tool"] == "validate_cad_operation_graph"
    assert contract["execution_contract"]["tool"] == "execute_cad_operation_graph"
    assert contract["execution_contract"]["mutation"] == "writes_output_mesh_and_asset_manifest"
    assert contract["execution_contract"]["required_arguments"] == ["graph", "output_dir"]
    assert "input_mesh_path" in contract["execution_contract"]["optional_arguments"]
    assert "commands_exist_in_descriptor_registry" in contract["validation_gates"]


def test_cad_operation_graph_validation_tool_returns_ai_repair_diagnostics():
    server = _server()

    payload = _call(
        server,
        "validate_cad_operation_graph",
        {
            "graph": _transform_graph_payload(
                parameters={"translate": [0.0, 0.0, 0.0], "imaginary_slider": 7}
            )
        },
    )

    assert payload["summary"]["ok"] is False
    assert payload["summary"]["status"] == "invalid"
    assert payload["summary"]["error_count"] >= 1
    assert payload["summary"]["replay_step_count"] == 0
    diagnostics = {diagnostic["code"]: diagnostic for diagnostic in payload["validation"]["diagnostics"]}
    assert "parameter.unknown" in diagnostics
    assert diagnostics["parameter.unknown"]["node_id"] == "n_transform"
    assert diagnostics["parameter.unknown"]["repair_suggestions"]


def test_cad_operation_graph_execution_tool_writes_mesh_manifest_and_lineage(tmp_path):
    server = _server()
    input_mesh = _cube_mesh(tmp_path / "cube.glb")
    output_dir = tmp_path / "cad_exec"

    payload = _call(
        server,
        "execute_cad_operation_graph",
        {
            "graph": _transform_graph_payload(parameters={"translate": [1.0, 0.0, 0.0]}),
            "input_mesh_path": str(input_mesh),
            "output_dir": str(output_dir),
            "output_format": "glb",
            "asset_id": "mcp_cad_exec",
        },
    )

    assert payload["runtime_dependency"] == "none"
    assert payload["plasticity_role"] == "development_evidence_only"
    assert payload["mutation"] == "writes_output_mesh_and_asset_manifest"
    assert payload["status"] == "succeeded"
    assert Path(payload["output_mesh_path"]).exists()
    assert Path(payload["manifest_path"]).exists()
    assert payload["mesh_quality_report"]["topology_lineage_record_count"] == 1
    assert "lineage:n_transform" in payload["graph"]["topology_table"]
    assert payload["artifact_manifest"]["asset_id"] == "mcp_cad_exec"
    assert payload["artifact_manifest"]["custom"]["cad_execution"]["step_count"] == 1


def test_cad_operation_graph_execution_tool_runs_source_box_without_input_mesh(tmp_path):
    server = _server()
    output_dir = tmp_path / "cad_box_exec"

    payload = _call(
        server,
        "execute_cad_operation_graph",
        {
            "graph": _create_box_graph_payload(),
            "output_dir": str(output_dir),
            "output_format": "glb",
            "asset_id": "mcp_cad_box_exec",
        },
    )

    assert payload["status"] == "succeeded"
    assert payload["mutation"] == "writes_output_mesh_and_asset_manifest"
    assert Path(payload["output_mesh_path"]).exists()
    assert Path(payload["manifest_path"]).exists()
    assert payload["mesh_quality_report"]["vertex_count"] == 8
    assert payload["steps"][0]["topology_delta"]["lineage"][0]["relation"] == "created"
    assert payload["graph"]["entity_table"]["box_mesh"]["producing_node_id"] == "n_box"
    assert payload["artifact_manifest"]["asset_id"] == "mcp_cad_box_exec"


def test_cad_fixture_tools_expose_named_topology_and_selection_sets():
    server = _server()

    payload = _call(server, "list_cad_fixtures", {"geometry_kind": "mesh"})
    fixture_ids = {fixture["fixture_id"] for fixture in payload["fixtures"]}
    assert {"fixture_cube_mesh", "fixture_degenerate_mesh"}.issubset(fixture_ids)
    assert payload["summary"]["fixture_count"] == 2

    cube = _call(server, "get_cad_fixture", {"fixture_id": "fixture_cube_mesh"})
    assert cube["named_topology"]["faces"]["top"] == 0
    assert {"object", "top_face", "vertical_edge"}.issubset(
        {selection["selection_id"] for selection in cube["selection_sets"]}
    )

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/fixtures/fixture_cube_solid")))
    assert resource["named_topology"]["faces"]["top"] == "F_top"


def test_cad_fixture_expectations_link_commands_to_behavior_contracts():
    server = _server()

    payload = _call(server, "list_cad_command_fixture_expectations", {"command_id": "delete_selection"})
    assert payload["summary"]["commands_with_expectations"] == ["delete_selection"]
    expectation = payload["expectations"][0]
    assert expectation["fixture_id"] == "fixture_cube_mesh"
    assert expectation["selection_id"] == "top_face"
    assert "delete.all_geometry" in expectation["expected_failures"]
    assert expectation["expected_topology"]["expected_count_deltas"]["faces"] == "<0"

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/command-fixtures")))
    assert "transform" in resource["summary"]["commands_with_expectations"]
    assert "export_mesh" in resource["summary"]["commands_with_expectations"]


def test_cad_behavior_cases_expose_fixture_level_modeling_logic():
    server = _server()

    payload = _call(server, "list_cad_behavior_cases", {"command_id": "fillet"})
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["plasticity_role"] == "development_evidence_only"
    assert payload["summary"]["filtered_case_count"] == 1
    case = payload["cases"][0]
    assert case["case_id"] == "fillet_top_front_edge_blend_lineage"
    assert "blend face id is created" in case["topology_naming_assertions"]
    assert "radius_too_large" in {probe["probe_id"] for probe in case["failure_probes"]}

    export_case = _call(
        server,
        "get_cad_behavior_case",
        {"case_id": "export_mesh_cube_glb_preserves_source"},
    )
    assert export_case["automation"]["file_touching"] is True
    assert "source_topology_preserved" in export_case["automation"]["required_evidence"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/behavior-cases/xnurbs_boundary_contextual_surface_probe"))
    )
    assert resource["result_state"] == "relationship_owner_required"
    assert "surface_patch.wrong_side_count" in {
        probe["expected_failure_code"] for probe in resource["failure_probes"]
    }


def test_cad_probe_matrix_exposes_recon_gaps_and_automation_routes():
    server = _server()

    payload = _call(server, "list_cad_probe_matrix")
    assert payload["summary"]["static_asset_plan_count"] == 4
    assert payload["summary"]["format_plan_count"] == 6
    assert payload["summary"]["command_readiness_bucket_counts"]["palette_confirmation"] == 2

    export_mesh = _call(server, "get_cad_command_probe_plan", {"command_id": "export_mesh"})
    assert export_mesh["priority"] == "critical"
    assert {"angle_tolerance", "inflect", "max_width"}.issubset(
        set(export_mesh["option_panel_targets"])
    )
    assert any(step["tool"] == "plasticity_palette_search_probe" for step in export_mesh["automation_route"])
    assert any(step["requires_disposable_fixture"] for step in export_mesh["automation_route"])

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/probe-matrix/fillet")))
    assert resource["command_id"] == "fillet"
    assert "blend_face_ids" in resource["topology_naming_targets"]
    assert "radius_too_large" in resource["failure_mode_targets"]


def test_cad_logic_blueprint_exposes_native_ghostforge_modeling_logic():
    server = _server()

    payload = _call(server, "list_cad_logic_blueprint", {"command_id": "export_mesh"})
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["plasticity_role"] == "development_evidence_only"
    pattern_ids = {pattern["pattern_id"] for pattern in payload["patterns"]}
    assert {
        "descriptor_driven_command_pipeline",
        "export_import_format_pipeline",
        "static_asset_classification",
    }.issubset(pattern_ids)

    pattern = _call(server, "get_cad_logic_pattern", {"pattern_id": "topology_identity_and_lineage"})
    assert "Record split, merge, delete, replace, and create relationships." in pattern["topology_logic"]

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/logic-blueprint/export_import_format_pipeline")))
    assert "resolve_format_options" in {stage["stage_id"] for stage in resource["command_pipeline"]}


def test_cad_interop_formats_expose_native_format_option_contracts():
    server = _server()

    payload = _call(server, "list_cad_interop_formats", {"direction": "export"})
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["plasticity_role"] == "development_evidence_only"
    assert payload["summary"]["filtered_format_count"] == 6
    assert "mesh_export" in {descriptor["format_id"] for descriptor in payload["formats"]}

    mesh_export = _call(server, "get_cad_interop_format", {"format_id": "mesh_export"})
    option_names = {option["name"] for option in mesh_export["option_schema"]}
    assert {"angle_tolerance", "inflect", "max_width", "overwrite_policy"}.issubset(option_names)
    assert "source_topology_unchanged" in mesh_export["verification_gates"]

    resource = _resource_payload(asyncio.run(server.read_resource("ghostforge://cad/interop-formats/step_stp")))
    assert resource["family"] == "brep"
    assert {"heal_geometry", "step_schema"}.issubset(
        {option["name"] for option in resource["option_schema"]}
    )


def test_cad_development_queue_maps_recon_evidence_to_ghostforge_work(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "id": "fillet",
                        "label": "Fillet",
                        "categories": ["solid_modeling"],
                        "palette_queries": ["fillet"],
                        "reachability": "observed_palette",
                    },
                    {
                        "id": "face_change",
                        "label": "Face Change",
                        "categories": ["surface_modeling"],
                        "reachability": "reviewed_no_visible_match",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
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
                        "mcp_route": [
                            {"tool": "parameter_probe_session", "arguments": {"command_id": "fillet"}}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
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
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
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
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    (tmp_path / "static_command_mapping_review.json").write_text(
        json.dumps(
            {
                "recommended_batches": {
                    "review_as_option_or_alias": [
                        {
                            "command_id": "face_change",
                            "mapping_status": "likely_option_or_alias",
                            "candidate_existing_commands": [{"command_id": "match_face"}],
                            "static_operation_evidence": {
                                "inferred_options": ["grow"],
                                "evidence_assets": ["face-change-grow.png"],
                            },
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_development_queue",
        {"kb_root": str(tmp_path), "implementation_track": "static_asset_resolution"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_task_count"] == 1
    assert payload["tasks"][0]["command_id"] == "face_change"
    assert "static_asset.owner_unresolved" in payload["tasks"][0]["blockers"]

    fillet = _call(
        server,
        "get_cad_development_task",
        {"kb_root": str(tmp_path), "command_id": "fillet"},
    )
    assert fillet["implementation_track"] == "solid_modeling_kernel"
    assert fillet["template_parameters"] == ["radius", "continuity"]
    assert "parameter_probe_session" in fillet["automation_tools"]


def test_cad_automation_runbook_exposes_safety_gates_and_evidence(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {"id": "export_mesh", "label": "Export Mesh", "categories": ["file_io"]},
                    {"id": "face_change", "label": "Face Change", "categories": ["surface_modeling"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "destructive_or_file_touching": True,
                        "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "missing_template_parameters": ["path", "format"],
                        "reset_verified": False,
                    },
                    {
                        "command_id": "face_change",
                        "label": "Face Change",
                        "schema_status": "template_inferred_needs_probe",
                        "priority": "critical",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "missing_template_parameters": ["grow"],
                        "reset_verified": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "parameters_to_observe": [{"name": "path", "type": "filesystem_path"}],
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
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "evidence_capture_plan": {
                            "parameter_names_to_resolve": ["path", "format"],
                            "required_evidence": ["file_dialog_or_options_screenshot", "workspace_path_file_record"],
                        },
                        "fixture": {
                            "fixture": "temporary_export_output_path",
                            "reset_steps": ["Remove only files inside knowledge_base/fixtures/exports."],
                            "safety_notes": ["Use workspace-controlled paths."],
                            "state_requirements": ["output_path"],
                        },
                        "invocation_plan": {"preferred_invocation": "requires_runtime_probe"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(
        json.dumps(
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
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_automation_runbook",
        {"kb_root": str(tmp_path), "route_kind": "file_interop_probe"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_route_count"] == 1
    assert payload["routes"][0]["command_id"] == "export_mesh"
    assert payload["routes"][0]["live_execution_allowed"] is True
    assert "artifact_or_translator_diagnostics" in payload["routes"][0]["evidence"]["required"]

    face_change = _call(
        server,
        "get_cad_automation_route",
        {"kb_root": str(tmp_path), "command_id": "face_change"},
    )
    assert face_change["route_kind"] == "static_owner_probe"
    assert face_change["live_execution_allowed"] is False
    assert "owner_command_resolution" in [
        gate["gate_id"]
        for gate in face_change["safety_gates"]
        if gate["status"] == "missing"
    ]


def test_cad_schema_drafts_expose_parameter_and_option_panel_candidates(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {"id": "fillet", "label": "Fillet", "categories": ["solid_modeling"]},
                    {"id": "export_mesh", "label": "Export Mesh", "categories": ["file_io"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "priority": "high",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
                    },
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "destructive_or_file_touching": True,
                        "mcp_route": [{"tool": "plasticity_palette_search_probe", "arguments": {}}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "schema_status": "template_inferred_needs_probe",
                        "priority": "high",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
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
                        "missing_template_parameters": ["path", "format"],
                        "reset_verified": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "parameters_to_observe": [
                            {"name": "radius", "type": "number"},
                            {"name": "continuity", "type": "enum"},
                        ],
                        "validation_checks": ["before_screenshot_captured"],
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
                        ],
                        "validation_checks": ["workspace_controlled_path_used"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({"recommended_batches": {}}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_schema_drafts",
        {"kb_root": str(tmp_path), "implementation_track": "file_interop"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_draft_count"] == 1
    assert payload["drafts"][0]["command_id"] == "export_mesh"
    assert "file_options" in {group["group_id"] for group in payload["drafts"][0]["option_panel_groups"]}

    fillet = _call(server, "get_cad_schema_draft", {"kb_root": str(tmp_path), "command_id": "fillet"})
    radius = next(parameter for parameter in fillet["parameter_drafts"] if parameter["name"] == "radius")
    assert radius["ui_control"] == "numeric_input"
    assert radius["unit"] == "scene_units"
    assert fillet["parameter_specs"][0]["ui"]["draft_status"] == "inferred_from_recon_template"


def test_cad_schema_promotions_expose_observed_evidence_gates(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "id": "fillet",
                        "label": "Fillet",
                        "categories": ["solid_modeling"],
                        "palette_queries": ["Fillet"],
                        "reachability": "observed_palette",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
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
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "schema_status": "observed_schema",
                        "priority": "high",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "observed_parameter_count": 1,
                        "template_parameter_count": 1,
                        "missing_template_parameters": [],
                        "evidence_screenshots": ["baseline_screenshot", "panel_screenshot", "reset_screenshot"],
                        "reset_verified": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "schema_status": "observed_schema",
                        "reachability": "observed_palette",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "parameters_to_observe": [{"name": "radius", "type": "number"}],
                        "validation_checks": ["panel_controls_mapped"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "command_id": "fillet",
                        "label": "Fillet",
                        "evidence_capture_plan": {
                            "parameter_names_to_resolve": ["radius"],
                            "required_evidence": ["baseline_screenshot", "panel_screenshot", "reset_screenshot"],
                            "validation_checks": ["panel_controls_mapped"],
                        },
                        "fixture": {
                            "fixture": "fixture_cube_solid",
                            "setup_steps": ["Open disposable cube fixture."],
                            "reset_steps": ["Undo and verify fixture."],
                        },
                        "observation_record_template": {
                            "observed_parameters": [
                                {
                                    "name": "radius",
                                    "type": "number",
                                    "observed_control": "numeric_input",
                                    "confidence": "high",
                                    "value_or_options": 0.05,
                                }
                            ],
                            "validation_results": [
                                {"check": "panel_controls_mapped", "passed": True, "evidence": "panel_screenshot"}
                            ],
                            "schema_status": "observed_schema",
                            "reset_verified": True,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({"recommended_batches": {}}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_schema_promotions",
        {"kb_root": str(tmp_path), "promotion_status": "promotable_to_descriptor"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_candidate_count"] == 1
    assert payload["candidates"][0]["command_id"] == "fillet"

    fillet = _call(server, "get_cad_schema_promotion", {"kb_root": str(tmp_path), "command_id": "fillet"})
    assert fillet["promotion_status"] == "promotable_to_descriptor"
    assert fillet["parameter_specs"][0]["name"] == "radius"
    assert fillet["parameter_specs"][0]["ui"]["source"] == "plasticity_observed_schema"


def test_cad_evidence_packets_expose_live_probe_capture_contracts():
    server = _server()

    payload = _call(
        server,
        "list_cad_evidence_packets",
        {"packet_kind": "file_interop_packet", "readiness": "ready_to_capture"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_packet_count"] >= 1
    assert any(packet["command_id"] == "export_mesh" for packet in payload["packets"])

    export_mesh = _call(server, "get_cad_evidence_packet", {"command_id": "export_mesh"})
    assert export_mesh["packet_kind"] == "file_interop_packet"
    assert export_mesh["file_artifact_required"] is True
    assert "file_artifact" in export_mesh["required_section_ids"]
    assert "workspace_path_file_record" in export_mesh["required_evidence"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/evidence-packets/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"
    assert resource["readiness"] == "ready_to_capture"


def test_cad_probe_batches_order_live_recon_work():
    server = _server()

    payload = _call(
        server,
        "list_cad_probe_batches",
        {"batch_kind": "ready_live_capture", "packet_kind": "file_interop_packet"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_batch_count"] == 1
    batch = payload["batches"][0]
    assert batch["batch_id"] == "ready_live_capture:file_interop_packet"
    assert batch["live_execution_allowed"] is True
    assert batch["commands"][0]["command_id"] == "export_mesh"
    assert "file_artifact_record" in batch["required_outputs"]

    static_batch = _call(
        server,
        "get_cad_probe_batch",
        {"batch_id": "static_owner_resolution:static_owner_packet"},
    )
    assert static_batch["live_execution_allowed"] is False
    assert static_batch["commands"][0]["static_owner_required"] is True
    assert "owner_command_resolution" in static_batch["required_safety_gates"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/probe-batches/ready_live_capture:file_interop_packet"))
    )
    assert resource["batch_id"] == "ready_live_capture:file_interop_packet"


def test_cad_live_probe_sessions_expand_batches_into_steps():
    server = _server()

    payload = _call(
        server,
        "list_cad_live_probe_sessions",
        {"session_mode": "ready_for_manual_live_capture", "packet_kind": "file_interop_packet"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_session_count"] >= 1
    assert any(session["command_id"] == "export_mesh" for session in payload["sessions"])

    export_mesh = _call(server, "get_cad_live_probe_session", {"command_id": "export_mesh"})
    assert export_mesh["session_mode"] == "ready_for_manual_live_capture"
    assert export_mesh["batch_id"] == "ready_live_capture:file_interop_packet"
    step_ids = [step["step_id"] for step in export_mesh["steps"]]
    assert step_ids[:5] == [
        "guard_preflight",
        "prepare_fixture",
        "capture_baseline",
        "invoke_command_panel",
        "capture_parameters",
    ]
    assert "capture_file_artifact" in step_ids
    assert "workspace_controlled_path" in export_mesh["required_safety_gates"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/live-probe-sessions/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"


def test_cad_capture_campaign_prioritizes_next_recon_actions():
    server = _server()

    payload = _call(
        server,
        "list_cad_capture_campaign",
        {"status": "ready_to_capture", "packet_kind": "file_interop_packet"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_item_count"] >= 1
    assert any(item["command_id"] == "export_mesh" for item in payload["items"])

    export_mesh = _call(server, "get_cad_capture_campaign_command", {"command_id": "export_mesh"})
    assert export_mesh["status"] == "ready_to_capture"
    assert export_mesh["ledger_filename"] == "cad_live_observation_records.json"
    assert "workspace_controlled_path" in export_mesh["required_safety_gates"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/capture-campaign/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"


def test_cad_observation_templates_and_validation_gate_completed_captures():
    server = _server()

    payload = _call(
        server,
        "list_cad_observation_templates",
        {"session_mode": "ready_for_manual_live_capture"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_template_count"] >= 1
    assert any(template["command_id"] == "export_mesh" for template in payload["templates"])

    template = _call(server, "get_cad_observation_template", {"command_id": "export_mesh"})
    assert template["command_id"] == "export_mesh"
    assert {section["section_id"] for section in template["captured_sections"]} >= {
        "parameter_panel",
        "file_artifact",
        "reset_verification",
    }

    observation = {
        **template,
        "plasticity_version": "26.1.3",
        "captured_sections": [
            {
                **section,
                "status": "captured",
                "evidence_refs": [f"{section['section_id']}.png"],
                "fields": {"captured": True},
            }
            for section in template["captured_sections"]
        ],
        "observed_controls": [
            {
                **control,
                "control_type": "dropdown",
                "current_value": "captured",
                "confidence": "high",
                "evidence_refs": ["file_dialog_or_options_screenshot"],
            }
            for control in template["observed_controls"]
        ],
        "validation_results": [
            {
                "check_id": "workspace_controlled_path_used",
                "passed": True,
                "evidence_refs": ["workspace_path_file_record"],
            }
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
    report = _call(
        server,
        "validate_cad_observation_record",
        {"observation_record": observation},
    )
    assert report["status"] == "accepted_for_promotion"
    assert "schema_promotion" in report["promotion_targets"]
    assert "interop_contract" in report["promotion_targets"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/observation-templates/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"


def test_cad_observation_ledger_loads_validated_capture_records(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "id": "export_mesh",
                        "label": "Export Mesh",
                        "categories": ["file_io"],
                        "palette_queries": ["Export Mesh"],
                        "reachability": "observed_palette",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "destructive_or_file_touching": True,
                        "missing_parameter_count": 2,
                        "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "export_mesh"}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "observed_parameter_count": 0,
                        "template_parameter_count": 2,
                        "missing_template_parameters": ["path", "format"],
                        "evidence_screenshots": [],
                        "reset_verified": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
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
                        "validation_checks": ["workspace_controlled_path_used"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(
        json.dumps(
            {
                "packages": [
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
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({"recommended_batches": {}}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()
    template = _call(server, "get_cad_observation_template", {"kb_root": str(tmp_path), "command_id": "export_mesh"})
    record = {
        **template,
        "plasticity_version": "26.1.3",
        "captured_sections": [
            {
                **section,
                "status": "captured",
                "evidence_refs": [f"{section['section_id']}.png"],
                "fields": {"captured": True},
            }
            for section in template["captured_sections"]
        ],
        "observed_controls": [
            {
                **control,
                "control_type": "dropdown",
                "current_value": "captured",
                "confidence": "high",
                "evidence_refs": ["file_dialog_or_options_screenshot"],
            }
            for control in template["observed_controls"]
        ],
        "validation_results": [
            {"check_id": "workspace_controlled_path_used", "passed": True, "evidence_refs": ["workspace_path_file_record"]}
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
    (tmp_path / "cad_live_observation_records.json").write_text(json.dumps({"records": [record]}), encoding="utf-8")

    payload = _call(
        server,
        "list_cad_observation_ledger",
        {"kb_root": str(tmp_path), "promotion_target": "schema_promotion"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["record_count"] == 1
    assert payload["summary"]["filtered_entry_count"] == 1
    assert payload["entries"][0]["validation"]["status"] == "accepted_for_promotion"

    command = _call(
        server,
        "get_cad_observation_ledger_command",
        {"kb_root": str(tmp_path), "command_id": "export_mesh"},
    )
    assert command["entry_count"] == 1
    assert command["latest"]["validation"]["promotion_targets"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/observation-ledger/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"
    assert "entry_count" in resource


def test_cad_native_handoffs_translate_validated_observations_into_work(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "id": "export_mesh",
                        "label": "Export Mesh",
                        "categories": ["file_io"],
                        "palette_queries": ["Export Mesh"],
                        "reachability": "observed_palette",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "destructive_or_file_touching": True,
                        "missing_parameter_count": 2,
                        "mcp_route": [{"tool": "parameter_probe_session", "arguments": {"command_id": "export_mesh"}}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "observed_parameter_count": 0,
                        "template_parameter_count": 2,
                        "missing_template_parameters": ["path", "format"],
                        "evidence_screenshots": [],
                        "reset_verified": False,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
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
                        "validation_checks": ["workspace_controlled_path_used"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(
        json.dumps(
            {
                "packages": [
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
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({"recommended_batches": {}}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()
    template = _call(server, "get_cad_observation_template", {"kb_root": str(tmp_path), "command_id": "export_mesh"})
    record = {
        **template,
        "plasticity_version": "26.1.3",
        "captured_sections": [
            {
                **section,
                "status": "captured",
                "evidence_refs": [f"{section['section_id']}.png"],
                "fields": {"captured": True},
            }
            for section in template["captured_sections"]
        ],
        "observed_controls": [
            {
                **control,
                "control_type": "dropdown",
                "current_value": "captured",
                "confidence": "high",
                "evidence_refs": ["file_dialog_or_options_screenshot"],
            }
            for control in template["observed_controls"]
        ],
        "validation_results": [
            {"check_id": "workspace_controlled_path_used", "passed": True, "evidence_refs": ["workspace_path_file_record"]}
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
    (tmp_path / "cad_live_observation_records.json").write_text(json.dumps({"records": [record]}), encoding="utf-8")

    payload = _call(
        server,
        "list_cad_native_handoffs",
        {"kb_root": str(tmp_path), "handoff_status": "ready_for_native_application"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_handoff_count"] == 1
    assert payload["handoffs"][0]["command_id"] == "export_mesh"
    assert "apply_descriptor_schema" in {step["step_id"] for step in payload["handoffs"][0]["steps"]}

    command = _call(server, "get_cad_native_handoff_command", {"kb_root": str(tmp_path), "command_id": "export_mesh"})
    assert command["handoff_count"] == 1
    assert command["latest"]["next_action"] == "implement handoff step: apply_descriptor_schema"

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/native-handoffs/export_mesh"))
    )
    assert resource["command_id"] == "export_mesh"
    assert "handoff_count" in resource


def test_cad_selection_contracts_expose_modes_and_state_transitions(tmp_path):
    (tmp_path / "command_recon_index.json").write_text(
        json.dumps(
            {
                "commands": [
                    {"id": "selection_mode_set_edge", "label": "Selection mode: set edge", "categories": ["selection_modes"]},
                    {"id": "selection_convert_to_faces", "label": "Selection: convert to faces", "categories": ["selection_modes"]},
                    {"id": "grid_toggle_grid_snapping", "label": "Grid: toggle grid snapping", "categories": ["snapping_planes"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "command_id": "selection_mode_set_edge",
            "label": "Selection mode: set edge",
            "probe_kind": "selection_or_snapping_state_probe",
            "fixture": "neutral_document_session",
            "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
        },
        {
            "command_id": "selection_convert_to_faces",
            "label": "Selection: convert to faces",
            "probe_kind": "selection_or_snapping_state_probe",
            "fixture": "neutral_document_session",
            "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
        },
        {
            "command_id": "grid_toggle_grid_snapping",
            "label": "Grid: toggle grid snapping",
            "probe_kind": "selection_or_snapping_state_probe",
            "fixture": "neutral_document_session",
            "mcp_route": [{"tool": "parameter_probe_session", "arguments": {}}],
        },
    ]
    (tmp_path / "parameter_observation_readiness.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        **row,
                        "schema_status": "template_inferred_needs_probe",
                        "priority": "medium",
                        "missing_template_parameters": ["selection_filter"],
                        "reset_verified": False,
                    }
                    for row in rows
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "command_id": row["command_id"],
                        "label": row["label"],
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": row["probe_kind"],
                        "fixture": row["fixture"],
                        "parameters_to_observe": [{"name": "selection_filter", "type": "enum"}],
                    }
                    for row in rows
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_packages.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({"recommended_batches": {}}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_selection_contracts",
        {"kb_root": str(tmp_path), "operation_kind": "convert_selection"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["filtered_command_count"] == 1
    assert payload["commands"][0]["command_id"] == "selection_convert_to_faces"
    assert "face" in payload["modes"][2]["selection_kinds"] or any(mode["mode_id"] == "face" for mode in payload["modes"])

    edge = _call(
        server,
        "get_cad_selection_command",
        {"kb_root": str(tmp_path), "command_id": "selection_mode_set_edge"},
    )
    assert edge["operation_kind"] == "set_mode"
    assert edge["output_modes"] == ["edge"]
    assert "selection_filter.mode=edge" in edge["expected_state_delta"]


def test_cad_robustness_contracts_expose_topology_tolerance_and_failures():
    server = _server()

    payload = _call(
        server,
        "list_cad_robustness_contracts",
        {"subject_type": "cad_command", "has_topology_policy": "face_identity"},
    )
    assert payload["summary"]["runtime_dependency"] == "none"
    assert payload["summary"]["plasticity_role"] == "development_evidence_only"
    assert payload["summary"]["filtered_contract_count"] >= 1
    assert payload["topology_policies"]
    assert payload["failure_contracts"]
    assert payload["tolerance_contracts"]

    fillet = _call(server, "get_cad_robustness_contract", {"contract_id": "fillet"})
    assert fillet["contract_id"] == "command:fillet"
    assert "fillet.radius_too_large" in fillet["failure_codes"]
    assert any(policy["policy_id"] == "edge_boundary_identity" for policy in fillet["topology_policies"])
    assert fillet["tolerance_contracts"]

    resource = _resource_payload(
        asyncio.run(server.read_resource("ghostforge://cad/robustness-contracts/mesh_export"))
    )
    assert resource["contract_id"] in {"command:export_mesh", "format:mesh_export"}
    assert resource["failure_contracts"]


def test_plasticity_recon_coverage_tool_loads_external_readiness_rows(tmp_path):
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-06-01T14:08:16+00:00",
                "basis": {"command_count": 2},
                "bucket_counts": {"palette_confirmation": 1, "fixture_required": 1},
                "summary": {"command_count": 2},
                "operating_sequence": ["Confirm static-only commands."],
                "recommended_batches": {
                    "palette_confirmation": [
                        {
                            "command_id": "export_mesh",
                            "label": "Export Mesh",
                            "readiness_bucket": "palette_confirmation",
                            "stage": "static_inferred_needs_palette_confirmation",
                            "priority": "critical",
                            "probe_kind": "file_dialog_or_export_options_probe",
                            "fixture": "temporary_export_output_path",
                            "next_tool": "plasticity_palette_search_probe",
                            "missing_parameter_count": 6,
                            "mcp_route": [
                                {
                                    "tool": "plasticity_palette_search_probe",
                                    "arguments": {"query": "Export Mesh"},
                                }
                            ],
                        }
                    ],
                    "fixture_required": [
                        {
                            "command_id": "fillet",
                            "label": "Fillet",
                            "readiness_bucket": "fixture_required",
                            "stage": "palette_reachable_needs_parameter_probe",
                            "priority": "high",
                            "probe_kind": "geometry_operation_parameter_panel_probe",
                            "fixture": "fixture_cube_solid",
                            "next_tool": "parameter_probe_session",
                            "missing_parameter_count": 9,
                            "mcp_route": [
                                {
                                    "tool": "parameter_probe_session",
                                    "arguments": {"command_id": "fillet", "mode": "plan"},
                                }
                            ],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(
        json.dumps({"status_counts": {"controlled_probe_needed": 2}}),
        encoding="utf-8",
    )
    (tmp_path / "plasticity_file_format_map.json").write_text(
        json.dumps({"formats": {"mesh_export": {}, "step_stp": {}}}),
        encoding="utf-8",
    )
    (tmp_path / "goal_progress_audit.json").write_text(
        json.dumps({"requirements": [{"status": "partial"}]}),
        encoding="utf-8",
    )
    server = _server()

    payload = _call(
        server,
        "list_plasticity_recon_coverage",
        {"kb_root": str(tmp_path), "readiness_bucket": "palette_confirmation"},
    )
    assert payload["summary"]["loaded_command_count"] == 2
    assert payload["summary"]["filtered_command_count"] == 1
    assert payload["summary"]["commands_with_automation_routes"] == 2
    assert payload["summary"]["static_mapping_status_counts"] == {"controlled_probe_needed": 2}
    assert payload["format_families"] == ["mesh_export", "step_stp"]
    assert payload["commands"][0]["command_id"] == "export_mesh"

    command = _call(
        server,
        "get_plasticity_recon_command",
        {"kb_root": str(tmp_path), "command_id": "fillet"},
    )
    assert command["next_tool"] == "parameter_probe_session"
    assert command["mcp_route"][0]["arguments"]["command_id"] == "fillet"


def test_plasticity_observation_evidence_tool_separates_ledger_template_and_session(tmp_path):
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "basis": {"observation_count": 0, "template_count": 1},
                "commands": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "observed_parameter_count": 0,
                        "template_parameter_count": 3,
                        "missing_template_parameters": ["format", "tolerance", "path"],
                        "reset_verified": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps(
            {
                "generated_utc": "2026-06-01T14:08:16+00:00",
                "basis": {"command_count": 1},
                "schema_status_counts": {"template_inferred_needs_probe": 1},
                "template_groups": {"file_io_parameter_panels": ["export_mesh"]},
                "fixture_counts": {"temporary_export_output_path": 1},
                "probe_kind_counts": {"file_dialog_or_export_options_probe": 1},
                "templates": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "parameters_to_observe": [
                            {"name": "format", "type": "enum"},
                            {"name": "tolerance", "type": "float"},
                        ],
                        "validation_checks": ["format_options_detected"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_session_last.json").write_text(
        json.dumps(
            {
                "command_id": "export_mesh",
                "mode": "plan",
                "executed": False,
                "package": {
                    "evidence_capture_plan": {
                        "parameter_names_to_resolve": ["format", "tolerance"],
                        "required_evidence": ["file_dialog_or_options_screenshot"],
                        "validation_checks": ["format_options_detected"],
                    },
                    "invocation_plan": {"reset_steps": ["Close dialog"]},
                },
            }
        ),
        encoding="utf-8",
    )
    server = _server()

    payload = _call(
        server,
        "list_plasticity_observation_evidence",
        {"kb_root": str(tmp_path), "probe_kind": "file_dialog_or_export_options_probe"},
    )
    assert payload["summary"]["ledger_command_count"] == 1
    assert payload["summary"]["filtered_command_count"] == 1
    assert payload["summary"]["template_only_count"] == 1
    assert payload["latest_session"]["command_id"] == "export_mesh"
    assert payload["latest_session"]["parameter_names_to_resolve"] == ["format", "tolerance"]

    command = _call(
        server,
        "get_plasticity_observation_command",
        {"kb_root": str(tmp_path), "command_id": "export_mesh"},
    )
    assert command["status"]["missing_template_parameters"] == ["format", "tolerance", "path"]
    assert command["template"]["parameters_to_observe"][0]["name"] == "format"


def test_plasticity_probe_package_tool_exposes_next_executable_evidence_unit(tmp_path):
    package = {
        "command_id": "export_mesh",
        "label": "Export Mesh",
        "evidence_capture_plan": {
            "parameter_names_to_resolve": ["path", "format", "tolerance"],
            "required_evidence": ["baseline_screenshot", "file_dialog_or_options_screenshot", "workspace_path_file_record"],
            "validation_checks": ["workspace_controlled_path_used", "format_options_detected"],
        },
        "fixture": {
            "fixture": "temporary_export_output_path",
            "purpose": "Exercise export options into workspace-controlled temporary paths.",
            "setup_steps": ["Choose knowledge_base/fixtures/exports as the export destination."],
            "reset_steps": ["Remove or overwrite only files inside knowledge_base/fixtures/exports."],
            "safety_notes": ["Never export into source folders."],
            "state_requirements": ["document_session", "output_path"],
        },
        "invocation_plan": {
            "palette_queries": ["Export Mesh"],
            "preferred_invocation": "requires_runtime_probe",
            "probe_steps": ["Open the command palette.", "Capture visible options."],
            "reset_steps": ["Remove or overwrite only files inside knowledge_base/fixtures/exports."],
        },
        "observation_record_template": {
            "schema_status": "observed_partial",
            "observed_parameters": [
                {"name": "path", "type": "filesystem_path", "confidence": "medium"},
                {"name": "format", "type": "enum", "confidence": "medium"},
            ],
            "validation_results": [
                {"check": "workspace_controlled_path_used", "passed": False, "evidence": ""},
                {"check": "format_options_detected", "passed": False, "evidence": ""},
            ],
        },
    }
    (tmp_path / "parameter_probe_packages.json").write_text(
        json.dumps({"packages": [package], "basis": {"selected_count": 1}}),
        encoding="utf-8",
    )
    server = _server()

    payload = _call(
        server,
        "list_plasticity_probe_packages",
        {"kb_root": str(tmp_path), "requires_file_evidence": True},
    )
    assert payload["summary"]["package_count"] == 1
    assert payload["summary"]["filtered_package_count"] == 1
    assert payload["packages"][0]["command_id"] == "export_mesh"

    command = _call(
        server,
        "get_plasticity_probe_package",
        {"kb_root": str(tmp_path), "command_id": "export_mesh"},
    )
    assert command["parameter_names_to_resolve"] == ["path", "format", "tolerance"]
    assert command["has_workspace_safety_gate"] is True
    assert command["observation_validation_results"][1]["check"] == "format_options_detected"


def test_cad_parity_report_joins_ghostforge_contracts_with_plasticity_evidence(tmp_path):
    (tmp_path / "parameter_observation_readiness.json").write_text(
        json.dumps(
            {
                "bucket_counts": {"palette_confirmation": 1},
                "rows": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "readiness_bucket": "palette_confirmation",
                        "stage": "static_inferred_needs_palette_confirmation",
                        "priority": "critical",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "next_tool": "plasticity_palette_search_probe",
                        "missing_parameter_count": 6,
                        "mcp_route": [
                            {
                                "tool": "plasticity_palette_search_probe",
                                "arguments": {"query": "Export Mesh"},
                            }
                        ],
                    },
                    {
                        "command_id": "face_change",
                        "label": "Face Change",
                        "readiness_bucket": "palette_confirmation",
                        "stage": "static_inferred_needs_palette_confirmation",
                        "priority": "critical",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "next_tool": "plasticity_palette_search_probe",
                        "missing_parameter_count": 1,
                        "mcp_route": [
                            {
                                "tool": "plasticity_palette_search_probe",
                                "arguments": {"query": "Face Change"},
                            }
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_observation_ledger.json").write_text(
        json.dumps(
            {
                "commands": [
                    {
                        "command_id": "export_mesh",
                        "label": "Export Mesh",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "file_dialog_or_export_options_probe",
                        "fixture": "temporary_export_output_path",
                        "observed_parameter_count": 0,
                        "template_parameter_count": 6,
                        "missing_template_parameters": ["path", "format"],
                        "reset_verified": False,
                    },
                    {
                        "command_id": "face_change",
                        "label": "Face Change",
                        "schema_status": "template_inferred_needs_probe",
                        "probe_kind": "geometry_operation_parameter_panel_probe",
                        "fixture": "fixture_cube_solid",
                        "observed_parameter_count": 0,
                        "template_parameter_count": 1,
                        "missing_template_parameters": ["grow"],
                        "reset_verified": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "parameter_schema_templates.json").write_text(
        json.dumps({"templates": [], "schema_status_counts": {"template_inferred_needs_probe": 2}}),
        encoding="utf-8",
    )
    (tmp_path / "parameter_probe_session_last.json").write_text(
        json.dumps({"command_id": "export_mesh", "mode": "plan", "executed": False}),
        encoding="utf-8",
    )
    (tmp_path / "static_command_mapping_review.json").write_text(json.dumps({}), encoding="utf-8")
    (tmp_path / "plasticity_file_format_map.json").write_text(json.dumps({"formats": {}}), encoding="utf-8")
    (tmp_path / "goal_progress_audit.json").write_text(json.dumps({"requirements": []}), encoding="utf-8")
    server = _server()

    payload = _call(
        server,
        "list_cad_parity_report",
        {"kb_root": str(tmp_path), "has_blocker": "plasticity.observed_schema_missing"},
    )
    assert payload["summary"]["command_count"] >= 11
    assert payload["summary"]["filtered_command_count"] >= 1
    assert payload["summary"]["latest_session_command_id"] == "export_mesh"

    export_mesh = _call(
        server,
        "get_cad_parity_command",
        {"kb_root": str(tmp_path), "command_id": "export_mesh"},
    )
    assert export_mesh["plasticity_route_ready"] is True
    assert export_mesh["latest_session_command"] is True
    assert "ghostforge.implementation_controlled_probe_needed" in export_mesh["blockers"]
    assert export_mesh["missing_parameters"] == ["path", "format"]

    face_change = _resource_payload(
        asyncio.run(server.read_resource(f"ghostforge://cad/parity-report/face_change_grow"))
    )
    assert face_change["plasticity_command_id"] == "face_change"
    assert "plasticity.relationship_owner_unverified" in face_change["blockers"]
