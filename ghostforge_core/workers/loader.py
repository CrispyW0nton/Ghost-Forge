"""Default-worker registration helpers.

Two functions:

* :func:`default_workers` — return a fresh :class:`WorkerRegistry` populated
  with every shipped worker (real + stubs).
* :func:`register_default_workers` — append the same set onto an existing
  registry. Useful when callers (tests, custom adapters) want to add more
  workers alongside the defaults.
"""

from __future__ import annotations

from .base import Worker, WorkerRegistry
from .diffusers_texture import DiffusersTextureWorker
from .hunyuan3d import Hunyuan3DWorker
from .instantmesh import InstantMeshWorker
from .paint3d import Paint3DWorker
from .silhouette_image import SilhouetteImageTo3DWorker
from .stub import (
    StubImageTo3DWorker,
    StubRefineMeshWorker,
    StubTextureMeshWorker,
)
from .syncmvd import SyncMVDWorker
from .trellis import TrellisWorker
from .tripo_api import TripoAPIWorker
from .triposg import TripoSGWorker


def _instances() -> list[Worker]:
    return [
        # Real production workers (hosted API or GPU-backed, priority >= 70).
        TrellisWorker(),
        Hunyuan3DWorker(),
        TripoAPIWorker(),
        TripoSGWorker(),
        InstantMeshWorker(),
        DiffusersTextureWorker(),
        Paint3DWorker(),
        SyncMVDWorker(),
        # Real CPU-only image worker. Ghost-Forge's production mesh
        # generation contract is image/reference driven; text prompts
        # guide texture/style, not mesh topology.
        SilhouetteImageTo3DWorker(),
        # Always-on stubs (priority 0) for deterministic test output.
        StubImageTo3DWorker(),
        StubTextureMeshWorker(),
        StubRefineMeshWorker(),
    ]


def register_default_workers(registry: WorkerRegistry) -> WorkerRegistry:
    for worker in _instances():
        registry.register(worker)
    return registry


def default_workers() -> WorkerRegistry:
    return register_default_workers(WorkerRegistry())


__all__ = ["default_workers", "register_default_workers"]
