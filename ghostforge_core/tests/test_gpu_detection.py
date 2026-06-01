"""GPU detection: torch/pynvml fallback chain + cache."""

from __future__ import annotations

import pytest

from ghostforge_core import gpu as gpu_module
from ghostforge_core.gpu import GpuInfo, GpuStatus, detect_gpus, reset_cache_for_tests


@pytest.fixture(autouse=True)
def _reset_cache():
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


def test_detect_gpus_returns_status_object_on_cpu_only_host(monkeypatch):
    monkeypatch.setattr(gpu_module, "_detect_with_torch", lambda: ([], ["torch absent"]))
    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", lambda: ([], ["pynvml absent"]))

    status = detect_gpus(force=True)
    assert isinstance(status, GpuStatus)
    assert status.cpu_only is True
    assert status.backend == "none"
    assert status.gpus == []
    assert "torch absent" in status.notes


def test_detect_gpus_prefers_torch_over_pynvml(monkeypatch):
    fake_gpu = GpuInfo(
        index=0,
        name="Fake RTX",
        total_vram_mb=24000,
        free_vram_mb=20000,
        backend="torch",
    )
    monkeypatch.setattr(gpu_module, "_detect_with_torch", lambda: ([fake_gpu], []))
    pynvml_calls = []

    def _pynvml():
        pynvml_calls.append(1)
        return ([], [])

    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", _pynvml)

    status = detect_gpus(force=True)
    assert status.backend == "torch"
    assert status.gpus == [fake_gpu]
    assert pynvml_calls == [], "pynvml should be skipped when torch found GPUs"


def test_detect_gpus_falls_back_to_pynvml(monkeypatch):
    pynvml_gpu = GpuInfo(
        index=0,
        name="GTX 9999",
        total_vram_mb=8000,
        free_vram_mb=4000,
        backend="pynvml",
    )
    monkeypatch.setattr(gpu_module, "_detect_with_torch", lambda: ([], ["torch absent"]))
    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", lambda: ([pynvml_gpu], []))

    status = detect_gpus(force=True)
    assert status.backend == "pynvml"
    assert status.gpus == [pynvml_gpu]
    assert status.cpu_only is False


def test_detect_gpus_caches_result(monkeypatch):
    calls = {"count": 0}

    def _torch():
        calls["count"] += 1
        return ([], [])

    monkeypatch.setattr(gpu_module, "_detect_with_torch", _torch)
    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", lambda: ([], []))

    detect_gpus(force=True, ttl_seconds=10)
    detect_gpus(ttl_seconds=10)
    detect_gpus(ttl_seconds=10)
    assert calls["count"] == 1, "second/third calls within TTL should hit the cache"


def test_detect_gpus_force_bypasses_cache(monkeypatch):
    calls = {"count": 0}

    def _torch():
        calls["count"] += 1
        return ([], [])

    monkeypatch.setattr(gpu_module, "_detect_with_torch", _torch)
    monkeypatch.setattr(gpu_module, "_detect_with_pynvml", lambda: ([], []))

    detect_gpus(force=True)
    detect_gpus(force=True)
    detect_gpus(force=True)
    assert calls["count"] == 3
