"""Real ``texture_mesh`` worker backed by Diffusers Stable Diffusion.

Pipeline:

1. Load (or reuse cached) SD pipeline via :class:`WorkerSession`.
2. Generate a 2D texture image from ``spec.prompt`` (img2img when a
   ``reference_image_path`` is provided, txt2img otherwise).
3. Bake the generated image into the input mesh's UV atlas with
   ``api.texture_gen.bake_texture_to_uv``.
4. Re-export the mesh with the baked texture as the new diffuse map.

Why "real":

* Uses real ML weights downloaded from HuggingFace via the model
  registry (``runwayml/stable-diffusion-v1-5`` by default; configurable
  via env var).
* Probes for ``torch`` + ``diffusers`` honestly; reports ``cpu_fallback``
  so the scheduler runs it on CPU when no GPU exists (slow but
  functional — useful for low-volume hosting).
* Reuses the loaded pipeline across calls via :class:`WorkerSession`,
  so the second invocation skips the 30-second checkpoint load.

The worker deliberately depends on ``api/texture_gen.py``'s baking
helpers — they are battle-tested numpy code shipping in the repo, and
duplicating them would invite drift.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import WorkerResources
from .session import WorkerSession, get_session_registry
from ._probes import probe_imports, probe_torch_cuda

logger = logging.getLogger(__name__)

# Defaults are conservative: SD1.5 fits in ~6 GB VRAM at fp16.
_DEFAULT_MODEL_ID = os.environ.get(
    "GHOSTFORGE_DIFFUSERS_MODEL", "runwayml/stable-diffusion-v1-5"
)
_REQUIRED_MODULES = ["torch", "diffusers", "PIL"]
_MIN_VRAM_GB_GPU = 6.0


class DiffusersTextureWorker:
    """Stable-Diffusion-driven texture generator + UV baker."""

    name = "diffusers_texture"
    capabilities = [Capability.texture_mesh]
    priority = 40
    license = "CreativeML Open RAIL-M (SD1.5 weights)"
    description = (
        "Stable Diffusion 1.5 texture generator: txt2img / img2img → "
        "UV-baked texture map. Runs on CUDA preferentially; falls back "
        "to CPU when no GPU is available."
    )
    homepage = "https://huggingface.co/runwayml/stable-diffusion-v1-5"
    paper_url = "https://arxiv.org/abs/2112.10752"
    weights_url = "https://huggingface.co/runwayml/stable-diffusion-v1-5"
    is_stub = False
    resources = WorkerResources(
        requires_cuda=True,
        min_vram_mb=int(_MIN_VRAM_GB_GPU * 1024),
        recommended_vram_mb=int((_MIN_VRAM_GB_GPU + 4.0) * 1024),
        max_concurrent_per_gpu=1,
        cpu_fallback=True,
        cpu_concurrent=1,
    )
    required_models: list[str] = ["sd-1-5"]

    def __init__(self, model_id: str = _DEFAULT_MODEL_ID) -> None:
        self._model_id = model_id
        self._lock = threading.RLock()
        self._txt2img_session: WorkerSession[Any] | None = None
        self._img2img_session: WorkerSession[Any] | None = None

    # ------------------------------------------------------------------
    # Probing
    # ------------------------------------------------------------------

    def probe(self) -> ProbeResult:
        # We don't gate on the SD checkpoint being downloaded — that's
        # the model registry's job. We only check that the deps that
        # would let us *attempt* loading are present.
        torch_info = probe_torch_cuda(min_vram_gb=None)
        modules_missing = probe_imports(_REQUIRED_MODULES)
        runnable = (
            torch_info["has_torch"]
            and not [m for m in modules_missing if m != "torch"]
        )

        if runnable:
            reason = None
        elif modules_missing:
            reason = f"missing modules: {modules_missing}"
        else:
            reason = "torch not installed"

        return ProbeResult(
            name=self.name,
            runnable=runnable,
            reason=reason,
            missing=modules_missing,
            device=torch_info["device"],
            available_vram_mb=(
                int(torch_info["vram_gb"] * 1024) if torch_info["vram_gb"] else None
            ),
            metadata={
                "model_id": self._model_id,
                "min_vram_mb": self.resources.min_vram_mb,
                "vram_gb": torch_info["vram_gb"],
            },
        )

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        spec: Any,  # TextureMeshRequest
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        probe = self.probe()
        if not probe.runnable:
            raise WorkerUnavailable(
                f"diffusers_texture not runnable: {probe.reason}. "
                f"Install with `pip install ghostforge[ai]`."
            )

        try:
            from PIL import Image
        except ImportError as exc:
            raise WorkerUnavailable("PIL is required for texture generation") from exc

        reporter and reporter("diffusers.start", 5.0, "preparing pipeline")
        cancel and cancel.throw_if_cancelled()

        ref_image: Any = None
        if getattr(spec, "reference_image_path", None) is not None:
            ref_image = Image.open(spec.reference_image_path).convert("RGB")

        # Generate the source texture (SD inference).
        texture_image = self._generate_texture(
            prompt=spec.prompt,
            size=int(spec.texture_size),
            reference_image=ref_image,
            seed=getattr(spec, "seed", None),
            reporter=reporter,
            cancel=cancel,
        )

        cancel and cancel.throw_if_cancelled()
        reporter and reporter("diffusers.bake", 80.0, "baking into UV atlas")

        # Bake into UV atlas. Uses the existing api.texture_gen helper.
        baked = self._bake_to_uv(spec.input_mesh_path, texture_image, int(spec.texture_size))

        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        texture_path = out_dir / "diffusers_texture.png"
        baked["texture"].save(str(texture_path))

        # Re-export mesh referencing the baked texture.
        mesh_path = self._export_mesh(
            input_mesh=spec.input_mesh_path,
            texture_path=texture_path,
            output_dir=out_dir,
            output_format=getattr(spec, "output_format", "glb"),
            uvs=baked["uvs"],
        )

        reporter and reporter("diffusers.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(mesh_path),
            "texture_map": str(texture_path),
            "metadata": {
                "model_id": self._model_id,
                "device": probe.device,
                "is_stub": False,
                "img2img": ref_image is not None,
                "texture_size": int(spec.texture_size),
            },
        }

    # ------------------------------------------------------------------
    # Inference + baking helpers (private)
    # ------------------------------------------------------------------

    def _generate_texture(
        self,
        *,
        prompt: str,
        size: int,
        reference_image: Any,
        seed: int | None,
        reporter: Any,
        cancel: Any,
    ) -> Any:
        # All heavy imports happen inside this method so probe() stays cheap.
        import torch  # type: ignore
        from diffusers import (  # type: ignore
            StableDiffusionImg2ImgPipeline,
            StableDiffusionPipeline,
        )

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32

        enh_prompt = (
            f"{prompt}, seamless tileable PBR texture, "
            "high frequency detail, 4K resolution, surface material"
        )
        neg_prompt = "blurry, low quality, watermark, text, logo, artifacts, seams"

        # Pick (and lazily build) the correct session.
        if reference_image is not None:
            session = self._get_img2img_session(device=device, dtype=dtype)
            reporter and reporter("diffusers.gen", 25.0, "img2img inference")
            with session.lease() as pipe:
                cancel and cancel.throw_if_cancelled()
                generator = (
                    torch.Generator(device=device).manual_seed(int(seed))
                    if seed is not None
                    else None
                )
                ref = reference_image.resize((size, size))
                result = pipe(
                    prompt=enh_prompt,
                    negative_prompt=neg_prompt,
                    image=ref,
                    strength=0.75,
                    num_inference_steps=20,
                    guidance_scale=7.5,
                    generator=generator,
                ).images[0]
        else:
            session = self._get_txt2img_session(device=device, dtype=dtype)
            reporter and reporter("diffusers.gen", 25.0, "txt2img inference")
            with session.lease() as pipe:
                cancel and cancel.throw_if_cancelled()
                generator = (
                    torch.Generator(device=device).manual_seed(int(seed))
                    if seed is not None
                    else None
                )
                result = pipe(
                    prompt=enh_prompt,
                    negative_prompt=neg_prompt,
                    width=size,
                    height=size,
                    num_inference_steps=20,
                    guidance_scale=7.5,
                    generator=generator,
                ).images[0]
        return result

    def _get_txt2img_session(self, *, device: str, dtype: Any) -> WorkerSession[Any]:
        with self._lock:
            if self._txt2img_session is None:
                self._txt2img_session = WorkerSession(
                    loader=lambda: self._load_txt2img(device=device, dtype=dtype),
                    disposer=_dispose_pipeline,
                    name=f"{self.name}.txt2img",
                )
                get_session_registry().register(self._txt2img_session)
            return self._txt2img_session

    def _get_img2img_session(self, *, device: str, dtype: Any) -> WorkerSession[Any]:
        with self._lock:
            if self._img2img_session is None:
                self._img2img_session = WorkerSession(
                    loader=lambda: self._load_img2img(device=device, dtype=dtype),
                    disposer=_dispose_pipeline,
                    name=f"{self.name}.img2img",
                )
                get_session_registry().register(self._img2img_session)
            return self._img2img_session

    def _load_txt2img(self, *, device: str, dtype: Any) -> Any:
        from diffusers import StableDiffusionPipeline  # type: ignore

        logger.info(
            "diffusers_texture: loading %s for txt2img on %s", self._model_id, device
        )
        pipe = StableDiffusionPipeline.from_pretrained(
            self._model_id, torch_dtype=dtype, safety_checker=None
        ).to(device)
        if device == "cuda":
            pipe.enable_attention_slicing()
        return pipe

    def _load_img2img(self, *, device: str, dtype: Any) -> Any:
        from diffusers import StableDiffusionImg2ImgPipeline  # type: ignore

        logger.info(
            "diffusers_texture: loading %s for img2img on %s", self._model_id, device
        )
        pipe = StableDiffusionImg2ImgPipeline.from_pretrained(
            self._model_id, torch_dtype=dtype, safety_checker=None
        ).to(device)
        if device == "cuda":
            pipe.enable_attention_slicing()
        return pipe

    def _bake_to_uv(self, input_mesh_path: Path, texture_image: Any, output_size: int) -> dict:
        from api.texture_gen import bake_texture_to_uv  # type: ignore
        from api.uv_unwrap import (  # type: ignore
            build_unwrapped_mesh,
            detect_existing_uvs,
            get_existing_uvs,
            load_mesh_scene,
            unwrap_mesh,
        )

        loaded = load_mesh_scene(str(input_mesh_path))
        mesh = loaded["merged"]

        # Re-use existing UVs when present, otherwise auto-unwrap. The
        # unwrap path returns a *new* mesh with seams duplicated.
        if detect_existing_uvs(mesh):
            existing_uvs, _ = get_existing_uvs(mesh)
            unwrap_result = {
                "vertices": mesh.vertices,
                "faces": mesh.faces,
                "uvs": existing_uvs,
            }
        else:
            unwrap_result = unwrap_mesh(mesh, atlas_size=output_size, padding=2)

        unwrapped = build_unwrapped_mesh(unwrap_result)

        baked = bake_texture_to_uv(
            texture=texture_image,
            uvs=unwrap_result["uvs"],
            faces=unwrap_result["faces"],
            output_size=output_size,
        )
        return {"texture": baked, "mesh": unwrapped, "uvs": unwrap_result["uvs"]}

    def _export_mesh(
        self,
        *,
        input_mesh: Path,
        texture_path: Path,
        output_dir: Path,
        output_format: str,
        uvs: Any,
    ) -> Path:
        from PIL import Image  # type: ignore
        import trimesh  # type: ignore

        # We could re-derive the unwrapped mesh from `_bake_to_uv`'s
        # output, but recomputing the unwrap once more is acceptable
        # — we trade a few hundred ms for a much simpler call signature
        # and the unwrap is idempotent for meshes that already have UVs.
        from api.uv_unwrap import (  # type: ignore
            build_unwrapped_mesh,
            detect_existing_uvs,
            get_existing_uvs,
            load_mesh_scene,
            unwrap_mesh,
        )

        loaded = load_mesh_scene(str(input_mesh))
        mesh = loaded["merged"]
        if detect_existing_uvs(mesh):
            existing_uvs, _ = get_existing_uvs(mesh)
            unwrap_result = {
                "vertices": mesh.vertices,
                "faces": mesh.faces,
                "uvs": existing_uvs,
            }
        else:
            # Texture size of 1024 is fine for the unwrap atlas hint here
            # — the atlas size affects layout, not pixel resolution.
            unwrap_result = unwrap_mesh(mesh, atlas_size=1024, padding=2)
        unwrapped = build_unwrapped_mesh(unwrap_result)

        texture_img = Image.open(texture_path).convert("RGB")
        material = trimesh.visual.material.PBRMaterial(
            name="diffusers_baked",
            baseColorTexture=texture_img,
        )
        unwrapped.visual = trimesh.visual.TextureVisuals(
            uv=unwrap_result["uvs"], material=material
        )

        out_path = output_dir / f"diffusers_texture.{output_format.lstrip('.')}"
        unwrapped.export(str(out_path))
        return out_path


def _dispose_pipeline(pipeline: Any) -> None:
    """Best-effort GPU memory release."""

    try:
        del pipeline  # noqa: F841
    except Exception:
        pass
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


__all__ = ["DiffusersTextureWorker"]
