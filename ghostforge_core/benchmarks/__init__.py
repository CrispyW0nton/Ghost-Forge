"""Worker benchmarks.

Run any worker through the same dispatch path real jobs use, time it
across repeat runs, and persist a JSON report under
``data/benchmarks/`` so an operator can compare runs over time.
"""

from __future__ import annotations

from .runner import BenchmarkStore, make_benchmark_id, run_benchmark
from .schema import BenchmarkRequest, BenchmarkResult, RunSample

__all__ = [
    "BenchmarkRequest",
    "BenchmarkResult",
    "BenchmarkStore",
    "RunSample",
    "make_benchmark_id",
    "run_benchmark",
]
