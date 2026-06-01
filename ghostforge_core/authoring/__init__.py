"""Non-destructive authoring layer (P11).

Exposes:

* :class:`OperationNode` / :class:`EditGraph` — Pydantic schemas for
  modifier-stack-style edits.
* :class:`OperationRegistry` + :func:`make_operation` — pluggable
  operation directory.
* :func:`evaluate_graph` — deterministic evaluator that re-derives the
  output mesh from a graph plus its base asset.
* :class:`EditGraphStore` — file-backed persistence for graphs and
  their last evaluation reports.
* :data:`DEFAULT_OPERATIONS` — list of built-in geometry / topology /
  material operations registered at bootstrap time.
"""

from __future__ import annotations

from .bake import BAKE_OPERATIONS
from .builtins import DEFAULT_OPERATIONS
from .evaluate import evaluate_graph, evaluate_graph_streaming
from .registry import (
    Operation,
    OperationContext,
    OperationError,
    OperationRegistry,
    make_operation,
)
from .schema import (
    EditGraph,
    EvaluationResult,
    EvaluationStep,
    OperationDescriptor,
    OperationNode,
    StepStatus,
)
from .store import EditGraphStore, GraphNotFound
from .workers import SOURCE_OPERATION_KINDS, WORKER_OPERATIONS


def default_operation_registry() -> OperationRegistry:
    registry = OperationRegistry()
    registry.register_all(DEFAULT_OPERATIONS)
    registry.register_all(BAKE_OPERATIONS)
    registry.register_all(WORKER_OPERATIONS)
    return registry


__all__ = [
    "BAKE_OPERATIONS",
    "DEFAULT_OPERATIONS",
    "EditGraph",
    "EditGraphStore",
    "EvaluationResult",
    "EvaluationStep",
    "GraphNotFound",
    "Operation",
    "OperationContext",
    "OperationDescriptor",
    "OperationError",
    "OperationNode",
    "OperationRegistry",
    "SOURCE_OPERATION_KINDS",
    "StepStatus",
    "WORKER_OPERATIONS",
    "default_operation_registry",
    "evaluate_graph",
    "evaluate_graph_streaming",
    "make_operation",
]
