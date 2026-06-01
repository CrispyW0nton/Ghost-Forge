"""Tests for :class:`DiffusersTextureWorker`.

The probe path is exercised regardless of optional ML deps; the actual
inference path is gated on the ``gpu`` marker because it pulls a
multi-GB SD checkpoint from HuggingFace.
"""

from __future__ import annotations

import pytest

from ghostforge_core.workers.base import WorkerUnavailable
from ghostforge_core.workers.capabilities import Capability
from ghostforge_core.workers.diffusers_texture import DiffusersTextureWorker


def test_descriptor_metadata():
    w = DiffusersTextureWorker()
    assert w.name == "diffusers_texture"
    assert Capability.texture_mesh in w.capabilities
    assert w.is_stub is False
    # Resources advertise CUDA preference but allow CPU fallback so the
    # scheduler can still place the worker on hosts without a GPU.
    assert w.resources.requires_cuda is True
    assert w.resources.cpu_fallback is True
    assert "sd-1-5" in w.required_models


def test_probe_reports_missing_torch_when_absent():
    w = DiffusersTextureWorker()
    p = w.probe()
    assert p.name == "diffusers_texture"
    # On the CPU-only test host neither torch nor diffusers is installed,
    # so probe() must report runnable=False with a clear `missing` list.
    if p.runnable:
        # If the host *does* have torch (e.g. dev workstation), we don't
        # want to fail — just confirm the metadata is sane.
        assert isinstance(p.metadata.get("vram_gb"), (int, float))
    else:
        assert p.reason
        assert any(m in {"torch", "diffusers"} for m in p.missing)


def test_run_raises_worker_unavailable_without_torch():
    w = DiffusersTextureWorker()
    p = w.probe()
    if p.runnable:
        pytest.skip("torch + diffusers installed; can't validate the unavailable path")

    class _Spec:
        prompt = "stone wall"
        input_mesh_path = "/tmp/whatever.obj"
        output_dir = "/tmp/out"
        texture_size = 512
        reference_image_path = None
        seed = None
        output_format = "glb"

    with pytest.raises(WorkerUnavailable):
        w.run(_Spec(), reporter=None, cancel=None)


@pytest.mark.gpu
@pytest.mark.heavy_deps("torch", "diffusers")
def test_real_inference_smoke(tmp_path):
    """Smoke test: real SD inference into UV atlas. Opt-in only.

    Run with ``pytest --run-gpu -k diffusers_texture`` on a machine with
    the ``ai`` extras installed and a CUDA-capable GPU.
    """

    import trimesh  # type: ignore

    cube = trimesh.creation.box(extents=(1, 1, 1))
    mesh_path = tmp_path / "cube.obj"
    cube.export(str(mesh_path))

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    class _Spec:
        prompt = "rusted iron"
        input_mesh_path = str(mesh_path)
        output_dir = str(out_dir)
        texture_size = 256  # tiny — keep the test fast
        reference_image_path = None
        seed = 1234
        output_format = "glb"

    w = DiffusersTextureWorker()
    result = w.run(_Spec(), reporter=lambda *a, **kw: None, cancel=None)
    assert result["worker"] == "diffusers_texture"
    assert result["metadata"]["is_stub"] is False
    assert (out_dir / "diffusers_texture.png").exists()
