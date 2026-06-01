"""MCP tool surface for the worker-session lifecycle (Prompt 9)."""

from __future__ import annotations

import asyncio
import json

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


def test_session_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_worker_sessions",
        "free_worker_session",
        "free_idle_worker_sessions",
    }
    missing = expected - names
    assert not missing, f"missing P9 session tools: {missing}"


def test_list_worker_sessions_when_empty():
    """A freshly built server has no loaded sessions yet.

    Bare-host reset: real workers can't load (no torch), so the global
    session registry is empty.
    """

    from ghostforge_core.workers.session import get_session_registry
    from ghostforge_mcp.server import build_server

    # Drop any residue from prior tests in the same process.
    get_session_registry().free(force=True)

    server = build_server()
    payload = _payload(asyncio.run(server.call_tool("list_worker_sessions", {})))
    assert isinstance(payload, list)
    assert payload == []


def test_free_worker_session_idempotent_when_none_loaded():
    from ghostforge_core.workers.session import get_session_registry
    from ghostforge_mcp.server import build_server

    get_session_registry().free(force=True)

    server = build_server()
    payload = _payload(asyncio.run(server.call_tool("free_worker_session", {})))
    assert payload["freed"] == 0
    assert payload["force"] is False


def test_session_lifecycle_visible_through_mcp():
    from ghostforge_core.workers.session import (
        WorkerSession,
        get_session_registry,
    )
    from ghostforge_mcp.server import build_server

    registry = get_session_registry()
    registry.free(force=True)

    # Create a fake session that appears loaded.
    session = WorkerSession(loader=lambda: "checkpoint", name="test_p9_session")
    registry.register(session)
    session.get()
    session.release()

    server = build_server()
    listing = _payload(asyncio.run(server.call_tool("list_worker_sessions", {})))
    names = {entry["name"] for entry in listing}
    assert "test_p9_session" in names

    freed = _payload(
        asyncio.run(
            server.call_tool("free_worker_session", {"name": "test_p9_session"})
        )
    )
    assert freed["freed"] == 1

    # Cleanup any lingering global state for the next test.
    registry.free(force=True)
