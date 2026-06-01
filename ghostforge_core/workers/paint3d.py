"""Paint3D texture-generation worker.

Paper: https://arxiv.org/abs/2312.13913
Repo:  https://github.com/OpenTexture/Paint3D
License: Apache-2.0
"""

from __future__ import annotations

from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import WorkerResources
from ._probes import probe_imports, probe_torch_cuda

_MIN_VRAM_GB = 8.0
_CANDIDATE_MODULES = ["paint3d"]


class Paint3DWorker:
    name = "paint3d"
    capabilities = [Capability.texture_mesh]
    priority = 55
    license = "Apache-2.0"
    description = (
        "Paint3D — coarse-to-fine 2K UV texture map generation, lighting-less "
        "outputs suitable for downstream relighting in any engine."
    )
    homepage = "https://github.com/OpenTexture/Paint3D"
    paper_url = "https://arxiv.org/abs/2312.13913"
    weights_url = "https://huggingface.co/GeneralAwareness/Paint3D"
    is_stub = False
    resources = WorkerResources(
        requires_cuda=True,
        min_vram_mb=int(_MIN_VRAM_GB * 1024),
        recommended_vram_mb=int((_MIN_VRAM_GB + 4.0) * 1024),
        max_concurrent_per_gpu=1,
    )
    required_models: list[str] = ["paint3d"]

    def probe(self) -> ProbeResult:
        torch_info = probe_torch_cuda(min_vram_gb=_MIN_VRAM_GB)
        missing_modules = probe_imports(_CANDIDATE_MODULES)
        missing = list(torch_info["missing"]) + missing_modules

        runnable = (
            torch_info["has_torch"]
            and torch_info["has_cuda"]
            and torch_info["meets_min_vram"]
            and not missing_modules
        )
        reason: str | None
        if runnable:
            reason = None
        elif not torch_info["has_torch"]:
            reason = "torch not installed"
        elif not torch_info["has_cuda"]:
            reason = "CUDA GPU required"
        elif not torch_info["meets_min_vram"]:
            reason = f"requires ≥ {_MIN_VRAM_GB:.0f} GB VRAM"
        elif missing_modules:
            reason = f"missing modules: {missing_modules}"
        else:
            reason = "unknown"

        return ProbeResult(
            name=self.name,
            runnable=runnable,
            reason=reason,
            missing=missing,
            device=torch_info["device"],
            metadata={
                "min_vram_gb": _MIN_VRAM_GB,
                "vram_gb": torch_info["vram_gb"],
                "supports_lighting_free": True,
            },
        )

    def run(self, spec: Any, reporter: Any, cancel: Any) -> dict[str, Any]:
        probe = self.probe()
        if not probe.runnable:
            raise WorkerUnavailable(
                f"Paint3D not runnable on this host: {probe.reason}. "
                f"See {self.homepage} for installation."
            )
        raise NotImplementedError(
            "Paint3D worker scaffold registered but real model invocation is "
            "not yet wired. See ghostforge_core/workers/paint3d.py."
        )
