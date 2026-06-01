"""Deterministic graph evaluator.

Given an :class:`EditGraph` and an input mesh path, produces a fresh
output mesh by applying every enabled :class:`OperationNode` in order.
The base asset is never mutated; the evaluator works on a fresh
:class:`trimesh.Trimesh` for the duration of the run.

Per-node failures don't abort the whole graph by default — instead the
evaluator captures the error in :class:`EvaluationStep` and proceeds
with the *previous* good mesh, mimicking Blender's "modifier disabled
on error" behaviour. Pass ``fail_fast=True`` to abort on the first
failure (used by CLI / agent flows where partial results are useless).

This module also exposes :func:`evaluate_graph_streaming`, a generator
twin of :func:`evaluate_graph` that yields a small dict per step. SSE
endpoints, MCP progress notifications, and UI live-preview consume
the same generator — the buffered ``evaluate_graph`` is implemented in
terms of it so the two paths can never drift.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterator

import trimesh

from .registry import OperationContext, OperationError, OperationRegistry
from .schema import (
    EditGraph,
    EvaluationResult,
    EvaluationStep,
    StepStatus,
    utc_now,
)
from .workers import SOURCE_OPERATION_KINDS


def evaluate_graph(
    graph: EditGraph,
    *,
    registry: OperationRegistry,
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    output_format: str = "glb",
    fail_fast: bool = False,
    reporter: Any | None = None,
    cancel: Any | None = None,
) -> tuple[EvaluationResult, trimesh.Trimesh | None]:
    """Run a graph over its base asset and return the evaluation report.

    Returns ``(result, mesh)`` where ``mesh`` is the post-evaluation
    trimesh (None if loading the base asset failed). Callers that just
    want the report can ignore the second element.
    """

    started = utc_now()
    started_clock = time.perf_counter()
    src = _resolve_input(graph, input_path)
    steps: list[EvaluationStep] = []

    if src is None and not _has_enabled_source_node(graph):
        return (
            EvaluationResult(
                graph_id=graph.graph_id,
                status="failed",
                output_path=None,
                output_format=output_format,
                steps=tuple(steps),
                started_at=started,
                finished_at=utc_now(),
                duration_ms=(time.perf_counter() - started_clock) * 1000,
                metadata={"error": "no input mesh path on graph or call"},
            ),
            None,
        )

    mesh: trimesh.Trimesh | None = None
    if src is not None:
        try:
            loaded = trimesh.load(str(src), process=False, force="mesh")
        except Exception as exc:
            return (
                EvaluationResult(
                    graph_id=graph.graph_id,
                    status="failed",
                    output_path=None,
                    output_format=output_format,
                    steps=tuple(steps),
                    started_at=started,
                    finished_at=utc_now(),
                    duration_ms=(time.perf_counter() - started_clock) * 1000,
                    metadata={"error": f"failed to load {src!s}: {exc}"},
                ),
                None,
            )

        if isinstance(loaded, trimesh.Scene):
            # Concatenate scene geometry into a single mesh — operations
            # are mesh-scoped at this layer; multi-mesh authoring is on
            # the P12 roadmap (cross-engine retargeting).
            meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                return (
                    EvaluationResult(
                        graph_id=graph.graph_id,
                        status="failed",
                        output_path=None,
                        output_format=output_format,
                        steps=tuple(steps),
                        started_at=started,
                        finished_at=utc_now(),
                        duration_ms=(time.perf_counter() - started_clock) * 1000,
                        metadata={"error": "scene has no Trimesh geometry"},
                    ),
                    None,
                )
            mesh = trimesh.util.concatenate(meshes)
        else:
            mesh = loaded
        if not isinstance(mesh, trimesh.Trimesh):
            return (
                EvaluationResult(
                    graph_id=graph.graph_id,
                    status="failed",
                    output_path=None,
                    output_format=output_format,
                    steps=tuple(steps),
                    started_at=started,
                    finished_at=utc_now(),
                    duration_ms=(time.perf_counter() - started_clock) * 1000,
                    metadata={"error": f"unexpected mesh type {type(mesh).__name__}"},
                ),
                None,
            )

    out_path = _resolve_output(graph, output_path, output_format)
    eval_output_dir = out_path.parent if out_path is not None else None
    side_effects: list[dict[str, Any]] = []

    overall_status: StepStatus = "succeeded"
    for node in graph.nodes:
        if cancel is not None:
            cancel.throw_if_cancelled()
        if not node.enabled:
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="skipped",
                    duration_ms=0.0,
                    message="node disabled",
                )
            )
            continue
        if not registry.has(node.kind):
            err = f"unknown operation kind {node.kind!r}"
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=0.0,
                    error=err,
                )
            )
            overall_status = "failed"
            if fail_fast:
                break
            continue

        op = registry.get(node.kind)
        ctx = OperationContext(
            mesh=mesh,
            params=dict(node.params),
            node_id=node.id,
            graph_id=graph.graph_id,
            output_dir=eval_output_dir,
            side_effects=side_effects,
            reporter=reporter,
            cancel=cancel,
        )
        node_started = time.perf_counter()
        try:
            new_mesh = op(ctx)
        except OperationError as exc:
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=(time.perf_counter() - node_started) * 1000,
                    error=str(exc),
                )
            )
            overall_status = "failed"
            if fail_fast:
                break
            continue
        except Exception as exc:  # pragma: no cover — defensive
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=(time.perf_counter() - node_started) * 1000,
                    error=f"unexpected error: {exc}",
                )
            )
            overall_status = "failed"
            if fail_fast:
                break
            continue

        if not isinstance(new_mesh, trimesh.Trimesh):
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=(time.perf_counter() - node_started) * 1000,
                    error=f"handler returned {type(new_mesh).__name__}, not Trimesh",
                )
            )
            overall_status = "failed"
            if fail_fast:
                break
            continue

        mesh = new_mesh
        steps.append(
            EvaluationStep(
                node_id=node.id,
                kind=node.kind,
                status="succeeded",
                duration_ms=(time.perf_counter() - node_started) * 1000,
                message=f"vertices={len(mesh.vertices)} faces={len(mesh.faces)}",
            )
        )

    if out_path is not None and overall_status != "failed" and mesh is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mesh.export(str(out_path))
        except Exception as exc:
            steps.append(
                EvaluationStep(
                    node_id="__export__",
                    kind="export",
                    status="failed",
                    duration_ms=0.0,
                    error=f"export to {out_path}: {exc}",
                )
            )
            overall_status = "failed"

    finished = utc_now()
    return (
        EvaluationResult(
            graph_id=graph.graph_id,
            status=overall_status,
            output_path=str(out_path) if out_path is not None else None,
            output_format=output_format,
            steps=tuple(steps),
            started_at=started,
            finished_at=finished,
            duration_ms=(time.perf_counter() - started_clock) * 1000,
            metadata=_mesh_metadata(mesh, side_effects, src=src),
        ),
        mesh,
    )


def _resolve_input(graph: EditGraph, override: str | Path | None) -> Path | None:
    src: Any = override or graph.base_asset_path
    return Path(src) if src else None


def _has_enabled_source_node(graph: EditGraph) -> bool:
    return any(node.enabled and node.kind in SOURCE_OPERATION_KINDS for node in graph.nodes)


def _mesh_metadata(mesh: trimesh.Trimesh | None, side_effects: list[dict[str, Any]], *, src: Path | None) -> dict[str, Any]:
    return {
        "vertices": int(len(mesh.vertices)) if mesh is not None else 0,
        "faces": int(len(mesh.faces)) if mesh is not None else 0,
        "side_effects": list(side_effects),
        "source_mode": "operation" if src is None else "base_asset",
    }


def _resolve_output(
    graph: EditGraph,
    override: str | Path | None,
    output_format: str,
) -> Path | None:
    candidate: Any = override or graph.output_path
    if not candidate:
        return None
    path = Path(candidate)
    fmt = output_format.lstrip(".")
    if path.suffix.lower() != f".{fmt.lower()}":
        path = path.with_suffix(f".{fmt}")
    return path


# ---------------------------------------------------------------------------
# Streaming evaluator
# ---------------------------------------------------------------------------


def evaluate_graph_streaming(
    graph: EditGraph,
    *,
    registry: OperationRegistry,
    input_path: str | Path | None = None,
    output_path: str | Path | None = None,
    output_format: str = "glb",
    fail_fast: bool = False,
    reporter: Any | None = None,
    cancel: Any | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield evaluation events as the graph runs.

    Event kinds:

    * ``{"event": "started", "graph_id": ..., "node_count": N}``
    * ``{"event": "step", "node_id": ..., "kind": ..., "status": ...,
      "duration_ms": ..., "message": ..., "error": ...,
      "vertex_count": ..., "face_count": ..., "progress": 0..100}``
    * ``{"event": "exported", "output_path": ...}``
    * ``{"event": "completed", "result": <EvaluationResult.model_dump>}``

    Consumers should treat unknown event kinds as opaque (forward-compat).

    The generator is not re-entrant — start a fresh one per evaluation.
    """

    started = utc_now()
    started_clock = time.perf_counter()
    src = _resolve_input(graph, input_path)
    steps: list[EvaluationStep] = []
    out_path = _resolve_output(graph, output_path, output_format)
    eval_output_dir = out_path.parent if out_path is not None else None
    side_effects: list[dict[str, Any]] = []

    def _final(status: StepStatus, error: str | None = None, mesh: trimesh.Trimesh | None = None) -> dict[str, Any]:
        result = EvaluationResult(
            graph_id=graph.graph_id,
            status=status,
            output_path=str(out_path) if out_path is not None and status != "failed" else None,
            output_format=output_format,
            steps=tuple(steps),
            started_at=started,
            finished_at=utc_now(),
            duration_ms=(time.perf_counter() - started_clock) * 1000,
            metadata=(
                {"error": error}
                if error is not None
                else _mesh_metadata(mesh, side_effects, src=src)
            ),
        )
        return {"event": "completed", "result": result.model_dump(mode="json")}

    yield {
        "event": "started",
        "graph_id": graph.graph_id,
        "node_count": len(graph.nodes),
        "asset_path": str(src) if src is not None else None,
    }

    if src is None and not _has_enabled_source_node(graph):
        yield _final("failed", error="no input mesh path on graph or call")
        return

    mesh: trimesh.Trimesh | None = None
    if src is not None:
        try:
            loaded = trimesh.load(str(src), process=False, force="mesh")
        except Exception as exc:
            yield _final("failed", error=f"failed to load {src!s}: {exc}")
            return

        if isinstance(loaded, trimesh.Scene):
            meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                yield _final("failed", error="scene has no Trimesh geometry")
                return
            mesh = trimesh.util.concatenate(meshes)
        else:
            mesh = loaded
        if not isinstance(mesh, trimesh.Trimesh):
            yield _final("failed", error=f"unexpected mesh type {type(mesh).__name__}")
            return

    overall_status: StepStatus = "succeeded"
    total_nodes = max(len(graph.nodes), 1)
    for index, node in enumerate(graph.nodes):
        if cancel is not None:
            cancel.throw_if_cancelled()
        progress = (index / total_nodes) * 100.0

        if not node.enabled:
            step = EvaluationStep(
                node_id=node.id,
                kind=node.kind,
                status="skipped",
                duration_ms=0.0,
                message="node disabled",
            )
            steps.append(step)
            yield {
                "event": "step",
                "node_id": node.id,
                "kind": node.kind,
                "status": "skipped",
                "duration_ms": 0.0,
                "message": "node disabled",
                "progress": progress,
                "vertex_count": int(len(mesh.vertices)) if mesh is not None else 0,
                "face_count": int(len(mesh.faces)) if mesh is not None else 0,
            }
            continue
        if not registry.has(node.kind):
            err = f"unknown operation kind {node.kind!r}"
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=0.0,
                    error=err,
                )
            )
            yield {
                "event": "step",
                "node_id": node.id,
                "kind": node.kind,
                "status": "failed",
                "duration_ms": 0.0,
                "error": err,
                "progress": progress,
            }
            overall_status = "failed"
            if fail_fast:
                break
            continue

        op = registry.get(node.kind)
        ctx = OperationContext(
            mesh=mesh,
            params=dict(node.params),
            node_id=node.id,
            graph_id=graph.graph_id,
            output_dir=eval_output_dir,
            side_effects=side_effects,
            reporter=reporter,
            cancel=cancel,
        )
        node_started = time.perf_counter()
        try:
            new_mesh = op(ctx)
        except OperationError as exc:
            duration = (time.perf_counter() - node_started) * 1000
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=duration,
                    error=str(exc),
                )
            )
            yield {
                "event": "step",
                "node_id": node.id,
                "kind": node.kind,
                "status": "failed",
                "duration_ms": duration,
                "error": str(exc),
                "progress": progress,
            }
            overall_status = "failed"
            if fail_fast:
                break
            continue
        except Exception as exc:  # pragma: no cover — defensive
            duration = (time.perf_counter() - node_started) * 1000
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=duration,
                    error=f"unexpected error: {exc}",
                )
            )
            yield {
                "event": "step",
                "node_id": node.id,
                "kind": node.kind,
                "status": "failed",
                "duration_ms": duration,
                "error": f"unexpected error: {exc}",
                "progress": progress,
            }
            overall_status = "failed"
            if fail_fast:
                break
            continue

        if not isinstance(new_mesh, trimesh.Trimesh):
            duration = (time.perf_counter() - node_started) * 1000
            err = f"handler returned {type(new_mesh).__name__}, not Trimesh"
            steps.append(
                EvaluationStep(
                    node_id=node.id,
                    kind=node.kind,
                    status="failed",
                    duration_ms=duration,
                    error=err,
                )
            )
            yield {
                "event": "step",
                "node_id": node.id,
                "kind": node.kind,
                "status": "failed",
                "duration_ms": duration,
                "error": err,
                "progress": progress,
            }
            overall_status = "failed"
            if fail_fast:
                break
            continue

        mesh = new_mesh
        duration = (time.perf_counter() - node_started) * 1000
        msg = f"vertices={len(mesh.vertices)} faces={len(mesh.faces)}"
        steps.append(
            EvaluationStep(
                node_id=node.id,
                kind=node.kind,
                status="succeeded",
                duration_ms=duration,
                message=msg,
            )
        )
        yield {
            "event": "step",
            "node_id": node.id,
            "kind": node.kind,
            "status": "succeeded",
            "duration_ms": duration,
            "message": msg,
            "progress": ((index + 1) / total_nodes) * 100.0,
            "vertex_count": int(len(mesh.vertices)),
            "face_count": int(len(mesh.faces)),
        }

    if out_path is not None and overall_status != "failed" and mesh is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            mesh.export(str(out_path))
            yield {"event": "exported", "output_path": str(out_path)}
        except Exception as exc:
            steps.append(
                EvaluationStep(
                    node_id="__export__",
                    kind="export",
                    status="failed",
                    duration_ms=0.0,
                    error=f"export to {out_path}: {exc}",
                )
            )
            overall_status = "failed"

    yield _final(overall_status, mesh=mesh)


__all__ = ["evaluate_graph", "evaluate_graph_streaming"]
