"""GhostForge knowledge base.

The KB stores **concept entries** — image references, style guides, and
project-internal notes — and answers similarity queries that ground asset
generation in real source material.

Public surface:

* :class:`KnowledgeBase` — the facade used by every adapter (Flask, MCP).
* :class:`ConceptEntry` / :class:`ConceptCitation` — Pydantic v1 models
  shared with :mod:`ghostforge_core.manifest`.
* :func:`build_knowledge_base` — selects backends from env / config so
  desktop and MCP processes are guaranteed to agree on the resolved store.

Two backends keep the system runnable without heavy ML dependencies:

* Embedders: :class:`HashEmbedder` (always available) or OpenCLIP when the
  optional ``openclip`` extra is installed.
* Vector stores: :class:`JsonVectorStore` (always available) or LanceDB
  when the optional ``lancedb`` extra is installed.

Cross-modal text↔image queries are only meaningful with a real CLIP-style
embedder; ``HashEmbedder`` is intentionally deterministic-but-coarse so
tests pass and the surface stays exercised regardless of installed extras.
"""

from __future__ import annotations

from .base import KnowledgeBase, build_knowledge_base
from .embeddings import Embedder, HashEmbedder, make_embedder
from .schema import (
    ConceptCitation,
    ConceptEntry,
    ConceptSearchResult,
    ConceptSource,
    StyleGuideEntry,
)
from .store import JsonVectorStore, VectorStore, make_vector_store

__all__ = [
    "ConceptCitation",
    "ConceptEntry",
    "ConceptSearchResult",
    "ConceptSource",
    "Embedder",
    "HashEmbedder",
    "JsonVectorStore",
    "KnowledgeBase",
    "StyleGuideEntry",
    "VectorStore",
    "build_knowledge_base",
    "make_embedder",
    "make_vector_store",
]
