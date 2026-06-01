"""Tests for the real PrimitiveTextTo3DWorker."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import trimesh

from ghostforge_core.workers.capabilities import Capability
from ghostforge_core.workers.primitive_text import (
    PrimitiveTextTo3DWorker,
    _detect_modifiers,
    _detect_shape,
    _detect_size,
)
from ghostforge_core.workers.schemas import TextTo3DRequest


@pytest.fixture
def worker() -> PrimitiveTextTo3DWorker:
    return PrimitiveTextTo3DWorker()


def _request(prompt: str, output_dir: Path, **extra) -> TextTo3DRequest:
    return TextTo3DRequest(
        output_dir=output_dir,
        prompt=prompt,
        output_format="glb",
        seed=extra.pop("seed", 42),
        **extra,
    )


# ---------------------------------------------------------------------------
# Probe + descriptor
# ---------------------------------------------------------------------------


def test_probe_is_always_runnable(worker):
    probe = worker.probe()
    assert probe.runnable is True
    assert probe.device == "cpu"


def test_descriptor_marked_real_not_stub(worker):
    assert worker.is_stub is False
    assert worker.priority > 0
    assert Capability.text_to_3d in worker.capabilities
    assert worker.required_models == []


# ---------------------------------------------------------------------------
# Prompt parsing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt,expected", [
    ("a wooden crate", "box"),
    ("tall sphere on a pedestal", "sphere"),
    ("rusted barrel", "cylinder"),
    ("traffic cone", "cone"),
    ("a glowing torus ring", "torus"),
    ("a stone wall blocking the path", "wall"),
    ("flight of stairs", "stairs"),
    ("a small rock", "icosphere"),
    ("just some random gibberish", "box"),  # fallback
])
def test_detect_shape(prompt, expected):
    assert _detect_shape(prompt) == expected


def test_detect_size_explicit_meters():
    assert _detect_size("a tall 2m pillar") == pytest.approx(2.0)


def test_detect_size_centimeters():
    assert _detect_size("a 50cm cube") == pytest.approx(0.5)


def test_detect_size_returns_none_when_absent():
    assert _detect_size("a cube") is None


def test_detect_modifiers_picks_up_tall_and_narrow():
    mods = _detect_modifiers("a tall narrow column")
    axes = {axis for axis, _ in mods}
    assert "up" in axes
    assert "right" in axes


# ---------------------------------------------------------------------------
# Run output
# ---------------------------------------------------------------------------


def test_run_box_emits_real_mesh(tmp_path, worker):
    spec = _request("a small wooden crate", tmp_path)
    result = worker.run(spec, reporter=None, cancel=None)
    out = Path(result["output_mesh"])
    assert out.exists()
    mesh = trimesh.load(str(out), force="mesh", process=False)
    assert isinstance(mesh, trimesh.Trimesh)
    assert len(mesh.faces) > 0


def test_run_responds_to_shape_keyword(tmp_path, worker):
    box_spec = _request("a box", tmp_path / "box")
    sphere_spec = _request("a ball", tmp_path / "sphere")
    box_res = worker.run(box_spec, reporter=None, cancel=None)
    sphere_res = worker.run(sphere_spec, reporter=None, cancel=None)
    box_mesh = trimesh.load(box_res["output_mesh"], force="mesh", process=False)
    sphere_mesh = trimesh.load(sphere_res["output_mesh"], force="mesh", process=False)
    # Box has 8 vertices; sphere has many more.
    assert len(sphere_mesh.vertices) > len(box_mesh.vertices) * 5


def test_run_explicit_size_drives_extents(tmp_path, worker):
    spec = _request("a 4m tall column", tmp_path, seed=7)
    res = worker.run(spec, reporter=None, cancel=None)
    mesh = trimesh.load(res["output_mesh"], force="mesh", process=False)
    # 'tall' boosts up axis by 1.6, so y extent should be ~4 * 1.6 = 6.4m.
    assert max(mesh.extents) >= 4.0
    assert max(mesh.extents) <= 8.0


def test_run_returns_metadata(tmp_path, worker):
    spec = _request("a tall narrow column", tmp_path)
    result = worker.run(spec, reporter=None, cancel=None)
    md = result["metadata"]
    assert md["is_stub"] is False
    assert md["shape"] == "cylinder"
    assert md["vertex_count"] > 0
    assert md["face_count"] > 0
    assert isinstance(md["modifiers"], list)


def test_run_deterministic_for_same_seed(tmp_path, worker):
    s1 = _request("a small rock", tmp_path / "a", seed=99)
    s2 = _request("a small rock", tmp_path / "b", seed=99)
    a = worker.run(s1, reporter=None, cancel=None)
    b = worker.run(s2, reporter=None, cancel=None)
    ma = trimesh.load(a["output_mesh"], force="mesh", process=False)
    mb = trimesh.load(b["output_mesh"], force="mesh", process=False)
    assert ma.vertices.shape == mb.vertices.shape
    assert math.isclose(ma.volume, mb.volume, rel_tol=1e-9)


def test_run_stairs_produces_multi_step_geometry(tmp_path, worker):
    spec = _request("a flight of stairs", tmp_path, seed=1)
    res = worker.run(spec, reporter=None, cancel=None)
    mesh = trimesh.load(res["output_mesh"], force="mesh", process=False)
    # Stairs are concatenated boxes; expect >= 24 verts (>=3 stacked boxes).
    assert len(mesh.vertices) >= 24


def test_primitive_worker_not_registered_by_default():
    """Primitive blockouts are not production text-to-3D mesh generation."""

    from ghostforge_core.workers import default_workers
    from ghostforge_core.workers.base import WorkerSelectionError

    reg = default_workers()
    names = {w.name for w in reg.all()}
    assert "primitive_text_to_3d" not in names
    with pytest.raises(WorkerSelectionError):
        reg.select(Capability.text_to_3d, allow_stub=True)
