from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path

import pytest


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (16, 16), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _unwrap(value):
    # FastMCP wraps non-dict structured returns (lists, scalars) in
    # {"result": ...} for the structured output channel; unwrap it so test
    # assertions can target the raw shape.
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


def test_kb_tools_registered():
    from ghostforge_mcp.server import build_server

    server = build_server()
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        "kb_status",
        "kb_ingest_local_image",
        "kb_ingest_url",
        "kb_ingest_openverse",
        "kb_ingest_style_guide",
        "kb_search_text",
        "kb_search_image",
        "kb_get",
        "kb_list",
        "kb_cite_in_manifest",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_kb_status_reports_default_backends(tmp_path):
    from ghostforge_mcp.server import build_server

    server = build_server()
    result = asyncio.run(server.call_tool("kb_status", {}))
    payload = _payload(result)
    assert payload["backend"] == "json"
    assert payload["embedder"] == "hash:256"
    assert payload["embedding_dim"] == 256
    assert payload["count"] == 0


def test_kb_ingest_local_then_search_then_cite(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(_png_bytes((30, 90, 200)))

    from ghostforge_mcp.server import build_server

    server = build_server()

    ingest_result = asyncio.run(
        server.call_tool(
            "kb_ingest_local_image",
            {
                "image_path": str(image_path),
                "title": "Blueprint reference",
                "license": "CC-BY-4.0",
                "attribution": "Photo by sample, CC BY 4.0",
                "tags": ["test", "blue"],
            },
        )
    )
    entry = _payload(ingest_result)
    concept_id = entry["id"]
    assert entry["license"] == "CC-BY-4.0"

    style_result = asyncio.run(
        server.call_tool(
            "kb_ingest_style_guide",
            {
                "title": "Style note",
                "text": "blueprint references with deep blue tones and crisp lines",
                "tags": ["blue"],
            },
        )
    )
    style_entry = _payload(style_result)
    assert style_entry["source"] == "style_guide"
    assert style_entry["license"] == "project-internal"

    search_result = asyncio.run(
        server.call_tool(
            "kb_search_text",
            {"query": "blueprint references", "k": 3},
        )
    )
    search_payload = _payload(search_result)
    ids = {item["entry"]["id"] for item in search_payload}
    assert style_entry["id"] in ids

    image_search = asyncio.run(
        server.call_tool(
            "kb_search_image",
            {"image_path": str(image_path), "k": 3},
        )
    )
    image_payload = _payload(image_search)
    image_ids = {item["entry"]["id"] for item in image_payload}
    assert concept_id in image_ids

    asset_dir = tmp_path / "asset_with_concepts"
    cite_result = asyncio.run(
        server.call_tool(
            "kb_cite_in_manifest",
            {
                "asset_dir": str(asset_dir),
                "concept_ids": [concept_id],
                "note": "primary reference",
            },
        )
    )
    manifest_payload = _payload(cite_result)
    citations = manifest_payload["concept_citations"]
    assert len(citations) == 1
    assert citations[0]["concept_id"] == concept_id
    assert citations[0]["license"] == "CC-BY-4.0"
    assert citations[0]["note"] == "primary reference"


def test_kb_ingest_local_rejects_missing_license(tmp_path):
    image_path = tmp_path / "ref.png"
    image_path.write_bytes(_png_bytes((1, 2, 3)))

    from ghostforge_mcp.server import build_server

    server = build_server()
    with pytest.raises(Exception):
        asyncio.run(
            server.call_tool(
                "kb_ingest_local_image",
                {
                    "image_path": str(image_path),
                    "title": "no-license",
                    "license": "",
                },
            )
        )
