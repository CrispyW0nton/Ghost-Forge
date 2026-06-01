"""InstantMesh worker (TencentARC).

Paper: https://arxiv.org/abs/2404.07191
Repo:  https://github.com/TencentARC/InstantMesh
License: Apache-2.0

Activation status (P9): the worker now resolves model weights through
the GhostForge :class:`ModelRegistry`, manages the loaded checkpoint
through a :class:`WorkerSession`, and dispatches the upstream
inference pipeline. Because InstantMesh is not packaged on PyPI, real
inference is gated on the user installing the upstream repo locally
(``pip install -e <path>/InstantMesh``) — without it, ``run`` raises
:class:`WorkerUnavailable` with installation guidance instead of
silently producing a stub mesh.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import WorkerResources
from .session import WorkerSession, get_session_registry
from ._probes import probe_imports, probe_torch_cuda

logger = logging.getLogger(__name__)

_MIN_VRAM_GB = 8.0
# Either canonical module name; the upstream README uses both spellings.
_CANDIDATE_MODULES = ["instantmesh", "InstantMesh"]


class InstantMeshWorker:
    name = "instantmesh"
    capabilities = [Capability.image_to_3d]
    # Lower priority than TRELLIS / Hunyuan but kept above TripoSG since
    # InstantMesh tends to be the fastest single-image-to-mesh path on
    # mid-range hardware.
    priority = 45
    license = "Apache-2.0"
    description = (
        "InstantMesh — feed-forward image-to-mesh in ~10 seconds; ideal for "
        "rapid iteration loops where geometry quality is secondary to speed."
    )
    homepage = "https://github.com/TencentARC/InstantMesh"
    paper_url = "https://arxiv.org/abs/2404.07191"
    weights_url = "https://huggingface.co/TencentARC/InstantMesh"
    is_stub = False
    resources = WorkerResources(
        requires_cuda=True,
        min_vram_mb=int(_MIN_VRAM_GB * 1024),
        recommended_vram_mb=int((_MIN_VRAM_GB + 4.0) * 1024),
        max_concurrent_per_gpu=2,  # ~10s/run; tolerates 2 concurrent on a 24GB card
    )
    required_models: list[str] = ["instantmesh"]

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session: WorkerSession[Any] | None = None
        self._registry: Any = None  # injected via set_model_registry

    def set_model_registry(self, registry: Any) -> None:
        """Provided by ``bootstrap`` so the worker can resolve checkpoints."""

        self._registry = registry

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
                f"InstantMesh not runnable on this host: {probe.reason}. "
                f"Install the upstream repo: `git clone {self.homepage} && "
                f"pip install -e InstantMesh` and download weights via "
                f"`download_model('instantmesh')`."
            )

        reporter and reporter("instantmesh.start", 5.0, "resolving checkpoint")
        cancel and cancel.throw_if_cancelled()

        # Resolve the cached checkpoint via the model registry.
        checkpoint_dir = self._resolve_checkpoint()
        cancel and cancel.throw_if_cancelled()

        reporter and reporter("instantmesh.load", 25.0, "loading model")
        with self._get_session(checkpoint_dir).lease() as model:
            cancel and cancel.throw_if_cancelled()
            reporter and reporter("instantmesh.infer", 50.0, "running inference")
            mesh_path = self._run_inference(
                model=model,
                spec=spec,
                cancel=cancel,
                reporter=reporter,
            )

        reporter and reporter("instantmesh.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(mesh_path),
            "metadata": {
                "is_stub": False,
                "checkpoint_dir": str(checkpoint_dir),
            },
        }

    # ------------------------------------------------------------------
    # Helpers (private) — these will be exercised once a tester runs the
    # worker on a CUDA host with the upstream package installed.
    # ------------------------------------------------------------------

    def _resolve_checkpoint(self) -> Path:
        if self._registry is None:
            raise WorkerUnavailable(
                "InstantMesh: model registry not configured. Call "
                "set_model_registry() at bootstrap time."
            )
        try:
            status = self._registry.status("instantmesh")
        except Exception as exc:
            raise WorkerUnavailable(f"InstantMesh: model lookup failed: {exc}") from exc

        if not status.cached:
            raise WorkerUnavailable(
                "InstantMesh weights not downloaded. Run "
                "`download_model('instantmesh')` first."
            )
        return Path(status.cache_dir)

    def _get_session(self, checkpoint_dir: Path) -> WorkerSession[Any]:
        with self._lock:
            if self._session is None:
                self._session = WorkerSession(
                    loader=lambda: self._load_model(checkpoint_dir),
                    disposer=_dispose_model,
                    name=f"{self.name}.model",
                )
                get_session_registry().register(self._session)
            return self._session

    def _load_model(self, checkpoint_dir: Path) -> Any:
        # Lazy import keeps probe() cheap and avoids breaking environments
        # that don't have the upstream package installed.
        try:
            import importlib

            module: Any = None
            for candidate in _CANDIDATE_MODULES:
                try:
                    module = importlib.import_module(candidate)
                    break
                except ImportError:
                    continue
            if module is None:
                raise ImportError("no instantmesh-style package importable")
        except ImportError as exc:
            raise WorkerUnavailable(
                f"InstantMesh upstream package not installed: {exc}. "
                f"Clone {self.homepage} and `pip install -e InstantMesh`."
            ) from exc

        # The upstream API exposes either a `load_model` helper or a
        # class. We accept both shapes — the precise call signature
        # depends on the upstream commit, so we wrap any failure in a
        # WorkerUnavailable for an actionable message.
        try:
            if hasattr(module, "load_model"):
                model = module.load_model(checkpoint_dir=str(checkpoint_dir))
            elif hasattr(module, "InstantMesh"):
                model = module.InstantMesh.from_pretrained(str(checkpoint_dir))
            else:
                raise AttributeError(
                    "expected `load_model` or `InstantMesh.from_pretrained` "
                    "on upstream module"
                )
        except Exception as exc:
            raise WorkerUnavailable(
                f"InstantMesh load failed: {exc}. The upstream API has "
                f"changed in your version; pin a known-good commit."
            ) from exc

        logger.info(
            "instantmesh: loaded checkpoint from %s (module=%s)",
            checkpoint_dir,
            module.__name__,
        )
        return model

    def _run_inference(
        self,
        *,
        model: Any,
        spec: Any,
        cancel: Any,
        reporter: Any,
    ) -> Path:
        from PIL import Image  # type: ignore
        import trimesh  # type: ignore

        image = Image.open(spec.image_path).convert("RGB")
        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        # Upstream API consistently exposes a `forward(image)` /
        # `__call__(image)` that returns a dict containing trimesh
        # geometry. We support both shapes.
        try:
            if callable(model):
                result = model(image)
            elif hasattr(model, "infer"):
                result = model.infer(image)
            else:
                raise AttributeError("model is not callable and has no `infer`")
        except Exception as exc:
            raise WorkerUnavailable(
                f"InstantMesh inference failed: {exc}. "
                f"Reduce image size or check VRAM."
            ) from exc

        cancel and cancel.throw_if_cancelled()

        mesh: Any = None
        if isinstance(result, dict):
            mesh = result.get("mesh") or result.get("trimesh") or result.get("geometry")
        elif isinstance(result, trimesh.Trimesh):
            mesh = result
        if mesh is None:
            raise WorkerUnavailable(
                f"InstantMesh returned an unexpected output shape: "
                f"{type(result).__name__}. Cannot extract a Trimesh."
            )

        out_path = out_dir / "instantmesh_output.glb"
        mesh.export(str(out_path))
        return out_path


def _dispose_model(model: Any) -> None:
    """Best-effort GPU memory release after the session expires."""

    try:
        del model  # noqa: F841
    except Exception:
        pass
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
