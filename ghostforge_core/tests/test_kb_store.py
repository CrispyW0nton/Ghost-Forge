from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ghostforge_core.kb.schema import ConceptEntry, ConceptSource
from ghostforge_core.kb.store import JsonVectorStore


def _entry(suffix: str, source: ConceptSource = ConceptSource.local) -> tuple[ConceptEntry, list[float]]:
    entry = ConceptEntry(
        id=f"id_{suffix}",
        source=source,
        title=f"title {suffix}",
        license="CC-BY-4.0",
        embedding_model="hash:256",
        embedding_dim=4,
        tags=[suffix],
        created_at=datetime(2026, 1, int(suffix) if suffix.isdigit() else 1, tzinfo=timezone.utc),
    )
    base = [0.1, 0.2, 0.3, 0.4]
    if suffix == "1":
        vector = base
    elif suffix == "2":
        vector = [0.0, 0.0, 1.0, 0.0]
    else:
        vector = [-0.1, -0.2, -0.3, -0.4]
    return entry, vector


def test_json_store_persists_and_searches(tmp_path):
    path = tmp_path / "concepts.json"
    store = JsonVectorStore(path)

    e1, v1 = _entry("1")
    e2, v2 = _entry("2")
    e3, v3 = _entry("3")
    for entry, vec in [(e1, v1), (e2, v2), (e3, v3)]:
        store.add(entry, vec)

    assert store.count() == 3
    assert path.exists()

    reopened = JsonVectorStore(path)
    assert reopened.count() == 3

    results = reopened.search([0.1, 0.2, 0.3, 0.4], k=2)
    assert len(results) == 2
    assert results[0].entry.id == "id_1"
    assert 0.0 <= results[0].score <= 1.0
    assert results[0].score >= results[1].score


def test_json_store_filters_by_source(tmp_path):
    store = JsonVectorStore(tmp_path / "c.json")
    local_entry, vec = _entry("1", ConceptSource.local)
    style_entry = ConceptEntry(
        id="style_1",
        source=ConceptSource.style_guide,
        title="palette guide",
        license="project-internal",
        embedding_model="hash:256",
        embedding_dim=4,
    )
    store.add(local_entry, vec)
    store.add(style_entry, [0.1, 0.2, 0.3, 0.4])

    only_styles = store.search(
        [0.1, 0.2, 0.3, 0.4], k=5, sources=[ConceptSource.style_guide]
    )
    assert len(only_styles) == 1
    assert only_styles[0].entry.id == "style_1"


def test_json_store_dim_mismatch_raises(tmp_path):
    store = JsonVectorStore(tmp_path / "c.json")
    entry, vec = _entry("1")
    store.add(entry, vec)
    with pytest.raises(ValueError):
        store.search([0.0, 1.0, 0.0])


def test_json_store_get_and_delete(tmp_path):
    store = JsonVectorStore(tmp_path / "c.json")
    entry, vec = _entry("1")
    store.add(entry, vec)
    assert store.get("id_1").id == "id_1"

    store.delete("id_1")
    with pytest.raises(KeyError):
        store.get("id_1")
