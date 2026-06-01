"""Always-runnable real image-to-3D worker.

Like :mod:`primitive_text`, this is a *real* worker (not a stub) that
ships in the base install. It produces honest, useful geometry from an
input image without any ML dependencies — by extracting the silhouette
of the subject and extruding it into a thickened mesh.

The technique works exceptionally well for:

* 2D game sprites you want to bring into a 3D scene
* Cards, banners, signs, decals
* Cookie-cutter / cardboard prop blockouts
* Any input where the alpha channel or background is reasonably
  separable from the subject

Pipeline:

1. Load the image with PIL.
2. Build a binary mask. If the image has alpha, use that. Otherwise
   threshold against a corner-sampled background colour.
3. Trace the mask's outer contour with a marching-squares walker (no
   OpenCV dependency — implemented inline against numpy).
4. Polygon-simplify the contour with a Ramer-Douglas-Peucker pass so
   the resulting mesh isn't a million triangles.
5. Triangulate the simplified polygon (use ``shapely`` + ``mapbox-earcut``
   if available, otherwise a fan triangulation that's correct for
   convex outlines and acceptable for most game assets).
6. Extrude along Z with the requested thickness, cap front and back.
7. Center the mesh on the origin and export.

When dependencies are missing, the probe reports honestly and the
selector falls back to a real GPU worker (if installed) or the stub.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

import numpy as np

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import CPU_ONLY_RESOURCES
from .schemas import ImageTo3DRequest


# ---------------------------------------------------------------------------
# Mask extraction
# ---------------------------------------------------------------------------


def _load_mask(image_path: Path, alpha_threshold: int = 16) -> np.ndarray:
    """Return a (H, W) bool array — True inside the subject."""

    from PIL import Image

    img = Image.open(image_path)
    img.load()

    if img.mode in ("RGBA", "LA"):
        alpha = np.asarray(img.split()[-1])
        return alpha > alpha_threshold

    rgb = np.asarray(img.convert("RGB"))
    # Sample the four corners as a reference background colour.
    corners = np.array(
        [rgb[0, 0], rgb[0, -1], rgb[-1, 0], rgb[-1, -1]], dtype=np.float32
    )
    bg = corners.mean(axis=0)
    distance = np.linalg.norm(rgb.astype(np.float32) - bg, axis=-1)
    threshold = max(20.0, distance.max() * 0.15)
    mask = distance > threshold
    if mask.sum() < (mask.size * 0.005):
        # Fallback: assume luminance > 50% is foreground.
        gray = np.asarray(img.convert("L"))
        mask = gray > 127
    return mask


# ---------------------------------------------------------------------------
# Contour tracing (no OpenCV)
# ---------------------------------------------------------------------------


_NEIGHBOURS = [
    (-1, 0), (-1, 1), (0, 1), (1, 1),
    (1, 0), (1, -1), (0, -1), (-1, -1),
]


def _trace_outer_contour(mask: np.ndarray) -> list[tuple[float, float]]:
    """Moore-neighbour boundary trace of the largest connected region.

    Returns a closed polygon as (x, y) tuples in image coordinates
    (origin top-left). Empty list if the mask has no foreground.
    """

    if not mask.any():
        return []

    # Find the topmost-leftmost foreground pixel as the starting point —
    # this guarantees we trace the outer boundary, not a hole.
    rows, cols = np.where(mask)
    start_idx = int(np.lexsort((cols, rows))[0])
    start = (int(rows[start_idx]), int(cols[start_idx]))

    contour: list[tuple[int, int]] = [start]
    current = start
    prev_dir = 6  # Came "from the left"; start scanning rotated.

    h, w = mask.shape
    max_iters = h * w * 4
    for _ in range(max_iters):
        # Try neighbours in clockwise order starting from prev_dir + 2.
        found = False
        for offset in range(8):
            d = (prev_dir + 2 + offset) % 8
            dr, dc = _NEIGHBOURS[d]
            nr, nc = current[0] + dr, current[1] + dc
            if 0 <= nr < h and 0 <= nc < w and mask[nr, nc]:
                if (nr, nc) == start and len(contour) > 1:
                    return [(float(c) + 0.5, float(r) + 0.5) for r, c in contour]
                contour.append((nr, nc))
                # Direction we came from = opposite of d.
                prev_dir = (d + 4) % 8
                current = (nr, nc)
                found = True
                break
        if not found:
            break

    return [(float(c) + 0.5, float(r) + 0.5) for r, c in contour]


# ---------------------------------------------------------------------------
# Polygon simplification (Ramer-Douglas-Peucker)
# ---------------------------------------------------------------------------


def _rdp(points: list[tuple[float, float]], epsilon: float) -> list[tuple[float, float]]:
    if len(points) < 3:
        return list(points)

    def perp_distance(p, a, b):
        ax, ay = a
        bx, by = b
        px, py = p
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        return abs(dy * px - dx * py + bx * ay - by * ax) / math.hypot(dx, dy)

    a, b = points[0], points[-1]
    max_d = 0.0
    index = 0
    for i in range(1, len(points) - 1):
        d = perp_distance(points[i], a, b)
        if d > max_d:
            max_d, index = d, i
    if max_d <= epsilon:
        return [a, b]
    left = _rdp(points[: index + 1], epsilon)
    right = _rdp(points[index:], epsilon)
    return left[:-1] + right


# ---------------------------------------------------------------------------
# Triangulation + extrusion
# ---------------------------------------------------------------------------


def _signed_area(poly: list[tuple[float, float]]) -> float:
    s = 0.0
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return s * 0.5


def _triangulate(poly: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate a simple polygon. Returns (verts2d, faces).

    Tries shapely + mapbox-earcut when available; falls back to ear-
    clipping with a small custom implementation that's correct for
    simple polygons and good enough for most silhouettes.
    """

    if _signed_area(poly) < 0:
        poly = list(reversed(poly))

    try:
        import mapbox_earcut as earcut  # type: ignore

        verts = np.array(poly, dtype=np.float64)
        faces = earcut.triangulate_float64(verts.flatten(), [len(verts)])
        return verts, faces.reshape(-1, 3)
    except Exception:
        pass

    return _ear_clip(poly)


