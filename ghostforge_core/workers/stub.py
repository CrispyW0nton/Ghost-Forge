"""Always-available stub workers.

Stubs let the asset pipeline run end-to-end on machines without any of
TRELLIS / Hunyuan3D / TripoSG / InstantMesh / Paint3D / SyncMVD installed.
They produce deterministic, valid output (a unit cube exported via trimesh)
so downstream stages — manifest emission, validation, engine handoff — can
be tested in isolation.

Stubs are flagged ``is_stub=True`` and assigned ``priority=0`` so the
selector always prefers a real worker when one is runnable; agents that
require deterministic test output should pass ``allow_stub=True`` and a
specific stub ``name`` rather than relying on auto-selection.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .base import ProbeResult, WorkerUnavailable
from .capabilities import Capability
from .resources import CPU_ONLY_RESOURCES
from .schemas import (
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)


def _seed_from(spec: Any) -> int:
    """Pick a deterministic seed from a spec for stable test output.

    Prefers the explicit ``seed`` field; falls back to a hash of the
    spec's JSON form so the same input always produces the same mesh.
    """
    seed = getattr(spec, "seed", None)
    if seed is not None:
        return int(seed)
    digest = hashlib.sha256(spec.model_dump_json().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _ensure_trimesh():
    try:
        import trimesh  # noqa: F401
    except ImportError as exc:  # pragma: no cover - trimesh is a hard dep
        raise WorkerUnavailable("trimesh is required for stub workers") from exc


def _probe_runnable(name: str) -> ProbeResult:
    try:
        import trimesh  # noqa: F401
    except ImportError:
        return ProbeResult(
            name=name,
            runnable=False,
            reason="trimesh missing",
            missing=["trimesh"],
            metadata={"is_stub": True},
        )
    return ProbeResult(
        name=name,
        runnable=True,
        device="cpu",
        metadata={"is_stub": True},
    )


def _emit_box(spec: Any, out_path: Path) -> None:
    import trimesh

    seed = _seed_from(spec)
    # Vary the box dims slightly by seed so the same input is reproducible
    # but different inputs yield distinguishable outputs.
    a = 0.5 + (seed % 7) * 0.05
    b = 0.5 + ((seed >> 4) % 7) * 0.05
    c = 0.5 + ((seed >> 8) % 7) * 0.05
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mesh = trimesh.creation.box(extents=(a, b, c))
    mesh.export(str(out_path))


class StubImageTo3DWorker:
    name = "stub_image_to_3d"
    capabilities = [Capability.image_to_3d]
    priority = 0
    license = "stub"
    description = (
        "Always-available stub image-to-3D worker. Produces a deterministic "
        "placeholder cube so the pipeline can be tested without GPU models."
    )
    homepage = None
    paper_url = None
    weights_url = None
    is_stub = True
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def probe(self) -> ProbeResult:
        return _probe_runnable(self.name)

    def run(
        self,
        spec: ImageTo3DRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        _ensure_trimesh()
        reporter and reporter("stub:image_to_3d.start", 5.0, "starting")
        cancel and cancel.throw_if_cancelled()
        out_path = Path(spec.output_dir) / f"stub_image_to_3d.{spec.output_format}"
        _emit_box(spec, out_path)
        reporter and reporter("stub:image_to_3d.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "is_stub": True,
                "seed": _seed_from(spec),
                "input_image_path": str(spec.input_image_path),
                "prompt": spec.prompt,
            },
        }


class StubTextTo3DWorker:
    """Legacy test stub retained for explicit tests, not registered by default."""

    name = "stub_text_to_3d"
    capabilities = [Capability.text_to_3d]
    priority = 0
    license = "stub"
    description = (
        "Always-available stub text-to-3D worker. Produces a deterministic "
        "placeholder cube keyed on the prompt."
    )
    homepage = None
    paper_url = None
    weights_url = None
    is_stub = True
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def probe(self) -> ProbeResult:
        return _probe_runnable(self.name)

    def run(
        self,
        spec: TextTo3DRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        _ensure_trimesh()
        reporter and reporter("stub:text_to_3d.start", 5.0, "starting")
        cancel and cancel.throw_if_cancelled()
        out_path = Path(spec.output_dir) / f"stub_text_to_3d.{spec.output_format}"
        _emit_box(spec, out_path)
        reporter and reporter("stub:text_to_3d.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "is_stub": True,
                "seed": _seed_from(spec),
                "prompt": spec.prompt,
            },
        }


class StubTextureMeshWorker:
    name = "stub_texture_mesh"
    capabilities = [Capability.texture_mesh]
    priority = 0
    license = "stub"
    description = (
        "Always-available stub texture worker. Re-exports the input mesh and "
        "emits a 32x32 solid-colour PNG as a placeholder texture."
    )
    homepage = None
    paper_url = None
    weights_url = None
    is_stub = True
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def probe(self) -> ProbeResult:
        result = _probe_runnable(self.name)
        if not result.runnable:
            return result
        try:
            import PIL  # noqa: F401
        except ImportError:
            return ProbeResult(
                name=self.name,
                runnable=False,
                reason="Pillow missing",
                missing=["Pillow"],
                metadata={"is_stub": True},
            )
        return result

    def run(
        self,
        spec: TextureMeshRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        _ensure_trimesh()
        from PIL import Image

        import trimesh

        reporter and reporter("stub:texture_mesh.start", 5.0, "starting")
        cancel and cancel.throw_if_cancelled()

        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        mesh = trimesh.load(str(spec.input_mesh_path), force="mesh", process=False)
        if isinstance(mesh, trimesh.Scene):
            meshes = [g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                raise WorkerUnavailable("Input mesh has no geometry")
            mesh = trimesh.util.concatenate(meshes)
        out_mesh = out_dir / f"stub_textured.{spec.output_format}"
        mesh.export(str(out_mesh))

        seed = _seed_from(spec)
        color = (seed & 0xFF, (seed >> 8) & 0xFF, (seed >> 16) & 0xFF)
        size = max(32, min(spec.texture_size, 256))
        texture_path = out_dir / "stub_basecolor.png"
        Image.new("RGB", (size, size), color=color).save(texture_path)

        reporter and reporter("stub:texture_mesh.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_mesh),
            "texture_map": str(texture_path),
            "metadata": {
                "is_stub": True,
                "seed": seed,
                "prompt": spec.prompt,
            },
        }


class StubRefineMeshWorker:
    name = "stub_refine_mesh"
    capabilities = [Capability.refine_mesh]
    priority = 0
    license = "stub"
    description = (
        "Always-available stub mesh-refinement worker. Re-exports the input "
        "mesh as the output so the dispatch pipeline (manifest emission, "
        "validation, engine handoff) can be tested without a real "
        "retopology model."
    )
    homepage = None
    paper_url = None
    weights_url = None
    is_stub = True
    resources = CPU_ONLY_RESOURCES
    required_models: list[str] = []

    def probe(self) -> ProbeResult:
        return _probe_runnable(self.name)

    def run(
        self,
        spec: RefineMeshRequest,
        reporter: Any,
        cancel: Any,
    ) -> dict[str, Any]:
        _ensure_trimesh()
        import trimesh

        reporter and reporter("stub:refine_mesh.start", 5.0, "starting")
        cancel and cancel.throw_if_cancelled()
        out_dir = Path(spec.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        mesh = trimesh.load(str(spec.input_mesh_path), force="mesh", process=False)
        if isinstance(mesh, trimesh.Scene):
            meshes = [g for g in mesh.geometry.values() if isinstance(g, trimesh.Trimesh)]
            if not meshes:
                raise WorkerUnavailable("Input mesh has no geometry")
            mesh = trimesh.util.concatenate(meshes)
        out_path = out_dir / f"stub_refined.{spec.output_format}"
        mesh.export(str(out_path))
        reporter and reporter("stub:refine_mesh.done", 100.0, "done")
        return {
            "worker": self.name,
            "output_mesh": str(out_path),
            "metadata": {
                "is_stub": True,
                "preserve_uvs": spec.preserve_uvs,
                "target_face_count": spec.target_face_count,
            },
        }


__all__ = [
    "StubImageTo3DWorker",
    "StubRefineMeshWorker",
    "StubTextTo3DWorker",
    "StubTextureMeshWorker",
]
