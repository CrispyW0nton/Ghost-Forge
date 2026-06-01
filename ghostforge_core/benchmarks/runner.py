"""Benchmark execution + persistence.

A benchmark drives a worker through the same ``operations.workers``
dispatch path real jobs use, so timings include manifest emission,
artifact hashing, and scheduler acquisition — the things that
actually matter for end-to-end iteration speed. We deliberately don't
try to measure VRAM peaks here: that requires per-process
hooks that diverge sharply across torch versions and Linux/Windows
drivers, and is better delegated to NVIDIA Nsight or PyTorch's own
profiler.
"""

from __future__ import annotations

import json
import os
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

from ..jobs import CancelToken, ProgressReporter
from ..storage import Storage
from ..workers import Capability, WorkerRegistry
from ..workers.schemas import (
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from .schema import BenchmarkRequest, BenchmarkResult, RunSample

_CAPABILITY_REQUEST_MAP: dict[Capability, type] = {
    Capability.image_to_3d: ImageTo3DRequest,
    Capability.text_to_3d: TextTo3DRequest,
    Capability.texture_mesh: TextureMeshRequest,
    Capability.refine_mesh: RefineMeshRequest,
}


class BenchmarkStore:
    """Persists benchmark JSON files under ``data/benchmarks/``."""

    def __init__(self, storage: Storage) -> None:
        self.storage = storage
        self.root = storage.root / "benchmarks"
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, result: BenchmarkResult) -> Path:
        target = self.root / f"{result.benchmark_id}.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return target

    def load(self, benchmark_id: str) -> BenchmarkResult | None:
        target = self.root / f"{benchmark_id}.json"
        if not target.exists():
            return None
        return BenchmarkResult.model_validate_json(target.read_text(encoding="utf-8"))

    def list(self, *, limit: int = 50) -> list[BenchmarkResult]:
        if not self.root.exists():
            return []
        files = sorted(
            (p for p in self.root.iterdir() if p.suffix == ".json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        out: list[BenchmarkResult] = []
        for path in files[:limit]:
            try:
                out.append(BenchmarkResult.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return out


def _run_via_dispatcher(
    capability: Capability,
    spec: Any,
) -> dict[str, Any]:
    # Defer the import so benchmark execution doesn't pin operations on
    # registry import; matches the rest of the codebase's lazy pattern.
    from ..operations import workers as worker_ops

    if capability == Capability.image_to_3d:
        return worker_ops.run_image_to_3d(spec)
    if capability == Capability.text_to_3d:
        return worker_ops.run_text_to_3d(spec)
    if capability == Capability.texture_mesh:
        return worker_ops.run_texture_mesh(spec)
    if capability == Capability.refine_mesh:
        return worker_ops.run_refine_mesh(spec)
    raise ValueError(f"Unknown benchmark capability: {capability}")


def run_benchmark(
    request: BenchmarkRequest,
    *,
    registry: WorkerRegistry,
    store: BenchmarkStore,
    storage: Storage,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> BenchmarkResult:
    """Run ``request.runs`` invocations of a worker, time each, persist."""

    request_cls = _CAPABILITY_REQUEST_MAP.get(request.capability)
    if request_cls is None:
        raise ValueError(f"Unsupported benchmark capability: {request.capability}")

    # Default output_dir to a fresh per-run directory under data/cache/benchmarks/
    base_dir = storage.cache_dir / "benchmarks" / request.benchmark_id
    base_dir.mkdir(parents=True, exist_ok=True)

    # Verify worker advertises the capability before timing anything.
    worker = registry.get(request.worker_name)
    if request.capability not in worker.capabilities:
        raise ValueError(
            f"Worker {request.worker_name!r} does not advertise capability "
            f"{request.capability.value!r}"
        )

    # Warmup runs are not recorded.
    for warmup_index in range(request.warmup_runs):
        if cancel is not None and cancel.is_cancel_requested():
            break
        spec_dict = dict(request.spec)
        spec_dict["output_dir"] = str(base_dir / f"warmup_{warmup_index}")
        spec_dict.setdefault("worker", request.worker_name)
        spec = request_cls.model_validate(spec_dict)
        try:
            _run_via_dispatcher(request.capability, spec)
        except Exception:
            # Warmup failures are not fatal; we still want to record the
            # measured runs so the operator can see whether the worker is
            # healthy at all.
            pass

    samples: list[RunSample] = []
    backend = "skipped"
    gpu_index: int | None = None
    gpu_name: str | None = None

    for run_index in range(request.runs):
        if cancel is not None and cancel.is_cancel_requested():
            samples.append(
                RunSample(
                    index=run_index,
                    succeeded=False,
                    wall_seconds=0.0,
                    error="cancelled",
                )
            )
            break

        spec_dict = dict(request.spec)
        spec_dict["output_dir"] = str(base_dir / f"run_{run_index}")
        spec_dict.setdefault("worker", request.worker_name)
        spec = request_cls.model_validate(spec_dict)

        if reporter is not None:
            reporter(
                "benchmark.run",
                100.0 * run_index / max(request.runs, 1),
                f"run {run_index + 1}/{request.runs}",
            )

        start = time.monotonic()
        succeeded = False
        error: str | None = None
        output_mesh: Path | None = None
        output_bytes: int | None = None
        metadata: dict[str, Any] = {}
        try:
            result = _run_via_dispatcher(request.capability, spec)
            succeeded = True
            output_mesh = Path(result["output_mesh"])
            try:
                output_bytes = output_mesh.stat().st_size
            except OSError:
                output_bytes = None
            metadata = dict(result.get("metadata", {}))
            scheduler_slot = result.get("metadata", {}).get("scheduler_slot")
            # Some workers nest scheduler metadata under "metadata", but
            # the dispatch layer also stamps it onto the parameters block
            # of the manifest. Read whichever we got, else leave None.
            slot = scheduler_slot or metadata.get("scheduler_slot")
            if isinstance(slot, dict):
                backend = slot.get("backend", backend) or backend
                gpu_index = slot.get("gpu_index", gpu_index)
                gpu_name = slot.get("gpu_name", gpu_name)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        wall = max(0.0, time.monotonic() - start)

        samples.append(
            RunSample(
                index=run_index,
                succeeded=succeeded,
                wall_seconds=wall,
                error=error,
                output_mesh=output_mesh,
                output_bytes=output_bytes,
                metadata=metadata,
            )
        )

    succeeded_runs = [s for s in samples if s.succeeded]
    timings = [s.wall_seconds for s in succeeded_runs]
    summary = BenchmarkResult(
        benchmark_id=request.benchmark_id,
        worker_name=request.worker_name,
        capability=request.capability,
        runs=samples,
        runs_succeeded=len(succeeded_runs),
        runs_failed=len(samples) - len(succeeded_runs),
        wall_seconds_min=min(timings) if timings else None,
        wall_seconds_mean=statistics.fmean(timings) if timings else None,
        wall_seconds_max=max(timings) if timings else None,
        wall_seconds_stdev=(statistics.pstdev(timings) if len(timings) > 1 else 0.0) if timings else None,
        backend=backend,
        gpu_index=gpu_index,
        gpu_name=gpu_name,
        note=request.note,
    )

    store.save(summary)
    return summary


def make_benchmark_id(prefix: str = "bench") -> str:
    return f"{prefix}-{int(time.time())}-{uuid.uuid4().hex[:8]}"


__all__ = ["BenchmarkStore", "make_benchmark_id", "run_benchmark"]
