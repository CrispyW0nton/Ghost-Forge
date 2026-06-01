from __future__ import annotations

import io
from pathlib import Path

import pytest


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    pil = pytest.importorskip("PIL.Image")
    img = pil.new("RGB", (16, 16), color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_run_image_to_3d_with_stub_emits_manifest(tmp_path):
    pytest.importorskip("trimesh")
    from ghostforge_core import bootstrap, CoreConfig
    from ghostforge_core.manifest import read_manifest
    from ghostforge_core.operations.workers import run_image_to_3d
    from ghostforge_core.workers.schemas import ImageTo3DRequest

    bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    image_path = tmp_path / "concept.png"
    image_path.write_bytes(_png_bytes((40, 90, 200)))
    asset_dir = tmp_path / "asset_image_to_3d"

    spec = ImageTo3DRequest(
        input_image_path=image_path,
        prompt="floating crystal",
        output_dir=asset_dir,
        worker="stub_image_to_3d",
        seed=42,
        job_id="job_local",
    )
    result = run_image_to_3d(spec)
    assert result["worker"] == "stub_image_to_3d"
    assert Path(result["output_mesh"]).exists()

    manifest = read_manifest(asset_dir)
    assert manifest.geometry is not None
    assert manifest.geometry.triangle_count > 0
    assert manifest.source_prompt == "floating crystal"
    assert manifest.source_reference_image is not None
    kinds = [step.kind for step in manifest.provenance]
    assert "image_to_3d" in kinds
    step = next(s for s in manifest.provenance if s.kind == "image_to_3d")
    assert step.parameters["selected_worker"] == "stub_image_to_3d"
    assert step.parameters["worker"] == "stub_image_to_3d"
    assert step.job_id == "job_local"


def test_run_text_to_3d_requires_tripo_api_key(tmp_path, monkeypatch):
    pytest.importorskip("trimesh")
    from ghostforge_core import bootstrap, CoreConfig
    from ghostforge_core.operations.workers import run_text_to_3d
    from ghostforge_core.workers import WorkerUnavailable
    from ghostforge_core.workers.schemas import TextTo3DRequest

    monkeypatch.delenv("GHOSTFORGE_TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    asset_dir = tmp_path / "asset_text_to_3d"
    spec = TextTo3DRequest(
        prompt="ancient stone obelisk",
        output_dir=asset_dir,
        worker="tripo_api",
        seed=7,
    )
    with pytest.raises(WorkerUnavailable, match="Tripo API key"):
        run_text_to_3d(spec)


def test_run_text_to_3d_with_fake_tripo_emits_manifest_and_redacts_secrets(
    tmp_path,
    monkeypatch,
):
    trimesh = pytest.importorskip("trimesh")
    from ghostforge_core import bootstrap, CoreConfig
    from ghostforge_core.manifest import read_manifest
    from ghostforge_core.operations.workers import run_text_to_3d
    from ghostforge_core.workers.schemas import TextTo3DRequest
    from ghostforge_core.workers.tripo_api import TripoAPIWorker

    class _FakeClient:
        api_base = "https://api.tripo3d.ai/v2/openapi"

        def submit_text_to_model(self, payload):
            return {"task_id": "task-manifest"}

        def wait_for_task(self, task_id, *, reporter=None, cancel=None):
            return {
                "task_id": task_id,
                "status": "success",
                "output": {"pbr_model": "https://example.invalid/task-manifest.glb"},
                "consumed_credit": 20,
            }

        def download_url(self, url, destination):
            trimesh.creation.box(extents=(1, 1, 1)).export(str(destination))
            return destination

    monkeypatch.setenv("GHOSTFORGE_TRIPO_API_KEY", "secret-value")
    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    ctx.workers.unregister("tripo_api")
    ctx.workers.register(TripoAPIWorker(client=_FakeClient()))

    asset_dir = tmp_path / "asset_text_to_3d"
    spec = TextTo3DRequest(
        prompt="ancient stone obelisk",
        output_dir=asset_dir,
        worker="tripo_api",
        seed=7,
        extras={"texture": True, "nested": {"token": "secret-token"}},
    )
    result = run_text_to_3d(spec)

    assert result["worker"] == "tripo_api"
    assert Path(result["output_mesh"]).exists()
    manifest = read_manifest(asset_dir)
    assert manifest.source_prompt == "ancient stone obelisk"
    step = next(s for s in manifest.provenance if s.kind == "text_to_3d")
    assert step.parameters["selected_worker"] == "tripo_api"
    assert step.parameters["extras"]["nested"]["token"] == "<redacted>"
    assert "secret-value" not in step.model_dump_json()
    assert "secret-token" not in step.model_dump_json()


def test_run_texture_mesh_with_stub(tmp_path):
    trimesh = pytest.importorskip("trimesh")
    from ghostforge_core import bootstrap, CoreConfig
    from ghostforge_core.manifest import read_manifest
    from ghostforge_core.operations.workers import run_texture_mesh
    from ghostforge_core.workers.schemas import TextureMeshRequest

    bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    mesh = trimesh.creation.box(extents=(1, 1, 1))
    mesh_path = tmp_path / "input.obj"
    mesh.export(str(mesh_path))

    asset_dir = tmp_path / "asset_texture_mesh"
    spec = TextureMeshRequest(
        input_mesh_path=mesh_path,
        prompt="warm stone wall",
        output_dir=asset_dir,
        worker="stub_texture_mesh",
        texture_size=256,
    )
    result = run_texture_mesh(spec)
    assert Path(result["output_mesh"]).exists()
    assert result["texture_map"] and Path(result["texture_map"]).exists()

    manifest = read_manifest(asset_dir)
    roles = {a.role for a in manifest.artifacts}
    assert "texture.base_color" in roles


def test_dispatch_unknown_worker_raises(tmp_path):
    pytest.importorskip("trimesh")
    from ghostforge_core import bootstrap, CoreConfig
    from ghostforge_core.operations.workers import run_image_to_3d
    from ghostforge_core.workers import WorkerUnavailable
    from ghostforge_core.workers.schemas import ImageTo3DRequest

    bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    spec = ImageTo3DRequest(
        input_image_path=tmp_path / "x.png",
        output_dir=tmp_path / "out",
        worker="not_a_real_worker",
    )
    with pytest.raises(WorkerUnavailable):
        run_image_to_3d(spec)
