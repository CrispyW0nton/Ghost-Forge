"""Transports that speak MCP to an engine server.

The :class:`EngineTransport` interface is sync to keep adapter call sites
simple. Real transports wrap an internal asyncio loop because the MCP
Python SDK is async-only; we open a fresh connection per ``call_tool``
since engine handoffs are infrequent and short-lived (one tool call
per delivered asset, typically).

Three implementations:

* :class:`StdioMcpTransport` — spawns the engine MCP server as a
  subprocess and talks over stdio. Best for local Unity/Unreal MCP-Ghost
  installs that ship a Python entry point.
* :class:`HttpMcpTransport` — connects to a running engine MCP via the
  ``streamable-http`` transport. Useful when the engine MCP is already
  attached to the editor and exposes a port.
* :class:`RecordingTransport` — for tests. Records every ``call_tool``
  invocation and returns canned responses. No network or subprocess.

A normalized result shape (``{"content": [...], "structured": ...,
"isError": ...}``) lets adapters and tests reason about results without
re-implementing MCP framing.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@runtime_checkable
class EngineTransport(Protocol):
    """Sync interface adapters call. ``name`` is for logging/probing only."""

    name: str

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


def _normalize_call_tool_result(result: Any) -> dict[str, Any]:
    """Convert an MCP ``CallToolResult`` to a JSON-friendly dict.

    The SDK's ``CallToolResult`` model carries content blocks plus an
    optional structured payload. We preserve text blocks verbatim,
    surface structured content for downstream consumers, and flag
    ``isError`` so adapters can raise instead of silently returning a
    failure result.
    """

    content: list[dict[str, Any]] = []
    raw_content = getattr(result, "content", None) or []
    for item in raw_content:
        item_type = getattr(item, "type", None) or "unknown"
        text = getattr(item, "text", None)
        if text is not None:
            content.append({"type": item_type, "text": text})
        else:
            content.append({"type": item_type})

    out: dict[str, Any] = {"content": content}

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        out["structured"] = structured

    is_error = getattr(result, "isError", None)
    if is_error is None:
        is_error = getattr(result, "is_error", None)
    if is_error is not None:
        out["isError"] = bool(is_error)

    return out


@dataclass
class StdioMcpTransport:
    """Spawn the engine MCP via stdio for each call.

    Reconnecting per call keeps the transport stateless — handy because
    engine handoff is a rare event and the engine MCP may take seconds
    to fully boot. Long-lived connections can be added later if profiling
    shows the spawn cost matters.
    """

    name: str
    command: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 120.0

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call_tool_async(name, arguments))

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            from mcp import ClientSession  # noqa: F401  - imported lazily
            from mcp.client.stdio import StdioServerParameters, stdio_client
        except ImportError as exc:  # pragma: no cover - tested via skip path
            raise RuntimeError(
                "mcp client is not installed. Install the `mcp` extras: "
                "`pip install ghostforge[mcp]`."
            ) from exc

        merged_env: dict[str, str] | None = None
        if self.env:
            merged_env = dict(os.environ)
            merged_env.update(self.env)

        params = StdioServerParameters(
            command=self.command,
            args=list(self.args),
            cwd=self.cwd,
            env=merged_env,
        )
        from mcp import ClientSession

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=self.timeout_seconds)
                result = await asyncio.wait_for(
                    session.call_tool(name, arguments),
                    timeout=self.timeout_seconds,
                )
                return _normalize_call_tool_result(result)


@dataclass
class HttpMcpTransport:
    """Talk to an engine MCP via HTTP streamable transport."""

    name: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float = 120.0

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call_tool_async(name, arguments))

    async def _call_tool_async(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            from mcp import ClientSession  # noqa: F401
            from mcp.client.streamable_http import streamablehttp_client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "mcp client is not installed. Install the `mcp` extras: "
                "`pip install ghostforge[mcp]`."
            ) from exc

        from mcp import ClientSession

        async with streamablehttp_client(self.url, headers=dict(self.headers)) as (read, write, _):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=self.timeout_seconds)
                result = await asyncio.wait_for(
                    session.call_tool(name, arguments),
                    timeout=self.timeout_seconds,
                )
                return _normalize_call_tool_result(result)


@dataclass
class RecordingTransport:
    """Test-only transport that captures calls and returns scripted responses.

    The default handler returns a stub-success payload that's enough to
    drive most adapter assertions. Tests inject a custom ``handler`` to
    simulate engine errors or richer structured replies.
    """

    name: str = "recording"
    handler: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(arguments)))
        if self.handler is None:
            return {
                "content": [{"type": "text", "text": "ok"}],
                "structured": {"status": "ok", "engine": self.name, "tool": name},
                "isError": False,
            }
        return self.handler(name, arguments)


__all__ = [
    "EngineTransport",
    "HttpMcpTransport",
    "RecordingTransport",
    "StdioMcpTransport",
]
