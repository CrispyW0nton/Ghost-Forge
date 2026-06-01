from __future__ import annotations

from PySide6 import QtCore

from ghostforge_core import CoreConfig
from ghostforge_core.authoring import EditGraph, EvaluationResult, EvaluationStep, OperationNode
from ghostforge_core.types import Error, JobHandle, JobProgress, JobStatus, utc_now
from ghostforge_qt.panels.operation_graph import OperationGraphPanel
from ghostforge_qt.panels.operation_parameters import OperationParameterForm
from ghostforge_qt.services.core_bridge import CoreBridge, OperationRow


def _select_palette_kind(panel: OperationGraphPanel, kind: str) -> None:
    for row in range(panel.palette_model.rowCount()):
        operation = panel.palette_model.row_at(row)
        if operation is not None and operation.kind == kind:
            panel.palette_view.selectRow(row)
            QtCore.QCoreApplication.processEvents()
            return
    raise AssertionError(f"operation {kind!r} not found")


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
            "worker": {"type": "string", "default": None},
            "seed": {"type": "int", "default": None},
            "extras": {"type": "object", "default": {}},
        },
    )
    form = OperationParameterForm()

    form.set_operation(operation)
    form.set_value("prompt", "low-poly crate")
    form.set_value("worker", "stub_text_to_3d")
    form.set_value("seed", 42)
    form.set_value("extras", {"texture": True})

    assert form.values() == {
        "prompt": "low-poly crate",
        "worker": "stub_text_to_3d",
        "seed": 42,
        "extras": {"texture": True},
    }


def test_operation_graph_panel_adds_and_edits_descriptor_params(qapp, tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))
    panel = OperationGraphPanel(bridge)
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

        restored = OperationGraphPanel(bridge)
        try:
            restored.set_graph(graph, emit=False)
            restored.set_history_payloads(panel.history_payloads())

            assert "1/2 planned diagnostics resolved" in restored.retarget_diagnostics.text()
            assert "remaining=1, new=1" in restored.retarget_diagnostics.text()
        finally:
            restored.close()
    finally:
        panel.close()
