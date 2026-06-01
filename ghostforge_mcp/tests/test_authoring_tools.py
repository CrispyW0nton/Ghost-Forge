"""End-to-end MCP coverage for the P11 authoring tool surface."""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
from pathlib import Path

import pytest
import trimesh


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
            try:
                return _unwrap(json.loads(text))
            except json.JSONDecodeError:
                continue
        raise AssertionError(f"no payload in {result!r}")

    for item in result:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            return _unwrap(json.loads(text))
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"no payload in {result!r}")


@pytest.fixture(autouse=True)
def isolated_data_root(monkeypatch, tmp_path):
    """Each MCP test gets its own data root so graphs don't leak."""

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


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (16, 16), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _resource_payload(result):
    content = result[0].content if isinstance(result, list) else result.content
    return json.loads(content)


def test_graph_tools_registered():
    server = _server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_operations",
        "create_edit_graph",
        "list_edit_graphs",
        "get_edit_graph",
        "delete_edit_graph",
        "append_graph_node",
        "update_graph_node",
        "remove_graph_node",
        "reorder_graph_nodes",
        "evaluate_edit_graph",
        "submit_evaluate_edit_graph",
        "compare_scene_graph_history",
    }
    missing = expected - names
    assert not missing, f"missing P11 tools: {missing}"


def test_graph_resources_registered():
    server = _server()
    resources = asyncio.run(server.list_resources())
    resource_uris = {str(resource.uri) for resource in resources}
    templates = asyncio.run(server.list_resource_templates())
    template_uris = {template.uriTemplate for template in templates}

    assert "ghostforge://operations" in resource_uris
    assert "ghostforge://graphs" in resource_uris
    assert "ghostforge://scenes" in resource_uris
    assert "ghostforge://graphs/{graph_id}" in template_uris
    assert "ghostforge://graphs/{graph_id}/evaluation" in template_uris
    assert "ghostforge://scenes/{scene_id}" in template_uris
    assert "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history" in template_uris
    assert "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/{history_id}" in template_uris
    assert (
        "ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/"
        "{left_history_id}/compare/{right_history_id}"
    ) in template_uris


def test_graph_workflow_prompts_registered_and_render():
    server = _server()
    prompts = asyncio.run(server.list_prompts())
    names = {prompt.name for prompt in prompts}

    assert {
        "generate_engine_ready_prop",
        "repair_generated_mesh_for_unity",
        "prepare_unreal_static_mesh_package",
    }.issubset(names)

    prop = asyncio.run(
        server.get_prompt(
            "generate_engine_ready_prop",
            {
                "asset_prompt": "a stylized sci-fi crate",
                "target_engine": "unity",
                "art_direction": "clean bevels, painted panels",
                "target_path": "Assets/GhostForge/Crate.glb",
            },
        )
    )
    prop_text = prop.messages[0].content.text
    assert "list_worker_capabilities" in prop_text
    assert "submit_evaluate_edit_graph" in prop_text
    assert "create_engine_export_bridge" in prop_text

    repair = asyncio.run(
        server.get_prompt(
            "repair_generated_mesh_for_unity",
            {
                "scene_id": "level_one",
                "object_id": "obj_cube",
                "history_id": "hist_123",
            },
        )
    )
    repair_text = repair.messages[0].content.text
    assert "ghostforge://scenes/level_one/objects/obj_cube/graph-history/hist_123" in repair_text
    assert "preset='unity'" in repair_text

    unreal = asyncio.run(
        server.get_prompt(
            "prepare_unreal_static_mesh_package",
            {
                "asset_dir": "C:/GhostForge/assets/crate",
                "target_path": "/Game/GhostForge/Crate",
            },
        )
    )
    unreal_text = unreal.messages[0].content.text
    assert "ghostforge_bridge_unreal.json" in unreal_text
    assert "send_to_unreal" in unreal_text


