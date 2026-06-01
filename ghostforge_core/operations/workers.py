"""Capability dispatch handlers.

Each production capability (text_to_3d, image_to_3d, texture_mesh, refine_mesh) gets
one job-kind handler that:

1. Selects a runnable worker via :class:`WorkerRegistry.select`.
2. Invokes the worker with progress + cancellation hooks.
3. Emits an :class:`AssetManifest` covering geometry, artifacts, validation,
   provenance, and any concept citations specified up-front.

Workers themselves don't touch the manifest layer; that boundary keeps
worker code focused on inference and lets the dispatch layer evolve
independently (e.g. swap LanceDB for some other store later).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.scheduler import ResourceScheduler
from ghostforge_core.types import utc_now
from ghostforge_core.workers import (
    Capability,
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
    WorkerRegistry,
    WorkerResources,
    WorkerUnavailable,
)
from ghostforge_core.workers.base import WorkerSelectionError

from ._manifest import emit_operation_manifest


# Module-level handles assigned by `bootstrap`; alternative is to thread the
# registry through every job submission, which clutters the public API.
_REGISTRY: WorkerRegistry | None = None
_SCHEDULER: ResourceScheduler | None = None
_SECRET_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
)


def set_registry(registry: WorkerRegistry) -> None:
    global _REGISTRY
    _REGISTRY = registry


def set_scheduler(scheduler: ResourceScheduler | None) -> None:
    global _SCHEDULER
    _SCHEDULER = scheduler


def _registry() -> WorkerRegistry:
    if _REGISTRY is None:
        raise RuntimeError(
            "Worker registry not initialised. Call ghostforge_core.bootstrap() "
            "before submitting capability jobs."
        )
    return _REGISTRY


def _resources_for(worker: Any) -> WorkerResources:
    return getattr(worker, "resources", WorkerResources())


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower().replace("-", "_")
            if any(part in key_text for part in _SECRET_KEY_PARTS):
                out[key] = "<redacted>"
            else:
                out[key] = _redact_secrets(item)
        return out
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_secrets(item) for item in value)
    return value


def _common_run(
    capability: Capability,
    spec: Any,
    reporter: ProgressReporter | None,
    cancel: CancelToken | None,
    *,
    operation_kind: str,
    output_mesh_role: str = "mesh.primary",
    extra_artifacts: list[tuple[Path | None, str]] | None = None,
    source_prompt: str | None = None,
    reference_image: Path | None = None,
) -> dict[str, Any]:
    registry = _registry()
    try:
        worker = registry.select(capability, name=spec.worker)
    except WorkerSelectionError as exc:
        raise WorkerUnavailable(str(exc)) from exc

    reporter and reporter(f"select:{worker.name}", 2.0, f"selected {worker.name}")
    cancel and cancel.throw_if_cancelled()
    Path(spec.output_dir).mkdir(parents=True, exist_ok=True)

    started = utc_now()
    resources = _resources_for(worker)
    if _SCHEDULER is not None:
        with _SCHEDULER.acquire(resources, worker_name=worker.name) as slot:
            reporter and reporter(
                f"slot:{slot.backend}",
                3.0,
                f"acquired {slot.backend} slot (waited {slot.waited_seconds:.2f}s)",
            )
            cancel and cancel.throw_if_cancelled()
            result = worker.run(spec, reporter, cancel)
            scheduler_slot = {
                "backend": slot.backend,
                "gpu_index": slot.gpu_index,
                "gpu_name": slot.gpu_name,
                "waited_seconds": slot.waited_seconds,
            }
    else:
        scheduler_slot = None
        result = worker.run(spec, reporter, cancel)
    finished = utc_now()

    output_mesh = Path(result["output_mesh"])
    artifacts: list[tuple[Path | None, str]] = []
    if extra_artifacts:
        artifacts.extend(extra_artifacts)
    texture_map = result.get("texture_map")
    if texture_map:
        artifacts.append((Path(texture_map), "texture.base_color"))

    parameters = _redact_secrets(spec.model_dump(mode="json"))
    parameters["selected_worker"] = worker.name
    if scheduler_slot is not None:
        parameters["scheduler_slot"] = scheduler_slot
    if "metadata" in result:
        parameters["worker_metadata"] = _redact_secrets(result["metadata"])

    emit_operation_manifest(
        asset_dir=Path(spec.output_dir),
        operation_kind=operation_kind,
        job_id=getattr(spec, "job_id", None),
        parameters=parameters,
        output_mesh=output_mesh,
        artifacts=artifacts,
        source_prompt=source_prompt,
        reference_image=reference_image,
        started_at=started,
        finished_at=finished,
    )

    return {
        "worker": worker.name,
        "output_mesh": str(output_mesh),
        "texture_map": str(texture_map) if texture_map else None,
        "metadata": result.get("metadata", {}),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
    }


def run_image_to_3d(
    spec: ImageTo3DRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    return _common_run(
        Capability.image_to_3d,
        spec,
        reporter,
        cancel,
        operation_kind="image_to_3d",
        source_prompt=spec.prompt,
        reference_image=spec.input_image_path,
    )


def run_text_to_3d(
    spec: TextTo3DRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    return _common_run(
        Capability.text_to_3d,
        spec,
        reporter,
        cancel,
        operation_kind="text_to_3d",
        source_prompt=spec.prompt,
    )


def run_texture_mesh(
    spec: TextureMeshRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    return _common_run(
        Capability.texture_mesh,
        spec,
        reporter,
        cancel,
        operation_kind="texture_mesh",
        source_prompt=spec.prompt,
        reference_image=spec.reference_image_path,
    )


def run_refine_mesh(
    spec: RefineMeshRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    return _common_run(
        Capability.refine_mesh,
        spec,
        reporter,
        cancel,
        operation_kind="refine_mesh",
    )


__all__ = [
    "run_image_to_3d",
    "run_refine_mesh",
    "run_text_to_3d",
    "run_texture_mesh",
    "set_registry",
    "set_scheduler",
]
