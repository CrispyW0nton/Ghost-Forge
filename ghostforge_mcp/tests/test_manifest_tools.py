from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


def _payload(result):
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, dict):
            return structured
        for item in content:
            text = getattr(item, "text", None)
            if text is None:
                continue
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                continue
        raise AssertionError(f"no payload in {result!r}")

    for item in result:
        text = getattr(item, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            continue
    raise AssertionError(f"no payload in {result!r}")


def test_update_then_read_asset_manifest_via_mcp(tmp_path):
    asset_dir = tmp_path / "asset_manifest_demo"

    from ghostforge_mcp.server import build_server

    server = build_server()
    update_result = asyncio.run(
        server.call_tool(
            "update_asset_manifest",
            {
                "asset_dir": str(asset_dir),
                "name": "Demo Asset",
                "description": "MCP-driven manifest annotation",
                "license_spdx": "CC-BY-4.0",
                "license_holder": "GhostForge",
                "engine_targets": ["unity", "unreal"],
                "tags": ["demo", "test"],
            },
        )
    )
    payload = _payload(update_result)
    assert payload["manifest_version"] == "1.0"
    assert payload["name"] == "Demo Asset"
    assert payload["license"]["spdx"] == "CC-BY-4.0"
    targets = {t["engine"] for t in payload["engine_targets"]}
    assert {"unity", "unreal"}.issubset(targets)
    assert set(payload["tags"]) == {"demo", "test"}

    read_result = asyncio.run(
        server.call_tool("read_asset_manifest", {"asset_dir": str(asset_dir)})
    )
    read_payload = _payload(read_result)
    assert read_payload["asset_id"] == asset_dir.name
    assert read_payload["license"]["spdx"] == "CC-BY-4.0"
    assert {t["engine"] for t in read_payload["engine_targets"]} == {"unity", "unreal"}


def test_update_asset_manifest_rejects_unknown_engine(tmp_path):
    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception) as exc_info:
        asyncio.run(
            server.call_tool(
                "update_asset_manifest",
                {
                    "asset_dir": str(tmp_path / "bad"),
                    "engine_targets": ["dreamcast"],
                },
            )
        )
    assert "dreamcast" in str(exc_info.value).lower() or "unknown engine" in str(exc_info.value).lower()


def test_read_asset_manifest_missing_directory(tmp_path):
    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "read_asset_manifest",
                {"asset_dir": str(tmp_path / "does_not_exist")},
            )
        )