def test_list_operations_includes_builtins():
    server = _server()
    payload = _call(server, "list_operations")
    assert isinstance(payload, list)
    kinds = {op["kind"] for op in payload}
    assert {"transform", "recenter", "apply_material"}.issubset(kinds)
    image_source = next(op for op in payload if op["kind"] == "generate_image_to_3d")
    assert image_source["operation_type"] == "source"
    assert image_source["capability"] == "image_to_3d"
    assert image_source["capability_status"] in {"runnable", "stub", "missing"}
    assert any(worker["name"] == "stub_image_to_3d" for worker in image_source["workers"])
    text_source = next(op for op in payload if op["kind"] == "generate_text_to_3d")
    assert text_source["operation_type"] == "source"
    assert text_source["capability"] == "text_to_3d"
    texture = next(op for op in payload if op["kind"] == "worker_texture_mesh")
    assert texture["parameter_presets"][0]["label"] == "Realtime 1K"


def test_operation_resource_matches_tool_payload():
    server = _server()
    tool_payload = _call(server, "list_operations")
    resource_payload = _resource_payload(asyncio.run(server.read_resource("ghostforge://operations")))

    assert resource_payload["operations"][0]["kind"] == tool_payload[0]["kind"]
    assert any(op["kind"] == "worker_texture_mesh" for op in resource_payload["operations"])


