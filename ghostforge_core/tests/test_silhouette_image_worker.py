"""Tests for the real SilhouetteImageTo3DWorker."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import trimesh

from ghostforge_core.workers.capabilities import Capability
from ghostforge_core.workers.schemas import ImageTo3DRequest
from ghostforge_core.workers.silhouette_image import (
    SilhouetteImageTo3DWorker,
    _ear_clip,
    _load_mask,
    _rdp,
    _trace_outer_contour,
)


@pytest.fixture
def worker() -> SilhouetteImageTo3DWorker:
    return SilhouetteImageTo3DWorker()


def _write_circle_png(path: Path, size: int = 64, radius: int = 24) -> Path:
    from PIL import Image

    img = np.zeros((size, size, 4), dtype=np.uint8)
    cy, cx = size // 2, size // 2
    yy, xx = np.mgrid[:size, :size]
    mask = (xx - cx) ** 2 + (yy - cy) ** 2 <= radius ** 2
    img[mask] = (255, 200, 100, 255)
    Image.fromarray(img, mode="RGBA").save(path)
    return path


def _write_rect_rgb_png(path: Path, size: int = 64) -> Path:
    """Image with white background and a black rectangle subject."""
    from PIL import Image

    img = np.full((size, size, 3), 255, dtype=np.uint8)
    img[16:48, 20:44] = (10, 10, 10)
    Image.fromarray(img, mode="RGB").save(path)
    return path


def _request(image: Path, output_dir: Path) -> ImageTo3DRequest:
    return ImageTo3DRequest(
        output_dir=output_dir,
        input_image_path=image,
        prompt="silhouette",
        output_format="glb",
        seed=1,
    )


# ---------------------------------------------------------------------------
# Probe + descriptor
# ---------------------------------------------------------------------------


def test_probe_runnable_with_pillow_present(worker):
    probe = worker.probe()
    assert probe.runnable is True
    assert probe.device == "cpu"


def test_descriptor_marked_real(worker):
    assert worker.is_stub is False
    assert worker.priority > 0
    assert Capability.image_to_3d in worker.capabilities


# ---------------------------------------------------------------------------
# Mask + contour helpers
# ---------------------------------------------------------------------------


def test_load_mask_from_alpha(tmp_path):
    p = _write_circle_png(tmp_path / "circle.png")
    mask = _load_mask(p)
    assert mask.dtype == bool
    assert mask.sum() > 0
    assert mask.sum() < mask.size  # not the whole frame


def test_load_mask_from_rgb_background_subtraction(tmp_path):
    p = _write_rect_rgb_png(tmp_path / "rect.png")
    mask = _load_mask(p)
    assert mask.sum() > 0
    # Subject is ~32x24 pixels.
    assert 200 < mask.sum() < 1500


def test_trace_outer_contour_on_filled_rectangle():
    mask = np.zeros((20, 30), dtype=bool)
    mask[5:15, 8:22] = True
    contour = _trace_outer_contour(mask)
    assert len(contour) >= 4


def test_rdp_simplifies_rectangle_contour():
    rect = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (2.0, 2.0), (0.0, 2.0)]
    simplified = _rdp(rect, epsilon=0.1)
    # Collinear midpoints should drop out.
    assert len(simplified) <= 4


def test_ear_clip_rectangle_yields_two_triangles():
    poly = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    verts, faces = _ear_clip(poly)
    assert len(verts) == 4
    assert len(faces) == 2


# ---------------------------------------------------------------------------
# Run output
# ---------------------------------------------------------------------------


def test_run_circle_emits_extruded_mesh(tmp_path, worker):
    img = _write_circle_png(tmp_path / "circle.png", size=128, radius=48)
    spec = _request(img, tmp_path)
    result = worker.run(spec, reporter=None, cancel=None)
    out = Path(result["output_mesh"])
    assert out.exists()
    mesh = trimesh.load(str(out), force="mesh", process=False)
    assert isinstance(mesh, trimesh.Trimesh)
    # Roughly disc-shaped extrusion with reasonable face count.
    assert len(mesh.faces) > 20
    # Z extent equals the configured thickness.
    assert mesh.extents[2] == pytest.approx(worker.default_thickness_m, rel=0.05)


def test_run_rect_rgb_extracts_silhouette_without_alpha(tmp_path, worker):
    img = _write_rect_rgb_png(tmp_path / "rect.png", size=128)
    spec = _request(img, tmp_path)
    result = worker.run(spec, reporter=None, cancel=None)
    mesh = trimesh.load(result["output_mesh"], force="mesh", process=False)
    assert len(mesh.faces) > 0
    # Front + back caps for a rectangle = 2*2 tris each, plus 4 side quads.
    assert len(mesh.faces) >= 12


def test_run_returns_metadata(tmp_path, worker):
    img = _write_circle_png(tmp_path / "circle.png")
    spec = _request(img, tmp_path)
    result = worker.run(spec, reporter=None, cancel=None)
    md = result["metadata"]
    assert md["is_stub"] is False
    assert md["vertex_count"] > 0
    assert md["face_count"] > 0
    assert md["contour_points"] >= 3


def test_run_rejects_blank_image(tmp_path, worker):
    from PIL import Image

    blank = tmp_path / "blank.png"
    Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(blank)
    spec = _request(blank, tmp_path)
    from ghostforge_core.workers.base import WorkerUnavailable

    with pytest.raises(WorkerUnavailable):
        worker.run(spec, reporter=None, cancel=None)


def test_selector_prefers_silhouette_over_stub():
    from ghostforge_core.workers import default_workers

    reg = default_workers()
    chosen = reg.select(Capability.image_to_3d, allow_stub=True)
    assert chosen.name == "silhouette_image_to_3d"
