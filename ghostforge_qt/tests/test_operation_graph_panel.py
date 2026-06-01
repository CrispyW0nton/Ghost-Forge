from __future__ import annotations

import json

from PySide6 import QtCore, QtWidgets

from ghostforge_core import CoreConfig
from ghostforge_core.authoring import EditGraph, EvaluationResult, EvaluationStep, OperationNode
from ghostforge_core.types import Error, JobHandle, JobProgress, JobStatus, utc_now
from ghostforge_qt.panels.operation_graph import OperationGraphPanel
from ghostforge_qt.panels.operation_parameters import OperationParameterForm, PathParameterWidget
from ghostforge_qt.services.core_bridge import CoreBridge, OperationRow


def _select_palette_kind(panel: OperationGraphPanel, kind: str) -> None:
    for row in range(panel.palette_model.rowCount()):
        operation = panel.palette_model.row_at(row)
        if operation is not None and operation.kind == kind:
            panel.palette_view.selectRow(row)
            QtCore.QCoreApplication.processEvents()
            return
    raise AssertionError(f"operation {kind!r} not found")


def _set_resource_filter(panel: OperationGraphPanel, kind: str) -> None:
    index = panel.resource_filter.findData(kind)
    assert index >= 0
    panel.resource_filter.setCurrentIndex(index)
    QtCore.QCoreApplication.processEvents()


def _job(
    job_id: str,
    status: JobStatus,
    *,
    percent: float | None = None,
    stage: str = "graph",
    message: str = "",
    error: str | None = None,
    cancel_requested: bool = False,
) -> JobHandle:
    return JobHandle(
        id=job_id,
        kind="evaluate_edit_graph",
        status=status,
        progress=None if percent is None else JobProgress(percent=percent, stage=stage, message=message),
        error=None if error is None else Error(code="graph_error", message=error),
        created_at=utc_now(),
        updated_at=utc_now(),
        cancel_requested=cancel_requested,
    )


def test_operation_parameter_form_reads_descriptor_schema(qapp):
    operation = OperationRow(
        kind="generate_text_to_3d",
        label="Generate Text To 3D",
        category="ai.source",
        summary="",
        operation_type="source",
        capability="text_to_3d",
        status="stub",
        workers=("stub_text_to_3d",),
        params_schema={
            "prompt": {"type": "string", "required": True},
            "input_image_path": {"type": "path", "required": True},
            "output_dir": {"type": "string", "format": "directory", "default": None},
            "worker": {"type": "string", "default": None},
            "seed": {"type": "int", "default": None},
            "extras": {"type": "object", "default": {}},
        },
    )
    form = OperationParameterForm()

    form.set_operation(operation)
    form.set_value("prompt", "low-poly crate")
    form.set_value("input_image_path", "C:/concepts/crate.png")
    form.set_value("output_dir", "C:/assets/crate")
    form.set_value("worker", "stub_text_to_3d")
    form.set_value("seed", 42)
    form.set_value("extras", {"texture": True})

    path_widgets = form.findChildren(PathParameterWidget)
    assert len(path_widgets) == 2
    assert sorted(widget.mode for widget in path_widgets) == ["directory", "file"]
    assert form.values() == {
        "prompt": "low-poly crate",
        "input_image_path": "C:/concepts/crate.png",
        "output_dir": "C:/assets/crate",
        "worker": "stub_text_to_3d",
        "seed": 42,
        "extras": {"texture": True},
    }


def test_path_parameter_widget_browse_uses_file_dialog(qapp, tmp_path, monkeypatch):
    chosen = str(tmp_path / "reference.png")
    widget = PathParameterWidget(mode="file", file_filter="Images (*.png)")

    def fake_get_open_file_name(*args, **kwargs):
        return chosen, "Images (*.png)"

    monkeypatch.setattr(QtWidgets.QFileDialog, "getOpenFileName", fake_get_open_file_name)

    widget.browse_button.click()

    assert widget.value() == chosen


def test_operation_parameter_form_applies_descriptor_presets(qapp):
    operation = OperationRow(
        kind="worker_texture_mesh",
        label="Worker Texture Mesh",
        category="ai.process",
        summary="",
        operation_type="worker",
        capability="texture_mesh",
        status="stub",
        workers=("stub_texture_mesh",),
        params_schema={
            "texture_size": {"type": "int", "default": 1024, "min": 256, "max": 4096},
            "preserve_uvs": {"type": "bool", "default": True},
            "extras": {"type": "object", "default": {}},
        },
        parameter_presets=(
            {
                "label": "Realtime 1K",
                "values": {"texture_size": 1024, "preserve_uvs": True, "extras": {"target": "realtime"}},
                "default": True,
            },
            {
                "label": "Hero 4K",
                "values": {"texture_size": 4096, "preserve_uvs": True, "extras": {"target": "hero"}},
            },
        ),
    )
    form = OperationParameterForm()

    form.set_operation(operation)

    assert form.preset_labels == ("Realtime 1K", "Hero 4K")
    assert form.values() == {
        "texture_size": 1024,
        "preserve_uvs": True,
        "extras": {"target": "realtime"},
    }

    form.apply_preset("Hero 4K")

    assert form.values() == {
        "texture_size": 4096,
        "preserve_uvs": True,
        "extras": {"target": "hero"},
    }