def _ear_clip(poly: list[tuple[float, float]]) -> tuple[np.ndarray, np.ndarray]:
    verts = list(poly)
    indices = list(range(len(verts)))
    faces: list[tuple[int, int, int]] = []

    def is_convex(prev_idx, idx, next_idx):
        ax, ay = verts[prev_idx]
        bx, by = verts[idx]
        cx, cy = verts[next_idx]
        return (bx - ax) * (cy - ay) - (by - ay) * (cx - ax) > 0

    def point_in_triangle(p, a, b, c):
        def sign(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])

        d1 = sign(p, a, b)
        d2 = sign(p, b, c)
        d3 = sign(p, c, a)
        has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
        has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
        return not (has_neg and has_pos)

    safety = len(indices) * 4
    while len(indices) > 3 and safety > 0:
        safety -= 1
        n = len(indices)
        ear_found = False
        for i in range(n):
            prev_i = indices[(i - 1) % n]
            curr_i = indices[i]
            next_i = indices[(i + 1) % n]
            if not is_convex(prev_i, curr_i, next_i):
                continue
            a, b, c = verts[prev_i], verts[curr_i], verts[next_i]
            contains_other = any(
                point_in_triangle(verts[j], a, b, c)
                for j in indices
                if j not in (prev_i, curr_i, next_i)
            )
            if contains_other:
                continue
            faces.append((prev_i, curr_i, next_i))
            indices.pop(i)
            ear_found = True
            break
        if not ear_found:
            # Polygon is non-simple or numerically degenerate; fan-triangulate
            # the remainder so we never return zero faces for a non-empty
            # silhouette. Quality drop is acceptable for blockout assets.
            for i in range(1, len(indices) - 1):
                faces.append((indices[0], indices[i], indices[i + 1]))
            indices = [indices[0], indices[1], indices[-1]]
            break

    if len(indices) == 3:
        faces.append((indices[0], indices[1], indices[2]))
    return np.array(verts, dtype=np.float64), np.array(faces, dtype=np.int64)


