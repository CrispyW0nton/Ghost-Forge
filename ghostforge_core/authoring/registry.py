"""Pluggable registry of authoring operations.

Authoring is intentionally not a closed-world enum: third parties
(plugins, future capability prompts) need to be able to register new
operations without modifying core code. The registry mirrors the
worker / engine / model patterns: a small ``Operation`` protocol, an
``OperationRegistry`` directory, and an ``OperationDescriptor`` for
listings.

Handlers receive an :class:`OperationContext` with the current
``trimesh`` object plus a parameter dict (already validated against
the handler's declared schema). They return a new ``trimesh`` —
never mutating the input — so the evaluator can rewind cleanly when
a downstream node fails.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

import trimesh

from .schema import OperationDescriptor


@dataclass
class OperationContext:
    """State passed to every operation handler at evaluation time.

    ``output_dir`` is the directory the evaluator will export the final
    mesh into (or ``None`` when evaluating in memory). Operations that
    need to write *sibling* artifacts — collision meshes, lightmap
    atlases, baked textures — should resolve them relative to this dir
    so the on-disk asset bundle stays consistent.

    ``side_effects`` is an opt-in collector. Operations that produce
    auxiliary outputs append a small dict here; the evaluator forwards
    it into ``EvaluationResult.metadata['side_effects']`` so callers
    (manifest emitter, UI) can wire them up after the run.
    """

    mesh: trimesh.Trimesh
    params: dict[str, Any]
    node_id: str
    graph_id: str
    output_dir: Any | None = None
    side_effects: list[dict[str, Any]] | None = None


class OperationError(RuntimeError):
    """Raised when an operation handler can't proceed.

    The evaluator catches this and records the failure as a per-step
    ``EvaluationStep(status="failed")`` so partial pipelines can still
    surface useful diagnostics in the UI.
    """


@runtime_checkable
class Operation(Protocol):
    """Protocol every authoring operation must satisfy."""

    descriptor: OperationDescriptor

    def __call__(self, ctx: OperationContext) -> trimesh.Trimesh:
        ...


class OperationRegistry:
    """Directory of available operations keyed by ``descriptor.kind``."""

    def __init__(self) -> None:
        self._ops: dict[str, Operation] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, operation: Operation) -> None:
        with self._lock:
            kind = operation.descriptor.kind
            self._ops[kind] = operation

    def register_all(self, operations: Iterable[Operation]) -> None:
        for op in operations:
            self.register(op)

    def unregister(self, kind: str) -> None:
        with self._lock:
            self._ops.pop(kind, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, kind: str) -> Operation:
        with self._lock:
            try:
                return self._ops[kind]
            except KeyError as exc:
                known = sorted(self._ops)
                raise KeyError(
                    f"Unknown operation kind {kind!r}. Known: {known}"
                ) from exc

    def has(self, kind: str) -> bool:
        with self._lock:
            return kind in self._ops

    def all(self) -> list[Operation]:
        with self._lock:
            return list(self._ops.values())

    def descriptors(self) -> list[OperationDescriptor]:
        with self._lock:
            return sorted(
                (op.descriptor for op in self._ops.values()),
                key=lambda d: (d.category, d.kind),
            )


def make_operation(
    *,
    kind: str,
    label: str,
    summary: str = "",
    category: str = "general",
    params_schema: dict[str, Any] | None = None,
    requires_modules: tuple[str, ...] = (),
    handler: Callable[[OperationContext], trimesh.Trimesh],
) -> Operation:
    """Convenience wrapper to bind a free function as an operation."""

    descriptor = OperationDescriptor(
        kind=kind,
        label=label,
        summary=summary,
        category=category,
        params_schema=params_schema or {},
        requires_modules=requires_modules,
    )

    class _BoundOperation:
        def __init__(self) -> None:
            self.descriptor = descriptor

        def __call__(self, ctx: OperationContext) -> trimesh.Trimesh:
            return handler(ctx)

    return _BoundOperation()


__all__ = [
    "Operation",
    "OperationContext",
    "OperationError",
    "OperationRegistry",
    "make_operation",
]
