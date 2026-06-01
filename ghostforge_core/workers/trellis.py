"""TRELLIS image-to-3D worker (Microsoft).

Paper: https://arxiv.org/abs/2412.01506
Repo:  https://github.com/Microsoft/TRELLIS
License: MIT
"""

from __future__ import annotations

from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import WorkerResources
from ._probes import probe_imports, probe_torch_cuda

_MIN_VRAM_GB = 16.0
_REQUIRED_MODULES = ["trellis"]


class TrellisWorker:
    name = "trellis"
    capabilities = [Capability.image_to_3d]
    priority = 60
    license = "MIT"
    description = (
        "Microsoft TRELLIS — high-quality structured 3D generation producing "
        "meshes, Gaussians, and radiance fields from a single image or "
        "text prompt."
    )
    homepage = "https://microsoft.github.io/TRELLIS/"
    paper_url = "https://arxiv.org/abs/2412.01506"
    weights_url = "https://huggingface.co/JeffreyXiang/TRELLIS-image-large"
    is_stub = False
    resources = WorkerResources(
        requires_cuda=True,
        min_vram_mb=int(_MIN_VRAM_GB * 1024),
        recommended_vram_mb=int(_MIN_VRAM_GB * 1024),
        max_concurrent_per_gpu=1,
    )
    required_models: list[str] = ["trellis-image-large"]

    def probe(self) -> ProbeResult:
        torch_info = probe_torch_cuda(min_vram_gb=_MIN_VRAM_GB)
        missing = list(torch_info["missing"]) + probe_imports(_REQUIRED_MODULES)

        runnable = (
            torch_info["has_torch"]
            and torch_info["has_cuda"]
            and torch_info["meets_min_vram"]
            and not [m for m in missing if m not in {"cuda"}]
        )

        if runnable:
            reason = None
        elif not torch_info["has_torch"]:
            reason = "torch not installed"
        elif not torch_info["has_cuda"]:
            reason = "CUDA GPU required"
        elif not torch_info["meets_min_vram"]:
            reason = f"requires ≥ {_MIN_VRAM_GB:.0f} GB VRAM"
        else:
            reason = f"missing modules: {missing}"

        return ProbeResult(
            name=self.name,
            runnable=runnable,
            reason=reason,
            missing=missing,
            device=torch_info["device"],
            metadata={
                "min_vram_gb": _MIN_VRAM_GB,
                "vram_gb": torch_info["vram_gb"],
            },
        )

    def run(self, spec: Any, reporter: Any, cancel: Any) -> dict[str, Any]:
        probe = self.probe()
        if not probe.runnable:
            raise WorkerUnavailable(
                f"TRELLIS not runnable on this host: {probe.reason}. "
                f"Install the upstream repo from {self.homepage} and ensure a "
                f"CUDA GPU with ≥{_MIN_VRAM_GB:.0f} GB VRAM is available."
            )
        # Real TRELLIS invocation lives behind this guard. The scaffold is
        # intentionally explicit: silently producing a fake output would
        # poison downstream manifests with unverified geometry.
        raise NotImplementedError(
            "TRELLIS worker scaffold registered but real model invocation "
            "is not yet wired. See ghostforge_core/workers/trellis.py."
        )
