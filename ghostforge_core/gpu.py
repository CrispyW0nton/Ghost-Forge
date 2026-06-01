"""GPU detection.

Workers and the scheduler both need a consistent picture of what GPUs
are available before deciding whether (and where) to run a job. We use
a layered detection strategy:

1. **PyTorch** — preferred when present because every real worker we
   ship targets it; ``torch.cuda`` reports the same device set the
   worker would see at run time.
2. **PyNVML** — falls back to NVIDIA's management library when PyTorch
   isn't installed (lightweight CI hosts, MCP-only deployments).
3. **None** — neither library available; report "CPU only" instead of
   raising. The scheduler then funnels every job through a single CPU
   slot rather than refusing to run.

Detection is intentionally cheap: we cache the device list on a short
TTL so the MCP ``list_gpus`` tool can be polled by a UI without
hammering the GPU each time, and the scheduler can re-detect cheaply
when a user plugs/unplugs an eGPU mid-session.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pydantic import Field

from .types import FrozenModel

_DEFAULT_CACHE_TTL_SECONDS = 5.0


class GpuInfo(FrozenModel):
    """Per-device GPU snapshot used by the scheduler and MCP tools."""

    index: int = Field(ge=0)
    name: str
    total_vram_mb: int = Field(ge=0)
    free_vram_mb: int | None = None
    compute_capability: tuple[int, int] | None = None
    driver_version: str | None = None
    backend: str  # "torch" | "pynvml" | "none"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GpuStatus(FrozenModel):
    """Top-level result of :func:`detect_gpus` calls."""

    gpus: list[GpuInfo] = Field(default_factory=list)
    backend: str  # which detection layer succeeded
    cpu_only: bool
    detected_at: float
    notes: list[str] = Field(default_factory=list)


_lock = threading.RLock()
_last_status: GpuStatus | None = None
_last_at: float = 0.0


def _detect_with_torch() -> tuple[list[GpuInfo], list[str]]:
    notes: list[str] = []
    try:
        import torch
    except ImportError:
        return [], ["torch not installed"]

    if not torch.cuda.is_available():
        notes.append("torch present but cuda unavailable")
        return [], notes

    out: list[GpuInfo] = []
    try:
        count = torch.cuda.device_count()
    except Exception as exc:
        notes.append(f"torch.cuda.device_count failed: {exc}")
        return [], notes

    for index in range(count):
        try:
            props = torch.cuda.get_device_properties(index)
            total_bytes = int(getattr(props, "total_memory", 0))
            total_mb = total_bytes // (1024 * 1024)
            cc = (int(props.major), int(props.minor)) if hasattr(props, "major") else None

            free_mb: int | None = None
            try:
                free_bytes, _total = torch.cuda.mem_get_info(index)
                free_mb = int(free_bytes) // (1024 * 1024)
            except Exception:
                pass

            out.append(
                GpuInfo(
                    index=index,
                    name=str(props.name),
                    total_vram_mb=total_mb,
                    free_vram_mb=free_mb,
                    compute_capability=cc,
                    driver_version=str(getattr(torch.version, "cuda", None) or ""),
                    backend="torch",
                    metadata={
                        "multi_processor_count": getattr(props, "multi_processor_count", None),
                    },
                )
            )
        except Exception as exc:
            notes.append(f"torch device {index} probe failed: {exc}")

    return out, notes


def _detect_with_pynvml() -> tuple[list[GpuInfo], list[str]]:
    notes: list[str] = []
    try:
        import pynvml  # type: ignore
    except ImportError:
        return [], ["pynvml not installed"]

    try:
        pynvml.nvmlInit()
    except Exception as exc:
        notes.append(f"nvmlInit failed: {exc}")
        return [], notes

    out: list[GpuInfo] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        driver = None
        try:
            driver = pynvml.nvmlSystemGetDriverVersion()
            if isinstance(driver, bytes):
                driver = driver.decode()
        except Exception:
            pass

        for index in range(count):
            try:
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode()
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                total_mb = int(memory.total) // (1024 * 1024)
                free_mb = int(memory.free) // (1024 * 1024)

                cc: tuple[int, int] | None = None
                try:
                    major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                    cc = (int(major), int(minor))
                except Exception:
                    pass

                out.append(
                    GpuInfo(
                        index=index,
                        name=str(name),
                        total_vram_mb=total_mb,
                        free_vram_mb=free_mb,
                        compute_capability=cc,
                        driver_version=str(driver) if driver else None,
                        backend="pynvml",
                    )
                )
            except Exception as exc:
                notes.append(f"pynvml device {index} probe failed: {exc}")
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass

    return out, notes


def detect_gpus(*, ttl_seconds: float = _DEFAULT_CACHE_TTL_SECONDS, force: bool = False) -> GpuStatus:
    """Return the current GPU snapshot.

    Cached for ``ttl_seconds`` so callers can poll cheaply. Pass
    ``force=True`` to bypass the cache after a known device change
    (e.g. driver reinstall, container restart).
    """

    global _last_status, _last_at
    now = time.monotonic()
    with _lock:
        if not force and _last_status is not None and (now - _last_at) < ttl_seconds:
            return _last_status

        gpus, notes = _detect_with_torch()
        backend = "torch" if gpus else ""
        if not gpus:
            pynvml_gpus, pynvml_notes = _detect_with_pynvml()
            notes.extend(pynvml_notes)
            if pynvml_gpus:
                gpus = pynvml_gpus
                backend = "pynvml"

        if not gpus:
            backend = "none"

        status = GpuStatus(
            gpus=gpus,
            backend=backend,
            cpu_only=not gpus,
            detected_at=time.time(),
            notes=notes,
        )
        _last_status = status
        _last_at = now
        return status


def reset_cache_for_tests() -> None:
    """Drop the cached GPU snapshot — used by tests, not callers."""

    global _last_status, _last_at
    with _lock:
        _last_status = None
        _last_at = 0.0


__all__ = ["GpuInfo", "GpuStatus", "detect_gpus", "reset_cache_for_tests"]
