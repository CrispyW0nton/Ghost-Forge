"""GhostForge MCP adapter.

Exposes the shared `ghostforge_core` operations through MCP tools over both
``stdio`` (for local agents like Cursor and Claude Desktop) and
``streamable-http`` (for remote agents and HTTP-based orchestration). The
``mcp`` Python SDK is an optional runtime dependency; importing this package
does not pull it in. The actual server modules import ``mcp`` lazily so unit
tests of the core continue to run in environments where the MCP SDK is not
installed.
"""

from __future__ import annotations

__all__ = [
    "build_server",
    "get_context",
    "reset_context_for_tests",
]


def build_server():  # pragma: no cover - thin re-export
    from .server import build_server as _impl

    return _impl()


def get_context():  # pragma: no cover - thin re-export
    from .server import get_context as _impl

    return _impl()


def reset_context_for_tests() -> None:  # pragma: no cover - thin re-export
    from .server import reset_context_for_tests as _impl

    _impl()
