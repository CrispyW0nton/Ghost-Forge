"""Default model artifacts shipped with GhostForge.

Each entry mirrors what the matching worker advertises in its
``required_models`` list. Concrete file lists are kept light — most
artifacts ship ``config.json`` plus a single weight file at the
canonical path, and the registry's verification step will catch a
mismatch loudly. Workers that need finer-grained tracking can extend
the ``files`` list at registration time.
"""

from __future__ import annotations

from .schema import ModelArtifact, ModelFile

DEFAULT_ARTIFACTS: list[ModelArtifact] = [
    ModelArtifact(
        model_id="trellis-image-large",
        repo_id="JeffreyXiang/TRELLIS-image-large",
        description="Microsoft TRELLIS image-conditioned 3D generation, large variant.",
        license="MIT",
        homepage="https://microsoft.github.io/TRELLIS/",
        files=[
            ModelFile(path="ckpts/slat_dec_mesh_swin8_B_64l8m256c_fp16.safetensors"),
            ModelFile(path="ckpts/slat_dec_gs_swin8_B_64l8gs32_fp16.safetensors"),
            ModelFile(path="ckpts/slat_dec_rf_swin8_B_64l8r16_fp16.safetensors"),
            ModelFile(path="ckpts/slat_flow_img_dit_L_64l8p2_fp16.safetensors"),
            ModelFile(path="ckpts/ss_dec_conv3d_16l8_fp16.safetensors"),
            ModelFile(path="ckpts/ss_flow_img_dit_L_16l8_fp16.safetensors"),
        ],
    ),
    ModelArtifact(
        model_id="hunyuan3d-2",
        repo_id="tencent/Hunyuan3D-2",
        description="Tencent Hunyuan3D-2 dual-stage geometry + texture model.",
        license="Tencent Hunyuan Community License",
        homepage="https://github.com/Tencent/Hunyuan3D-2",
        files=[
            ModelFile(path="hunyuan3d-dit-v2-0/model.fp16.safetensors"),
            ModelFile(path="hunyuan3d-vae-v2-0/model.fp16.safetensors"),
            ModelFile(path="hunyuan3d-paint-v2-0/unet/diffusion_pytorch_model.fp16.safetensors"),
        ],
    ),
    ModelArtifact(
        model_id="triposg",
        repo_id="VAST-AI/TripoSG",
        description="TripoSG image-to-3D reconstruction model.",
        license="MIT (weights upstream; check repo)",
        homepage="https://github.com/VAST-AI-Research/TripoSG",
        files=[ModelFile(path="model.safetensors")],
    ),
    ModelArtifact(
        model_id="instantmesh",
        repo_id="TencentARC/InstantMesh",
        description="InstantMesh feed-forward image-to-mesh.",
        license="Apache-2.0",
        homepage="https://github.com/TencentARC/InstantMesh",
        files=[ModelFile(path="instant_mesh_large.ckpt")],
    ),
    ModelArtifact(
        model_id="paint3d",
        repo_id="GeneralAwareness/Paint3D",
        description="Paint3D coarse-to-fine 2K UV texture generator.",
        license="Apache-2.0",
        homepage="https://github.com/OpenTexture/Paint3D",
        files=[ModelFile(path="paint3d_unet.safetensors")],
    ),
    ModelArtifact(
        model_id="syncmvd-sd",
        repo_id="stabilityai/stable-diffusion-2-1",
        description="SyncMVD relies on a SD2.1 checkpoint for texture diffusion.",
        license="CreativeML Open RAIL-M",
        homepage="https://huggingface.co/stabilityai/stable-diffusion-2-1",
        files=[ModelFile(path="v2-1_768-ema-pruned.safetensors")],
    ),
]


__all__ = ["DEFAULT_ARTIFACTS"]