def test_scene_resources_expose_graph_history_links(tmp_path):
    scene_dir = tmp_path / "project" / "scenes"
    scene_dir.mkdir(parents=True)
    scene_path = scene_dir / "level_one.gforge"
    scene_path.write_text(
        json.dumps(
            {
                "document_version": "1.0",
                "application": "Ghost Forge",
                "saved_at": "2026-06-01T10:00:00Z",
                "project_root": str(tmp_path / "project"),
                "objects": [
                    {
                        "object_id": "obj_cube",
                        "name": "Cube",
                        "path": str(tmp_path / "cube.glb"),
                        "operation_graph": {"graph_id": "obj_cube_graph"},
                        "operation_graph_history": [
                            {
                                "graph_id": "obj_cube_graph",
                                "status": "succeeded",
                                "output_path": str(tmp_path / "cube_out.glb"),
                                "duration_ms": 12.0,
                                "artifact_count": 1,
                                "audit_badge": "passed",
                                "message": "audit passed",
                                "details": {
                                    "artifact_paths": [str(tmp_path / "cube_out.glb")],
                                    "manifest_paths": [str(tmp_path / "asset_manifest.json")],
                                    "audit_history": {
                                        "preset": "unity",
                                        "status": "passed",
                                        "error_count": 0,
                                        "warning_count": 0,
                                        "audit_issue_list": [],
                                    },
                                },
                            },
                            {
                                "graph_id": "obj_cube_graph",
                                "status": "succeeded",
                                "output_path": str(tmp_path / "cube_repaired.glb"),
                                "duration_ms": 20.0,
                                "artifact_count": 3,
                                "audit_badge": "warnings",
                                "message": "audit warnings",
                                "details": {
                                    "artifact_paths": [
                                        str(tmp_path / "cube_repaired.glb"),
                                        str(tmp_path / "albedo.png"),
                                    ],
                                    "manifest_paths": [str(tmp_path / "asset_manifest.json")],
                                    "bridge_paths": [str(tmp_path / "ghostforge_bridge_unity.json")],
                                    "retarget_resolved": ["retarget.axis:axis_mismatch_assumed"],
                                    "audit_history": {
                                        "preset": "unity",
                                        "status": "warnings",
                                        "error_count": 0,
                                        "warning_count": 1,
                                        "audit_issue_list": [
                                            "warning texture:missing_metallic: Metallic texture is absent."
                                        ],
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    server = _server()

    scenes = _resource_payload(asyncio.run(server.read_resource("ghostforge://scenes")))
    assert scenes["scenes"][0]["scene_id"] == "level_one"
    assert scenes["scenes"][0]["object_count"] == 1

    scene = _resource_payload(asyncio.run(server.read_resource("ghostforge://scenes/level_one")))
    history = scene["objects"][0]["operation_graph_history"][0]
    assert history["history_id"].startswith("obj_cube_graph_succeeded_")
    assert history["mcp_links"]["graph"] == "ghostforge://graphs/obj_cube_graph"
    assert history["mcp_links"]["scene"] == "ghostforge://scenes/level_one"

    history_list = _resource_payload(
        asyncio.run(
            server.read_resource("ghostforge://scenes/level_one/objects/obj_cube/graph-history")
        )
    )
    assert history_list["history"][0]["history_id"] == history["history_id"]
    assert len(history_list["history"]) == 2

    history_item = _resource_payload(
        asyncio.run(
            server.read_resource(
                f"ghostforge://scenes/level_one/objects/obj_cube/graph-history/{history['history_id']}"
            )
        )
    )
    assert history_item["resource_uri"] == history["resource_uri"]

    left_id = history_list["history"][0]["history_id"]
    right_id = history_list["history"][1]["history_id"]
    comparison = _call(
        server,
        "compare_scene_graph_history",
        {
            "scene_id": "level_one",
            "object_id": "obj_cube",
            "left_history_id": left_id,
            "right_history_id": right_id,
        },
    )
    assert comparison["comparison"]["has_changes"]
    assert comparison["comparison"]["changed_fields"]["audit_badge"] == {
        "left": "passed",
        "right": "warnings",
    }
    assert str(tmp_path / "cube_repaired.glb") in comparison["comparison"]["detail_changes"]["artifact_paths"]["added"]
    assert comparison["comparison"]["audit_changes"]["changed_fields"]["warning_count"] == {
        "left": 0,
        "right": 1,
    }

    resource_comparison = _resource_payload(
        asyncio.run(
            server.read_resource(
                "ghostforge://scenes/level_one/objects/obj_cube/graph-history/"
                f"{left_id}/compare/{right_id}"
            )
        )
    )
    assert resource_comparison["resource_uri"] == comparison["resource_uri"]


def test_create_get_delete_graph_round_trip():
    server = _server()
    created = _call(server, "create_edit_graph", {"name": "demo"})
    gid = created["graph_id"]
    listed = _call(server, "list_edit_graphs")
    assert any(g["graph_id"] == gid for g in listed)
    fetched = _call(server, "get_edit_graph", {"graph_id": gid})
    assert fetched["graph"]["graph_id"] == gid
    assert "evaluation" not in fetched
    deleted = _call(server, "delete_edit_graph", {"graph_id": gid})
    assert deleted == {"deleted": gid}


def test_append_update_remove_node_lifecycle():
    server = _server()
    graph = _call(server, "create_edit_graph", {"name": "demo"})
    gid = graph["graph_id"]
    after_append = _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "transform", "label": "first"},
    )
    assert len(after_append["nodes"]) == 1
    node_id = after_append["nodes"][0]["id"]

    after_update = _call(
        server,
        "update_graph_node",
        {"graph_id": gid, "node_id": node_id, "label": "renamed", "enabled": False},
    )
    node = after_update["nodes"][0]
    assert node["label"] == "renamed"
    assert node["enabled"] is False

    after_remove = _call(
        server, "remove_graph_node", {"graph_id": gid, "node_id": node_id}
    )
    assert after_remove["nodes"] == []


def test_reorder_graph_nodes_round_trip():
    server = _server()
    gid = _call(server, "create_edit_graph", {"name": "ord"})["graph_id"]
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "transform", "node_id": "alpha"},
    )
    _call(
        server,
        "append_graph_node",
        {"graph_id": gid, "kind": "recenter", "node_id": "beta"},
    )
    after = _call(
        server,
        "reorder_graph_nodes",
        {"graph_id": gid, "order": ["beta", "alpha"]},
    )
    assert [n["id"] for n in after["nodes"]] == ["beta", "alpha"]


def test_evaluate_edit_graph_writes_output(tmp_path):
    cube = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    base = tmp_path / "cube.glb"
    cube.export(str(base))
    out = tmp_path / "out.glb"

    server = _server()
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "eval",
            "base_asset_path": str(base),
            "output_path": str(out),
        },
    )["graph_id"]
    _call(
        server,
        "append_graph_node",
        {
            "graph_id": gid,
            "kind": "transform",
            "params": {"translate": [1.0, 0.0, 0.0]},
        },
    )
    result = _call(server, "evaluate_edit_graph", {"graph_id": gid})
    assert result["status"] == "succeeded"
    assert result["output_path"]
    assert Path(result["output_path"]).exists()

    fetched = _call(server, "get_edit_graph", {"graph_id": gid})
    assert "evaluation" in fetched
    assert fetched["evaluation"]["status"] == "succeeded"

    resource = _resource_payload(asyncio.run(server.read_resource(f"ghostforge://graphs/{gid}")))
    assert resource["graph"]["graph_id"] == gid
    assert resource["evaluation"]["status"] == "succeeded"


def test_submit_evaluate_edit_graph_runs_as_durable_job(tmp_path, monkeypatch):
    import time

    from ghostforge_mcp import server as server_mod

    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "1")
    server_mod.reset_context_for_tests()
    server = server_mod.build_server()

    base = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(base))
    out = tmp_path / "job_out.glb"
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "job graph",
            "base_asset_path": str(base),
            "output_path": str(out),
        },
    )["graph_id"]
    _call(server, "append_graph_node", {"graph_id": gid, "kind": "recenter"})

    handle = _call(server, "submit_evaluate_edit_graph", {"graph_id": gid})

    assert handle["kind"] == "evaluate_edit_graph"
    deadline = time.monotonic() + 15
    final = handle
    while time.monotonic() < deadline:
        final = _call(server, "get_job", {"job_id": handle["id"]})
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.05)

    server_mod.get_context().runner.shutdown(wait=True)
    assert final["status"] == "succeeded", final
    assert final["progress"]["percent"] == 100.0
    assert Path(final["result"]["output_path"]).exists()
    resource = _resource_payload(asyncio.run(server.read_resource(f"ghostforge://graphs/{gid}/evaluation")))
    assert resource["evaluation"]["status"] == "succeeded"


