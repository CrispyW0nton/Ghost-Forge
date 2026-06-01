from __future__ import annotations

from pathlib import Path

from ghostforge_core.authoring import EvaluationResult, EvaluationStep
from ghostforge_core.types import MeshInfo
from ghostforge_qt.models.operation_graph_model import OperationGraphModel, OperationPaletteModel
from ghostforge_qt.models.scene_model import SceneTableModel, TransformState
from ghostforge_qt.models.worker_model import WorkerTableModel
from ghostforge_qt.services.core_bridge import OperationRow, WorkerRow


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


def test_operation_palette_model_exposes_worker_status(qapp):
    model = OperationPaletteModel(
        [
            OperationRow(
                kind="generate_text_to_3d",
                label="Generate Text To 3D",
                category="ai.source",
                summary="source",
                operation_type="source",
                capability="text_to_3d",
                status="stub",
                workers=("stub_text_to_3d",),
                params_schema={"prompt": {"type": "string"}},
            )
        ]
    )

    assert model.rowCount() == 1
    assert model.data(model.index(0, 0)) == "generate_text_to_3d"
    assert model.data(model.index(0, 1)) == "source"
    assert model.data(model.index(0, 2)) == "stub"
    assert model.row_at(0).workers == ("stub_text_to_3d",)


def test_operation_graph_model_tracks_nodes_and_results(qapp):
    operation = OperationRow(
        kind="recenter",
        label="Recenter",
        category="transform",
        summary="",
        operation_type="operation",
        capability=None,
        status="available",
        workers=(),
        params_schema={},
    )
    model = OperationGraphModel()

    node = model.append_operation(operation, {"pivot": "bounds_center"})
    result = EvaluationResult(
        graph_id=model.graph().graph_id,
        steps=(
            EvaluationStep(
                node_id=node.id,
                kind=node.kind,
                status="succeeded",
                message="vertices=8 faces=12",
            ),
        ),
    )
    model.set_evaluation_result(result)

    assert model.rowCount() == 1
    assert model.data(model.index(0, 1)) == "recenter"
    assert model.data(model.index(0, 3)) == "succeeded"
    assert model.remove_row(0).id == node.id
    assert model.rowCount() == 0
