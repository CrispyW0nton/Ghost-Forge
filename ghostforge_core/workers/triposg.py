"""TripoSG image-to-3D worker (VAST).

Paper: https://arxiv.org/abs/2502.06608
Repo:  https://github.com/VAST-AI-Research/TripoSG
License: MIT (model weights subject to upstream terms)
"""

from __future__ import annotations

from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import WorkerResources
from ._probes import probe_imports, probe_torch_cuda

_MIN_VRAM_GB = 8.0
_CANDIDATE_MODULES = ["triposg", "triposg_inference"]


class TripoSGWorker:
    name = "triposg"
    capabilities = [Capability.image_to_3d]
    priority = 50
    license = "MIT (weights upstream)"
    description = (
        "TripoSG — large reconstruction model for image-to-3D shape generation."
    )
    homepage = "https://github.com/VAST-AI-Research/TripoSG"
    paper_url = "https://arxiv.org/abs/2502.06608"
    weights_url = "https://huggingface.co/VAST-AI/TripoSG"
    is_stub = False
    resources = WorkerResources(
        requires_cuda=True,
        min_vram_mb=int(_MIN_VRAM_GB * 1024),
        recommended_vram_mb=int((_MIN_VRAM_GB + 4.0) * 1024),
        max_concurrent_per_gpu=1,
    )
    required_models: list[str] = ["triposg"]

    def probe(self) -> ProbeResult:
        torch_info = probe_torch_cuda(min_vram_gb=_MIN_VRAM_GB)
        modules_missing = probe_imports(_CANDIDATE_MODULES)
        any_present = len(modules_missing) < len(_CANDIDATE_MODULES)

        missing = list(torch_info["missing"])
        if not any_present:
            missing.extend(_CANDIDATE_MODULES)

        runnable = (
            torch_info["has_torch"]
            and torch_info["has_cuda"]
            and torch_info["meets_min_vram"]
            and any_present
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
        elif not any_present:
            reason = f"none of {_CANDIDATE_MODULES} importable"
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
                "candidate_modules": _CANDIDATE_MODULES,
            },
        )

    def run(self, spec: Any, reporter: Any, cancel: Any) -> dict[str, Any]:
        probe = self.probe()
        if not probe.runnable:
            raise WorkerUnavailable(
                f"TripoSG not runnable on this host: {probe.reason}. "
                f"See {self.homepage} for installation."
            )
        raise NotImplementedError(
            "TripoSG worker scaffold registered but real model invocation is "
            "not yet wired. See ghostforge_core/workers/triposg.py."
        )
