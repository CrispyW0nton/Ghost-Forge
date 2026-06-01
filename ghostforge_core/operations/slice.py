"""Operation handler that runs a planned vertical slice.

The slice executor wants references to the KB, engine registry, and
slice store; rather than threading those through the JobRunner's spec,
the bootstrap layer registers them via :func:`set_runtime` so this
module can fetch them when the JobRunner dispatches a slice job.
"""

from __future__ import annotations

from typing import Any

from ..engines import EngineRegistry
from ..jobs import CancelToken, ProgressReporter
from ..kb import KnowledgeBase
from ..slice import SliceStore, execute_vertical_slice
from ..types import ExecuteVerticalSliceRequest


_KB: KnowledgeBase | None = None
_ENGINES: EngineRegistry | None = None
_STORE: SliceStore | None = None


def set_runtime(
    *,
    kb: KnowledgeBase,
    engines: EngineRegistry,
    store: SliceStore,
) -> None:
    global _KB, _ENGINES, _STORE
    _KB = kb
    _ENGINES = engines
    _STORE = store


def _runtime():
    if _KB is None or _ENGINES is None or _STORE is None:
        raise RuntimeError(
            "Slice runtime not initialised. Call ghostforge_core.bootstrap() "
            "before submitting vertical-slice jobs."
        )
    return _KB, _ENGINES, _STORE


def run_execute_slice(
    spec: ExecuteVerticalSliceRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    kb, engines, store = _runtime()
    plan = store.load_plan(spec.slice_id)
    run = execute_vertical_slice(
        plan,
        store=store,
        kb=kb,
        engines=engines,
        reporter=reporter,
        cancel=cancel,
    )
    return run.model_dump(mode="json")


__all__ = ["run_execute_slice", "set_runtime"]
