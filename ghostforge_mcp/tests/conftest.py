from __future__ import annotations

import pytest

# These tests exercise the FastMCP integration, which is part of the optional
# `mcp` dependency. Skip the whole suite when it is unavailable so plain core
# checkouts (e.g. CI without extras) continue to run.
mcp = pytest.importorskip("mcp.server.fastmcp")


@pytest.fixture(autouse=True)
def _isolated_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOSTFORGE_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("GHOSTFORGE_DISPATCH_JOBS", "1")

    from ghostforge_mcp import server as mcp_server

    mcp_server.reset_context_for_tests()
    try:
        yield
    finally:
        mcp_server.reset_context_for_tests()
