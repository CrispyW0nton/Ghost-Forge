"""Shared low-level probe helpers used by real-model workers.

All helpers are import-free at module scope; they only touch their target
libraries inside the function body so worker probes never trigger heavy
imports at registration time.
"""

from __future__ import annotations

from typing import Any


def probe_torch_cuda(min_vram_gb: float | None = None) -> dict[str, Any]:
    """Best-effort torch + CUDA probe.

    Returns a dict with ``has_torch``, ``has_cuda``, ``device``, ``vram_gb``,
    ``meets_min_vram``, plus a ``missing`` list of unmet requirements.
    The dict is the same shape every time so workers can compose it
    directly into their :class:`ProbeResult.metadata`.
    """
    info: dict[str, Any] = {
        "has_torch": False,
        "has_cuda": False,
        "device": None,
        "vram_gb": None,
        "meets_min_vram": True,
        "missing": [],
    }
    try:
        import torch
    except ImportError:
        info["missing"].append("torch")
        return info

    info["has_torch"] = True
    try:
        if torch.cuda.is_available():
            info["has_cuda"] = True
            device = "cuda:0"
            info["device"] = device
            try:
                props = torch.cuda.get_device_properties(0)
                vram_gb = props.total_memory / (1024**3)
                info["vram_gb"] = round(vram_gb, 2)
                if min_vram_gb is not None:
                    info["meets_min_vram"] = vram_gb >= min_vram_gb
            except Exception:
                pass
        else:
            info["device"] = "cpu"
            if min_vram_gb is not None:
                info["meets_min_vram"] = False
                info["missing"].append("cuda")
    except Exception:
        info["device"] = "cpu"

    return info


def probe_imports(module_names: list[str]) -> list[str]:
    """Return the subset of ``module_names`` that fail to import."""
    missing: list[str] = []
    for name in module_names:
        try:
            __import__(name)
        except ImportError:
            missing.append(name)
    return missing


__all__ = ["probe_imports", "probe_torch_cuda"]
