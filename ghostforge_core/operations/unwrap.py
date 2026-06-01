from __future__ import annotations

import sys
from pathlib import Path

from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.types import UnwrapRequest, UnwrapResult, utc_now

from ._manifest import emit_operation_manifest


def _legacy_api_path() -> Path:
    return Path(__file__).resolve().parents[2] / "api"


def run(
    spec: UnwrapRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> UnwrapResult:
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
        texture_prompt="uv unwrap only",
        texture_size=spec.atlas_size,
        atlas_size=spec.atlas_size,
        padding=spec.padding,
        output_format=spec.output_format,
        uv_only=True,
        force_unwrap=spec.force_unwrap,
        job_id=spec.job_id,
        progress_callback=progress,
    )
    finished = utc_now()

    base = spec.input_mesh_path.stem
    output_mesh = Path(result["output_mesh"])
    uv_layout = Path(result["uv_layout"]) if result.get("uv_layout") else None
    metadata_path = spec.output_dir / f"{base}_meta.json"

    emit_operation_manifest(
        asset_dir=spec.output_dir,
        operation_kind="unwrap_uvs",
        job_id=spec.job_id,
        parameters={
            "atlas_size": spec.atlas_size,
            "padding": spec.padding,
            "output_format": spec.output_format,
            "force_unwrap": spec.force_unwrap,
            "uv_only": spec.uv_only,
            "input_mesh_path": str(spec.input_mesh_path),
        },
        output_mesh=output_mesh,
        artifacts=[
            (uv_layout, "uv.atlas"),
            (metadata_path, "meta.json"),
        ],
        started_at=started,
        finished_at=finished,
    )

    return UnwrapResult(
        output_mesh=output_mesh,
        uv_layout=uv_layout,
        metadata_path=metadata_path,
        original_stats=result.get("original_stats", {}),
        uv_stats=result.get("uv_stats", {}),
        processing_time_seconds=result.get("processing_time_seconds"),
    )