def _extrude(
    verts2d: np.ndarray, faces2d: np.ndarray, depth: float
) -> tuple[np.ndarray, np.ndarray]:
    """Extrude a 2D triangulated polygon along +Z by ``depth`` (centered)."""

    n = len(verts2d)
    front = np.column_stack([verts2d, np.full(n, +depth * 0.5)])
    back = np.column_stack([verts2d, np.full(n, -depth * 0.5)])
    verts3d = np.vstack([front, back])

    front_faces = faces2d.copy()
    back_faces = faces2d[:, ::-1] + n  # reversed winding for back caps

    # Side walls — quads as two triangles per polygon edge (use the
    # outline order, which we recover from the original polygon order).
    side: list[tuple[int, int, int]] = []
    for i in range(n):
        j = (i + 1) % n
        a, b = i, j  # front
        c, d = j + n, i + n  # back
        side.append((a, c, b))
        side.append((b, c, d))

    faces3d = np.vstack([front_faces, back_faces, np.array(side, dtype=np.int64)])
    return verts3d, faces3d


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def _seed_from(spec: ImageTo3DRequest) -> int:
    if spec.seed is not None:
        return int(spec.seed)
    digest = hashlib.sha256(spec.model_dump_json().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


class SilhouetteImageTo3DWorker:
    """Real CPU-only image-to-3D worker via silhouette extrusion."""

    name = "silhouette_image_to_3d"
    capabilities = [Capability.image_to_3d]
    priority = 25  # > stub (0); < GPU real workers (>= 70)
    license = "MIT"
    description = (
        "CPU-only image-to-3D via silhouette extrusion. Builds a mask from "
        "the alpha channel (or background-subtracted RGB), traces the outer "
        "contour, simplifies it, triangulates, and extrudes along Z. "
        "Excellent for cards, signs, sprites, and prototype props."
    )
    homepage = "https://github.com/CrispyW0nton/Ghost-Forge"
    paper_url = None
    weights_url = None
    is_stub = False
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    # Tunables (overridable via spec.reference_camera or extra args)
    default_thickness_m = 0.1
    default_target_height_m = 1.0
    default_simplify_eps_px = 1.0

    def probe(self) -> ProbeResult:
        missing: list[str] = []
        for module in ("trimesh", "numpy", "PIL"):
            try:
                __import__(module)
            except ImportError:
                missing.append(module)
        if missing:
            return ProbeResult(
                name=self.name,
                runnable=False,
                reason=f"missing dependency: {', '.join(missing)}",
                missing=missing,
            )
        return ProbeResult(name=self.name, runnable=True, device="cpu")

    def run(
        self,
        spec: ImageTo3DRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        try:
            import trimesh
        except ImportError as exc:  # pragma: no cover
            raise WorkerUnavailable("trimesh is required") from exc

        if reporter:
            reporter("silhouette:load", 5.0, "loading image")
        mask = _load_mask(Path(spec.input_image_path))
        if not mask.any():
            raise WorkerUnavailable(
                f"Could not extract a foreground silhouette from {spec.input_image_path}"
            )

        if cancel:
            cancel.throw_if_cancelled()
        if reporter:
            reporter("silhouette:trace", 25.0, "tracing contour")
        contour = _trace_outer_contour(mask)
        if len(contour) < 4:
            raise WorkerUnavailable(
                "Silhouette is too small or degenerate to extrude (need >= 4 boundary points)"
            )

        if reporter:
            reporter("silhouette:simplify", 45.0, "simplifying contour")
        simplified = _rdp(contour, epsilon=self.default_simplify_eps_px)
        # _rdp returns the open chain; reclose for triangulation.
        if simplified[0] != simplified[-1]:
            simplified = simplified + [simplified[0]]
        # Strip the duplicate closing point — triangulator wants an open chain.
        simplified = simplified[:-1]
        if len(simplified) < 3:
            raise WorkerUnavailable("Simplified polygon has < 3 vertices")

        if cancel:
            cancel.throw_if_cancelled()
        if reporter:
            reporter("silhouette:triangulate", 65.0, f"triangulating {len(simplified)} verts")
        verts2d, faces2d = _triangulate(simplified)
        if len(faces2d) == 0:
            raise WorkerUnavailable("Triangulator produced zero faces")

        # Image coordinates have +Y down; flip to make the mesh upright.
        verts2d = verts2d.copy()
        verts2d[:, 1] = -verts2d[:, 1]

        # Normalise to target height: longest extent → 1 m by default.
        height_px = float(np.ptp(verts2d[:, 1]) or 1.0)
        scale = self.default_target_height_m / height_px
        verts2d *= scale

        if reporter:
            reporter("silhouette:extrude", 85.0, "extruding")
        verts3d, faces3d = _extrude(verts2d, faces2d, depth=self.default_thickness_m)

        # Centre on origin.
        verts3d = verts3d - verts3d.mean(axis=0)
        mesh = trimesh.Trimesh(vertices=verts3d, faces=faces3d, process=True)
        mesh.fix_normals()

        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"silhouette_image_to_3d.{spec.output_format}"
        mesh.export(str(out_path))

        if reporter:
            reporter("silhouette:done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "is_stub": False,
                "seed": _seed_from(spec),
                "input_image_path": str(spec.input_image_path),
                "prompt": spec.prompt,
                "vertex_count": int(len(mesh.vertices)),
                "face_count": int(len(mesh.faces)),
                "contour_points": len(simplified),
                "extrusion_depth_m": self.default_thickness_m,
            },
        }


__all__ = ["SilhouetteImageTo3DWorker"]