def test_mcp_evaluates_source_worker_graph_and_applies_manifest_side_effects(tmp_path):
    from ghostforge_core.manifest import read_manifest

    image = tmp_path / "concept.png"
    image.write_bytes(_png_bytes((80, 120, 220)))
    out = tmp_path / "source_graph" / "out.glb"
    manifest_dir = tmp_path / "source_graph"

    server = _server()
    gid = _call(
        server,
        "create_edit_graph",
        {
            "name": "source graph",
            "output_path": str(out),
        },
    )["graph_id"]
    _call(
        server,
        "append_graph_node",
        {
            "graph_id": gid,
            "kind": "generate_image_to_3d",
            "params": {
                "input_image_path": str(image),
                "prompt": "blue crystal obelisk",
                "worker": "stub_image_to_3d",
                "seed": 19,
            },
        },
    )

    result = _call(
        server,
        "evaluate_edit_graph",
        {
            "graph_id": gid,
            "manifest_dir": str(manifest_dir),
            "asset_id": "source_graph_asset",
        },
    )

    assert result["status"] == "succeeded"
    assert Path(result["output_path"]).exists()
    assert result["metadata"]["source_mode"] == "operation"
    side_effects = result["metadata"]["side_effects"]
    assert side_effects[0]["operation"] == "generate_image_to_3d"
    assert result["graph"]["output_path"] == str(out)
    manifest = read_manifest(manifest_dir)
    assert manifest.custom["graph_worker_operations"][0]["worker"] == "stub_image_to_3d"
    assert any(artifact.role == "worker.output_mesh" for artifact in manifest.artifacts)

    evaluation_resource = _resource_payload(
        asyncio.run(server.read_resource(f"ghostforge://graphs/{gid}/evaluation"))
    )
    assert evaluation_resource["evaluation"]["status"] == "succeeded"


def test_append_unknown_kind_surfaces_error():
    server = _server()
    gid = _call(server, "create_edit_graph", {"name": "x"})["graph_id"]
    with pytest.raises(Exception):
        _call(
            server,
            "append_graph_node",
            {"graph_id": gid, "kind": "totally_invalid"},
        )
