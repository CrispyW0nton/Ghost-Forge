from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore

from ghostforge_core.authoring import EvaluationResult, EvaluationStep
from ghostforge_core.types import MeshInfo
from ghostforge_qt.models.operation_graph_model import (
    OperationGraphHistoryModel,
    OperationGraphModel,
    OperationPaletteModel,
)
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
    updated = model.update_node_params(0, {"pivot": "origin"})
    assert updated is not None
    assert updated.params == {"pivot": "origin"}
    assert model.data(model.index(0, 3)) == "pending"
    assert model.remove_row(0).id == node.id
    assert model.rowCount() == 0


def test_operation_graph_model_surfaces_node_artifacts_and_manifests(qapp):
    operation = OperationRow(
        kind="generate_text_to_3d",
        label="Generate Text To 3D",
        category="ai.source",
        summary="",
        operation_type="source",
        capability="text_to_3d",
        status="stub",
        workers=("stub_text_to_3d",),
        params_schema={"prompt": {"type": "string"}},
    )
    model = OperationGraphModel()

    node = model.append_operation(operation, {"prompt": "crate"})
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
        metadata={
            "side_effects": [
                {
                    "kind": "worker_operation",
                    "operation": node.kind,
                    "node_id": node.id,
                    "asset_dir": "C:/tmp/asset",
                    "output_mesh": "C:/tmp/asset/mesh.glb",
                    "texture_map": "C:/tmp/asset/base_color.png",
                    "manifest_path": "C:/tmp/asset/asset_manifest.json",
                }
            ]
        },
    )

    model.set_evaluation_result(result)

    assert model.data(model.index(0, 4)) == "mesh, texture"
    assert model.data(model.index(0, 5)) == "manifest"
    assert model.data(model.index(0, 4), model.ArtifactRole) == (
        "C:/tmp/asset/mesh.glb",
        "C:/tmp/asset/base_color.png",
        "C:/tmp/asset",
    )
    assert model.data(model.index(0, 5), model.ManifestRole) == ("C:/tmp/asset/asset_manifest.json",)
    tooltip = model.data(model.index(0, 4), QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "Artifacts:" in tooltip
    assert "asset_manifest.json" in tooltip


def test_operation_graph_model_surfaces_audit_badges_from_manifest_payload(qapp):
    operation = OperationRow(
        kind="generate_text_to_3d",
        label="Generate Text To 3D",
        category="ai.source",
        summary="",
        operation_type="source",
        capability="text_to_3d",
        status="stub",
        workers=("stub_text_to_3d",),
        params_schema={"prompt": {"type": "string"}},
    )
    model = OperationGraphModel()
    node = model.append_operation(operation, {"prompt": "crate"})
    result = EvaluationResult(
        graph_id=model.graph().graph_id,
        steps=(EvaluationStep(node_id=node.id, kind=node.kind, status="succeeded"),),
        metadata={
            "side_effects": [
                {
                    "kind": "worker_operation",
                    "node_id": node.id,
                    "output_mesh": "C:/tmp/mesh.glb",
                    "manifest_path": "C:/tmp/asset_manifest.json",
                }
            ]
        },
    )
    payload = result.model_dump(mode="json")
    payload["manifest"] = {
        "validation": {"status": "warnings"},
        "custom": {"audit_history": [{"status": "passed"}, {"status": "failed"}]},
        "artifacts": [{"role": "worker.output_mesh"}],
    }

    model.set_evaluation_result(result, payload=payload)

    assert model.data(model.index(0, 5)) == "manifest/failed"
    tooltip = model.data(model.index(0, 5), QtCore.Qt.ItemDataRole.ToolTipRole)
    assert "Audit: failed" in tooltip


def test_operation_graph_history_model_records_result_payloads(qapp):
    model = OperationGraphHistoryModel()
    result = EvaluationResult(
        graph_id="graph_1",
        status="succeeded",
        output_path="C:/tmp/out.glb",
        duration_ms=12.5,
        steps=(EvaluationStep(node_id="n1", kind="generate_text_to_3d", status="succeeded"),),
        metadata={"side_effects": [{"node_id": "n1", "output_mesh": "C:/tmp/out.glb"}]},
    )

    row = model.append_result(
        result,
        payload={
            **result.model_dump(mode="json"),
            "manifest": {
                "validation": {"status": "warnings"},
                "artifacts": [{"role": "mesh.primary"}, {"role": "texture.base_color"}],
            },
        },
    )

    assert row.status == "succeeded"
    assert row.artifact_count == 2
    assert row.audit_badge == "warnings"
    assert model.rowCount() == 1
    assert model.data(model.index(0, 0)) == "graph_1"
    assert model.data(model.index(0, 4)) == "warnings"


def test_operation_graph_history_model_appends_planned_payload(qapp):
    model = OperationGraphHistoryModel()

    row = model.append_payload(
        {
            "graph_id": "retarget-unreal",
            "status": "planned",
            "output_path": "C:/tmp/retarget.glb",
            "duration_ms": 0.0,
            "artifact_count": 0,
            "audit_badge": "warnings",
            "message": "planned retarget graph",
            "details": {
                "retarget_target": "unreal",
                "retarget_report": {"status": "warnings", "issues": []},
            },
        }
    )

    assert row.status == "planned"
    assert row.details["retarget_target"] == "unreal"
    assert model.rowCount() == 1
    assert model.data(model.index(0, 1)) == "planned"
    assert model.payloads()[0]["graph_id"] == "retarget-unreal"
    assert model.payloads()[0]["details"]["retarget_report"]["status"] == "warnings"
