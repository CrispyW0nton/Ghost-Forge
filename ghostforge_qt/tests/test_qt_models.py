from __future__ import annotations

from pathlib import Path

from ghostforge_core.types import MeshInfo
from ghostforge_qt.models.scene_model import SceneTableModel, TransformState
from ghostforge_qt.models.worker_model import WorkerTableModel
from ghostforge_qt.services.core_bridge import WorkerRow


def test_scene_model_adds_mesh_records(qapp):
    model = SceneTableModel()
    info = MeshInfo(vertices=8, faces=12, edges=18, watertight=True, format=".glb")

    record = model.add_mesh(Path("cube.glb"), info)

    assert model.rowCount() == 1
    assert record.name == "cube"
    assert model.data(model.index(0, 0)) == "cube"
    assert model.data(model.index(0, 1)) == 8
    assert model.data(model.index(0, 3)) == "yes"


def test_scene_model_updates_transform(qapp):
    model = SceneTableModel()
    info = MeshInfo(vertices=8, faces=12, edges=18, watertight=True, format=".glb")
    record = model.add_mesh(Path("cube.glb"), info)

    updated = model.update_transform(
        record.object_id,
        TransformState(translate=(1.0, 2.0, 3.0)),
    )

    assert updated is not None
    assert updated.transform.translate == (1.0, 2.0, 3.0)
    assert model.data(model.index(0, 4)) == "1.00, 2.00, 3.00"


def test_worker_model_marks_stub_and_missing_states(qapp):
    model = WorkerTableModel(
        [
            WorkerRow(
                name="stub_image_to_3d",
                capabilities=("image_to_3d",),
                priority=0,
                runnable=True,
                reason="",
                is_stub=True,
                license="MIT",
                device="cpu",
                required_models=(),
            ),
            WorkerRow(
                name="trellis",
                capabilities=("image_to_3d",),
                priority=90,
                runnable=False,
                reason="torch not installed",
                is_stub=False,
                license="MIT",
                device="",
                required_models=("trellis-large",),
            ),
        ]
    )

    assert model.rowCount() == 2
    assert model.data(model.index(0, 2)) == "stub"
    assert model.data(model.index(1, 2)) == "missing"
    assert model.data(model.index(1, 5)) == "torch not installed"
