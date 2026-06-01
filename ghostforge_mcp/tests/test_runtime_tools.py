"""MCP tool surface for the GPU runtime layer (Prompt 8)."""

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


pytest.importorskip("trimesh")


def test_runtime_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_gpus",
        "refresh_gpus",
        "get_worker_resources",
        "list_models",
        "model_status",
        "list_required_models",
        "download_model",
        "verify_model",
        "clear_model_cache",
        "run_benchmark",
        "list_benchmarks",
        "get_benchmark",
    }
    missing = expected - names
    assert not missing, f"missing P8 tools: {missing}"


def test_list_gpus_reports_cpu_only_on_bare_host():
    from ghostforge_mcp.server import build_server

    server = build_server()
    payload = _payload(asyncio.run(server.call_tool("list_gpus", {})))
    assert payload["scheduler_enabled"] is True
    # The test host is CPU-only — torch / pynvml are unlikely to be installed.
    assert payload["cpu_only"] is True
    assert payload["gpus"] == []


def test_get_worker_resources_includes_stub_and_real():
    from ghostforge_mcp.server import build_server

    server = build_server()
    payload = _payload(asyncio.run(server.call_tool("get_worker_resources", {})))
    by_name = {entry["name"]: entry for entry in payload}
    stub = by_name["stub_image_to_3d"]
    assert stub["resources"]["requires_cuda"] is False
    assert stub["is_stub"] is True
    trellis = by_name["trellis"]
    assert trellis["resources"]["requires_cuda"] is True
    assert trellis["resources"]["min_vram_mb"] >= 16 * 1024
    assert "trellis-image-large" in trellis["required_models"]


def test_list_models_returns_default_artifacts():
    from ghostforge_mcp.server import build_server

    server = build_server()
    payload = _payload(asyncio.run(server.call_tool("list_models", {})))
    ids = {entry["artifact"]["model_id"] for entry in payload}
    assert {"trellis-image-large", "hunyuan3d-2", "triposg"}.issubset(ids)
    for entry in payload:
        # Bare host: nothing cached yet.
        assert entry["status"]["cached"] is False


def test_model_status_unknown_id_errors():
    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(server.call_tool("model_status", {"model_id": "ghost-not-here"}))


def test_list_required_models_for_trellis():
    from ghostforge_mcp.server import build_server

    server = build_server()
    payload = _payload(
        asyncio.run(server.call_tool("list_required_models", {"worker_name": "trellis"}))
    )
    ids = {entry.get("model_id") for entry in payload}
    assert "trellis-image-large" in ids


def test_run_benchmark_with_stub_worker():
    from ghostforge_mcp.server import build_server

    server = build_server()
    payload = _payload(
        asyncio.run(
            server.call_tool(
                "run_benchmark",
                {
                    "worker_name": "stub_image_to_3d",
                    "capability": "image_to_3d",
                    "spec": {"input_image_path": "concept.png", "prompt": "demo"},
                    "runs": 2,
                    "benchmark_id": "mcp-bench-1",
                    "note": "smoke",
                },
            )
        )
    )
    assert payload["benchmark_id"] == "mcp-bench-1"
    assert payload["runs_succeeded"] == 2
    assert payload["runs_failed"] == 0
    assert payload["wall_seconds_mean"] is not None


def test_list_benchmarks_after_run():
    from ghostforge_mcp.server import build_server

    server = build_server()
    asyncio.run(
        server.call_tool(
            "run_benchmark",
            {
                "worker_name": "stub_image_to_3d",
                "capability": "image_to_3d",
                "spec": {"input_image_path": "concept.png", "prompt": "list-test"},
                "runs": 1,
                "benchmark_id": "mcp-bench-list",
            },
        )
    )
    payload = _payload(asyncio.run(server.call_tool("list_benchmarks", {"limit": 10})))
    assert any(entry["benchmark_id"] == "mcp-bench-list" for entry in payload)


def test_clear_model_cache_specific_id():
    from ghostforge_mcp.server import build_server, get_context

    server = build_server()
    cache_dir = get_context().models.model_dir("triposg")
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "model.safetensors").write_bytes(b"placeholder")
    assert (cache_dir / "model.safetensors").exists()
    payload = _payload(
        asyncio.run(server.call_tool("clear_model_cache", {"model_id": "triposg"}))
    )
    assert payload == {"cleared": 1, "model_id": "triposg"}
    assert not cache_dir.exists()
