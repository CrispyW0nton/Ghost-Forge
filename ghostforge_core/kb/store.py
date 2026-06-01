"""Vector stores backing the GhostForge knowledge base.

`VectorStore` is the storage protocol the KB uses; it intentionally hides
the embedding type so adapters can swap between LanceDB-backed vectors,
the always-available JSON brute-force store, or future remote stores.

Both implementations persist enough metadata that a fresh process can
rebuild a :class:`KnowledgeBase` against the same on-disk state.
"""

from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Protocol, runtime_checkable

from .schema import ConceptEntry, ConceptSearchResult, ConceptSource


@runtime_checkable
class VectorStore(Protocol):
    """Common surface for storing and querying concept vectors."""

    name: str

    def add(self, entry: ConceptEntry, vector: list[float]) -> None: ...
    def search(
        self,
        vector: list[float],
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]: ...
    def get(self, concept_id: str) -> ConceptEntry: ...
    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        sources: list[ConceptSource] | None = None,
    ) -> list[ConceptEntry]: ...
    def count(self) -> int: ...
    def delete(self, concept_id: str) -> None: ...


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise ValueError(f"Vector dim mismatch: {len(a)} vs {len(b)}")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class JsonVectorStore:
    """Brute-force JSON-backed vector store.

    Trades query speed for zero dependencies and trivial inspection (the
    underlying ``concepts.json`` file is human-readable). Linear-scan search
    is fine for the few hundred concepts a vertical slice typically pulls
    from Openverse plus a handful of project style guides.

    Entries are stored as ``{entry: serialised, vector: [...]}`` records and
    persisted on every mutation. A reader-writer lock prevents corruption
    when the desktop and MCP processes share a data root.
    """

    name = "json"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: dict[str, tuple[ConceptEntry, list[float]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # Corrupt sidecars are extremely rare but recoverable: archive
            # the bad file and start fresh rather than refusing to boot.
            backup = self.path.with_suffix(self.path.suffix + ".corrupt")
            self.path.rename(backup)
            return
        for record in raw.get("records", []):
            entry = ConceptEntry.model_validate(record["entry"])
            vector = list(record["vector"])
            self._records[entry.id] = (entry, vector)

    def _persist(self) -> None:
        payload = {
            "version": "1",
            "records": [
                {
                    "entry": entry.model_dump(mode="json"),
                    "vector": vector,
                }
                for entry, vector in self._records.values()
            ],
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, self.path)

    def add(self, entry: ConceptEntry, vector: list[float]) -> None:
        with self._lock:
            self._records[entry.id] = (entry, list(vector))
            self._persist()

    def get(self, concept_id: str) -> ConceptEntry:
        with self._lock:
            if concept_id not in self._records:
                raise KeyError(concept_id)
            return self._records[concept_id][0]

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        sources: list[ConceptSource] | None = None,
    ) -> list[ConceptEntry]:
        with self._lock:
            entries = [entry for entry, _ in self._records.values()]
        entries.sort(key=lambda e: e.created_at, reverse=True)
        if sources:
            allowed = set(sources)
            entries = [e for e in entries if e.source in allowed]
        return entries[offset : offset + limit]

    def count(self) -> int:
        with self._lock:
            return len(self._records)

    def delete(self, concept_id: str) -> None:
        with self._lock:
            self._records.pop(concept_id, None)
            self._persist()

    def search(
        self,
        vector: list[float],
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]:
        allowed_sources = set(sources) if sources else None
        required_tags = set(tags) if tags else None
        with self._lock:
            scored: list[tuple[ConceptEntry, float]] = []
            for entry, stored in self._records.values():
                if allowed_sources is not None and entry.source not in allowed_sources:
                    continue
                if required_tags is not None and not required_tags.issubset(set(entry.tags)):
                    continue
                similarity = _cosine(vector, stored)
                # Cosine ∈ [-1, 1]; scale into [0, 1] so the API contract is
                # uniform regardless of how the underlying store ranks.
                scored.append((entry, max(0.0, (similarity + 1.0) / 2.0)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [
            ConceptSearchResult(entry=entry, score=score)
            for entry, score in scored[:k]
        ]


class LanceDBVectorStore:  # pragma: no cover - optional, exercised manually
    """LanceDB-backed vector store.

    Active only when the ``lancedb`` extra is installed. Schema is identical
    to :class:`JsonVectorStore` so a deployment can migrate between them by
    re-ingesting.
    """

    name = "lancedb"

    def __init__(self, path: Path | str) -> None:
        try:
            import lancedb
        except ImportError as exc:
            raise RuntimeError(
                "LanceDB requested but not installed. "
                "Install the `kb` extras to enable it."
            ) from exc

        self._lancedb = lancedb
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.path))
        self._table_name = "concepts"
        self._table = None

    def _ensure_table(self, vector_dim: int) -> Any:
        import pyarrow as pa

        if self._table is not None:
            return self._table
        if self._table_name in self._db.table_names():
            self._table = self._db.open_table(self._table_name)
            return self._table

        schema = pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("entry_json", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), vector_dim)),
                pa.field("source", pa.string()),
                pa.field("tags", pa.list_(pa.string())),
            ]
        )
        self._table = self._db.create_table(self._table_name, schema=schema)
        return self._table

    def add(self, entry: ConceptEntry, vector: list[float]) -> None:
        table = self._ensure_table(len(vector))
        table.delete(f"id = '{entry.id}'")
        table.add(
            [
                {
                    "id": entry.id,
                    "entry_json": entry.model_dump_json(),
                    "vector": vector,
                    "source": entry.source.value,
                    "tags": list(entry.tags),
                }
            ]
        )

    def _open(self) -> Any:
        if self._table is not None:
            return self._table
        if self._table_name in self._db.table_names():
            self._table = self._db.open_table(self._table_name)
            return self._table
        return None

    def search(
        self,
        vector: list[float],
        k: int = 5,
        sources: list[ConceptSource] | None = None,
        tags: list[str] | None = None,
    ) -> list[ConceptSearchResult]:
        table = self._open()
        if table is None:
            return []
        builder = table.search(vector).limit(k)
        if sources:
            allowed = ", ".join(f"'{s.value}'" for s in sources)
            builder = builder.where(f"source IN ({allowed})")
        rows = builder.to_list()
        results: list[ConceptSearchResult] = []
        for row in rows:
            entry = ConceptEntry.model_validate_json(row["entry_json"])
            if tags:
                if not set(tags).issubset(set(entry.tags)):
                    continue
            distance = float(row.get("_distance", 0.0))
            score = max(0.0, 1.0 - distance / 2.0)
            results.append(ConceptSearchResult(entry=entry, score=score))
        return results

    def get(self, concept_id: str) -> ConceptEntry:
        table = self._open()
        if table is None:
            raise KeyError(concept_id)
        df = table.search().where(f"id = '{concept_id}'").limit(1).to_list()
        if not df:
            raise KeyError(concept_id)
        return ConceptEntry.model_validate_json(df[0]["entry_json"])

    def list(
        self,
        limit: int = 50,
        offset: int = 0,
        sources: list[ConceptSource] | None = None,
    ) -> list[ConceptEntry]:
        table = self._open()
        if table is None:
            return []
        builder = table.search()
        if sources:
            allowed = ", ".join(f"'{s.value}'" for s in sources)
            builder = builder.where(f"source IN ({allowed})")
        rows = builder.limit(limit + offset).to_list()
        entries = [ConceptEntry.model_validate_json(row["entry_json"]) for row in rows]
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries[offset : offset + limit]

    def count(self) -> int:
        table = self._open()
        return 0 if table is None else int(table.count_rows())

    def delete(self, concept_id: str) -> None:
        table = self._open()
        if table is not None:
            table.delete(f"id = '{concept_id}'")


def make_vector_store(path: Path | str, backend: str | None = None) -> VectorStore:
    """Resolve a vector store from the requested backend name.

    Resolution: explicit ``backend`` ⇒ ``GHOSTFORGE_KB_BACKEND`` env ⇒ ``json``.
    """
    target = (backend or os.environ.get("GHOSTFORGE_KB_BACKEND") or "json").lower()
    base = Path(path)
    if target == "json":
        return JsonVectorStore(base / "concepts.json")
    if target in {"lance", "lancedb"}:
        return LanceDBVectorStore(base / "concepts.lance")
    raise ValueError(f"Unknown vector store backend: {backend!r}")


__all__ = [
    "JsonVectorStore",
    "LanceDBVectorStore",
    "VectorStore",
    "make_vector_store",
]
