"""Pluggable model workers for GhostForge.

A *worker* wraps a single generative-3D model (TRELLIS, Hunyuan3D, TripoSG,
InstantMesh, Paint3D, SyncMVD, …) behind a uniform contract so the rest of
the system never has to know which model produced a given asset.

Two design goals shape everything in this package:

1. **Isolation.** Heavy imports (torch, custom CUDA ops, model-specific
   Python repos) are only triggered inside ``probe()`` and ``run()``.
   Importing :mod:`ghostforge_core.workers` itself remains cheap, so the
   desktop app and MCP server boot in the same time regardless of which
   GPU stack is installed on the host.

2. **Honesty about availability.** Every worker has a real
   :meth:`~Worker.probe` that reports whether it is runnable on this host
   and why not, when not. Selection logic refuses to silently swap out
   models — the agent or user must opt into the stub fallback explicitly.

Always-available stub workers make tests deterministic without requiring
any of the real ML stacks to be installed.
"""

from __future__ import annotations

from .base import (
    CPU_ONLY_RESOURCES,
    ProbeResult,
    Worker,
    WorkerDescriptor,
    WorkerRegistry,
    WorkerResources,
    WorkerSelectionError,
    WorkerUnavailable,
)
from .capabilities import Capability
from .loader import default_workers, register_default_workers
from .resources import DEFAULT_GPU_RESOURCES
from .schemas import (
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
    WorkerResult,
)
from .tripo_api import TripoAPIClient, TripoAPIError, TripoAPIWorker

__all__ = [
    "CPU_ONLY_RESOURCES",
    "Capability",
    "DEFAULT_GPU_RESOURCES",
    "ImageTo3DRequest",
    "ProbeResult",
    "RefineMeshRequest",
    "TextTo3DRequest",
    "TextureMeshRequest",
    "TripoAPIClient",
    "TripoAPIError",
    "TripoAPIWorker",
    "Worker",
    "WorkerDescriptor",
    "WorkerRegistry",
    "WorkerResources",
    "WorkerResult",
    "WorkerSelectionError",
    "WorkerUnavailable",
    "default_workers",
    "register_default_workers",
]
