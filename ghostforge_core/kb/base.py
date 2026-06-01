"""KnowledgeBase facade.

The facade is the only public ingestion + retrieval path used by Flask, MCP,
and tests. It owns:

* the embedder (text + image vectorisation),
* the vector store (persistence + similarity),
* the on-disk image cache (so concept downloads survive restart),
* license enforcement (every entry must declare a license),
* citation helpers used by manifest tooling.
"""

from __future__ import annotations

import hashlib
import io
import os
import uuid
from pathlib import Path
from typing import Any

from .embeddings import Embedder, make_embedder
from .schema import (
    ConceptCitation,
    ConceptEntry,
    ConceptSearchResult,
    ConceptSource,
    StyleGuideEntry,
)
from .store import VectorStore, make_vector_store


class KnowledgeBase:
    """Single source of truth for KB operations."""

    def __init__(
        self,
        store: VectorStore,
        embedder: Embedder,
        image_dir: Path | str,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.image_dir = Path(image_dir)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def backend(self) -> str:
        return self.store.name

    @property
    def embedding_model(self) -> str:
        return self.embedder.name

    @property
    def embedding_dim(self) -> int:
        return self.embedder.dim

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_license(license_value: str | None) -> str:
        # License enforcement is the single most important promise of the
        # KB. It is enforced here once instead of at every transport.
        if not license_value or not license_value.strip():
            raise ValueError(
                "Knowledge base entries require a non-empty license. "
                "Use 'CC0-1.0' for public-domain assets, an SPDX identifier "
                "for licensed work, or 'project-internal' for in-house notes."
            )
        return license_value.strip()

    def _store_image(self, data: bytes, suffix: str = ".bin") -> tuple[Path, str]:
        digest = hashlib.sha256(data).hexdigest()
        target = self.image_dir / f"{digest}{suffix}"
        if not target.exists():
            target.write_bytes(data)
        return target, digest

    @staticmethod
    def _detect_suffix(data: bytes, hint: str | None = None) -> str:
        if hint:
            return hint if hint.startswith(".") else f".{hint}"
        # Cheap magic-byte sniffing covers the formats Openverse / casual user
        # uploads return; fall back to ``.bin`` so the cache stays accurate
        # even for unknown formats.
        if data.startswith(b"\x89PNG"):
            return ".png"
        if data[:3] == b"\xff\xd8\xff":
            return ".jpg"
        if data[:4] == b"GIF8":
            return ".gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        return ".bin"

    # ------------------------------------------------------------------
    # Add / ingest APIs
    # ------------------------------------------------------------------

    def add_image(
        self,
        *,
        image_bytes: bytes,
        title: str,
        license: str,
        source: ConceptSource = ConceptSource.local,
        description: str = "",
        source_url: str | None = None,
        license_url: str | None = None,
        attribution: str | None = None,
        creator: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        suffix_hint: str | None = None,
        concept_id: str | None = None,
    ) -> ConceptEntry:
        license_clean = self._require_license(license)
        suffix = self._detect_suffix(image_bytes, suffix_hint)
        cached_path, sha = self._store_image(image_bytes, suffix=suffix)
        vector = self.embedder.embed_image_bytes(image_bytes)
        entry = ConceptEntry(
            id=concept_id or uuid.uuid4().hex,
            source=source,
            title=title,
            description=description,
            image_path=cached_path,
            image_sha256=sha,
            source_url=source_url,
            license=license_clean,
            license_url=license_url,
            attribution=attribution,
            creator=creator,
            tags=list(tags or []),
            embedding_model=self.embedder.name,
            embedding_dim=self.embedder.dim,
            metadata=dict(metadata or {}),
        )
        self.store.add(entry, vector)
        return entry

    def add_image_path(
        self,
        path: Path | str,
        *,
        title: str,
        license: str,
        **kwargs: Any,
    ) -> ConceptEntry:
        data = Path(path).read_bytes()
        suffix_hint = kwargs.pop("suffix_hint", Path(path).suffix or None)
        return self.add_image(
            image_bytes=data,
            title=title,
            license=license,
            suffix_hint=suffix_hint,
            **kwargs,
        )

    def add_text(
        self,
        *,
        text: str,
        title: str,
        license: str,
        source: ConceptSource = ConceptSource.style_guide,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        concept_id: str | None = None,
    ) -> ConceptEntry:
        license_clean = self._require_license(license)
        if not text.strip():
            raise ValueError("Cannot ingest empty text into the knowledge base")
        vector = self.embedder.embed_text(text)
        entry = ConceptEntry(
            id=concept_id or uuid.uuid4().hex,
            source=source,
            title=title,
            description=text,
            image_path=None,
            image_sha256=None,
            source_url=None,
            license=license_clean,
            tags=list(tags or []),
            embedding_model=self.embedder.name,
            embedding_dim=self.embedder.dim,
            metadata=dict(metadata or {}),
        )
        self.store.add(entry, vector)
        return entry

    def add_style_guide(self, guide: StyleGuideEntry, license: str = "project-internal") -> ConceptEntry:
        return self.add_text(
            text=guide.text,
            title=guide.title,
            license=license,
            source=ConceptSource.style_guide,
            tags=guide.tags,
        )

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search_text(
        self,
        query: str,
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]:
        vector = self.embedder.embed_text(query)
        return self.store.search(vector, k=k, sources=sources, tags=tags)

    def search_image_bytes(
        self,
        data: bytes,
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]:
        vector = self.embedder.embed_image_bytes(data)
        return self.store.search(vector, k=k, sources=sources, tags=tags)

    def search_image_path(
        self,
        path: Path | str,
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]:
        return self.search_image_bytes(
            Path(path).read_bytes(), k=k, sources=sources, tags=tags
        )

    # ------------------------------------------------------------------
    # Direct accessors
    # ------------------------------------------------------------------

    def get(self, concept_id: str) -> ConceptEntry:
        return self.store.get(concept_id)

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        sources: list[ConceptSource] | None = None,
    ) -> list[ConceptEntry]:
        return self.store.list(limit=limit, offset=offset, sources=sources)

    def count(self) -> int:
        return self.store.count()

    def delete(self, concept_id: str) -> None:
        self.store.delete(concept_id)

    # ------------------------------------------------------------------
    # Citation helpers
    # ------------------------------------------------------------------

    def make_citation(
        self,
        concept_id: str,
        note: str | None = None,
        score: float | None = None,
    ) -> ConceptCitation:
        entry = self.get(concept_id)
        return ConceptCitation(
            concept_id=entry.id,
            source=entry.source,
            title=entry.title,
            source_url=entry.source_url,
            license=entry.license,
            attribution=entry.attribution,
            note=note,
            score=score,
        )


def build_knowledge_base(
    data_root: Path | str,
    *,
    backend: str | None = None,
    embedder_name: str | None = None,
) -> KnowledgeBase:
    """Construct a KB rooted at ``data_root/kb`` using the requested backends.

    Defaults follow the env-var precedence in :func:`make_embedder` and
    :func:`make_vector_store`, which is what the bootstrap uses so desktop
    and MCP processes pick the same stack.
    """
    kb_root = Path(data_root) / "kb"
    kb_root.mkdir(parents=True, exist_ok=True)
    image_dir = kb_root / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    embedder = make_embedder(embedder_name)
    store = make_vector_store(kb_root, backend=backend)
    return KnowledgeBase(store=store, embedder=embedder, image_dir=image_dir)


__all__ = ["KnowledgeBase", "build_knowledge_base"]
