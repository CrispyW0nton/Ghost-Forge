"""ResourceScheduler: GPU lane gating, CPU semaphore, fallback."""

from __future__ import annotations

import threading
import time

import pytest

from ghostforge_core import gpu as gpu_module
from ghostforge_core.gpu import GpuInfo, reset_cache_for_tests
from ghostforge_core.scheduler import ResourceScheduler, ResourceUnavailable
from ghostforge_core.workers.resources import WorkerResources


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def _make_fake_gpu(index: int = 0, total_mb: int = 24000, free_mb: int = 20000) -> GpuInfo:
    return GpuInfo(
        index=index,
        name=f"FakeGPU{index}",
        total_vram_mb=total_mb,
        free_vram_mb=free_mb,
        backend="torch",
    )


def _patch_detection(monkeypatch, gpus: list[GpuInfo]) -> None:
    monkeypatch.setattr(gpu_module, "_detect_with_torch", lambda: (list(gpus), []))
    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", lambda: ([], []))


def test_cpu_only_host_refuses_cuda_required_workers(monkeypatch):
    _patch_detection(monkeypatch, [])
    scheduler = ResourceScheduler()
    res = WorkerResources(requires_cuda=True, min_vram_mb=8000, cpu_fallback=False)
    with pytest.raises(ResourceUnavailable):
        with scheduler.acquire(res, worker_name="trellis"):
            pass


def test_cpu_only_host_allows_cpu_fallback_workers(monkeypatch):
    _patch_detection(monkeypatch, [])
    scheduler = ResourceScheduler()
    res = WorkerResources(requires_cuda=True, min_vram_mb=8000, cpu_fallback=True)
    with scheduler.acquire(res, worker_name="trellis-cpu") as slot:
        assert slot.backend == "cpu"


def test_cpu_concurrency_is_capped(monkeypatch):
    _patch_detection(monkeypatch, [])
    scheduler = ResourceScheduler(cpu_concurrency=2)
    res = WorkerResources(requires_cuda=False, cpu_concurrent=10)

    holder_acquired = threading.Event()
    release = threading.Event()
    held: list[bool] = []

    def _hold():
        with scheduler.acquire(res):
            held.append(True)
            holder_acquired.set()
            release.wait(timeout=5)

    workers = [threading.Thread(target=_hold) for _ in range(2)]
    for t in workers:
        t.start()
    # Wait for both to be holding slots.
    deadline = time.monotonic() + 3.0
    while sum(held) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(held) == 2

    blocked: list[float] = []

    def _try_acquire():
        start = time.monotonic()
        with scheduler.acquire(res):
            blocked.append(time.monotonic() - start)

    blocked_thread = threading.Thread(target=_try_acquire)
    blocked_thread.start()
    time.sleep(0.2)  # let the third thread block on the semaphore

    assert not blocked, "third acquire should be blocked while first two hold the semaphore"
    release.set()
    for t in workers:
        t.join(timeout=2)
    blocked_thread.join(timeout=2)
    assert blocked, "third acquire should eventually proceed"


def test_gpu_lane_serialises_above_max_concurrent(monkeypatch):
    _patch_detection(monkeypatch, [_make_fake_gpu()])
    scheduler = ResourceScheduler()
    res = WorkerResources(requires_cuda=True, min_vram_mb=8000, max_concurrent_per_gpu=1)

    barrier_in = threading.Event()
    release = threading.Event()
    saw: list[str] = []

    def _hog():
        with scheduler.acquire(res, worker_name="hog") as slot:
            saw.append(f"hog:{slot.backend}:{slot.gpu_index}")
            barrier_in.set()
            release.wait(timeout=5)

    hog = threading.Thread(target=_hog)
    hog.start()
    barrier_in.wait(timeout=2)

    blocked = []

    def _later():
        with scheduler.acquire(res, worker_name="later") as slot:
            blocked.append(f"later:{slot.backend}:{slot.gpu_index}")

    later = threading.Thread(target=_later)
    later.start()
    time.sleep(0.2)
    assert blocked == [], "second GPU job should block while first holds the lane"
    release.set()
    hog.join(timeout=2)
    later.join(timeout=2)
    assert saw == ["hog:cuda:0"]
    assert blocked == ["later:cuda:0"]


def test_gpu_lane_picks_gpu_with_more_free_vram(monkeypatch):
    gpus = [
        _make_fake_gpu(index=0, total_mb=24000, free_mb=4000),
        _make_fake_gpu(index=1, total_mb=24000, free_mb=20000),
    ]
    _patch_detection(monkeypatch, gpus)
    scheduler = ResourceScheduler()
    res = WorkerResources(requires_cuda=True, min_vram_mb=8000, max_concurrent_per_gpu=1)

    with scheduler.acquire(res) as slot:
        assert slot.backend == "cuda"
        assert slot.gpu_index == 1, "scheduler should prefer the GPU with more free VRAM"


def test_gpu_below_min_vram_falls_back_when_allowed(monkeypatch):
    _patch_detection(
        monkeypatch,
        [_make_fake_gpu(index=0, total_mb=4000, free_mb=2000)],
    )
    scheduler = ResourceScheduler()
    res = WorkerResources(
        requires_cuda=True,
        min_vram_mb=16000,  # all detected GPUs are too small
        cpu_fallback=True,
    )
    with scheduler.acquire(res) as slot:
        assert slot.backend == "cpu"


def test_status_reports_in_flight_count(monkeypatch):
    _patch_detection(monkeypatch, [_make_fake_gpu(index=0, total_mb=24000, free_mb=20000)])
    scheduler = ResourceScheduler()
    res = WorkerResources(requires_cuda=True, min_vram_mb=8000, max_concurrent_per_gpu=2)

    barrier = threading.Event()
    release = threading.Event()

    def _hold():
        with scheduler.acquire(res):
            barrier.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=_hold)
    holder.start()
    barrier.wait(timeout=2)

    snapshot = scheduler.status()
    assert snapshot["gpus"][0]["in_flight"] == 1

    release.set()
    holder.join(timeout=2)

    after = scheduler.status()
    assert after["gpus"][0]["in_flight"] == 0
