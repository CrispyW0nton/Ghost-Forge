"""MCP tool surface for engine handoff."""

from __future__ import annotations

import asyncio
import json
import time
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


def _seed_asset(tmp_path: Path, *, with_unity: bool = True) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    from ghostforge_core.manifest import (
        EngineTarget,
        EngineTargetSpec,
        LicenseSpec,
        ManifestBuilder,
    )

    asset_dir = tmp_path / "asset_mcp"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="asset_mcp")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    if with_unity:
        builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unity))
    builder.write()
    return asset_dir


def test_engine_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert {
        "list_engine_adapters",
        "configure_engine_adapter",
        "send_to_unity",
        "send_to_unreal",
        "create_engine_export_bridge",
        "submit_send_to_engine",
    }.issubset(names), f"missing: {names}"


def test_list_engine_adapters_includes_both():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("list_engine_adapters", {}))
    payload = _payload(result)
    names = {entry["name"] for entry in payload}
    assert names == {"unity", "unreal"}
    for entry in payload:
        assert "config" in entry and "probe" in entry
        assert entry["probe"]["configured"] is False  # default: env not set


def test_configure_engine_adapter_round_trip():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(
        server.call_tool(
            "configure_engine_adapter",
            {
                "name": "unity",
                "transport": "stdio",
                "command": ["python", "-m", "unity_mcp_ghost"],
                "import_tool": "ghost.import",
                "project_path": "C:/Projects/Game",
            },
        )
    )
    payload = _payload(result)
    assert payload["config"]["transport"] == "stdio"
    assert payload["config"]["command"] == ["python", "-m", "unity_mcp_ghost"]
    assert payload["config"]["import_tool"] == "ghost.import"
    assert payload["probe"]["configured"] is True


def test_configure_engine_adapter_invalid_transport_errors():
    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "configure_engine_adapter",
                {"name": "unity", "transport": "carrier-pigeon"},
            )
        )


def test_send_to_unity_dry_run(tmp_path):
    from ghostforge_mcp.server import build_server, get_context

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    # Force adapter into unconfigured state but still let dry_run work.
    get_context().engines.get("unity").set_transport(None)

    result = asyncio.run(
        server.call_tool(
            "send_to_unity",
            {"asset_dir": str(asset_dir), "dry_run": True, "audit": False},
        )
    )
    payload = _payload(result)
    assert payload["engine"] == "unity"
    assert payload["dry_run"] is True
    assert payload["target_path"].startswith("Assets/GhostForge/")


def test_send_to_unity_with_injected_transport(tmp_path):
    from ghostforge_core.engines import RecordingTransport
    from ghostforge_mcp.server import build_server, get_context

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    transport = RecordingTransport(
        handler=lambda name, args: {
            "content": [{"type": "text", "text": "imported"}],
            "structured": {"engine_id": "u-42"},
            "isError": False,
        }
    )
    get_context().engines.get("unity").set_transport(transport)

    result = asyncio.run(
        server.call_tool(
            "send_to_unity",
            {
                "asset_dir": str(asset_dir),
                "target_path": "Assets/Custom/Foo",
                "audit": False,
            },
        )
    )
    payload = _payload(result)
    assert payload["target_path"] == "Assets/Custom/Foo"
    assert payload["engine_response"]["structured"]["engine_id"] == "u-42"
    assert transport.calls and transport.calls[0][0] == "import_asset"


def test_send_to_unreal_engine_target_check(tmp_path):
    from ghostforge_core.engines import RecordingTransport
    from ghostforge_mcp.server import build_server, get_context

    asset_dir = _seed_asset(tmp_path, with_unity=True)  # only unity in targets
    server = build_server()
    get_context().engines.get("unreal").set_transport(RecordingTransport())

    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "send_to_unreal",
                {"asset_dir": str(asset_dir), "audit": False},
            )
        )

    # Force=True should succeed and add unreal to engine_targets afterwards.
    result = asyncio.run(
        server.call_tool(
            "send_to_unreal",
            {"asset_dir": str(asset_dir), "force": True, "audit": False},
        )
    )
    payload = _payload(result)
    assert payload["engine"] == "unreal"
    assert payload["target_path"].startswith("/Game/GhostForge/")


def test_create_engine_export_bridge_tool(tmp_path):
    from ghostforge_mcp.server import build_server

    asset_dir = _seed_asset(tmp_path, with_unity=False)
    server = build_server()
    result = asyncio.run(
        server.call_tool(
            "create_engine_export_bridge",
            {"asset_dir": str(asset_dir), "target_engine": "unreal"},
        )
    )
    payload = _payload(result)
    assert payload["direct_engine_call"] is False
    assert Path(payload["package_path"]).exists()
    assert payload["package"]["recommended_mcp_server"] == "Unreal-MCP-Ghost"


def test_submit_send_to_engine_runs_through_runner(tmp_path):
    from ghostforge_core.engines import RecordingTransport
    from ghostforge_mcp.server import build_server, get_context

    asset_dir = _seed_asset(tmp_path)
    server = build_server()
    get_context().engines.get("unity").set_transport(RecordingTransport())

    submit_result = asyncio.run(
        server.call_tool(
            "submit_send_to_engine",
            {"asset_dir": str(asset_dir), "engine": "unity", "audit": False},
        )
    )
    handle = _payload(submit_result)
    assert handle["kind"] == "send_to_engine"
    job_id = handle["id"]

    deadline = time.monotonic() + 10.0
    final = handle
    while time.monotonic() < deadline:
        final = _payload(asyncio.run(server.call_tool("get_job", {"job_id": job_id})))
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.1)
    get_context().runner.shutdown(wait=True)
    assert final["status"] == "succeeded", f"job did not succeed: {final}"
    assert final["result"]["engine"] == "unity"
