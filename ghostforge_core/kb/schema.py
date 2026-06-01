"""Pydantic schemas for knowledge base entries and citations."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import Field

from ..types import FrozenModel, utc_now


class ConceptSource(str, Enum):
    local = "local"
    url = "url"
    openverse = "openverse"
    style_guide = "style_guide"
    project = "project"


class ConceptEntry(FrozenModel):
    """A single piece of source material the KB can return for a query.

    ``license`` is mandatory at construction time. The KB's ingestion APIs
    refuse to add an entry without one — this is the only place to enforce
    that promise consistently for every transport (Flask, MCP, scripted).
    """

    id: str
    source: ConceptSource
    title: str
    description: str = ""
    image_path: Path | None = None
    image_sha256: str | None = None
    source_url: str | None = None
    license: str = Field(min_length=1)
    license_url: str | None = None
    attribution: str | None = None
    creator: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    embedding_model: str
    embedding_dim: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConceptCitation(FrozenModel):
    """Reference to a concept embedded in an :class:`AssetManifest`.

    Citation captures the data an engine importer or licensing audit needs
    even after the source KB row is purged: title, source URL, license,
    attribution, and the role the concept played in generation.
    """

    concept_id: str
    source: ConceptSource
    title: str | None = None
    source_url: str | None = None
    license: str = Field(min_length=1)
    attribution: str | None = None
    note: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class ConceptSearchResult(FrozenModel):
    entry: ConceptEntry
    score: float = Field(ge=0.0, le=1.0)


class StyleGuideEntry(FrozenModel):
    """A piece of project-specific guidance text the KB embeds as a concept.

    Style guides bias retrieval toward in-house art direction. Stored in the
    same vector space as image concepts so a single search query can blend
    Openverse references with project notes.
    """

    title: str
    text: str
    tags: list[str] = Field(default_factory=list)


__all__ = [
    "ConceptCitation",
    "ConceptEntry",
    "ConceptSearchResult",
    "ConceptSource",
    "StyleGuideEntry",
]
