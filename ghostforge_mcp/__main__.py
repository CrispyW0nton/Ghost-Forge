"""Run the GhostForge MCP server.

Examples
--------
Local stdio (default; for Cursor / Claude Desktop)::

    python -m ghostforge_mcp

Remote streamable HTTP (recommended for cloud agents)::

    python -m ghostforge_mcp --transport streamable-http --host 0.0.0.0 --port 8765

SSE (older HTTP-based clients)::

    python -m ghostforge_mcp --transport sse --port 8765

Coexisting with the desktop Flask backend on the same SQLite store::

    set GHOSTFORGE_DISPATCH_JOBS=0
    python -m ghostforge_mcp --transport stdio
"""

from __future__ import annotations

import argparse
import logging
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ghostforge_mcp")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default=os.environ.get("GHOSTFORGE_MCP_TRANSPORT", "stdio"),
        help="MCP transport to expose. Default: stdio.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("GHOSTFORGE_MCP_HOST", "127.0.0.1"),
        help="Bind host for HTTP transports. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("GHOSTFORGE_MCP_PORT", "8765")),
        help="Bind port for HTTP transports. Default: 8765.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("GHOSTFORGE_MCP_LOG", "INFO"),
        help="Python logging level. Default: INFO.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    from .server import build_server, get_context

    # Force core bootstrap before transports take over so we surface SQLite or
    # path errors as plain stderr text rather than as MCP framing failures.
    ctx = get_context()
    log = logging.getLogger("ghostforge_mcp")
    log.info(
        "GhostForge MCP starting transport=%s data_root=%s dispatch_jobs=%s",
        args.transport,
        ctx.storage.root,
        ctx.config.dispatch_jobs,
    )

    server = build_server()

    # FastMCP's settings carry host/port for HTTP transports; mutate them
    # before run() rather than passing kwargs to keep the call site portable
    # across mcp SDK minor versions.
    if args.transport in {"streamable-http", "sse"}:
        try:
            server.settings.host = args.host
            server.settings.port = args.port
        except AttributeError:  # pragma: no cover - older SDK shapes
            log.warning("FastMCP settings missing host/port; using SDK defaults")

    server.run(transport=args.transport)
    return 0


if __name__ == "__main__":
    sys.exit(main())
