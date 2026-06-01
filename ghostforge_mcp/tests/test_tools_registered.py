from __future__ import annotations

import asyncio


def test_expected_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    expected = {
        "health",
        "list_capabilities",
        "mesh_info",
        "validate_mesh_tool",
        "submit_unwrap",
        "submit_texture",
        "get_job",
        "list_jobs",
        "cancel_job",
        "wait_for_job",
    }
    assert expected.issubset(names), f"missing tools: {expected - names}"


def test_submit_unwrap_input_schema_matches_unwrap_request_fields():
    """The agent-facing schema must mirror the Pydantic UnwrapRequest fields so
    `ghostforge_core.types` stays the single source of truth for parameters."""
    from ghostforge_core.types import UnwrapRequest
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    by_name = {tool.name: tool for tool in tools}

    unwrap_tool = by_name["submit_unwrap"]
    schema_props = set(unwrap_tool.inputSchema.get("properties", {}).keys())

    pydantic_fields = set(UnwrapRequest.model_fields.keys())
    server_managed = {"job_id"}  # set by the runner, not by clients
    derived_default = {"output_dir"}  # MCP tool resolves to a fresh asset dir

    expected_props = (pydantic_fields - server_managed - derived_default) | {"output_dir"}
    assert schema_props == expected_props, (
        f"submit_unwrap schema diverged from UnwrapRequest. "
        f"missing={expected_props - schema_props}, extra={schema_props - expected_props}"
    )


def test_health_tool_returns_registered_kinds():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("health", {}))

    payloads: list[object] = []
    if isinstance(result, tuple):
        # Newer FastMCP: (content, structured_output)
        content, structured = result
        if structured is not None:
            payloads.append(structured)
        for item in content:
            text = getattr(item, "text", None)
            if text is not None:
                payloads.append(_safe_json(text))
    else:
        for item in result:
            text = getattr(item, "text", None)
            if text is not None:
                payloads.append(_safe_json(text))

    found_kinds: set[str] = set()
    for payload in payloads:
        if isinstance(payload, dict):
            for kind in payload.get("kinds", []) or []:
                if isinstance(kind, dict) and "kind" in kind:
                    found_kinds.add(kind["kind"])

    assert {"mesh_info", "unwrap_uvs", "generate_texture_set"}.issubset(found_kinds), (
        f"health() did not advertise expected kinds; got {found_kinds}"
    )


def _safe_json(text: str):
    import json

    try:
        return json.loads(text)
    except Exception:
        return text
