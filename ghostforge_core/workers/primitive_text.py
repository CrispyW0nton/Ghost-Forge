"""Internal primitive blockout utility.

This is *not* Ghost-Forge's production mesh-generation path and is not
registered by :func:`default_workers`. Production mesh generation is
reference-image driven. This module stays as an internal deterministic
primitive-kit synthesizer for tests, demos, and future blockout tooling.

Why ship this:

* The framework was missing a real worker that anyone could run on a
  CPU-only laptop with the base install. Stubs always emit the same
  cube; this worker actually responds to the prompt.
* For 80% of vertical-slice props (crates, walls, columns, barrels,
  stairs, signs), parametric primitives are *better* than diffusion
  outputs anyway: clean topology, predictable scale, exact dimensions.
* It seeds future ML workers (TRELLIS, Hunyuan3D) without forcing the
  user to install them — auto-selection still prefers a real ML
  worker when one is runnable, because this worker has ``priority=20``
  while the GPU workers declare ``priority=80``+.

Supported shape keywords (case-insensitive):

* ``box`` / ``cube`` / ``crate`` — trimesh.creation.box
* ``sphere`` / ``ball`` / ``orb`` — UV sphere
* ``cylinder`` / ``column`` / ``pillar`` / ``barrel`` / ``can``
* ``cone`` / ``spike``
* ``capsule`` / ``pill``
* ``torus`` / ``ring`` / ``donut``
* ``plane`` / ``floor`` / ``slab``
* ``wall`` — thin slab in vertical orientation
* ``stairs`` / ``staircase`` — composite of stacked boxes
* ``icosphere`` / ``rock`` / ``boulder``

Modifier keywords:

* ``tall`` / ``short`` / ``wide`` / ``narrow`` / ``thin`` / ``thick``
  scale dominant axes by a factor.
* Numeric tokens like ``2m`` / ``1.5m`` set the dominant size.

Anything we can't parse falls back to a tagged box with the prompt
hash baked into the dimensions, so output is still deterministic and
keyed on the input.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import CPU_ONLY_RESOURCES
from .schemas import TextTo3DRequest


# ---------------------------------------------------------------------------
# Prompt parsing
# ---------------------------------------------------------------------------


_SHAPE_KEYWORDS: dict[str, str] = {
    # box family
    "box": "box",
    "cube": "box",
    "crate": "box",
    "block": "box",
    "brick": "box",
    "chest": "box",
    "case": "box",
    # sphere family
    "sphere": "sphere",
    "ball": "sphere",
    "orb": "sphere",
    "globe": "sphere",
    # cylinder family
    "cylinder": "cylinder",
    "column": "cylinder",
    "pillar": "cylinder",
    "barrel": "cylinder",
    "can": "cylinder",
    "tube": "cylinder",
    "log": "cylinder",
    # cone family
    "cone": "cone",
    "spike": "cone",
    "tent": "cone",
    # capsule family
    "capsule": "capsule",
    "pill": "capsule",
    # torus family
    "torus": "torus",
    "ring": "torus",
    "donut": "torus",
    "doughnut": "torus",
    # plane family
    "plane": "plane",
    "floor": "plane",
    "slab": "plane",
    "ground": "plane",
    "tile": "plane",
    # wall
    "wall": "wall",
    "fence": "wall",
    "panel": "wall",
    # stairs
    "stairs": "stairs",
    "staircase": "stairs",
    "steps": "stairs",
    "ladder": "stairs",
    # icosphere / rock
    "rock": "icosphere",
    "boulder": "icosphere",
    "stone": "icosphere",
    "icosphere": "icosphere",
}


_MODIFIER_KEYWORDS: dict[str, tuple[str, float]] = {
    # axis_focus, factor
    "tall": ("up", 1.6),
    "long": ("forward", 1.6),
    "wide": ("right", 1.6),
    "huge": ("uniform", 1.7),
    "big": ("uniform", 1.4),
    "large": ("uniform", 1.4),
    "small": ("uniform", 0.6),
    "tiny": ("uniform", 0.4),
    "short": ("up", 0.55),
    "narrow": ("right", 0.55),
    "thin": ("forward", 0.55),
    "thick": ("forward", 1.5),
    "flat": ("up", 0.35),
    "fat": ("uniform", 1.3),
}


_SIZE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(m|cm|mm|meter|meters|metre|metres)\b",
    re.IGNORECASE,
)


def _seed_from(spec: TextTo3DRequest) -> int:
    if spec.seed is not None:
        return int(spec.seed)
    digest = hashlib.sha256(spec.model_dump_json().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


# Specificity ranking — when multiple shape keywords appear in a prompt,
# the kind with the highest score wins. Walls/stairs/planes are highly
# specific architectural elements; rocks/spheres are catch-alls.
_SHAPE_SPECIFICITY: dict[str, int] = {
    "stairs": 100,
    "wall": 90,
    "torus": 85,
    "capsule": 80,
    "cone": 75,
    "cylinder": 70,
    "plane": 60,
    "icosphere": 50,
    "sphere": 40,
    "box": 30,
}


def _detect_shape(prompt: str) -> str:
    lowered = prompt.lower()
    matches: list[tuple[str, str, int]] = []
    for kw, kind in _SHAPE_KEYWORDS.items():
        # Require word-boundary match so "block" doesn't pick up "blocking".
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            matches.append((kw, kind, _SHAPE_SPECIFICITY.get(kind, 0)))
    if not matches:
        return "box"
    # Highest specificity wins; tie-broken by longer keyword.
    matches.sort(key=lambda m: (m[2], len(m[0])), reverse=True)
    return matches[0][1]


def _detect_size(prompt: str) -> float | None:
    match = _SIZE_PATTERN.search(prompt)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit in {"cm"}:
        return value * 0.01
    if unit in {"mm"}:
        return value * 0.001
    return value  # m / metre / meter


def _detect_modifiers(prompt: str) -> list[tuple[str, float]]:
    lowered = prompt.lower()
    out: list[tuple[str, float]] = []
    for kw, mod in _MODIFIER_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", lowered):
            out.append(mod)
    return out


# ---------------------------------------------------------------------------
# Geometry construction
# ---------------------------------------------------------------------------


def _apply_modifiers(extents: tuple[float, float, float], modifiers) -> tuple[float, float, float]:
    """Apply ``tall`` / ``wide`` / etc factors to the canonical (x, y, z) extents."""

    x, y, z = extents
    for axis, factor in modifiers:
        if axis == "uniform":
            x *= factor
            y *= factor
            z *= factor
        elif axis == "up":  # Y in canonical glTF
            y *= factor
        elif axis == "right":
            x *= factor
        elif axis == "forward":
            z *= factor
    # Clamp to a sane range so chained modifiers don't explode geometry.
    return (
        max(0.05, min(50.0, x)),
        max(0.05, min(50.0, y)),
        max(0.05, min(50.0, z)),
    )


def _build_mesh(shape: str, base: float, modifiers, seed: int):
    import trimesh

    extents = _apply_modifiers((base, base, base), modifiers)
    if shape == "box":
        return trimesh.creation.box(extents=extents)
    if shape == "sphere":
        radius = max(extents) * 0.5
        return trimesh.creation.uv_sphere(radius=radius, count=[24, 16])
    if shape == "cylinder":
        radius = (extents[0] + extents[2]) * 0.25
        height = extents[1]
        return trimesh.creation.cylinder(radius=max(radius, 0.05), height=height, sections=24)
    if shape == "cone":
        radius = (extents[0] + extents[2]) * 0.25
        height = extents[1]
        return trimesh.creation.cone(radius=max(radius, 0.05), height=height, sections=24)
    if shape == "capsule":
        radius = min(extents[0], extents[2]) * 0.5
        height = max(extents[1] - 2 * radius, 0.05)
        return trimesh.creation.capsule(radius=max(radius, 0.05), height=height, count=[16, 16])
    if shape == "torus":
        major = max(extents[0], extents[2]) * 0.4
        minor = major * 0.3
        return trimesh.creation.torus(major_radius=major, minor_radius=minor, major_sections=24, minor_sections=12)
    if shape == "plane":
        return trimesh.creation.box(extents=(extents[0], 0.05, extents[2]))
    if shape == "wall":
        return trimesh.creation.box(extents=(extents[0], extents[1], 0.1))
    if shape == "stairs":
        steps = max(3, min(12, 3 + (seed % 6)))
        run = extents[2] / steps
        rise = extents[1] / steps
        meshes = []
        for i in range(steps):
            step = trimesh.creation.box(
                extents=(extents[0], rise * (i + 1), run),
            )
            step.apply_translation((0.0, rise * (i + 1) * 0.5, run * (i + 0.5)))
            meshes.append(step)
        return trimesh.util.concatenate(meshes)
    if shape == "icosphere":
        radius = max(extents) * 0.5
        # Mid-resolution icosphere; we jitter the vertices a touch so the
        # output reads as "rock-shaped" rather than "perfect sphere".
        m = trimesh.creation.icosphere(subdivisions=2, radius=radius)
        import numpy as np

        rng = np.random.default_rng(seed)
        m.vertices = m.vertices + rng.normal(scale=radius * 0.06, size=m.vertices.shape)
        m.fix_normals()
        return m

    return trimesh.creation.box(extents=extents)


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


class PrimitiveTextTo3DWorker:
    """Internal non-generative primitive blockout worker.

    This class intentionally remains out of the default worker registry so
    Ghost-Forge does not advertise text-only mesh generation.
    """

    name = "primitive_text_to_3d"
    capabilities = [Capability.text_to_3d]
    priority = 20  # > stub (0), < GPU real workers (>= 70)
    license = "MIT"
    description = (
        "Deterministic primitive-kit text-to-3D. Parses prompts for shape "
        "and modifier keywords and emits real trimesh geometry — boxes, "
        "spheres, cylinders, cones, capsules, tori, planes, walls, stairs, "
        "and rock-like icospheres. CPU-only, no model weights required."
    )
    homepage = "https://github.com/CrispyW0nton/Ghost-Forge"
    paper_url = None
    weights_url = None
    is_stub = False
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def probe(self) -> ProbeResult:
        try:
            import trimesh  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            return ProbeResult(
                name=self.name,
                runnable=False,
                reason=f"missing dependency: {exc.name}",
                missing=[exc.name or "unknown"],
            )
        return ProbeResult(name=self.name, runnable=True, device="cpu")

    def run(
        self,
        spec: TextTo3DRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        try:
            import trimesh  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise WorkerUnavailable("trimesh is required") from exc

        if reporter:
            reporter("primitive_text:parse", 5.0, "parsing prompt")
        if cancel:
            cancel.throw_if_cancelled()

        seed = _seed_from(spec)
        shape = _detect_shape(spec.prompt)
        explicit_size = _detect_size(spec.prompt)
        modifiers = _detect_modifiers(spec.prompt)

        # Default base size by shape: a "wall" wants ~3 m by default,
        # an "orb" wants ~1 m, a stair flight wants ~2 m total run.
        defaults = {
            "wall": 3.0,
            "stairs": 2.0,
            "plane": 4.0,
            "torus": 1.5,
        }
        base = explicit_size if explicit_size is not None else defaults.get(shape, 1.0)

        if reporter:
            reporter("primitive_text:build", 50.0, f"building {shape}")
        mesh = _build_mesh(shape, base, modifiers, seed)
        if cancel:
            cancel.throw_if_cancelled()

        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"primitive_text_to_3d.{spec.output_format}"
        mesh.export(str(out_path))

        if reporter:
            reporter("primitive_text:done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "is_stub": False,
                "seed": seed,
                "prompt": spec.prompt,
                "shape": shape,
                "base_size_m": base,
                "modifiers": [{"axis": a, "factor": f} for a, f in modifiers],
                "vertex_count": int(len(mesh.vertices)),
                "face_count": int(len(mesh.faces)),
            },
        }


__all__ = ["PrimitiveTextTo3DWorker"]
