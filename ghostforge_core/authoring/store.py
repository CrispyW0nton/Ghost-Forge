"""File-backed persistence for edit graphs.

Each graph lives at ``data/graphs/<graph_id>.json``; the optional last
evaluation report sits next to it as ``<graph_id>.evaluation.json``.
Atomic writes via ``os.replace`` so a crashed agent never leaves a
half-serialised graph behind — the renderer would refuse to load it
otherwise.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

from ..storage import Storage
from .schema import EditGraph, EvaluationResult


class GraphNotFound(KeyError):
    pass


class EditGraphStore:
    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.dir = storage.root / "graphs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def graph_path(self, graph_id: str) -> Path:
        _validate_graph_id(graph_id)
        return self.dir / f"{graph_id}.json"

    def evaluation_path(self, graph_id: str) -> Path:
        _validate_graph_id(graph_id)
        return self.dir / f"{graph_id}.evaluation.json"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def make_id(self, prefix: str = "graph") -> str:
        return f"{prefix}-{uuid.uuid4().hex[:12]}"

    def save(self, graph: EditGraph) -> EditGraph:
        path = self.graph_path(graph.graph_id)
        with self._lock:
            self._atomic_write(path, graph.model_dump_json(indent=2))
        return graph

    def load(self, graph_id: str) -> EditGraph:
        path = self.graph_path(graph_id)
        if not path.exists():
            raise GraphNotFound(graph_id)
        return EditGraph.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[EditGraph]:
        out: list[EditGraph] = []
        if not self.dir.exists():
            return out
        for entry in sorted(self.dir.glob("*.json")):
            if entry.name.endswith(".evaluation.json"):
                continue
            try:
                out.append(EditGraph.model_validate_json(entry.read_text(encoding="utf-8")))
            except Exception:
                # Refuse to fail a list operation on a single corrupt
                # entry — the UI would otherwise be unable to surface
                # *any* graphs to the user.
                continue
        return out

    def delete(self, graph_id: str) -> None:
        path = self.graph_path(graph_id)
        if not path.exists():
            raise GraphNotFound(graph_id)
        with self._lock:
            try:
                path.unlink()
            except OSError:
                pass
            eval_path = self.evaluation_path(graph_id)
            if eval_path.exists():
                try:
                    eval_path.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Evaluation reports
    # ------------------------------------------------------------------

    def save_evaluation(self, result: EvaluationResult) -> None:
        path = self.evaluation_path(result.graph_id)
        with self._lock:
            self._atomic_write(path, result.model_dump_json(indent=2))

    def load_evaluation(self, graph_id: str) -> EvaluationResult | None:
        path = self.evaluation_path(graph_id)
        if not path.exists():
            return None
        try:
            return EvaluationResult.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _atomic_write(self, path: Path, payload: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)


_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _validate_graph_id(graph_id: str) -> None:
    if not graph_id or not _ID_RE.match(graph_id):
        raise ValueError(
            f"invalid graph id {graph_id!r}; expected [A-Za-z0-9._-]+"
        )


__all__ = ["EditGraphStore", "GraphNotFound"]
