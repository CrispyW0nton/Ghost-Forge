from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ghostforge_core.kb import HashEmbedder, JsonVectorStore, KnowledgeBase
from ghostforge_core.kb.ingest import (
    ingest_local_image,
    ingest_openverse,
    ingest_url,
)
from ghostforge_core.kb.schema import ConceptSource


def _kb(tmp_path) -> KnowledgeBase:
    return KnowledgeBase(
        store=JsonVectorStore(tmp_path / "kb" / "concepts.json"),
        embedder=HashEmbedder(),
        image_dir=tmp_path / "kb" / "images",
    )


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (16, 16), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_ingest_local_image(tmp_path):
    kb = _kb(tmp_path)
    src = tmp_path / "ref.png"
    src.write_bytes(_png_bytes((50, 100, 150)))
    entry = ingest_local_image(
        kb, src, title="Local ref", license="CC-BY-4.0", tags=["test"]
    )
    assert entry.source == ConceptSource.local
    assert entry.title == "Local ref"
    assert "test" in entry.tags
    assert entry.image_path is not None and entry.image_path.exists()


def test_ingest_url_uses_injected_fetcher(tmp_path):
    kb = _kb(tmp_path)
    captured: dict = {}

    def fake_fetcher(url: str, *, accept: str | None = None) -> bytes:
        captured["url"] = url
        captured["accept"] = accept
        return _png_bytes((10, 250, 10))

    entry = ingest_url(
        kb,
        "https://example.org/leaf.png",
        title="Leaf",
        license="CC0-1.0",
        fetcher=fake_fetcher,
    )
    assert captured["url"] == "https://example.org/leaf.png"
    assert captured["accept"] == "image/*"
    assert entry.source == ConceptSource.url
    assert entry.source_url == "https://example.org/leaf.png"


def test_ingest_openverse_with_fake_fetcher(tmp_path):
    kb = _kb(tmp_path)
    image_a = _png_bytes((255, 0, 0))
    image_b = _png_bytes((0, 255, 0))

    search_payload = {
        "result_count": 2,
        "page_count": 1,
        "results": [
            {
                "id": "ov-1",
                "title": "Greek Marble Column",
                "url": "https://cdn.example.org/img/a.png",
                "thumbnail": "https://cdn.example.org/thumb/a.png",
                "foreign_landing_url": "https://example.org/photo/a",
                "creator": "Photographer A",
                "license": "by",
                "license_version": "4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "provider": "wikimedia",
                "source": "wikimedia",
                "tags": [{"name": "stone"}, {"name": "marble"}],
            },
            {
                "id": "ov-2",
                "title": "Painted Pottery",
                "url": "https://cdn.example.org/img/b.png",
                "foreign_landing_url": "https://example.org/photo/b",
                "creator": "Photographer B",
                "license": "cc0",
                "license_version": "1.0",
                "tags": [],
            },
        ],
    }

    def fake_fetcher(url: str, *, accept: str | None = None) -> bytes:
        if "api.openverse" in url or url.startswith("http") and url.endswith("/images/"):
            return json.dumps(search_payload).encode("utf-8")
        if accept == "application/json":
            return json.dumps(search_payload).encode("utf-8")
        if "a.png" in url:
            return image_a
        if "b.png" in url:
            return image_b
        raise AssertionError(f"unexpected url {url}")

    entries = ingest_openverse(
        kb,
        "greek marble",
        count=2,
        fetcher=fake_fetcher,
    )
    assert len(entries) == 2
    titles = {e.title for e in entries}
    assert "Greek Marble Column" in titles
    assert "Painted Pottery" in titles
    licenses = {e.license for e in entries}
    assert any(l.startswith("CC-BY") for l in licenses)
    assert any(l.startswith("CC0") for l in licenses)
    sources = {e.source for e in entries}
    assert sources == {ConceptSource.openverse}
    assert all("openverse" in e.tags for e in entries)
    assert all(e.attribution for e in entries)


def test_openverse_skips_results_with_failed_image_fetch(tmp_path):
    kb = _kb(tmp_path)

    search_payload = {
        "results": [
            {
                "id": "ov-good",
                "title": "good",
                "url": "https://cdn.example.org/img/good.png",
                "license": "cc0",
            },
            {
                "id": "ov-bad",
                "title": "bad",
                "url": "https://cdn.example.org/img/bad.png",
                "license": "cc0",
            },
        ]
    }

    def fake_fetcher(url: str, *, accept: str | None = None) -> bytes:
        if "api.openverse" in url or accept == "application/json":
            return json.dumps(search_payload).encode("utf-8")
        if "good.png" in url:
            return _png_bytes((1, 2, 3))
        raise RuntimeError("image fetch failed")

    entries = ingest_openverse(kb, "x", count=2, fetcher=fake_fetcher)
    assert len(entries) == 1
    assert entries[0].metadata.get("openverse_id") == "ov-good"
