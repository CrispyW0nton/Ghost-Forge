from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ghostforge_core.manifest import (
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    AssetManifest,
    CollisionIntent,
    CollisionSpec,
    EngineTarget,
    EngineTargetSpec,
    GeometrySummary,
    LicenseSpec,
    ManifestBuilder,
    MaterialSpec,
    ProvenanceStep,
    TextureRole,
    TextureSlot,
    Units,
    manifest_path,
    read_manifest,
    write_manifest,
)
from ghostforge_core.types import Artifact


def _sample_manifest(asset_dir: Path) -> AssetManifest:
    return AssetManifest(
        asset_id="cube_001",
        name="Reference Cube",
        description="Unit cube for tests",
        asset_dir=asset_dir,
        source_prompt="a metallic cube",
        geometry=GeometrySummary(
            vertex_count=8,
            triangle_count=12,
            edge_count=18,
            bounds_min=(-0.5, -0.5, -0.5),
            bounds_max=(0.5, 0.5, 0.5),
            size=(1.0, 1.0, 1.0),
            units=Units.meters,
            watertight=True,
            uv_channels=1,
            has_normals=True,
        ),
        materials=[
            MaterialSpec(
                name="cube_mat",
                metallic_factor=0.4,
                roughness_factor=0.3,
                texture_slots=[
                    TextureSlot(
                        role=TextureRole.base_color,
                        path=asset_dir / "base_color.png",
                        resolution=(1024, 1024),
                    )
                ],
            )
        ],
        collision=CollisionSpec(intent=CollisionIntent.box),
        license=LicenseSpec(spdx="CC-BY-4.0", holder="GhostForge"),
        engine_targets=[EngineTargetSpec(engine=EngineTarget.unity)],
        artifacts=[
            Artifact(
                path=asset_dir / "cube.glb",
                sha256="0" * 64,
                bytes=128,
                mime="model/gltf-binary",
                role="mesh.primary",
            )
        ],
        provenance=[
            ProvenanceStep(
                kind="unwrap_uvs",
                job_id="job_test",
                parameters={"atlas_size": 1024, "padding": 2},
            )
        ],
        tags=["test", "cube"],
    )


def test_manifest_round_trip(tmp_path):
    manifest = _sample_manifest(tmp_path)
    target = write_manifest(tmp_path, manifest)

    assert target == manifest_path(tmp_path)
    assert target.name == MANIFEST_FILENAME
    loaded = read_manifest(tmp_path)

    assert loaded.manifest_version == MANIFEST_VERSION == "1.0"
    assert loaded.asset_id == manifest.asset_id
    assert loaded.geometry == manifest.geometry
    assert loaded.materials == manifest.materials
    assert loaded.collision.intent == CollisionIntent.box
    assert loaded.engine_targets[0].engine == EngineTarget.unity
    assert loaded.license.spdx == "CC-BY-4.0"
    assert loaded.tags == ["test", "cube"]


def test_manifest_rejects_unknown_fields(tmp_path):
    manifest = _sample_manifest(tmp_path)
    payload = json.loads(manifest.model_dump_json())
    payload["unknown_v2_field"] = "future"

    with pytest.raises(ValidationError):
        AssetManifest.model_validate(payload)


def test_manifest_rejects_unknown_manifest_version(tmp_path):
    manifest = _sample_manifest(tmp_path)
    payload = json.loads(manifest.model_dump_json())
    payload["manifest_version"] = "2.0"

    with pytest.raises(ValidationError):
        AssetManifest.model_validate(payload)


def test_manifest_atomic_write_does_not_leave_tmp(tmp_path):
    manifest = _sample_manifest(tmp_path)
    write_manifest(tmp_path, manifest)
    leftover_tmps = list(tmp_path.glob("*.tmp"))
    assert leftover_tmps == []


def test_manifest_builder_idempotent_for_dir(tmp_path):
    """Re-running an operation in the same asset_dir must accumulate provenance,
    not duplicate artifacts (matched by path+role) and not lose engine targets."""
    asset_id = "asset_xyz"

    first = (
        ManifestBuilder(asset_id=asset_id, asset_dir=tmp_path)
        .with_geometry(
            GeometrySummary(vertex_count=4, triangle_count=2)
        )
        .add_provenance(ProvenanceStep(kind="unwrap_uvs", parameters={"atlas_size": 1024}))
        .add_engine_target(EngineTargetSpec(engine=EngineTarget.unity))
    )
    first.write()

    second = (
        ManifestBuilder.for_dir(tmp_path)
        .add_provenance(ProvenanceStep(kind="generate_texture_set", parameters={"texture_size": 1024}))
        .add_engine_target(EngineTargetSpec(engine=EngineTarget.unreal))
    )
    second.write()

    final = read_manifest(tmp_path)
    assert final.asset_id == asset_id
    assert [step.kind for step in final.provenance] == ["unwrap_uvs", "generate_texture_set"]
    assert {target.engine for target in final.engine_targets} == {
        EngineTarget.unity,
        EngineTarget.unreal,
    }
    assert final.geometry is not None
    assert final.geometry.vertex_count == 4