def test_operation_graph_panel_adds_and_edits_descriptor_params(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    changed: list[EditGraph] = []
    panel.graphChanged.connect(changed.append)
    try:
        _select_palette_kind(panel, "recenter")
        panel.parameter_form.set_value("pivot", "bottom")

        panel.add_selected_operation()

        node = panel.graph().nodes[0]
        assert node.kind == "recenter"
        assert node.params == {"pivot": "bottom"}

        panel.graph_view.selectRow(0)
        QtCore.QCoreApplication.processEvents()
        panel.parameter_form.set_value("pivot", "origin")
        panel.apply_selected_node_params()

        assert panel.graph().nodes[0].params == {"pivot": "origin"}

        panel.toggle_node_button.click()
        assert not panel.graph().nodes[0].enabled
        assert panel.graph_model.data(panel.graph_model.index(0, 0)) == "no"
        assert panel.toggle_node_button.text() == "Enable Node"
        assert "disabled" in panel.status.text()

        panel.toggle_node_button.click()
        assert panel.graph().nodes[0].enabled
        assert panel.graph_model.data(panel.graph_model.index(0, 0)) == "yes"
        assert panel.toggle_node_button.text() == "Disable Node"
        assert "enabled" in panel.status.text()
        assert changed[-1].nodes[0].enabled
    finally:
        panel.close()


def test_operation_graph_panel_reports_required_param_errors(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    try:
        _select_palette_kind(panel, "generate_text_to_3d")

        panel.add_selected_operation()

        assert panel.graph_model.rowCount() == 0
        assert "prompt is required" in panel.status.text()
    finally:
        panel.close()


def test_operation_graph_panel_reorders_selected_nodes(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    changed: list[EditGraph] = []
    panel.graphChanged.connect(changed.append)
    try:
        _select_palette_kind(panel, "recenter")
        panel.parameter_form.set_value("pivot", "bottom")
        panel.add_selected_operation()
        first_id = panel.graph().nodes[0].id
        _select_palette_kind(panel, "recompute_normals")
        panel.add_selected_operation()
        second_id = panel.graph().nodes[1].id

        assert panel.graph_view.selectionModel().selectedRows()[0].row() == 1
        assert panel.move_up_button.isEnabled()
        assert not panel.move_down_button.isEnabled()
        assert panel.graph_view.dragDropMode() == QtWidgets.QAbstractItemView.DragDropMode.InternalMove
        assert panel.graph_view.defaultDropAction() == QtCore.Qt.DropAction.MoveAction

        panel.move_up_button.click()

        assert [node.id for node in panel.graph().nodes] == [second_id, first_id]
        assert panel.graph().nodes[1].params == {"pivot": "bottom"}
        assert panel.graph_view.selectionModel().selectedRows()[0].row() == 0
        assert not panel.move_up_button.isEnabled()
        assert panel.move_down_button.isEnabled()
        assert "Moved recompute_normals up." in panel.status.text()
        assert changed[-1].nodes[0].id == second_id

        panel.move_down_button.click()

        assert [node.id for node in panel.graph().nodes] == [first_id, second_id]
        assert panel.graph_view.selectionModel().selectedRows()[0].row() == 1
        assert panel.move_up_button.isEnabled()
        assert not panel.move_down_button.isEnabled()

        changed_count = len(changed)
        mime = panel.graph_model.mimeData([panel.graph_model.index(1, 0)])
        assert panel.graph_model.dropMimeData(
            mime,
            QtCore.Qt.DropAction.MoveAction,
            0,
            0,
            QtCore.QModelIndex(),
        )
        assert [node.id for node in panel.graph().nodes] == [second_id, first_id]
        assert len(changed) == changed_count + 1
    finally:
        panel.close()


def test_operation_graph_panel_tracks_job_progress_cancel_and_retry(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    cancelled: list[str] = []
    panel.cancelGraphJobRequested.connect(cancelled.append)
    try:
        panel.set_graph_job_submitted("job-progress-123456")

        assert not panel.evaluate_button.isEnabled()
        assert panel.cancel_job_button.isEnabled()
        assert not panel.retry_button.isEnabled()
        assert "job-progress" in panel.job_status.text()

        panel.set_graph_job_progress(
            _job(
                "job-progress-123456",
                JobStatus.running,
                percent=37.0,
                stage="graph.recenter",
                message="succeeded vertices=8 faces=12",
            )
        )

        assert panel.job_progress.value() == 37
        assert "graph.recenter" in panel.job_status.text()

        panel.cancel_job_button.click()

        assert cancelled == ["job-progress-123456"]
        assert not panel.cancel_job_button.isEnabled()
        assert "Cancel requested" in panel.job_status.text()

        panel.set_graph_job_finished(
            _job("job-progress-123456", JobStatus.failed, error="worker unavailable"),
            message="worker unavailable",
        )

        assert panel.evaluate_button.isEnabled()
        assert panel.retry_button.isEnabled()
        assert "failed" in panel.job_status.text()
    finally:
        panel.close()


def test_operation_graph_panel_focuses_failed_node_and_shows_badges(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    try:
        operations = {row.kind: row for row in bridge.list_operations()}
        first = panel.graph_model.append_operation(operations["generate_text_to_3d"], {"prompt": "crate"})
        second = panel.graph_model.append_operation(operations["worker_texture_mesh"], {"prompt": "painted crate"})
        result = EvaluationResult(
            graph_id=panel.graph().graph_id,
            status="failed",
            steps=(
                EvaluationStep(
                    node_id=first.id,
                    kind=first.kind,
                    status="succeeded",
                    message="vertices=8 faces=12",
                ),
                EvaluationStep(
                    node_id=second.id,
                    kind=second.kind,
                    status="failed",
                    error="texture worker unavailable",
                ),
            ),
            metadata={
                "side_effects": [
                    {
                        "kind": "worker_operation",
                        "operation": first.kind,
                        "node_id": first.id,
                        "asset_dir": "C:/tmp/graph_node",
                        "output_mesh": "C:/tmp/graph_node/mesh.glb",
                        "manifest_path": "C:/tmp/graph_node/asset_manifest.json",
                    }
                ]
            },
        )

        panel.set_evaluation_result(result)

        assert panel.graph_model.data(panel.graph_model.index(0, 4)) == "mesh"
        assert panel.graph_model.data(panel.graph_model.index(0, 5)) == "manifest"
        assert panel.graph_view.selectionModel().selectedRows()[0].row() == 1
        assert "failed at row 2" in panel.status.text()
        assert panel.history_model.rowCount() == 1
        assert panel.history_model.data(panel.history_model.index(0, 1)) == "failed"

        audit_requests: list[bool] = []
        panel.auditGraphResultRequested.connect(lambda: audit_requests.append(True))
        assert panel.audit_button.isEnabled()
        panel.audit_button.click()
        assert audit_requests == [True]

        panel.apply_audit_manifest(
            {
                "validation": {"status": "warnings"},
                "custom": {"audit_history": [{"status": "warnings"}]},
                "artifacts": [{"role": "mesh.primary"}],
            },
            message="audit warnings: 0 errors, 1 warnings",
        )

        assert panel.history_model.rowCount() == 2
        assert panel.history_model.data(panel.history_model.index(0, 4)) == "warnings"
        assert "audit warnings" in panel.audit_status.text()
    finally:
        panel.close()


def test_operation_graph_panel_round_trips_history_payloads(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    payload = {
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "output_path": str(tmp_path / "cube_out.glb"),
        "duration_ms": 9.5,
        "artifact_count": 2,
        "audit_badge": "passed",
        "message": "audit passed",
    }
    try:
        panel.set_history_payloads([payload])

        assert panel.history_model.rowCount() == 1
        assert panel.history_model.data(panel.history_model.index(0, 0)) == "obj_cube_graph"
        assert panel.history_model.data(panel.history_model.index(0, 4)) == "passed"
        assert panel.history_payloads()[0] == payload
    finally:
        panel.close()


def test_operation_graph_panel_compares_selected_history_payload(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    older = {
        "history_id": "obj_cube_graph_succeeded_1_old",
        "resource_uri": "ghostforge://scenes/demo/objects/cube/graph-history/old",
        "mcp_links": {"scene_object_graph_history": "ghostforge://scenes/demo/objects/cube/graph-history/old"},
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "output_path": str(tmp_path / "cube_first.glb"),
        "duration_ms": 9.5,
        "artifact_count": 1,
        "audit_badge": "passed",
        "message": "audit passed",
        "details": {
            "artifact_paths": [str(tmp_path / "cube_first.glb")],
            "audit_history": {
                "status": "passed",
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "audit_issue_list": [],
            },
        },
    }
    oldest = {
        "history_id": "obj_cube_graph_succeeded_2_oldest",
        "resource_uri": "ghostforge://scenes/demo/objects/cube/graph-history/oldest",
        "mcp_links": {"scene_object_graph_history": "ghostforge://scenes/demo/objects/cube/graph-history/oldest"},
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "output_path": str(tmp_path / "cube_blockout.glb"),
        "duration_ms": 7.0,
        "artifact_count": 1,
        "audit_badge": "passed",
        "message": "blockout passed",
        "details": {
            "artifact_paths": [str(tmp_path / "cube_blockout.glb")],
            "audit_history": {
                "status": "passed",
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "audit_issue_list": [],
            },
        },
    }
    newer = {
        "history_id": "obj_cube_graph_succeeded_0_new",
        "resource_uri": "ghostforge://scenes/demo/objects/cube/graph-history/new",
        "mcp_links": {"scene_object_graph_history": "ghostforge://scenes/demo/objects/cube/graph-history/new"},
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "output_path": str(tmp_path / "cube_latest.glb"),
        "duration_ms": 14.25,
        "artifact_count": 3,
        "audit_badge": "warnings",
        "message": "audit warnings",
        "details": {
            "artifact_paths": [str(tmp_path / "cube_latest.glb"), str(tmp_path / "cube_albedo.png")],
            "bridge_paths": [str(tmp_path / "ghostforge_bridge_unity.json")],
            "retarget_remaining": ["retarget.units:units_scale_required"],
            "audit_history": {
                "status": "warnings",
                "error_count": 0,
                "warning_count": 1,
                "info_count": 0,
                "audit_issue_list": [
                    {
                        "severity": "warning",
                        "rule": "texture.channels",
                        "code": "missing_metallic",
                        "target": "material.default",
                        "message": "Metallic texture is absent.",
                    }
                ],
            },
        },
    }
    try:
        panel.set_history_payloads([newer, older, oldest])

        assert panel.history_payloads()[0]["history_id"] == newer["history_id"]
        assert panel.history_payloads()[0]["mcp_links"] == newer["mcp_links"]
        comparison = panel.selected_history_comparison()
        assert comparison is not None
        assert comparison["left"]["history_id"] == older["history_id"]
        assert comparison["right"]["history_id"] == newer["history_id"]
        assert panel.history_comparison_pair() == {
            "left_history_id": older["history_id"],
            "right_history_id": newer["history_id"],
        }
        assert comparison["changed_fields"]["audit_badge"] == {"left": "passed", "right": "warnings"}
        assert comparison["audit_changes"]["issues_added"]

        text = panel.history_comparison.text()
        assert "Previous -> Selected" in text
        assert "Audit Badge: passed -> warnings" in text
        assert "Artifact Paths Added" in text
        assert "cube_albedo.png" in text
        assert "Bridge Paths Added" in text
        assert "Retarget Remaining Added" in text
        assert "Audit Issues Added" in text
        assert "missing_metallic" in text
        delta_rows = panel.history_delta_model.rows()
        assert ("Field", "Audit Badge", "changed") in {
            (row.area, row.item, row.change) for row in delta_rows
        }
        assert ("Audit", "Warning Count", "changed") in {
            (row.area, row.item, row.change) for row in delta_rows
        }
        assert ("Resource", "Bridge Paths", "added") in {
            (row.area, row.item, row.change) for row in delta_rows
        }
        assert ("Retarget", "Retarget Remaining", "added") in {
            (row.area, row.item, row.change) for row in delta_rows
        }
        assert any(row.area == "Audit" and row.item == "Issues" and "missing_metallic" in row.detail for row in delta_rows)
        assert panel.history_delta_model.data(panel.history_delta_model.index(0, 0)) == delta_rows[0].area
        assert panel.history_delta_view.selectionModel().selectedRows()[0].row() == 0
        assert panel.selected_history_comparison_resource_uri() == (
            "ghostforge://scenes/demo/objects/cube/graph-history/old/"
            f"compare/{newer['history_id']}"
        )
        assert panel.history_comparison_uri.text() == panel.selected_history_comparison_resource_uri()
        assert panel.copy_history_comparison_link_button.isEnabled()

        emitted_pairs: list[dict[str, str]] = []
        panel.historyComparisonPairChanged.connect(emitted_pairs.append)
        panel.history_compare_left.setCurrentIndex(panel.history_compare_left.findData(2))
        panel.history_compare_right.setCurrentIndex(panel.history_compare_right.findData(0))
        QtCore.QCoreApplication.processEvents()
        comparison = panel.selected_history_comparison()
        assert comparison is not None
        assert comparison["left"]["history_id"] == oldest["history_id"]
        assert comparison["right"]["history_id"] == newer["history_id"]
        assert panel.history_comparison_pair() == {
            "left_history_id": oldest["history_id"],
            "right_history_id": newer["history_id"],
        }
        assert emitted_pairs[-1] == panel.history_comparison_pair()
        assert "Comparison Pair" in panel.history_comparison.text()
        assert panel.history_delta_model.rowCount() > 0
        assert panel.selected_history_comparison_resource_uri() == (
            "ghostforge://scenes/demo/objects/cube/graph-history/oldest/"
            f"compare/{newer['history_id']}"
        )

        restored = OperationGraphPanel(bridge)
        try:
            restored.set_history_payloads([newer, older, oldest])
            restored.set_history_comparison_pair(panel.history_comparison_pair())
            assert restored.history_compare_left.currentData() == 2
            assert restored.history_compare_right.currentData() == 0
            restored_comparison = restored.selected_history_comparison()
            assert restored_comparison is not None
            assert restored_comparison["left"]["history_id"] == oldest["history_id"]
            assert restored_comparison["right"]["history_id"] == newer["history_id"]
        finally:
            restored.close()

        copied: list[str] = []
        panel.historyComparisonLinkCopied.connect(copied.append)
        panel.copy_history_comparison_link_button.click()
        assert copied == [panel.selected_history_comparison_resource_uri()]
        assert QtWidgets.QApplication.clipboard().text() == panel.selected_history_comparison_resource_uri()

        panel.history_view.selectRow(2)
        QtCore.QCoreApplication.processEvents()
        assert panel.history_comparison_pair() == {
            "left_history_id": oldest["history_id"],
            "right_history_id": newer["history_id"],
        }
        assert panel.selected_history_comparison() is not None

        panel.set_history_comparison_pair({})
        panel.history_view.selectRow(2)
        QtCore.QCoreApplication.processEvents()
        assert panel.selected_history_comparison() is None
        assert "Choose two different" in panel.history_comparison.text()
        assert panel.history_delta_model.rowCount() == 0
        assert not panel.copy_history_comparison_link_button.isEnabled()
    finally:
        panel.close()


def test_operation_graph_panel_inspects_manifest_readiness_and_bridge_signals(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    bridge_calls: list[str] = []
    retarget_calls: list[str] = []
    panel.createEngineBridgeRequested.connect(bridge_calls.append)
    panel.planRetargetGraphRequested.connect(retarget_calls.append)
    payload = {
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "output_path": str(tmp_path / "cube_out.glb"),
        "duration_ms": 9.5,
        "artifact_count": 2,
        "audit_badge": "passed",
        "message": "audit passed",
    }
    try:
        panel.set_history_payloads([payload])
        panel.set_result_manifest(
            {
                "validation": {"status": "warnings", "error_count": 0, "warning_count": 2},
                "engine_targets": [{"engine": "unity"}, {"engine": "unreal"}],
                "custom": {"engine_export_bridges": [{"target_engine": "unity"}]},
            },
            asset_dir=str(tmp_path / "asset"),
        )

        assert "Engine bridge ready with 2 warning" in panel.result_readiness.text()
        assert "Targets: unity, unreal" in panel.result_readiness.text()
        assert "Bridges: unity" in panel.result_readiness.text()
        assert panel.create_unity_bridge_button.isEnabled()
        assert panel.create_unreal_bridge_button.isEnabled()
        assert panel.plan_unity_retarget_button.isEnabled()
        assert panel.plan_unreal_retarget_button.isEnabled()

        panel.create_unity_bridge_button.click()
        panel.plan_unreal_retarget_button.click()

        assert bridge_calls == ["unity"]
        assert retarget_calls == ["unreal"]

        panel.set_result_manifest(
            {
                "validation": {"status": "failed", "error_count": 1, "warning_count": 0},
                "custom": {},
            },
            asset_dir=str(tmp_path / "asset"),
        )

        assert "Blocked by audit errors" in panel.result_readiness.text()
        assert not panel.create_unity_bridge_button.isEnabled()
        assert not panel.create_unreal_bridge_button.isEnabled()
        assert panel.plan_unity_retarget_button.isEnabled()
        assert panel.plan_unreal_retarget_button.isEnabled()
    finally:
        panel.close()


def test_operation_graph_panel_emits_result_path_actions(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    output_path = tmp_path / "cube_out.glb"
    artifact_path = tmp_path / "cube_albedo.png"
    bridge_path = tmp_path / "ghostforge_bridge_unity.json"
    asset_dir = tmp_path / "asset"
    manifest_path = asset_dir / "asset_manifest.json"
    output_path.write_text("mesh")
    artifact_path.write_text("texture")
    bridge_path.write_text(
        json.dumps(
            {
                "bridge_version": "1.0",
                "target_engine": "unity",
                "recommended_mcp_server": "Unity-MCP-Ghost",
                "recommended_tool": "import_asset",
                "asset_id": "asset-cube",
                "asset_path": str(output_path),
                "manifest_path": str(manifest_path),
                "target_path": "Assets/GhostForge/asset-cube.glb",
                "manifest": {
                    "validation": {"status": "passed"},
                    "artifacts": [
                        {"role": "mesh.primary", "path": str(output_path)},
                        {"role": "texture.base_color", "path": str(artifact_path)},
                    ],
                },
                "notes": "Offline bridge package only.",
            }
        )
    )
    asset_dir.mkdir()
    manifest_path.write_text("{}")
    graph = EditGraph(
        graph_id="graph_paths",
        nodes=(OperationNode(id="n1", kind="generate_text_to_3d"),),
    )
    result = EvaluationResult(
        graph_id=graph.graph_id,
        status="succeeded",
        output_path=str(output_path),
        duration_ms=4.0,
        steps=(EvaluationStep(node_id="n1", kind="generate_text_to_3d", status="succeeded"),),
        metadata={
            "side_effects": [
                {
                    "node_id": "n1",
                    "output_mesh": str(output_path),
                    "texture_map": str(artifact_path),
                    "asset_dir": str(asset_dir),
                    "manifest_path": str(manifest_path),
                }
            ]
        },
    )
    payload = result.model_dump(mode="json")
    payload["manifest"] = {
        "asset_id": "asset-cube",
        "validation": {
            "status": "passed",
            "error_count": 0,
            "warning_count": 0,
            "report": {
                "errors": [],
                "warnings": [{"code": "scale.warning", "message": "Scale is unusual", "location": "mesh"}],
                "info": [{"code": "mesh.info", "message": "Mesh inspected"}],
            },
        },
        "artifacts": [
            {"role": "texture.base_color", "path": str(artifact_path)},
            {"role": "engine.bridge.unity", "path": str(bridge_path)},
        ],
        "provenance": [
            {"kind": "import_mesh"},
            {"kind": "audit", "job_id": "audit_job_123456789"},
            {
                "kind": "export_bridge_unity",
                "started_at": "2026-06-01T10:00:00Z",
                "finished_at": "2026-06-01T10:00:01Z",
            },
        ],
        "custom": {
            "audit_history": [
                {
                    "preset": "unity",
                    "status": "passed",
                    "warning_count": 0,
                    "issues": [
                        {
                            "severity": "warning",
                            "rule": "texture.channels",
                            "code": "missing_metallic",
                            "message": "Metallic texture is absent.",
                            "target": "material.default",
                        }
                    ],
                }
            ],
            "engine_export_bridges": [
                {
                    "target_engine": "unity",
                    "package_path": str(bridge_path),
                    "recommended_mcp_server": "Unity-MCP-Ghost",
                    "recommended_tool": "import_asset",
                    "created_at": "2026-06-01T10:00:02Z",
                    "direct_engine_call": False,
                }
            ],
        },
    }
    opened: list[str] = []
    revealed: list[str] = []
    panel.openGraphPathRequested.connect(opened.append)
    panel.revealGraphPathRequested.connect(revealed.append)
    try:
        panel.set_graph(graph, emit=False)
        panel.set_evaluation_result(result, payload=payload)
        panel.set_result_manifest(payload["manifest"], asset_dir=str(asset_dir))
        panel.graph_view.selectRow(0)

        paths = panel.selected_result_paths()
        assert paths["output"] == str(output_path)
        assert paths["artifact"] == str(output_path)
        assert paths["manifest"] == str(manifest_path)
        assert paths["asset_dir"] == str(asset_dir)
        assert panel.open_output_button.isEnabled()
        assert panel.reveal_output_button.isEnabled()
        assert panel.open_resource_button.isEnabled()
        assert panel.reveal_resource_button.isEnabled()
        assert panel.open_artifact_button.isEnabled()
        assert panel.open_manifest_button.isEnabled()
        assert panel.reveal_asset_dir_button.isEnabled()
        assert panel.resource_model.rowCount() == 7
        assert panel.resource_model.data(panel.resource_model.index(2, 0)) == "artifact"
        assert panel.resource_model.data(panel.resource_model.index(2, 2)) == str(artifact_path)
        kinds = [panel.resource_model.data(panel.resource_model.index(row, 0)) for row in range(panel.resource_model.rowCount())]
        assert "bridge" in kinds
        assert "audit_history" in kinds
        bridge_row = kinds.index("bridge")
        audit_row = kinds.index("audit_history")

        _set_resource_filter(panel, "bridge")
        assert panel.resource_model.rowCount() == 1
        assert panel.resource_model.data(panel.resource_model.index(0, 0)) == "bridge"
        assert "Recommended Mcp Server: Unity-MCP-Ghost" in panel.resource_details.text()
        _set_resource_filter(panel, "audit_history")
        assert panel.resource_model.rowCount() == 1
        assert panel.resource_model.data(panel.resource_model.index(0, 0)) == "audit_history"
        assert "missing_metallic" in panel.resource_details.text()
        _set_resource_filter(panel, "artifact")
        assert panel.resource_model.rowCount() == 2
        assert {
            panel.resource_model.data(panel.resource_model.index(row, 2))
            for row in range(panel.resource_model.rowCount())
        } == {str(output_path), str(artifact_path)}
        _set_resource_filter(panel, "manifest")
        assert panel.resource_model.rowCount() == 1
        assert panel.resource_model.data(panel.resource_model.index(0, 2)) == str(manifest_path)
        _set_resource_filter(panel, "asset_dir")
        assert panel.resource_model.rowCount() == 1
        assert panel.resource_model.data(panel.resource_model.index(0, 2)) == str(asset_dir)
        assert panel.selected_result_paths()["output"] == str(output_path)
        _set_resource_filter(panel, "all")
        assert panel.resource_model.rowCount() == 7

        panel.open_output_button.click()
        panel.reveal_output_button.click()
        panel.open_artifact_button.click()
        panel.open_manifest_button.click()
        panel.reveal_asset_dir_button.click()
        panel.resource_view.selectRow(2)
        panel.open_resource_button.click()
        panel.reveal_resource_button.click()
        panel.resource_view.selectRow(bridge_row)
        assert "Target Engine: unity" in panel.resource_details.text()
        assert "Recommended Mcp Server: Unity-MCP-Ghost" in panel.resource_details.text()
        assert "Package Preview:" in panel.resource_details.text()
        assert "- recommended_tool=import_asset" in panel.resource_details.text()
        assert "- direct_engine_call=False" in panel.resource_details.text()
        assert "Bridge Package JSON:" in panel.resource_details.text()
        assert "- bridge_version=1.0" in panel.resource_details.text()
        assert "- asset_id=asset-cube" in panel.resource_details.text()
        assert "- manifest_validation=passed" in panel.resource_details.text()
        assert "- manifest_artifacts=2" in panel.resource_details.text()
        assert "- target_path=Assets/GhostForge/asset-cube.glb" in panel.resource_details.text()
        panel.resource_view.selectRow(audit_row)
        assert "Status: passed" in panel.resource_details.text()
        assert "Warning Count: 0" in panel.resource_details.text()
        assert "Audit Issue List:" in panel.resource_details.text()
        assert "- warning texture.channels:missing_metallic [material.default]: Metallic texture is absent." in panel.resource_details.text()
        manifest_row = kinds.index("manifest")
        panel.resource_view.selectRow(manifest_row)
        assert "Asset Id: asset-cube" in panel.resource_details.text()
        assert "Validation Issues: warnings:scale.warning | info:mesh.info" in panel.resource_details.text()
        assert "Validation Issue List:" in panel.resource_details.text()
        assert "- warning scale.warning [mesh]: Scale is unusual" in panel.resource_details.text()
        assert "- info mesh.info: Mesh inspected" in panel.resource_details.text()
        assert "Latest Provenance: import_mesh -> audit(audit_jo) -> export_bridge_unity" in panel.resource_details.text()
        assert "Provenance Step List:" in panel.resource_details.text()
        assert "- 1. import_mesh" in panel.resource_details.text()
        assert "- 2. audit job=audit_job_12" in panel.resource_details.text()

        assert opened == [str(output_path), str(output_path), str(manifest_path), str(artifact_path)]
        assert revealed == [str(output_path), str(asset_dir), str(artifact_path)]
        details = panel.history_payloads()[0]["details"]
        assert details["artifact_paths"] == [str(output_path), str(artifact_path)]
        assert details["asset_dirs"] == [str(asset_dir)]
        assert details["bridge_paths"] == [str(bridge_path)]
        assert details["manifest_paths"] == [str(manifest_path)]
        assert details["audit_history"]["status"] == "passed"

        restored = OperationGraphPanel(bridge)
        try:
            restored.set_history_payloads(panel.history_payloads())
            restored_paths = restored.selected_result_paths()
            assert restored_paths["artifact"] == str(output_path)
            assert restored_paths["asset_dir"] == str(asset_dir)
            assert restored_paths["manifest"] == str(manifest_path)
            assert restored.resource_model.rowCount() == 7
            restored_kinds = [
                restored.resource_model.data(restored.resource_model.index(row, 0))
                for row in range(restored.resource_model.rowCount())
            ]
            restored.resource_view.selectRow(restored_kinds.index("bridge"))
            assert "Recommended Mcp Server: Unity-MCP-Ghost" in restored.resource_details.text()
            assert "- recommended_tool=import_asset" in restored.resource_details.text()
            assert "Bridge Package JSON:" in restored.resource_details.text()
            assert "- target_engine=unity" in restored.resource_details.text()
            assert "- manifest_artifacts=2" in restored.resource_details.text()
            restored.resource_view.selectRow(restored_kinds.index("audit_history"))
            assert "Status: passed" in restored.resource_details.text()
            assert "missing_metallic" in restored.resource_details.text()
        finally:
            restored.close()
    finally:
        panel.close()


def test_operation_graph_panel_shows_retarget_diagnostics(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
    graph = EditGraph(
        graph_id="retarget-unreal",
        output_path=str(tmp_path / "retarget_result.glb"),
        nodes=(
            OperationNode(id="axis", kind="retarget_axis"),
            OperationNode(id="units", kind="retarget_units"),
        ),
    )
    report_payload = {
        "status": "warnings",
        "issues": [
            {
                "rule": "retarget.axis",
                "severity": "info",
                "code": "axis_mismatch_assumed",
                "message": "Axis swap needed",
                "suggestion": "Insert a retarget_axis op.",
            },
            {
                "rule": "retarget.units",
                "severity": "warning",
                "code": "units_scale_required",
                "message": "Scale needed",
                "suggestion": "Insert a retarget_units op.",
            },
            {
                "rule": "geometry.watertight",
                "severity": "warning",
                "code": "mesh_open",
                "message": "Not a retarget issue",
            },
        ],
    }
    try:
        panel.set_graph(graph, emit=False)

        panel.set_retarget_plan(
            target_engine="unreal",
            graph=graph,
            report_payload=report_payload,
        )

        assert panel.history_model.rowCount() == 1
        assert panel.history_model.data(panel.history_model.index(0, 1)) == "planned"
        assert panel.history_model.data(panel.history_model.index(0, 4)) == "warnings"
        assert panel.history_payloads()[0]["details"]["retarget_target"] == "unreal"
        assert "Unreal retarget plan: 2 nodes from 2 diagnostics" in panel.retarget_diagnostics.text()
        assert "warning=1" in panel.retarget_diagnostics.text()
        assert "axis_mismatch_assumed" in panel.retarget_diagnostics.text()
        assert "mesh_open" not in panel.retarget_diagnostics.text()
        assert panel.retarget_model.rowCount() == 2
        assert {
            panel.retarget_model.data(panel.retarget_model.index(row, 3))
            for row in range(panel.retarget_model.rowCount())
        } == {"axis_mismatch_assumed", "units_scale_required"}
        assert {
            panel.retarget_model.data(panel.retarget_model.index(row, 0))
            for row in range(panel.retarget_model.rowCount())
        } == {"planned"}

        panel.set_retarget_comparison(
            target_engine="unreal",
            graph=graph,
            report_payload={
                "status": "warnings",
                "issues": [
                    {
                        "rule": "retarget.units",
                        "severity": "warning",
                        "code": "units_scale_required",
                        "message": "Still needs scale",
                    },
                    {
                        "rule": "retarget.pivot",
                        "severity": "warning",
                        "code": "pivot_not_at_base",
                        "message": "New pivot issue",
                    },
                ],
            },
        )

        assert panel.history_model.data(panel.history_model.index(0, 1)) == "verified"
        verified = panel.history_payloads()[0]["details"]
        assert verified["retarget_resolved"] == ["retarget.axis:axis_mismatch_assumed"]
        assert verified["retarget_remaining"] == ["retarget.units:units_scale_required"]
        assert verified["retarget_new"] == ["retarget.pivot:pivot_not_at_base"]
        assert "1/2 planned diagnostics resolved" in panel.retarget_diagnostics.text()
        assert "remaining=1, new=1" in panel.retarget_diagnostics.text()
        assert "Remaining families: retarget.units" in panel.retarget_diagnostics.text()
        assert "New families: retarget.pivot" in panel.retarget_diagnostics.text()
        assert panel.retarget_model.rowCount() == 3
        assert panel.retarget_model.data(panel.retarget_model.index(0, 0)) == "remaining"
        assert panel.retarget_model.data(panel.retarget_model.index(0, 2)) == "retarget.units"
        assert panel.retarget_model.data(panel.retarget_model.index(0, 3)) == "units_scale_required"
        assert panel.retarget_model.data(panel.retarget_model.index(0, 5)) == "Still needs scale"
        assert panel.retarget_model.data(panel.retarget_model.index(1, 0)) == "new"
        assert panel.retarget_model.data(panel.retarget_model.index(1, 2)) == "retarget.pivot"
        assert panel.retarget_model.data(panel.retarget_model.index(2, 0)) == "resolved"
        assert panel.retarget_model.data(panel.retarget_model.index(2, 2)) == "retarget.axis"
        assert panel.retarget_view.selectionModel().selectedRows()[0].row() == 0

        restored = OperationGraphPanel(bridge)
        try:
            restored.set_graph(graph, emit=False)
            restored.set_history_payloads(panel.history_payloads())

            assert "1/2 planned diagnostics resolved" in restored.retarget_diagnostics.text()
            assert "remaining=1, new=1" in restored.retarget_diagnostics.text()
            assert restored.retarget_model.rowCount() == 3
            assert restored.retarget_model.data(restored.retarget_model.index(0, 0)) == "remaining"
            assert restored.retarget_model.data(restored.retarget_model.index(1, 0)) == "new"
        finally:
            restored.close()
    finally:
        panel.close()
