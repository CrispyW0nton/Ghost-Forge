from __future__ import annotations

import io

import pytest

from ghostforge_core.kb import HashEmbedder, JsonVectorStore, KnowledgeBase
from ghostforge_core.kb.schema import ConceptSource
from ghostforge_core.manifest import (
    ManifestBuilder,
    read_manifest,
)


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (8, 8), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_concept_citation_persists_in_manifest(tmp_path):
    kb = KnowledgeBase(
        store=JsonVectorStore(tmp_path / "kb" / "concepts.json"),
        embedder=HashEmbedder(),
        image_dir=tmp_path / "kb" / "images",
    )
    entry = kb.add_image(
        image_bytes=_png_bytes((100, 50, 200)),
        title="Pillar reference",
        license="CC-BY-4.0",
        attribution="Photographer A, CC BY 4.0",
        source_url="https://example.org/pillar",
        tags=["greek"],
        source=ConceptSource.openverse,
    )

    asset_dir = tmp_path / "asset_007"
    asset_dir.mkdir()
    builder = ManifestBuilder.for_dir(asset_dir, asset_id="asset_007")
    builder.add_concept_citation(kb.make_citation(entry.id, note="primary reference"))
    builder.write()

    reloaded = read_manifest(asset_dir)
    assert len(reloaded.concept_citations) == 1
    citation = reloaded.concept_citations[0]
    assert citation.concept_id == entry.id
    assert citation.license == "CC-BY-4.0"
    assert citation.note == "primary reference"
    assert citation.source == ConceptSource.openverse


def test_concept_citation_dedupes_by_id(tmp_path):
    kb = KnowledgeBase(
        store=JsonVectorStore(tmp_path / "kb" / "concepts.json"),
        embedder=HashEmbedder(),
        image_dir=tmp_path / "kb" / "images",
    )
    entry = kb.add_image(
        image_bytes=_png_bytes((1, 2, 3)),
        title="Ref",
        license="CC0-1.0",
    )

    asset_dir = tmp_path / "asset_dup"
    asset_dir.mkdir()
    b = ManifestBuilder.for_dir(asset_dir)
    b.add_concept_citation(kb.make_citation(entry.id, note="first"))
    b.add_concept_citation(kb.make_citation(entry.id, note="second"))
    b.write()

    reloaded = read_manifest(asset_dir)
    assert len(reloaded.concept_citations) == 1
    assert reloaded.concept_citations[0].note == "second"
