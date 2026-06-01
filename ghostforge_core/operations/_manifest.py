"""Shared helpers for emitting manifests from operations.

Operations stay focused on their core work and call ``emit_operation_manifest``
once they have an output mesh in hand. This keeps manifest population logic in
one place — fields, defaults, and provenance shape evolve together rather than
drifting per-operation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ghostforge_core.manifest import (
    AssetManifest,
    ManifestBuilder,
    MaterialSpec,
)


def emit_operation_manifest(
    *,
    asset_dir: Path,
    operation_kind: str,
    job_id: str | None,
    parameters: dict[str, Any],
    output_mesh: Path | None = None,
    artifacts: list[tuple[Path | None, str]] | None = None,
    materials: list[MaterialSpec] | None = None,
    source_prompt: str | None = None,
    reference_image: Path | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    asset_id: str | None = None,
    notes: str | None = None,
) -> tuple[AssetManifest, Path]:
    """Build, persist, and return the manifest for a completed operation.

    Idempotent: re-running an operation against the same ``asset_dir`` updates
    the existing manifest in place rather than overwriting unrelated fields,
    so multi-step pipelines (unwrap then texture) accumulate provenance and
    artifacts in a single document.
    """
    builder = ManifestBuilder.for_dir(asset_dir, asset_id=asset_id)

    if source_prompt is not None:
        builder.with_source_prompt(source_prompt)
    if reference_image is not None:
        builder.with_reference_image(reference_image)

    if output_mesh is not None and output_mesh.exists():
        try:
            builder.with_geometry_from_mesh(output_mesh)
        except Exception:
            # Geometry inspection should never block manifest emission; the
            # validation pass below still records that something was wrong.
            pass
        try:
            builder.with_validation_from_mesh(output_mesh)
        except Exception:
            pass
        builder.add_artifact_from_path(output_mesh, role="mesh.primary")

    for path, role in artifacts or []:
        builder.add_artifact_from_path(path, role=role)

    for material in materials or []:
        builder.add_material(material)

    from ghostforge_core.manifest import ProvenanceStep

    builder.add_provenance(
        ProvenanceStep(
            kind=operation_kind,
            job_id=job_id,
            started_at=started_at,
            finished_at=finished_at,
            parameters=parameters,
            notes=notes,
        )
    )

    return builder.write()


__all__ = ["emit_operation_manifest"]
