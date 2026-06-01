from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.manifest import (
    MANIFEST_VERSION,
    ManifestBuilder,
    ProvenanceStep,
    Units,
    build_geometry_summary,
    manifest_exists,
    read_manifest,
    summarize_validation,
)
from ghostforge_core.operations._manifest import emit_operation_manifest
from ghostforge_core.validation import Issue, ValidationReport


@pytest.fixture
def cube_obj(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.creation.box(extents=(1.0, 2.0, 3.0))
    path = tmp_path / "cube.obj"
    mesh.export(str(path))
    return path


def test_build_geometry_summary_from_cube(cube_obj):
    summary = build_geometry_summary(cube_obj, units=Units.meters)
    assert summary.vertex_count > 0
    assert summary.triangle_count > 0
    assert summary.bounds_min is not None and summary.bounds_max is not None
    assert summary.size is not None
    assert all(s > 0 for s in summary.size)
    assert summary.units == Units.meters
    assert summary.watertight is True


def test_summarize_validation_status_transitions():
    passed = summarize_validation(ValidationReport())
    assert passed.status == "passed"
    assert passed.error_count == 0 and passed.warning_count == 0

    warned = summarize_validation(
        ValidationReport(warnings=[Issue(code="mesh.x", message="warn")])
    )
    assert warned.status == "warnings"
    assert warned.warning_count == 1

    failed = summarize_validation(
        ValidationReport(
            errors=[Issue(code="mesh.bad", message="bad")],
            warnings=[Issue(code="mesh.x", message="warn")],
        )
    )
    assert failed.status == "failed"
    assert failed.error_count == 1


def test_emit_operation_manifest_unwrap_shape(tmp_path, cube_obj):
    output_dir = tmp_path / "asset_001"
    output_dir.mkdir()
    output_mesh = output_dir / "cube.glb"

    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(cube_obj), force="mesh", process=False)
    mesh.export(str(output_mesh))

    uv_layout = output_dir / "cube_uv.png"
    uv_layout.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    manifest, manifest_file = emit_operation_manifest(
        asset_dir=output_dir,
        operation_kind="unwrap_uvs",
        job_id="job_42",
        parameters={"atlas_size": 1024, "padding": 2},
        output_mesh=output_mesh,
        artifacts=[(uv_layout, "uv.atlas")],
    )

    assert manifest.manifest_version == MANIFEST_VERSION
    assert manifest_exists(output_dir)
    assert manifest_file.parent == output_dir

    assert manifest.geometry is not None
    assert manifest.geometry.triangle_count > 0

    roles = {a.role for a in manifest.artifacts}
    assert "mesh.primary" in roles
    assert "uv.atlas" in roles

    assert len(manifest.provenance) == 1
    assert manifest.provenance[0].kind == "unwrap_uvs"
    assert manifest.provenance[0].job_id == "job_42"
    assert manifest.provenance[0].parameters["atlas_size"] == 1024

    assert manifest.validation.status in {"passed", "warnings", "failed"}


def test_emit_operation_manifest_accumulates_provenance(tmp_path, cube_obj):
    output_dir = tmp_path / "asset_002"
    output_dir.mkdir()
    output_mesh = output_dir / "cube.glb"

    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.load(str(cube_obj), force="mesh", process=False)
    mesh.export(str(output_mesh))

    emit_operation_manifest(
        asset_dir=output_dir,
        operation_kind="unwrap_uvs",
        job_id="job_a",
        parameters={"atlas_size": 1024},
        output_mesh=output_mesh,
    )
    emit_operation_manifest(
        asset_dir=output_dir,
        operation_kind="generate_texture_set",
        job_id="job_b",
        parameters={"texture_size": 1024},
        output_mesh=output_mesh,
    )

    final = read_manifest(output_dir)
    kinds = [step.kind for step in final.provenance]
    assert kinds == ["unwrap_uvs", "generate_texture_set"]
    assert {step.job_id for step in final.provenance} == {"job_a", "job_b"}


def test_manifest_builder_uses_directory_name_when_asset_id_absent(tmp_path):
    asset_dir = tmp_path / "fox-walk-cycle"
    asset_dir.mkdir()
    builder = ManifestBuilder.for_dir(asset_dir)
    builder.add_provenance(ProvenanceStep(kind="bootstrap"))
    manifest, _ = builder.write()
    assert manifest.asset_id == "fox-walk-cycle"
