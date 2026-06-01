"""Resource-aware scheduler for worker dispatch.

The :class:`JobRunner` pool is tuned for CPU-bound and I/O-bound work
(``max_workers`` defaults to 2). That number is a poor fit for GPU
inference: two TRELLIS jobs on a 16 GB card would OOM, while two
InstantMesh runs on a 24 GB card are perfectly fine. Rather than make
``max_workers`` a single number we treat the GPU as a separately
managed resource.

The :class:`ResourceScheduler` is in-process (suitable for the desktop
app and a single-process MCP server); a future cluster setup would
swap in a Redis-backed implementation that exposes the same
:meth:`acquire` contract.

Workers don't know about the scheduler directly; the dispatcher
(``operations/workers.py``) wraps each ``worker.run`` call in
``with scheduler.acquire(...) as slot``. That keeps worker code
focused on inference and lets us evolve scheduling without touching
every model.
"""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from .gpu import GpuStatus, detect_gpus
from .workers.resources import WorkerResources

logger = logging.getLogger(__name__)


class ResourceUnavailable(RuntimeError):
    """Raised when a worker requires a GPU the host cannot provide.

    Distinct from :class:`WorkerUnavailable` because that one is the
    worker's own self-report; this is the *scheduler's* refusal to
    place the run.
    """


@dataclass
class SchedulerSlot:
    """Granted slot returned by :meth:`ResourceScheduler.acquire`."""

    backend: str  # "cuda" | "cpu"
    gpu_index: int | None
    gpu_name: str | None
    free_vram_mb_at_acquire: int | None
    waited_seconds: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _GpuLane:
    """In-memory slot accounting for a single GPU."""

    index: int
    name: str
    total_vram_mb: int
    free_vram_mb: int | None
    in_flight: int = 0
    cv: threading.Condition = field(default_factory=lambda: threading.Condition(threading.RLock()))


