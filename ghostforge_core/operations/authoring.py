"""Job handlers for non-destructive authoring graphs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghostforge_core.authoring import EditGraphStore, EvaluationResult, OperationRegistry, evaluate_graph_streaming
from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.manifest import apply_side_effects_to_manifest
from ghostforge_core.types import FrozenModel


class EvaluateGraphRequest(FrozenModel):
    graph_id: str
    input_path: Path | None = None
    output_path: Path | None = None
    output_format: str = "glb"
    fail_fast: bool = False
    manifest_dir: Path | None = None
    asset_id: str | None = None


_GRAPHS: EditGraphStore | None = None
_OPERATIONS: OperationRegistry | None = None


def set_runtime(*, graphs: EditGraphStore, operations: OperationRegistry) -> None:
    global _GRAPHS, _OPERATIONS
    _GRAPHS = graphs
    _OPERATIONS = operations


def _runtime() -> tuple[EditGraphStore, OperationRegistry]:
    if _GRAPHS is None or _OPERATIONS is None:
        raise RuntimeError(
            "Authoring runtime not initialised. Call ghostforge_core.bootstrap() "
            "before submitting graph evaluation jobs."
        )
    return _GRAPHS, _OPERATIONS


def run_evaluate_graph(
    spec: EvaluateGraphRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    graphs, operations = _runtime()
    graph = graphs.load(spec.graph_id)
    updates: dict[str, Any] = {}
    if spec.input_path is not None:
        updates["base_asset_path"] = str(spec.input_path)
    if spec.output_path is not None:
        updates["output_path"] = str(spec.output_path)
    if updates:
        graph = graph.model_copy(update=updates)
        graphs.save(graph)

    reporter and reporter("graph.started", 1.0, f"evaluating {graph.graph_id}")
    final_result: EvaluationResult | None = None
    for event in evaluate_graph_streaming(
        graph,
        registry=operations,
        output_format=spec.output_format,
        fail_fast=spec.fail_fast,
        reporter=reporter,
        cancel=cancel,
    ):
        cancel and cancel.throw_if_cancelled()
        if event.get("event") == "step":
            reporter and reporter(
                f"graph.{event.get('kind', 'step')}",
                float(event.get("progress") or 0.0),
                _event_message(event),
            )
        elif event.get("event") == "exported":
            reporter and reporter("graph.exported", 95.0, str(event.get("output_path") or ""))
        elif event.get("event") == "completed":
            final_result = EvaluationResult.model_validate(event.get("result"))

    if final_result is None:
        raise RuntimeError(f"Graph {graph.graph_id!r} did not produce an evaluation result")

    graphs.save_evaluation(final_result)
    payload = final_result.model_dump(mode="json")
    payload["graph"] = graph.model_dump(mode="json")

    side_effects = (final_result.metadata or {}).get("side_effects") or []
    if spec.manifest_dir is not None and side_effects:
        manifest = apply_side_effects_to_manifest(
            spec.manifest_dir,
            side_effects,
            asset_id=spec.asset_id,
        )
        if manifest is not None:
            payload["manifest"] = manifest.model_dump(mode="json")

    reporter and reporter("graph.completed", 100.0, final_result.status)
    return payload


def _event_message(event: dict[str, Any]) -> str:
    parts = [str(event.get("status") or "")]
    if event.get("message"):
        parts.append(str(event["message"]))
    if event.get("error"):
        parts.append(f"error: {event['error']}")
    return " ".join(part for part in parts if part).strip()


__all__ = ["EvaluateGraphRequest", "run_evaluate_graph", "set_runtime"]
