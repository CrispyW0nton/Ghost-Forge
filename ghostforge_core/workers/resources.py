"""Per-worker resource declarations.

Workers describe what they need *to run*: a CUDA GPU, minimum VRAM,
how much it parallelises, whether a CPU fallback exists. The
scheduler reads these declarations to decide which jobs to start
concurrently — without them every dispatch would either oversubscribe
the GPU or serialize trivially-parallel CPU work.

The declarations are deliberately conservative defaults: workers that
forget to set them get a "1 concurrent run, no GPU required" budget,
so missing metadata never *over*-uses the host.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..types import FrozenModel


class WorkerResources(FrozenModel):
    """Static resource budget for a single worker."""

    requires_cuda: bool = False
    """When True, the scheduler will refuse to dispatch on a CPU-only host."""

    min_vram_mb: int = Field(default=0, ge=0)
    """Minimum free VRAM (MB) on the chosen GPU before scheduling."""

    recommended_vram_mb: int | None = Field(default=None, ge=0)
    """Soft target VRAM (MB); used to rank multi-GPU placement."""

    max_concurrent_per_gpu: int = Field(default=1, ge=1)
    """How many simultaneous runs the scheduler allows on the same GPU."""

    cpu_fallback: bool = False
    """If the worker has a CPU code path, the scheduler may run it CPU-only."""

    cpu_concurrent: int = Field(default=2, ge=1)
    """Concurrency budget when running on CPU (no GPU bound)."""

    notes: str | None = None


DEFAULT_GPU_RESOURCES = WorkerResources(
    requires_cuda=True,
    min_vram_mb=8 * 1024,
    recommended_vram_mb=16 * 1024,
    max_concurrent_per_gpu=1,
)
"""Sensible defaults for a heavy generative worker (TRELLIS-class)."""


CPU_ONLY_RESOURCES = WorkerResources(
    requires_cuda=False,
    cpu_fallback=True,
    cpu_concurrent=2,
)
"""Sensible defaults for stub workers and anything that doesn't touch CUDA."""


__all__ = [
    "CPU_ONLY_RESOURCES",
    "DEFAULT_GPU_RESOURCES",
    "WorkerResources",
]
