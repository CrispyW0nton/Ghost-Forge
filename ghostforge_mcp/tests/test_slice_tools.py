"""MCP tool surface for vertical-slice planning + execution."""

from __future__ import annotations

import asyncio
import json
import time

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


pytest.importorskip("trimesh")


def _brief_payload() -> dict:
    return {
        "title": "Demo Slice",
        "description": "A small vertical slice.",
        "target_engine": "unity",
        "tags": ["demo"],
    }


def _asset_payload(asset_id: str = "rock_01") -> dict:
    return {
        "asset_id": asset_id,
        "description": f"A {asset_id} prop",
        "kind": "prop",
        "strategy": "image_to_3d",
        "reference_image_path": __file__,
        "worker": "stub_image_to_3d",
        "run_unwrap": False,
        "run_texture": False,
        # Stub workers produce a bare cube without UVs; default preset
        # is permissive enough that the executor's audit stage passes.
        "audit_preset": "default",
    }


def test_slice_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "create_vertical_slice",
        "update_vertical_slice_assets",
        "get_vertical_slice",
        "list_vertical_slices",
        "delete_vertical_slice",
        "execute_vertical_slice",
        "submit_vertical_slice",
        "call_engine_tool",
    }
    missing = expected - names
    assert not missing, f"missing slice tools: {missing}"


def test_create_and_get_vertical_slice():
    from ghostforge_mcp.server import build_server

    server = build_server()
    create_result = asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("rock"), _asset_payload("tree")],
                "slice_id": "slice-mcp",
                "skip_handoff": True,
            },
        )
    )
    plan = _payload(create_result)
    assert plan["slice_id"] == "slice-mcp"
    assert {a["asset_id"] for a in plan["assets"]} == {"rock", "tree"}

    get_result = asyncio.run(
        server.call_tool("get_vertical_slice", {"slice_id": "slice-mcp"})
    )
    payload = _payload(get_result)
    assert payload["plan"]["slice_id"] == "slice-mcp"
    assert payload["run"] is None  # not yet executed


def test_list_vertical_slices_returns_summaries():
    from ghostforge_mcp.server import build_server

    server = build_server()
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("a")],
                "slice_id": "slice-list-a",
                "skip_handoff": True,
            },
        )
    )
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": {**_brief_payload(), "title": "Other", "target_engine": "unreal"},
                "assets": [_asset_payload("b"), _asset_payload("c")],
                "slice_id": "slice-list-b",
                "skip_handoff": True,
            },
        )
    )
    summaries = _payload(asyncio.run(server.call_tool("list_vertical_slices", {})))
    by_id = {s["slice_id"]: s for s in summaries}
    assert by_id["slice-list-a"]["asset_count"] == 1
    assert by_id["slice-list-b"]["asset_count"] == 2
    assert by_id["slice-list-b"]["target_engine"] == "unreal"


def test_update_vertical_slice_assets():
    from ghostforge_mcp.server import build_server

    server = build_server()
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("first")],
                "slice_id": "slice-update",
                "skip_handoff": True,
            },
        )
    )
    updated = _payload(
        asyncio.run(
            server.call_tool(
                "update_vertical_slice_assets",
                {
                    "slice_id": "slice-update",
                    "assets": [_asset_payload("alpha"), _asset_payload("beta")],
                },
            )
        )
    )
    assert {a["asset_id"] for a in updated["assets"]} == {"alpha", "beta"}


def test_delete_vertical_slice_removes_plan():
    from ghostforge_mcp.server import build_server

    server = build_server()
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("doomed")],
                "slice_id": "slice-doomed",
                "skip_handoff": True,
            },
        )
    )
    deleted = _payload(
        asyncio.run(
            server.call_tool("delete_vertical_slice", {"slice_id": "slice-doomed"})
        )
    )
    assert deleted == {"deleted": True, "slice_id": "slice-doomed"}
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool("get_vertical_slice", {"slice_id": "slice-doomed"})
        )


def test_execute_vertical_slice_runs_through_stub_pipeline():
    from ghostforge_mcp.server import build_server

    server = build_server()
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("stub_rock")],
                "slice_id": "slice-exec",
                "skip_handoff": True,
            },
        )
    )
    run_result = asyncio.run(
        server.call_tool("execute_vertical_slice", {"slice_id": "slice-exec"})
    )
    payload = _payload(run_result)
    assert payload["status"] == "succeeded"
    assert "stub_rock" in payload["assets"]
    assert payload["assets"]["stub_rock"]["status"] == "succeeded"


def test_submit_vertical_slice_runs_in_background():
    from ghostforge_mcp.server import build_server, get_context

    server = build_server()
    asyncio.run(
        server.call_tool(
            "create_vertical_slice",
            {
                "brief": _brief_payload(),
                "assets": [_asset_payload("bg_asset")],
                "slice_id": "slice-bg",
                "skip_handoff": True,
            },
        )
    )
    submit = asyncio.run(
        server.call_tool("submit_vertical_slice", {"slice_id": "slice-bg"})
    )
    handle = _payload(submit)
    assert handle["kind"] == "execute_vertical_slice"
    job_id = handle["id"]

    deadline = time.monotonic() + 30.0
    final = handle
    while time.monotonic() < deadline:
        final = _payload(asyncio.run(server.call_tool("get_job", {"job_id": job_id})))
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.2)
    get_context().runner.shutdown(wait=True)
    assert final["status"] == "succeeded", f"job did not succeed: {final}"


def test_call_engine_tool_invokes_recording_transport():
    from ghostforge_core.engines import EngineConfig, RecordingTransport
    from ghostforge_mcp.server import build_server, get_context

    server = build_server()
    transport = RecordingTransport(name="unity-rec")
    adapter = get_context().engines.get("unity")
    adapter.configure(
        EngineConfig(
            name="unity",
            transport="none",
            import_tool="ghost.import_asset",
            description="recording adapter",
        )
    )
    adapter.set_transport(transport)

    result = _payload(
        asyncio.run(
            server.call_tool(
                "call_engine_tool",
                {
                    "engine": "unity",
                    "tool_name": "ghost.take_screenshot",
                    "arguments": {"camera": "MainCamera", "output": "shot.png"},
                },
            )
        )
    )
    assert isinstance(result, dict)
    assert transport.calls and transport.calls[-1][0] == "ghost.take_screenshot"
