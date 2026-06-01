"""Benchmark schemas."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import Field

from ..types import FrozenModel, utc_now
from ..workers.capabilities import Capability


class BenchmarkRequest(FrozenModel):
    """Caller-supplied benchmark configuration.

    The ``spec`` payload is the same shape the worker would receive in
    production (a ``TextTo3DRequest`` etc., serialised as a dict). We
    avoid re-typing those models here so adding new capabilities never
    forces a schema update on benchmarks.
    """

    benchmark_id: str
    worker_name: str
    capability: Capability
    spec: dict[str, Any]
    runs: int = Field(default=1, ge=1, le=64)
    warmup_runs: int = Field(default=0, ge=0, le=8)
    note: str | None = None


class RunSample(FrozenModel):
    """One timed invocation of a worker."""

    index: int = Field(ge=0)
    succeeded: bool
    wall_seconds: float = Field(ge=0.0)
    error: str | None = None
    output_mesh: Path | None = None
    output_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BenchmarkResult(FrozenModel):
    """Aggregated benchmark report; persisted under data/benchmarks/."""

    benchmark_id: str
    worker_name: str
    capability: Capability
    runs: list[RunSample] = Field(default_factory=list)
    runs_succeeded: int = Field(ge=0)
    runs_failed: int = Field(ge=0)
    wall_seconds_min: float | None = None
    wall_seconds_mean: float | None = None
    wall_seconds_max: float | None = None
    wall_seconds_stdev: float | None = None
    backend: str  # "cuda" | "cpu" | "skipped"
    gpu_index: int | None = None
    gpu_name: str | None = None
    note: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)


__all__ = ["BenchmarkRequest", "BenchmarkResult", "RunSample"]
