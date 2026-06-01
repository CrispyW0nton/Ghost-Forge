from __future__ import annotations

import sys
from pathlib import Path

from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.manifest import MaterialSpec, TextureRole, TextureSlot
from ghostforge_core.types import TextureRequest, TextureResult, utc_now

from ._manifest import emit_operation_manifest


def _legacy_api_path() -> Path:
    return Path(__file__).resolve().parents[2] / "api"


def run(
    spec: TextureRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> TextureResult:
    api_path = str(_legacy_api_path())
    if api_path not in sys.path:
        sys.path.insert(0, api_path)

    from pipeline import run_pipeline

    def progress(stage: str, percent: int) -> None:
        cancel and cancel.throw_if_cancelled()
        reporter and reporter(stage, float(percent))

    cancel and cancel.throw_if_cancelled()
    started = utc_now()
    result = run_pipeline(
        input_mesh_path=str(spec.input_mesh_path),
        output_dir=str(spec.output_dir),
        texture_prompt=spec.prompt,
        reference_image_path=str(spec.reference_image_path) if spec.reference_image_path else None,
        texture_size=spec.texture_size,
        use_ai=spec.use_ai,
        ai_steps=spec.ai_steps,
        output_format=spec.output_format,
        uv_only=False,
        force_unwrap=spec.force_unwrap,
        job_id=spec.job_id,
        progress_callback=progress,
    )
    finished = utc_now()

    base = spec.input_mesh_path.stem
    output_mesh = Path(result["output_mesh"])
    texture_map = Path(result["texture_map"]) if result.get("texture_map") else None
    uv_layout = Path(result["uv_layout"]) if result.get("uv_layout") else None
    metadata_path = spec.output_dir / f"{base}_meta.json"

    materials: list[MaterialSpec] = []
    if texture_map and texture_map.exists():
        slot = TextureSlot(
            role=TextureRole.base_color,
            path=texture_map,
            color_space="sRGB",
            resolution=(spec.texture_size, spec.texture_size),
        )
        materials.append(
            MaterialSpec(
                name=base or "material",
                base_color_factor=(1.0, 1.0, 1.0, 1.0),
                metallic_factor=0.0,
                roughness_factor=0.8,
                texture_slots=[slot],
            )
        )

    emit_operation_manifest(
        asset_dir=spec.output_dir,
        operation_kind="generate_texture_set",
        job_id=spec.job_id,
        parameters={
            "prompt": spec.prompt,
            "texture_size": spec.texture_size,
            "use_ai": spec.use_ai,
            "ai_steps": spec.ai_steps,
            "output_format": spec.output_format,
            "force_unwrap": spec.force_unwrap,
            "input_mesh_path": str(spec.input_mesh_path),
        },
        output_mesh=output_mesh,
        artifacts=[
            (texture_map, "texture.base_color"),
            (uv_layout, "uv.atlas"),
            (metadata_path, "meta.json"),
        ],
        materials=materials,
        source_prompt=spec.prompt,
        reference_image=spec.reference_image_path,
        started_at=started,
        finished_at=finished,
    )

    return TextureResult(
        output_mesh=output_mesh,
        texture_map=texture_map,
        uv_layout=uv_layout,
        metadata_path=metadata_path,
        original_stats=result.get("original_stats", {}),
        uv_stats=result.get("uv_stats", {}),
        processing_time_seconds=result.get("processing_time_seconds"),
    )
