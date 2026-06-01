"""Tests for :class:`InstantMeshWorker` activation logic.

The probe and unavailable-path tests run on every host. The full
inference path is gated behind ``--run-gpu`` because it requires the
upstream InstantMesh package and a CUDA GPU.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.workers.base import WorkerUnavailable
from ghostforge_core.workers.instantmesh import InstantMeshWorker


def test_set_model_registry_and_resolve_missing_model(tmp_path):
    from ghostforge_core.models import ModelArtifact, ModelFile, ModelRegistry

    registry = ModelRegistry(tmp_path)
    registry.register(
        ModelArtifact(
            model_id="instantmesh",
            repo_id="TencentARC/InstantMesh",
            files=[ModelFile(path="model.safetensors")],
        )
    )

    worker = InstantMeshWorker()
    worker.set_model_registry(registry)

    with pytest.raises(WorkerUnavailable, match="not downloaded"):
        worker._resolve_checkpoint()


def test_resolve_checkpoint_without_registry_raises():
    worker = InstantMeshWorker()
    with pytest.raises(WorkerUnavailable, match="model registry not configured"):
        worker._resolve_checkpoint()


def test_run_raises_when_dependencies_missing(tmp_path):
    worker = InstantMeshWorker()
    p = worker.probe()
    if p.runnable:
        pytest.skip("torch + instantmesh available; can't validate the unavailable path")

    class _Spec:
        image_path = str(tmp_path / "img.png")
        output_dir = str(tmp_path)
        seed = None

    with pytest.raises(WorkerUnavailable):
        worker.run(_Spec(), reporter=None, cancel=None)


def test_descriptor_advertises_required_models():
    worker = InstantMeshWorker()
    assert worker.required_models == ["instantmesh"]
    assert worker.is_stub is False


@pytest.mark.gpu
@pytest.mark.heavy_deps("torch")
def test_real_inference_smoke(tmp_path):
    """Opt-in: requires upstream InstantMesh package + downloaded weights."""

    pytest.importorskip("instantmesh")

    from PIL import Image

    img = Image.new("RGB", (256, 256), color=(120, 80, 50))
    img_path = tmp_path / "input.png"
    img.save(img_path)

    from ghostforge_core import bootstrap, CoreConfig

    ctx = bootstrap(CoreConfig(data_root=str(tmp_path / "data"), dispatch_jobs=False))
    worker = ctx.workers.get("instantmesh")

    class _Spec:
        image_path = str(img_path)
        output_dir = str(tmp_path / "out")
        seed = 0

    Path(_Spec.output_dir).mkdir(parents=True, exist_ok=True)
    result = worker.run(_Spec(), reporter=lambda *a, **kw: None, cancel=None)
    assert result["worker"] == "instantmesh"
    assert Path(result["output_mesh"]).exists()
