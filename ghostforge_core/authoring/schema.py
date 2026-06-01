"""Pydantic schemas for the non-destructive authoring layer.

The authoring stack is GhostForge's answer to "Blender modifiers" and
"Houdini SOP networks". Edits never mutate the base mesh — instead
they accumulate as :class:`OperationNode` entries on an
:class:`EditGraph`. Re-evaluating the graph is a deterministic function
of the input asset plus the ordered, enabled node list.

Why a flat ordered list rather than a true DAG:

* 95% of authoring operations are linear (modifier stack semantics).
* The flat shape is trivial to surface in the UI as a draggable list.
* True DAG support can be layered on later by adding ``inputs`` /
  ``outputs`` fields to :class:`OperationNode` without breaking the
  current schema.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class OperationNode(FrozenModel):
    """A single non-destructive edit operation in an :class:`EditGraph`.

    Nodes are immutable: reordering or parameter edits create a new
    node with the same ``id`` and a new revision. The :class:`EditGraph`
    container is also immutable so concurrent agents (e.g. an MCP
    client and the desktop UI) never see a half-mutated graph.
    """

    id: str = Field(min_length=1, max_length=64)
    kind: str  # OperationKind value; kept as plain str so the registry
               # is the source of truth, not an enum that has to ship
               # with every kind we add.
    label: str = ""
    enabled: bool = True
    params: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class EditGraph(FrozenModel):
    """Ordered list of operation nodes layered onto a base asset.

    The graph captures *intent* rather than result; calling
    :func:`ghostforge_core.authoring.evaluate.evaluate_graph` re-derives
    the output mesh from this graph plus the input asset.

    Stored under ``data/graphs/<graph_id>.json``.
    """

    graph_id: str = Field(min_length=1, max_length=64)
    asset_id: str | None = None  # optional link to a source asset
    name: str = ""
    description: str = ""
    nodes: tuple[OperationNode, ...] = Field(default_factory=tuple)
    base_asset_path: str | None = None
    output_path: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = 1

    def with_nodes(self, nodes: list[OperationNode]) -> "EditGraph":
        return self.model_copy(
            update={
                "nodes": tuple(nodes),
                "updated_at": utc_now(),
                "version": self.version + 1,
            }
        )


class EvaluationStepStatus:
    """Sentinel-style class for the literal type below."""

    SKIPPED = "skipped"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


StepStatus = Literal["skipped", "succeeded", "failed"]


class EvaluationStep(FrozenModel):
    """Per-node outcome captured during a graph evaluation."""

    node_id: str
    kind: str
    status: StepStatus
    duration_ms: float = 0.0
    message: str | None = None
    error: str | None = None


class EvaluationResult(FrozenModel):
    """Top-level outcome of :func:`evaluate_graph`.

    Persisted alongside the graph so the desktop UI can render the
    last-known evaluation state without re-running the pipeline. The
    output mesh path is recorded so consumers (audit, engine handoff,
    UI viewport) know where to load the post-evaluation result from.
    """

    graph_id: str
    status: StepStatus = "succeeded"
    output_path: str | None = None
    output_format: str = "glb"
    steps: tuple[EvaluationStep, ...] = Field(default_factory=tuple)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationDescriptor(FrozenModel):
    """Self-describing metadata for a registered operation handler.

    Surfaces in the UI palette and the MCP ``list_operations`` tool so
    agents can discover which operation kinds exist, what each does,
    and what parameters they accept.
    """

    kind: str
    label: str
    summary: str = ""
    category: str = "general"
    params_schema: dict[str, Any] = Field(default_factory=dict)
    requires_modules: tuple[str, ...] = ()


__all__ = [
    "EditGraph",
    "EvaluationResult",
    "EvaluationStep",
    "OperationDescriptor",
    "OperationNode",
    "StepStatus",
    "utc_now",
]
