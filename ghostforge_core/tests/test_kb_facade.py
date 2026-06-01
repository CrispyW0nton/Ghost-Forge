from __future__ import annotations

import io

import pytest

from ghostforge_core.kb import (
    HashEmbedder,
    JsonVectorStore,
    KnowledgeBase,
    StyleGuideEntry,
    build_knowledge_base,
)
from ghostforge_core.kb.schema import ConceptSource


def _kb(tmp_path) -> KnowledgeBase:
    return KnowledgeBase(
        store=JsonVectorStore(tmp_path / "kb" / "concepts.json"),
        embedder=HashEmbedder(),
        image_dir=tmp_path / "kb" / "images",
    )


def _png_bytes(color: tuple[int, int, int], size: int = 32) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (size, size), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_add_image_requires_license(tmp_path):
    kb = _kb(tmp_path)
    with pytest.raises(ValueError):
        kb.add_image(image_bytes=_png_bytes((10, 20, 30)), title="x", license="")


def test_add_text_requires_non_empty(tmp_path):
    kb = _kb(tmp_path)
    with pytest.raises(ValueError):
        kb.add_text(text="   ", title="x", license="project-internal")


def test_add_and_retrieve_local_image(tmp_path):
    kb = _kb(tmp_path)
    data = _png_bytes((180, 30, 30))
    entry = kb.add_image(
        image_bytes=data,
        title="Red square",
        license="CC0-1.0",
        tags=["red"],
    )
    assert entry.image_path is not None
    assert entry.image_path.exists()
    assert entry.image_sha256 is not None
    assert entry.embedding_model == "hash:256"
    assert entry.embedding_dim == 256

    fetched = kb.get(entry.id)
    assert fetched.id == entry.id

    matches = kb.search_image_bytes(data, k=1)
    assert matches and matches[0].entry.id == entry.id
    assert matches[0].score >= 0.95


def test_style_guide_round_trip(tmp_path):
    kb = _kb(tmp_path)
    guide = StyleGuideEntry(
        title="Greek Architecture",
        text="Use marble columns, doric capitals, soft warm light, weathered stone.",
        tags=["greek", "stone"],
    )
    entry = kb.add_style_guide(guide)
    assert entry.source == ConceptSource.style_guide
    assert entry.license == "project-internal"

    matches = kb.search_text("marble columns and weathered stone", k=3)
    assert matches and matches[0].entry.id == entry.id


def test_make_citation_pulls_through_metadata(tmp_path):
    kb = _kb(tmp_path)
    entry = kb.add_image(
        image_bytes=_png_bytes((10, 200, 50)),
        title="Forest canopy",
        license="CC-BY-4.0",
        attribution='"Forest canopy" by sample, CC BY 4.0',
        source_url="https://example.org/forest",
    )
    citation = kb.make_citation(entry.id, note="primary reference")
    assert citation.concept_id == entry.id
    assert citation.license == "CC-BY-4.0"
    assert citation.attribution == '"Forest canopy" by sample, CC BY 4.0'
    assert citation.source_url == "https://example.org/forest"
    assert citation.note == "primary reference"


def test_image_cache_dedupes_by_sha256(tmp_path):
    kb = _kb(tmp_path)
    data = _png_bytes((30, 60, 90))
    a = kb.add_image(image_bytes=data, title="A", license="CC0-1.0")
    b = kb.add_image(image_bytes=data, title="B", license="CC0-1.0")
    assert a.image_sha256 == b.image_sha256
    assert a.image_path == b.image_path
    cached = list((tmp_path / "kb" / "images").iterdir())
    assert len(cached) == 1


def test_build_knowledge_base_factory(tmp_path):
    kb = build_knowledge_base(tmp_path / "data")
    assert isinstance(kb.store, JsonVectorStore)
    assert isinstance(kb.embedder, HashEmbedder)
    assert (tmp_path / "data" / "kb").exists()
