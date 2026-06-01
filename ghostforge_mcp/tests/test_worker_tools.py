from __future__ import annotations

import asyncio
import io
import json
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


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (16, 16), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_worker_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "list_workers",
        "list_worker_capabilities",
        "probe_worker",
        "submit_image_to_3d",
        "submit_text_to_3d",
        "submit_texture_mesh",
        "submit_refine_mesh",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_list_workers_includes_real_and_stubs():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("list_workers", {}))
    payload = _payload(result)
    names = {entry["descriptor"]["name"] for entry in payload}
    assert {
        "trellis",
        "hunyuan3d",
        "tripo_api",
        "triposg",
        "instantmesh",
        "paint3d",
        "syncmvd",
    }.issubset(names)
    assert {"stub_image_to_3d", "stub_texture_mesh"}.issubset(names)
    assert "stub_text_to_3d" not in names
    stubs = [e for e in payload if e["descriptor"]["is_stub"]]
    assert all(e["probe"]["runnable"] for e in stubs)


def test_list_capabilities_groups_by_capability(monkeypatch):
    from ghostforge_mcp.server import build_server

    monkeypatch.delenv("GHOSTFORGE_TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    server = build_server()
    result = asyncio.run(server.call_tool("list_worker_capabilities", {}))
    payload = _payload(result)
    assert "image_to_3d" in payload
    assert "text_to_3d" in payload
    assert "texture_mesh" in payload
    image_workers = {entry["name"] for entry in payload["image_to_3d"]}
    assert "trellis" in image_workers
    assert "stub_image_to_3d" in image_workers
    text_worker = next(entry for entry in payload["text_to_3d"] if entry["name"] == "tripo_api")
    assert text_worker["runnable"] is False


def test_probe_worker_returns_probe_result():
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("probe_worker", {"name": "stub_image_to_3d"}))
    payload = _payload(result)
    assert payload["name"] == "stub_image_to_3d"
    assert payload["runnable"] is True


def test_probe_worker_unknown_name_errors():
    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(server.call_tool("probe_worker", {"name": "nope"}))


def test_submit_image_to_3d_via_mcp_runs_through_runner(tmp_path):
    pytest.importorskip("trimesh")
    from ghostforge_mcp.server import build_server, get_context

    server = build_server()
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(_png_bytes((30, 90, 200)))

    asset_dir = tmp_path / "asset_image_via_mcp"
    submit_result = asyncio.run(
        server.call_tool(
            "submit_image_to_3d",
            {
                "input_image_path": str(image_path),
                "prompt": "blue gem",
                "output_dir": str(asset_dir),
                "worker": "stub_image_to_3d",
                "seed": 13,
            },
        )
    )
    handle = _payload(submit_result)
    assert handle["kind"] == "image_to_3d"
    job_id = handle["id"]

    import time

    deadline = time.monotonic() + 30
    final = handle
    while time.monotonic() < deadline:
        final = _payload(asyncio.run(server.call_tool("get_job", {"job_id": job_id})))
        if final["status"] in {"succeeded", "failed", "cancelled"}:
            break
        time.sleep(0.1)

    get_context().runner.shutdown(wait=True)

    assert final["status"] == "succeeded", f"job did not succeed: {final}"
    assert (asset_dir / "asset_manifest.json").exists()


def test_submit_text_to_3d_via_mcp_returns_job_handle(tmp_path, monkeypatch):
    from ghostforge_mcp.server import build_server, get_context, reset_context_for_tests

    monkeypatch.delenv("GHOSTFORGE_TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    reset_context_for_tests()
    server = build_server()
    asset_dir = tmp_path / "asset_text_via_mcp"
    submit_result = asyncio.run(
        server.call_tool(
            "submit_text_to_3d",
            {
                "prompt": "low-poly mossy stone archway",
                "output_dir": str(asset_dir),
                "worker": "tripo_api",
                "smart_low_poly": True,
                "face_limit": 8000,
                "pbr": True,
            },
        )
    )
    handle = _payload(submit_result)
    assert handle["kind"] == "text_to_3d"
    assert handle["id"]
    get_context().runner.shutdown(wait=True)