class ResourceScheduler:
    """Concurrency gate for worker dispatch.

    Public surface is intentionally tiny: :meth:`acquire` (a context
    manager), :meth:`status` (introspection for MCP/UI), and
    :meth:`refresh` to redetect after device changes.
    """

    def __init__(
        self,
        *,
        cpu_concurrency: int = 4,
        wait_timeout_seconds: float | None = None,
    ) -> None:
        self._cpu_concurrency = max(1, cpu_concurrency)
        self._wait_timeout = wait_timeout_seconds
        self._cpu_sem = threading.BoundedSemaphore(self._cpu_concurrency)
        self._lanes: dict[int, _GpuLane] = {}
        self._lanes_lock = threading.RLock()
        self._refresh_lock = threading.RLock()
        self._gpu_status: GpuStatus | None = None
        self.refresh(force=True)

    # ------------------------------------------------------------------
    # Detection / refresh
    # ------------------------------------------------------------------

    def refresh(self, *, force: bool = False) -> GpuStatus:
        """Re-detect GPUs and reconcile lanes.

        Lanes for newly attached GPUs get a fresh ``_GpuLane``; lanes
        for detached GPUs are dropped (their pending acquisitions will
        already have been signalled by their condition variable).
        """

        with self._refresh_lock:
            status = detect_gpus(force=force)
            self._gpu_status = status

            with self._lanes_lock:
                discovered = {gpu.index for gpu in status.gpus}
                # Drop lanes for missing GPUs.
                for missing in [i for i in self._lanes if i not in discovered]:
                    logger.info("scheduler: dropping lane for detached GPU %d", missing)
                    self._lanes.pop(missing, None)

                # Add or update lanes.
                for gpu in status.gpus:
                    lane = self._lanes.get(gpu.index)
                    if lane is None:
                        self._lanes[gpu.index] = _GpuLane(
                            index=gpu.index,
                            name=gpu.name,
                            total_vram_mb=gpu.total_vram_mb,
                            free_vram_mb=gpu.free_vram_mb,
                        )
                    else:
                        lane.name = gpu.name
                        lane.total_vram_mb = gpu.total_vram_mb
                        lane.free_vram_mb = gpu.free_vram_mb
            return status

    @property
    def gpu_status(self) -> GpuStatus:
        if self._gpu_status is None:
            self.refresh(force=True)
        assert self._gpu_status is not None
        return self._gpu_status

    @property
    def cpu_only(self) -> bool:
        return self.gpu_status.cpu_only

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------

    @contextmanager
    def acquire(
        self,
        resources: WorkerResources,
        *,
        worker_name: str | None = None,
    ) -> Iterator[SchedulerSlot]:
        """Block until a slot matching ``resources`` is free, then yield it.

        Selection rules:

        1. If ``resources.requires_cuda`` and no GPU exists, raise
           :class:`ResourceUnavailable` unless ``cpu_fallback`` is
           true, in which case run on CPU.
        2. Otherwise pick the GPU with the most free VRAM that
           (a) has at least ``min_vram_mb`` total VRAM and
           (b) currently has fewer than ``max_concurrent_per_gpu``
               jobs in flight.
        3. If no GPU qualifies, fall back to CPU when the worker
           allows it; otherwise wait on the most permissive lane.
        """

        started_wait = time.monotonic()

        if resources.requires_cuda and self.cpu_only:
            if not resources.cpu_fallback:
                raise ResourceUnavailable(
                    f"Worker {worker_name or 'unknown'!r} requires CUDA but no GPU was detected"
                )
            with self._acquire_cpu(started_wait, resources, worker_name) as slot:
                yield slot
            return

        if not resources.requires_cuda:
            # Worker is CPU-friendly; honour its CPU concurrency budget.
            with self._acquire_cpu(started_wait, resources, worker_name) as slot:
                yield slot
            return

        # GPU path. Pick a lane and wait if necessary.
        lane = self._wait_for_lane(resources, worker_name)
        if lane is None:
            # No GPU has sufficient VRAM; CPU fallback if allowed, else error.
            if resources.cpu_fallback and self._cpu_sem.acquire(blocking=False):
                self._cpu_sem.release()
                with self._acquire_cpu(started_wait, resources, worker_name) as slot:
                    yield slot.__class__(
                        backend="cpu",
                        gpu_index=None,
                        gpu_name=None,
                        free_vram_mb_at_acquire=None,
                        waited_seconds=slot.waited_seconds,
                        metadata={"reason": "no GPU met VRAM requirement; cpu_fallback used"},
                    )
                return
            raise ResourceUnavailable(
                f"No GPU has at least {resources.min_vram_mb} MB total VRAM "
                f"for worker {worker_name or 'unknown'!r}"
            )

        # We are now responsible for incrementing in_flight on this lane.
        try:
            with lane.cv:
                lane.in_flight += 1
                free_at_acquire = lane.free_vram_mb
            slot = SchedulerSlot(
                backend="cuda",
                gpu_index=lane.index,
                gpu_name=lane.name,
                free_vram_mb_at_acquire=free_at_acquire,
                waited_seconds=time.monotonic() - started_wait,
                metadata={
                    "max_concurrent_per_gpu": resources.max_concurrent_per_gpu,
                    "min_vram_mb": resources.min_vram_mb,
                },
            )
            yield slot
        finally:
            with lane.cv:
                lane.in_flight = max(0, lane.in_flight - 1)
                lane.cv.notify_all()

    @contextmanager
    def _acquire_cpu(
        self,
        started_wait: float,
        resources: WorkerResources,
        worker_name: str | None,
    ) -> Iterator[SchedulerSlot]:
        budget = max(1, min(self._cpu_concurrency, resources.cpu_concurrent))
        # Honour the worker's narrower CPU budget if it's smaller than ours.
        # We don't actually create a per-worker semaphore here — workers
        # are dispatched serially per kind by the JobRunner already; the
        # CPU semaphore is the global cap.
        del budget
        acquired = self._cpu_sem.acquire(timeout=self._wait_timeout)
        if not acquired:
            raise ResourceUnavailable(
                f"Timed out waiting for a CPU slot for worker {worker_name or 'unknown'!r}"
            )
        try:
            yield SchedulerSlot(
                backend="cpu",
                gpu_index=None,
                gpu_name=None,
                free_vram_mb_at_acquire=None,
                waited_seconds=time.monotonic() - started_wait,
                metadata={"cpu_concurrency": self._cpu_concurrency},
            )
        finally:
            self._cpu_sem.release()

    def _wait_for_lane(
        self,
        resources: WorkerResources,
        worker_name: str | None,
    ) -> _GpuLane | None:
        """Block until any qualifying lane has capacity; return that lane.

        Returns ``None`` if no GPU has the required total VRAM (caller
        decides whether to CPU-fall-back or raise).
        """

        deadline = (
            time.monotonic() + self._wait_timeout if self._wait_timeout is not None else None
        )
        # Snapshot which lanes meet the VRAM floor; a lane that suddenly
        # vanishes mid-wait will be filtered out the next loop iteration.
        while True:
            with self._lanes_lock:
                qualifying = [
                    lane for lane in self._lanes.values()
                    if lane.total_vram_mb >= resources.min_vram_mb
                ]
            if not qualifying:
                return None

            # Try to claim a lane that has capacity right now.
            ranked = sorted(
                qualifying,
                key=lambda l: (l.free_vram_mb if l.free_vram_mb is not None else 0),
                reverse=True,
            )
            for lane in ranked:
                with lane.cv:
                    if lane.in_flight < resources.max_concurrent_per_gpu:
                        return lane

            # Nothing free — wait on the lane with the most free VRAM.
            target = ranked[0]
            with target.cv:
                if target.in_flight < resources.max_concurrent_per_gpu:
                    return target
                remaining = (
                    None if deadline is None else max(0.0, deadline - time.monotonic())
                )
                if remaining == 0.0:
                    raise ResourceUnavailable(
                        f"Timed out waiting for a GPU slot for worker {worker_name or 'unknown'!r}"
                    )
                target.cv.wait(timeout=remaining)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Snapshot used by the ``list_gpus`` MCP tool."""

        with self._lanes_lock:
            lanes = [
                {
                    "index": lane.index,
                    "name": lane.name,
                    "total_vram_mb": lane.total_vram_mb,
                    "free_vram_mb": lane.free_vram_mb,
                    "in_flight": lane.in_flight,
                }
                for lane in sorted(self._lanes.values(), key=lambda l: l.index)
            ]
        return {
            "backend": self.gpu_status.backend,
            "cpu_only": self.cpu_only,
            "cpu_concurrency": self._cpu_concurrency,
            "gpus": lanes,
            "notes": list(self.gpu_status.notes),
        }


__all__ = ["ResourceScheduler", "ResourceUnavailable", "SchedulerSlot"]
