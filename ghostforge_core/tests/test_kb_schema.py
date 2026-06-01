from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostforge_core.kb.schema import (
    ConceptCitation,
    ConceptEntry,
    ConceptSearchResult,
    ConceptSource,
)


def _entry(**overrides) -> ConceptEntry:
    payload = dict(
        id="abc",
        source=ConceptSource.local,
        title="A reference",
        license="CC-BY-4.0",
        embedding_model="hash:256",
        embedding_dim=256,
    )
    payload.update(overrides)
    return ConceptEntry(**payload)


def test_concept_entry_requires_non_empty_license():
    with pytest.raises(ValidationError):
        _entry(license="")


def test_concept_citation_requires_non_empty_license():
    with pytest.raises(ValidationError):
        ConceptCitation(concept_id="abc", source=ConceptSource.local, license="")


def test_concept_search_result_score_range():
    entry = _entry()
    ConceptSearchResult(entry=entry, score=0.0)
    ConceptSearchResult(entry=entry, score=1.0)
    with pytest.raises(ValidationError):
        ConceptSearchResult(entry=entry, score=1.5)
    with pytest.raises(ValidationError):
        ConceptSearchResult(entry=entry, score=-0.1)


def test_concept_entry_round_trip():
    entry = _entry(tags=["greek", "stone"], attribution="Photo by ...")
    rebuilt = ConceptEntry.model_validate_json(entry.model_dump_json())
    assert rebuilt == entry
