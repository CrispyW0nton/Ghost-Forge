from __future__ import annotations

import pytest

from ghostforge_core.operations import unwrap
from ghostforge_core.types import UnwrapRequest


def test_unwrap_via_core(tmp_path):
    pytest.importorskip("trimesh")
    pytest.importorskip("xatlas")

    import trimesh

    mesh_path = tmp_path / "box.obj"
    trimesh.creation.box().export(mesh_path)

    result = unwrap.run(
        UnwrapRequest(
            input_mesh_path=mesh_path,
            output_dir=tmp_path / "out",
            atlas_size=512,
            output_format="glb",
            force_unwrap=True,
        )
    )

    assert result.output_mesh.exists()
    assert result.uv_layout is not None
    assert result.uv_layout.exists()
    assert result.uv_stats["uv_coords"] > 0
