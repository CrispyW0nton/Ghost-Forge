from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ghostforge_core.authoring import EditGraph, EvaluationResult
from ghostforge_core.types import JobHandle
from ghostforge_qt.models.operation_graph_model import (
    GraphResultResource,
    GraphResultResourceModel,
    OperationGraphHistoryModel,
    OperationGraphModel,
    OperationPaletteModel,
)
from ghostforge_qt.models.scene_model import SceneObjectRecord
from ghostforge_qt.services.core_bridge import CoreBridge, OperationRow

from .operation_parameters import OperationParameterForm


class OperationGraphPanel(QtWidgets.QWidget):
    graphChanged = QtCore.Signal(object)
    evaluateRequested = QtCore.Signal()
    cancelGraphJobRequested = QtCore.Signal(str)
    auditGraphResultRequested = QtCore.Signal()
    createEngineBridgeRequested = QtCore.Signal(str)
    planRetargetGraphRequested = QtCore.Signal(str)
    openGraphPathRequested = QtCore.Signal(str)
    revealGraphPathRequested = QtCore.Signal(str)

    def __init__(self, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.palette_model = OperationPaletteModel(parent=self)
        self.graph_model = OperationGraphModel(parent=self)
        self.history_model = OperationGraphHistoryModel(parent=self)
        self.resource_model = GraphResultResourceModel(parent=self)
        self.active_object = QtWidgets.QLabel("-")
        self.active_object.setWordWrap(True)
        self.parameter_form = OperationParameterForm(self)
        self.status = QtWidgets.QLabel("Ready")
        self.status.setWordWrap(True)
        self.job_status = QtWidgets.QLabel("No graph job running.")
        self.job_status.setWordWrap(True)
        self.job_progress = QtWidgets.QProgressBar()
        self.job_progress.setRange(0, 100)
        self.job_progress.setValue(0)
        self.cancel_job_button = QtWidgets.QPushButton("Cancel Job")
        self.retry_button = QtWidgets.QPushButton("Retry")
        self.audit_button = QtWidgets.QPushButton("Audit Result")
        self.audit_status = QtWidgets.QLabel("Audit not run for this graph result.")
        self.audit_status.setWordWrap(True)
        self.cancel_job_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.audit_button.setEnabled(False)
        self._active_job_id: str | None = None
        self._active_audit_job_id: str | None = None
        self._last_result: EvaluationResult | None = None
        self._last_payload: dict[str, object] | None = None
        self._manifest_payload: dict[str, object] | None = None
        self._retarget_report_payload: dict[str, object] | None = None
        self._retarget_after_report_payload: dict[str, object] | None = None
        self._retarget_target: str = ""
        self._asset_dir: str = ""
        self._operations_by_kind: dict[str, OperationRow] = {}
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        context = QtWidgets.QGroupBox("Context")
        context_form = QtWidgets.QFormLayout(context)
        context_form.addRow("Active", self.active_object)
        root.addWidget(context)

        self.palette_view = QtWidgets.QTableView()
        self.palette_view.setModel(self.palette_model)
        self.palette_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.palette_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.palette_view.horizontalHeader().setStretchLastSection(True)
        self.palette_view.verticalHeader().hide()
        root.addWidget(QtWidgets.QLabel("Operations"))
        root.addWidget(self.palette_view, 2)

        button_row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh")
        self.add_button = QtWidgets.QPushButton("Add Node")
        self.remove_button = QtWidgets.QPushButton("Remove Node")
        self.apply_params_button = QtWidgets.QPushButton("Apply Params")
        self.evaluate_button = QtWidgets.QPushButton("Evaluate")
        self.refresh_button.clicked.connect(self.refresh)
        self.add_button.clicked.connect(self.add_selected_operation)
        self.remove_button.clicked.connect(self.remove_selected_node)
        self.apply_params_button.clicked.connect(self.apply_selected_node_params)
        self.evaluate_button.clicked.connect(self.evaluateRequested.emit)
        for button in (
            self.refresh_button,
            self.add_button,
            self.remove_button,
            self.apply_params_button,
            self.evaluate_button,
        ):
            button_row.addWidget(button)
        root.addLayout(button_row)

        self.graph_view = QtWidgets.QTableView()
        self.graph_view.setModel(self.graph_model)
        self.graph_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.graph_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.graph_view.horizontalHeader().setStretchLastSection(True)
        self.graph_view.verticalHeader().hide()
        root.addWidget(QtWidgets.QLabel("Graph"))
        root.addWidget(self.graph_view, 2)
        self.history_view = QtWidgets.QTableView()
        self.history_view.setModel(self.history_model)
        self.history_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.history_view.horizontalHeader().setStretchLastSection(True)
        self.history_view.verticalHeader().hide()
        root.addWidget(QtWidgets.QLabel("Result History"))
        root.addWidget(self.history_view, 1)

        inspector = QtWidgets.QGroupBox("Result Inspector")
        inspector_layout = QtWidgets.QFormLayout(inspector)
        self.result_summary = QtWidgets.QLabel("No graph result selected.")
        self.result_output = QtWidgets.QLabel("-")
        self.result_artifacts = QtWidgets.QLabel("-")
        self.result_manifests = QtWidgets.QLabel("-")
        self.result_readiness = QtWidgets.QLabel("No manifest loaded.")
        self.retarget_diagnostics = QtWidgets.QLabel("No retarget plan generated.")
        for label in (
            self.result_summary,
            self.result_output,
            self.result_artifacts,
            self.result_manifests,
            self.result_readiness,
            self.retarget_diagnostics,
        ):
            label.setWordWrap(True)
        inspector_layout.addRow("Result", self.result_summary)
        inspector_layout.addRow("Output", self.result_output)
        inspector_layout.addRow("Artifacts", self.result_artifacts)
        inspector_layout.addRow("Manifests", self.result_manifests)
        inspector_layout.addRow("Readiness", self.result_readiness)
        inspector_layout.addRow("Retarget", self.retarget_diagnostics)
        self.resource_view = QtWidgets.QTableView()
        self.resource_view.setModel(self.resource_model)
        self.resource_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.resource_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.resource_view.horizontalHeader().setStretchLastSection(True)
        self.resource_view.verticalHeader().hide()
        self.resource_view.setMinimumHeight(96)
        inspector_layout.addRow("Resources", self.resource_view)
        self.resource_details = QtWidgets.QLabel("No resource selected.")
        self.resource_details.setWordWrap(True)
        self.resource_details.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        inspector_layout.addRow("Details", self.resource_details)
        path_buttons = QtWidgets.QHBoxLayout()
        self.open_output_button = QtWidgets.QPushButton("Open Output")
        self.reveal_output_button = QtWidgets.QPushButton("Reveal Output")
        self.open_resource_button = QtWidgets.QPushButton("Open Selected")
        self.reveal_resource_button = QtWidgets.QPushButton("Reveal Selected")
        self.open_artifact_button = QtWidgets.QPushButton("Open Artifact")
        self.open_manifest_button = QtWidgets.QPushButton("Open Manifest/Audit")
        self.reveal_asset_dir_button = QtWidgets.QPushButton("Reveal Asset Dir")
        for button in (
            self.open_output_button,
            self.reveal_output_button,
            self.open_resource_button,
            self.reveal_resource_button,
            self.open_artifact_button,
            self.open_manifest_button,
            self.reveal_asset_dir_button,
        ):
            button.setEnabled(False)
            path_buttons.addWidget(button)
        self.open_output_button.clicked.connect(lambda _checked=False: self._emit_open_result_path("output"))
        self.reveal_output_button.clicked.connect(lambda _checked=False: self._emit_reveal_result_path("output"))
        self.open_resource_button.clicked.connect(lambda _checked=False: self._emit_open_result_path("selected"))
        self.reveal_resource_button.clicked.connect(lambda _checked=False: self._emit_reveal_result_path("selected"))
        self.open_artifact_button.clicked.connect(lambda _checked=False: self._emit_open_result_path("artifact"))
        self.open_manifest_button.clicked.connect(lambda _checked=False: self._emit_open_result_path("manifest"))
        self.reveal_asset_dir_button.clicked.connect(lambda _checked=False: self._emit_reveal_result_path("asset_dir"))
        inspector_layout.addRow("Files", path_buttons)
        bridge_buttons = QtWidgets.QHBoxLayout()
        self.create_unity_bridge_button = QtWidgets.QPushButton("Unity Bridge")
        self.create_unreal_bridge_button = QtWidgets.QPushButton("Unreal Bridge")
        self.create_unity_bridge_button.setEnabled(False)
        self.create_unreal_bridge_button.setEnabled(False)
        self.create_unity_bridge_button.clicked.connect(lambda: self.createEngineBridgeRequested.emit("unity"))
        self.create_unreal_bridge_button.clicked.connect(lambda: self.createEngineBridgeRequested.emit("unreal"))
        bridge_buttons.addWidget(self.create_unity_bridge_button)
        bridge_buttons.addWidget(self.create_unreal_bridge_button)
        inspector_layout.addRow("Export", bridge_buttons)
        retarget_buttons = QtWidgets.QHBoxLayout()
        self.plan_unity_retarget_button = QtWidgets.QPushButton("Plan Unity Retarget")
        self.plan_unreal_retarget_button = QtWidgets.QPushButton("Plan Unreal Retarget")
        self.plan_unity_retarget_button.setEnabled(False)
        self.plan_unreal_retarget_button.setEnabled(False)
        self.plan_unity_retarget_button.clicked.connect(lambda: self.planRetargetGraphRequested.emit("unity"))
        self.plan_unreal_retarget_button.clicked.connect(lambda: self.planRetargetGraphRequested.emit("unreal"))
        retarget_buttons.addWidget(self.plan_unity_retarget_button)
        retarget_buttons.addWidget(self.plan_unreal_retarget_button)
        inspector_layout.addRow("Retarget", retarget_buttons)
        root.addWidget(inspector)

        root.addWidget(QtWidgets.QLabel("Parameters"))
        root.addWidget(self.parameter_form)
        job_box = QtWidgets.QGroupBox("Evaluation Job")
        job_layout = QtWidgets.QVBoxLayout(job_box)
        job_layout.addWidget(self.job_status)
        job_layout.addWidget(self.job_progress)
        job_buttons = QtWidgets.QHBoxLayout()
        self.cancel_job_button.clicked.connect(self._cancel_graph_job)
        self.retry_button.clicked.connect(self.evaluateRequested.emit)
        self.audit_button.clicked.connect(self.auditGraphResultRequested.emit)
        job_buttons.addWidget(self.cancel_job_button)
        job_buttons.addWidget(self.retry_button)
        job_buttons.addWidget(self.audit_button)
        job_layout.addLayout(job_buttons)
        job_layout.addWidget(self.audit_status)
        root.addWidget(job_box)
        root.addWidget(self.status)

        self.palette_view.selectionModel().selectionChanged.connect(lambda *_: self._palette_selection_changed())
        self.graph_view.selectionModel().selectionChanged.connect(lambda *_: self._graph_selection_changed())
        self.history_view.selectionModel().selectionChanged.connect(lambda *_: self._refresh_result_inspector())
        self.resource_view.selectionModel().selectionChanged.connect(lambda *_: self._refresh_resource_selection())

    @QtCore.Slot()
    def refresh(self) -> None:
        rows = self.bridge.list_operations()
        self.palette_model.set_rows(rows)
        self._operations_by_kind = {row.kind: row for row in rows}
        if rows:
            self.palette_view.selectRow(0)
            self.parameter_form.set_operation(rows[0])
        else:
            self.parameter_form.set_operation(None)
        self.status.setText(f"{len(rows)} operations available.")

    def selected_operation(self) -> OperationRow | None:
        selection = self.palette_view.selectionModel()
        if selection is None or not selection.hasSelection():
            return None
        row = selection.selectedRows()[0].row()
        return self.palette_model.row_at(row)

    @QtCore.Slot()
    def add_selected_operation(self) -> None:
        operation = self.selected_operation()
        if operation is None:
            self.status.setText("Select an operation.")
            return
        if self.parameter_form.operation_kind != operation.kind:
            self.parameter_form.set_operation(operation)
        try:
            params = self._params_for(operation)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        node = self.graph_model.append_operation(operation, params)
        self.graph_view.selectRow(self.graph_model.rowCount() - 1)
        self.status.setText(f"Added {node.kind}.")
        self.graphChanged.emit(self.graph_model.graph())

    @QtCore.Slot()
    def remove_selected_node(self) -> None:
        selection = self.graph_view.selectionModel()
        if selection is None or not selection.hasSelection():
            self.status.setText("Select a graph node.")
            return
        removed = self.graph_model.remove_row(selection.selectedRows()[0].row())
        if removed is not None:
            self.status.setText(f"Removed {removed.kind}.")
            self.graphChanged.emit(self.graph_model.graph())
            if self.graph_model.rowCount() == 0:
                self.parameter_form.set_operation(self.selected_operation())

    @QtCore.Slot()
    def apply_selected_node_params(self) -> None:
        row = self._selected_graph_row()
        if row is None:
            self.status.setText("Select a graph node.")
            return
        node = self.graph_model.node_at(row)
        operation = self._operation_for_node(node)
        if operation is None:
            self.status.setText(f"No descriptor for {node.kind}.")
            return
        try:
            params = self.parameter_form.values()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        updated = self.graph_model.update_node_params(row, params)
        if updated is None:
            self.status.setText("Selected graph node no longer exists.")
            return
        self.status.setText(f"Updated {updated.kind} parameters.")
        self.graphChanged.emit(self.graph_model.graph())

    def _params_for(self, operation: OperationRow) -> dict[str, object]:
        return self.parameter_form.values()

    def graph(self) -> EditGraph:
        return self.graph_model.graph()

    def set_graph(self, graph: EditGraph, *, emit: bool = True) -> None:
        if graph.graph_id != self.graph_model.graph().graph_id:
            self.history_model.clear()
        self.graph_model.set_graph(graph)
        self._sync_parameter_form_to_graph()
        self._refresh_result_inspector()
        if emit:
            self.graphChanged.emit(graph)

    def reset_graph(self, *, graph_id: str | None = None) -> None:
        graph = EditGraph(graph_id=graph_id or self.graph_model.graph().graph_id, name="Qt Operation Graph")
        self.set_graph(graph, emit=False)
        self.history_model.clear()
        self._clear_retarget_plan()
        self._refresh_result_inspector()

    def set_evaluation_result(self, result: EvaluationResult, payload: dict[str, object] | None = None) -> None:
        self._last_result = result
        self._last_payload = dict(payload or result.model_dump(mode="json"))
        self.graph_model.set_evaluation_result(result, payload=payload)
        self.history_model.append_result(result, payload=payload)
        self.status.setText(f"Graph {result.status}: {len(result.steps)} steps.")
        self.audit_button.setEnabled(True)
        if self.history_model.rowCount():
            self.history_view.selectRow(0)
        failed_row = self.graph_model.first_failed_row()
        if failed_row is not None:
            self.graph_view.selectRow(failed_row)
            self.status.setText(f"Graph failed at row {failed_row + 1}.")
        self._refresh_result_inspector()

    def apply_audit_manifest(self, manifest_payload: dict[str, object], *, message: str = "") -> None:
        if self._last_result is None:
            self.audit_status.setText(message or "Audit complete.")
            return
        payload = dict(self._last_payload or self._last_result.model_dump(mode="json"))
        payload["manifest"] = dict(manifest_payload)
        self._last_payload = payload
        self.graph_model.set_evaluation_result(self._last_result, payload=payload)
        self.history_model.append_result(self._last_result, payload=payload, message=message or "audit refreshed")
        if self.history_model.rowCount():
            self.history_view.selectRow(0)
        self.audit_status.setText(message or "Audit refreshed graph result.")
        self._refresh_result_inspector()

    def set_graph_job_submitted(self, job_id: str) -> None:
        self._active_job_id = job_id
        self.job_progress.setValue(0)
        self.job_status.setText(f"Submitted graph job {job_id[:12]}.")
        self._set_graph_editing_enabled(False)
        self.cancel_job_button.setEnabled(True)
        self.retry_button.setEnabled(False)
        self.audit_button.setEnabled(False)

    def set_graph_job_progress(self, job: JobHandle) -> None:
        if self._active_job_id is not None and job.id != self._active_job_id:
            return
        if job.progress is not None:
            self.job_progress.setValue(round(job.progress.percent))
            details = f"{job.progress.stage}: {job.progress.message}".strip(": ")
        else:
            details = job.status.value
        cancel_note = " (cancel requested)" if job.cancel_requested else ""
        self.job_status.setText(f"Graph job {job.id[:12]} {job.status.value}{cancel_note}: {details}")
        self.cancel_job_button.setEnabled(job.status.value in {"pending", "running"} and not job.cancel_requested)

    def set_graph_job_finished(self, job: JobHandle, *, message: str = "") -> None:
        self._active_job_id = None
        self.job_progress.setValue(100 if job.status.value == "succeeded" else self.job_progress.value())
        detail = message or (job.error.message if job.error is not None else job.status.value)
        self.job_status.setText(f"Graph job {job.id[:12]} {job.status.value}: {detail}")
        self._set_graph_editing_enabled(True)
        self.cancel_job_button.setEnabled(False)
        self.retry_button.setEnabled(job.status.value in {"failed", "cancelled"})
        self.audit_button.setEnabled(self._last_result is not None and job.status.value == "succeeded")

    def clear_graph_job_state(self) -> None:
        self._active_job_id = None
        self._active_audit_job_id = None
        self._last_result = None
        self._last_payload = None
        self.job_progress.setValue(0)
        self.job_status.setText("No graph job running.")
        self.audit_status.setText("Audit not run for this graph result.")
        self._set_graph_editing_enabled(True)
        self.cancel_job_button.setEnabled(False)
        self.retry_button.setEnabled(False)
        self.audit_button.setEnabled(False)
        self._refresh_result_inspector()

    def set_history_payloads(self, payloads: tuple[dict[str, object], ...] | list[dict[str, object]]) -> None:
        self.history_model.set_payloads(payloads)
        self._restore_retarget_plan_from_history()
        if self.history_model.rowCount():
            self.history_view.selectRow(0)
        self._refresh_result_inspector()

    def history_payloads(self) -> tuple[dict[str, object], ...]:
        return self.history_model.payloads()

    def set_result_manifest(
        self,
        manifest_payload: dict[str, object] | None,
        *,
        asset_dir: str | None = None,
        message: str = "",
    ) -> None:
        self._manifest_payload = dict(manifest_payload) if isinstance(manifest_payload, dict) else None
        self._asset_dir = str(asset_dir or "")
        if message:
            self.audit_status.setText(message)
        self._refresh_result_inspector()

    def set_retarget_plan(
        self,
        *,
        target_engine: str,
        graph: EditGraph,
        report_payload: dict[str, object],
        message: str = "",
    ) -> None:
        self._retarget_target = target_engine
        self._retarget_report_payload = dict(report_payload)
        self._retarget_after_report_payload = None
        self.history_model.append_payload(
            {
                "graph_id": graph.graph_id,
                "status": "planned",
                "output_path": graph.output_path or "",
                "duration_ms": 0.0,
                "artifact_count": 0,
                "audit_badge": str(report_payload.get("status") or ""),
                "message": message or _retarget_summary(target_engine, graph, report_payload),
                "details": {
                    "retarget_target": target_engine,
                    "retarget_report": dict(report_payload),
                    "retarget_node_kinds": [node.kind for node in graph.nodes],
                },
            }
        )
        if self.history_model.rowCount():
            self.history_view.selectRow(0)
        self._refresh_result_inspector()

    def set_retarget_comparison(
        self,
        *,
        target_engine: str,
        graph: EditGraph,
        report_payload: dict[str, object],
        message: str = "",
    ) -> None:
        planned_report = self._retarget_report_payload or _latest_planned_retarget_report(
            self.history_model.payloads(),
            target_engine=target_engine,
        )
        self._retarget_target = target_engine
        self._retarget_report_payload = dict(planned_report or {})
        self._retarget_after_report_payload = dict(report_payload)
        comparison = _retarget_comparison(self._retarget_report_payload, self._retarget_after_report_payload)
        self.history_model.append_payload(
            {
                "graph_id": graph.graph_id,
                "status": "verified",
                "output_path": graph.output_path or "",
                "duration_ms": 0.0,
                "artifact_count": 0,
                "audit_badge": str(report_payload.get("status") or ""),
                "message": message or _retarget_comparison_summary(target_engine, graph, comparison),
                "details": {
                    "retarget_target": target_engine,
                    "retarget_report": self._retarget_report_payload,
                    "retarget_after_report": self._retarget_after_report_payload,
                    "retarget_resolved": comparison["resolved"],
                    "retarget_remaining": comparison["remaining"],
                    "retarget_new": comparison["new"],
                    "retarget_node_kinds": [node.kind for node in graph.nodes],
                },
            }
        )
        if self.history_model.rowCount():
            self.history_view.selectRow(0)
        self._refresh_result_inspector()

    def set_graph_audit_submitted(self, job_id: str) -> None:
        self._active_audit_job_id = job_id
        self.audit_status.setText(f"Submitted audit job {job_id[:12]}.")
        self.audit_button.setEnabled(False)

    def set_graph_audit_progress(self, job: JobHandle) -> None:
        if self._active_audit_job_id is not None and job.id != self._active_audit_job_id:
            return
        if job.progress is not None:
            details = f"{job.progress.stage}: {job.progress.message}".strip(": ")
        else:
            details = job.status.value
        self.audit_status.setText(f"Audit job {job.id[:12]} {job.status.value}: {details}")

    def set_graph_audit_finished(self, job: JobHandle, *, message: str = "") -> None:
        self._active_audit_job_id = None
        detail = message or (job.error.message if job.error is not None else job.status.value)
        self.audit_status.setText(f"Audit job {job.id[:12]} {job.status.value}: {detail}")
        self.audit_button.setEnabled(self._last_result is not None)

    def set_active_object(self, record: SceneObjectRecord | None) -> None:
        if record is None:
            self.active_object.setText("-")
            return
        self.active_object.setText(f"{record.name} ({record.object_id})")

    @QtCore.Slot()
    def _palette_selection_changed(self) -> None:
        graph_selection = self.graph_view.selectionModel()
        if graph_selection is not None and graph_selection.hasSelection():
            graph_selection.clearSelection()
        operation = self.selected_operation()
        self.parameter_form.set_operation(operation)

    @QtCore.Slot()
    def _graph_selection_changed(self) -> None:
        self._sync_parameter_form_to_graph()
        self._refresh_result_inspector()

    def _sync_parameter_form_to_graph(self) -> None:
        row = self._selected_graph_row()
        if row is None:
            self.parameter_form.set_operation(self.selected_operation())
            return
        node = self.graph_model.node_at(row)
        operation = self._operation_for_node(node)
        if operation is None:
            self.parameter_form.set_operation(None)
            return
        self.parameter_form.set_operation(operation, node.params)

    def _selected_graph_row(self) -> int | None:
        selection = self.graph_view.selectionModel()
        if selection is None or not selection.hasSelection():
            return None
        return selection.selectedRows()[0].row()

    def _selected_history_row(self):
        selection = self.history_view.selectionModel()
        if selection is not None and selection.hasSelection():
            return self.history_model.row_at(selection.selectedRows()[0].row())
        return self.history_model.row_at(0)

    def _operation_for_node(self, node) -> OperationRow | None:  # type: ignore[no-untyped-def]
        if node is None:
            return None
        return self._operations_by_kind.get(node.kind)

    @QtCore.Slot()
    def _cancel_graph_job(self) -> None:
        if self._active_job_id is None:
            return
        self.cancel_job_button.setEnabled(False)
        self.job_status.setText(f"Cancel requested for graph job {self._active_job_id[:12]}.")
        self.cancelGraphJobRequested.emit(self._active_job_id)

    def _set_graph_editing_enabled(self, enabled: bool) -> None:
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.apply_params_button.setEnabled(enabled)
        self.evaluate_button.setEnabled(enabled)
        self.parameter_form.setEnabled(enabled)

    def _refresh_result_inspector(self) -> None:
        history = self._selected_history_row()
        if history is None:
            self.result_summary.setText("No graph result selected.")
            self.result_output.setText("-")
        else:
            self.result_summary.setText(
                f"{history.status} | {history.graph_id} | {history.duration_ms:.0f} ms | {history.message}"
            )
            self.result_output.setText(history.output_path or "-")

        artifact_paths, manifest_paths = self._selected_node_paths()
        if artifact_paths:
            self.result_artifacts.setText("\n".join(artifact_paths))
        elif history is not None and history.artifact_count:
            self.result_artifacts.setText(f"{history.artifact_count} artifact(s) recorded.")
        else:
            self.result_artifacts.setText("-")

        if manifest_paths:
            self.result_manifests.setText("\n".join(manifest_paths))
        elif self._asset_dir:
            self.result_manifests.setText(f"{self._asset_dir}/asset_manifest.json")
        else:
            self.result_manifests.setText("-")

        self.result_readiness.setText(self._readiness_summary())
        self.retarget_diagnostics.setText(self._retarget_diagnostics_summary())
        self.resource_model.set_rows(self.selected_result_resources())
        if self.resource_model.rowCount() and not self.resource_view.selectionModel().hasSelection():
            self.resource_view.selectRow(0)
        self._refresh_resource_selection()
        can_bridge = self._manifest_engine_ready()
        self.create_unity_bridge_button.setEnabled(can_bridge)
        self.create_unreal_bridge_button.setEnabled(can_bridge)
        can_plan = self._manifest_payload is not None and bool(self._asset_dir)
        self.plan_unity_retarget_button.setEnabled(can_plan)
        self.plan_unreal_retarget_button.setEnabled(can_plan)

    def _refresh_resource_selection(self) -> None:
        self._refresh_resource_buttons()
        self.resource_details.setText(_resource_detail_text(self.selected_result_resource()))

    def _refresh_resource_buttons(self) -> None:
        paths = self.selected_result_paths()
        selected_resource = self.selected_result_resource()
        self.open_output_button.setEnabled(bool(paths["output"]))
        self.reveal_output_button.setEnabled(bool(paths["output"]))
        self.open_resource_button.setEnabled(selected_resource is not None)
        self.reveal_resource_button.setEnabled(selected_resource is not None)
        self.open_artifact_button.setEnabled(bool(paths["artifact"]))
        self.open_manifest_button.setEnabled(bool(paths["manifest"]))
        self.reveal_asset_dir_button.setEnabled(bool(paths["asset_dir"]))

    def selected_result_paths(self) -> dict[str, str]:
        resources = self.selected_result_resources()
        output_path = _first_resource_path(resources, "output")
        artifact_path = _preferred_resource_path(resources, "artifact")
        manifest_path = _preferred_resource_path(resources, "manifest")
        asset_dir = _preferred_resource_path(resources, "asset_dir")
        return {
            "output": output_path,
            "artifact": artifact_path,
            "manifest": manifest_path,
            "asset_dir": asset_dir,
        }

    def selected_result_resources(self) -> tuple[GraphResultResource, ...]:
        history = self._selected_history_row()
        details = history.details if history is not None else {}
        artifact_paths, manifest_paths = self._selected_node_paths()
        detail_manifest_paths = _string_list(details.get("manifest_paths"))
        known_asset_dirs = {self._asset_dir, *_string_list(details.get("asset_dirs"))}
        resources: list[GraphResultResource] = []
        output_path = ""
        if history is not None and history.output_path:
            output_path = history.output_path
            resources.append(
                GraphResultResource(
                    "output",
                    output_path,
                    "history",
                    {
                        "graph_id": history.graph_id,
                        "status": history.status,
                        "message": history.message,
                        "duration_ms": round(history.duration_ms, 2),
                    },
                )
            )
        for path in artifact_paths:
            kind = "asset_dir" if path in known_asset_dirs else "artifact"
            resources.append(GraphResultResource(kind, path, "selected node", {"node_selection": True}))
        resources.extend(
            GraphResultResource("artifact", path, "history", {"graph_id": history.graph_id if history else ""})
            for path in _string_list(details.get("artifact_paths"))
        )
        resources.extend(
            GraphResultResource("manifest", path, "selected node", self._manifest_summary_details())
            for path in manifest_paths
        )
        resources.extend(
            GraphResultResource("manifest", path, "history", _history_audit_summary(details))
            for path in detail_manifest_paths
        )
        if self._asset_dir:
            resources.append(
                GraphResultResource(
                    "asset_dir",
                    self._asset_dir,
                    "selected object",
                    {"manifest": self._asset_manifest_path()},
                )
            )
        resources.extend(
            GraphResultResource("asset_dir", path, "history", {"manifest": str(Path(path) / "asset_manifest.json")})
            for path in _string_list(details.get("asset_dirs"))
        )
        bridge_details = _bridge_details_by_path(details)
        resources.extend(
            GraphResultResource("bridge", path, "history", bridge_details.get(path, {}))
            for path in _string_list(details.get("bridge_paths"))
        )
        asset_manifest = self._asset_manifest_path()
        if asset_manifest:
            resources.append(
                GraphResultResource("manifest", asset_manifest, "selected object", self._manifest_summary_details())
            )
        elif manifest_paths:
            asset_manifest = manifest_paths[0]
        elif detail_manifest_paths:
            asset_manifest = detail_manifest_paths[0]
        audit_details = details.get("audit_history")
        if isinstance(audit_details, dict) and asset_manifest:
            status = str(audit_details.get("status") or "audit")
            preset = str(audit_details.get("preset") or "default")
            resources.append(GraphResultResource("audit_history", asset_manifest, f"{preset}:{status}", dict(audit_details)))
        resources.extend(self._manifest_resource_rows(asset_manifest, output_path=output_path))
        return _unique_resources(resources)

    def selected_result_resource(self) -> GraphResultResource | None:
        selection = self.resource_view.selectionModel()
        if selection is not None and selection.hasSelection():
            return self.resource_model.row_at(selection.selectedRows()[0].row())
        return self.resource_model.row_at(0)

    @QtCore.Slot(str)
    def _emit_open_result_path(self, key: str) -> None:
        path = self._path_for_action(key)
        if not path:
            self.status.setText(f"No {key.replace('_', ' ')} path available.")
            return
        self.openGraphPathRequested.emit(path)

    @QtCore.Slot(str)
    def _emit_reveal_result_path(self, key: str) -> None:
        path = self._path_for_action(key)
        if not path:
            self.status.setText(f"No {key.replace('_', ' ')} path available.")
            return
        self.revealGraphPathRequested.emit(path)

    def _path_for_action(self, key: str) -> str:
        if key == "selected":
            resource = self.selected_result_resource()
            return "" if resource is None else resource.path
        return self.selected_result_paths().get(key, "")

    def _asset_manifest_path(self) -> str:
        if not self._asset_dir:
            return ""
        return str(Path(self._asset_dir) / "asset_manifest.json")

    def _manifest_summary_details(self) -> dict[str, object]:
        payload = self._manifest_payload
        if payload is None:
            return {}
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        custom = payload.get("custom") if isinstance(payload.get("custom"), dict) else {}
        report = validation.get("report")
        provenance = payload.get("provenance")
        return {
            "asset_id": payload.get("asset_id"),
            "validation": validation.get("status"),
            "errors": validation.get("error_count"),
            "warnings": validation.get("warning_count"),
            "validation_issues": _validation_issue_text(report),
            "validation_issue_list": _validation_issue_lines(report),
            "artifacts": len(payload.get("artifacts", [])) if isinstance(payload.get("artifacts"), list) else 0,
            "provenance_steps": len(provenance) if isinstance(provenance, list) else 0,
            "latest_provenance": _provenance_text(provenance),
            "provenance_step_list": _provenance_lines(provenance),
            "audit_history": len(custom.get("audit_history", [])) if isinstance(custom.get("audit_history"), list) else 0,
            "bridge_history": len(custom.get("engine_export_bridges", []))
            if isinstance(custom.get("engine_export_bridges"), list)
            else 0,
        }

    def _manifest_resource_rows(
        self,
        asset_manifest: str,
        *,
        output_path: str = "",
    ) -> tuple[GraphResultResource, ...]:
        payload = self._manifest_payload
        if payload is None:
            return ()
        rows: list[GraphResultResource] = []
        artifacts = payload.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                role = str(artifact.get("role") or "")
                path = str(artifact.get("path") or "")
                if not path:
                    continue
                if role.startswith("engine.bridge."):
                    target = role.removeprefix("engine.bridge.") or "engine"
                    rows.append(
                        GraphResultResource(
                            "bridge",
                            path,
                            f"artifact:{target}",
                            {"target_engine": target, "role": role},
                        )
                    )
                elif role.startswith("texture."):
                    rows.append(GraphResultResource("artifact", path, f"manifest:{role}", {"role": role}))
                elif role.startswith("mesh.") and path != output_path:
                    rows.append(GraphResultResource("artifact", path, f"manifest:{role}", {"role": role}))

        custom = payload.get("custom") if isinstance(payload.get("custom"), dict) else {}
        bridge_history = custom.get("engine_export_bridges") if isinstance(custom, dict) else None
        if isinstance(bridge_history, list):
            for item in bridge_history:
                if not isinstance(item, dict):
                    continue
                path = str(item.get("package_path") or "")
                if path:
                    target = str(item.get("target_engine") or "engine")
                    rows.append(GraphResultResource("bridge", path, f"history:{target}", _bridge_summary(item)))
        audit_history = custom.get("audit_history") if isinstance(custom, dict) else None
        if isinstance(audit_history, list) and audit_history and asset_manifest:
            latest = audit_history[-1]
            if isinstance(latest, dict):
                status = str(latest.get("status") or "audit")
                preset = str(latest.get("preset") or "default")
                rows.append(GraphResultResource("audit_history", asset_manifest, f"{preset}:{status}", _audit_summary(latest)))
        return tuple(rows)

    def _selected_node_paths(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        row = self._selected_graph_row()
        if row is None:
            return (), ()
        index = self.graph_model.index(row, 0)
        artifact_paths = self.graph_model.data(index, self.graph_model.ArtifactRole) or ()
        manifest_paths = self.graph_model.data(index, self.graph_model.ManifestRole) or ()
        return tuple(str(item) for item in artifact_paths), tuple(str(item) for item in manifest_paths)

    def _readiness_summary(self) -> str:
        payload = self._manifest_payload
        if payload is None:
            return "No manifest loaded."
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        status = str(validation.get("status") or "skipped")
        errors = int(validation.get("error_count") or 0)
        warnings = int(validation.get("warning_count") or 0)
        if status in {"passed", "warnings"} and errors == 0:
            prefix = "Engine bridge ready"
            if warnings:
                prefix += f" with {warnings} warning(s)"
            else:
                prefix += ": audit passed"
        elif status == "failed" or errors:
            prefix = f"Blocked by audit errors ({errors} error(s), {warnings} warning(s))"
        else:
            prefix = "Audit required before engine bridge"
        targets = _engine_target_text(payload)
        bridges = _bridge_history_text(payload)
        details = [prefix]
        if targets:
            details.append(f"Targets: {targets}")
        if bridges:
            details.append(f"Bridges: {bridges}")
        return " | ".join(details)

    def _manifest_engine_ready(self) -> bool:
        payload = self._manifest_payload
        if payload is None or not self._asset_dir:
            return False
        validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
        status = str(validation.get("status") or "skipped")
        errors = int(validation.get("error_count") or 0)
        return status in {"passed", "warnings"} and errors == 0

    def _retarget_diagnostics_summary(self) -> str:
        if self._retarget_report_payload is None:
            return "No retarget plan generated."
        return _retarget_report_text(
            self._retarget_target,
            self.graph_model.graph(),
            self._retarget_report_payload,
            after_report_payload=self._retarget_after_report_payload,
        )

    def _restore_retarget_plan_from_history(self) -> None:
        for row in self.history_model.rows():
            details = row.details
            report = details.get("retarget_report")
            after_report = details.get("retarget_after_report")
            target = details.get("retarget_target")
            if isinstance(report, dict) and target:
                self._retarget_target = str(target)
                self._retarget_report_payload = dict(report)
                self._retarget_after_report_payload = (
                    dict(after_report) if isinstance(after_report, dict) else None
                )
                return
        self._clear_retarget_plan()

    def _clear_retarget_plan(self) -> None:
        self._retarget_target = ""
        self._retarget_report_payload = None
        self._retarget_after_report_payload = None


def _first_resource_path(resources: tuple[GraphResultResource, ...], kind: str) -> str:
    for resource in resources:
        if resource.kind == kind:
            return resource.path
    return ""


def _resource_detail_text(resource: GraphResultResource | None) -> str:
    if resource is None:
        return "No resource selected."
    parts = [
        f"{resource.kind} | {resource.source or 'result'}",
        resource.path,
    ]
    for key, value in resource.details.items():
        if value in (None, "", [], {}):
            continue
        label = key.replace("_", " ").title()
        if isinstance(value, list):
            lines = [str(item) for item in value if item]
            if lines:
                parts.append(f"{label}:\n" + "\n".join(f"- {item}" for item in lines))
        else:
            parts.append(f"{label}: {value}")
    return "\n".join(parts)


def _history_audit_summary(details: dict[str, object]) -> dict[str, object]:
    audit = details.get("audit_history")
    return dict(audit) if isinstance(audit, dict) else {}


def _bridge_details_by_path(details: dict[str, object]) -> dict[str, dict[str, object]]:
    bridge_history = details.get("bridge_history")
    if not isinstance(bridge_history, list):
        return {}
    rows: dict[str, dict[str, object]] = {}
    for item in bridge_history:
        if not isinstance(item, dict):
            continue
        path = str(item.get("package_path") or "")
        if path:
            rows[path] = _bridge_summary(item)
    return rows


def _bridge_summary(item: dict[str, object]) -> dict[str, object]:
    return {
        "target_engine": item.get("target_engine"),
        "recommended_mcp_server": item.get("recommended_mcp_server"),
        "recommended_tool": item.get("recommended_tool"),
        "created_at": item.get("created_at"),
        "direct_engine_call": item.get("direct_engine_call"),
        "package_preview": _bridge_preview_lines(item),
    }


def _audit_summary(item: dict[str, object]) -> dict[str, object]:
    return {
        "preset": item.get("preset"),
        "status": item.get("status"),
        "error_count": item.get("error_count"),
        "warning_count": item.get("warning_count"),
        "info_count": item.get("info_count"),
        "duration_seconds": item.get("duration_seconds"),
        "started_at": item.get("started_at"),
        "finished_at": item.get("finished_at"),
        "audit_issue_list": _audit_issue_lines(item),
    }


def _bridge_preview_lines(item: dict[str, object]) -> list[str]:
    fields = (
        ("target_engine", item.get("target_engine")),
        ("recommended_mcp_server", item.get("recommended_mcp_server")),
        ("recommended_tool", item.get("recommended_tool")),
        ("direct_engine_call", item.get("direct_engine_call")),
        ("package_path", item.get("package_path")),
    )
    return [f"{key}={value}" for key, value in fields if value not in (None, "", [], {})]


def _audit_issue_lines(report: dict[str, object]) -> list[str]:
    issues = report.get("issues")
    if not isinstance(issues, list):
        return []
    lines: list[str] = []
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        severity = str(issue.get("severity") or "issue")
        rule = str(issue.get("rule") or "")
        code = str(issue.get("code") or "diagnostic")
        message = str(issue.get("message") or "")
        target = str(issue.get("target") or "")
        prefix = f"{severity} {rule}:{code}" if rule else f"{severity} {code}"
        if target:
            prefix += f" [{target}]"
        if message:
            prefix += f": {message}"
        lines.append(prefix)
    return lines


def _validation_issue_text(report: object) -> str:
    if not isinstance(report, dict):
        return ""
    parts: list[str] = []
    for bucket in ("errors", "warnings", "info"):
        issues = report.get(bucket)
        if not isinstance(issues, list) or not issues:
            continue
        codes = []
        for issue in issues[:3]:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or issue.get("message") or "issue")
            codes.append(code)
        if codes:
            parts.append(f"{bucket}:{', '.join(codes)}")
    return " | ".join(parts)


def _validation_issue_lines(report: object) -> list[str]:
    if not isinstance(report, dict):
        return []
    lines: list[str] = []
    for bucket in ("errors", "warnings", "info"):
        issues = report.get(bucket)
        if not isinstance(issues, list):
            continue
        label = {"errors": "error", "warnings": "warning", "info": "info"}[bucket]
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "issue")
            message = str(issue.get("message") or "")
            location = str(issue.get("location") or "")
            line = f"{label} {code}"
            if location:
                line += f" [{location}]"
            if message:
                line += f": {message}"
            lines.append(line)
    return lines


def _provenance_text(provenance: object) -> str:
    if not isinstance(provenance, list) or not provenance:
        return ""
    steps: list[str] = []
    for item in provenance[-3:]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "step")
        job_id = str(item.get("job_id") or "")
        steps.append(f"{kind}({job_id[:8]})" if job_id else kind)
    return " -> ".join(steps)


def _provenance_lines(provenance: object) -> list[str]:
    if not isinstance(provenance, list):
        return []
    lines: list[str] = []
    for index, item in enumerate(provenance, start=1):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "step")
        job_id = str(item.get("job_id") or "")
        started = str(item.get("started_at") or "")
        finished = str(item.get("finished_at") or "")
        line = f"{index}. {kind}"
        if job_id:
            line += f" job={job_id[:12]}"
        if started or finished:
            line += f" {started} -> {finished}".rstrip()
        lines.append(line)
    return lines


def _preferred_resource_path(resources: tuple[GraphResultResource, ...], kind: str) -> str:
    selected = next((resource for resource in resources if resource.kind == kind and resource.source == "selected node"), None)
    if selected is not None:
        return selected.path
    return _first_resource_path(resources, kind)


def _unique_resources(resources: list[GraphResultResource]) -> tuple[GraphResultResource, ...]:
    unique: list[GraphResultResource] = []
    seen: set[tuple[str, str]] = set()
    for resource in resources:
        if not resource.path:
            continue
        key = (resource.kind, resource.path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(resource)
    return tuple(unique)


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _parent_dir(path_text: str) -> str:
    if not path_text:
        return ""
    return str(Path(path_text).parent)


def _engine_target_text(payload: dict[str, object]) -> str:
    targets = payload.get("engine_targets")
    if not isinstance(targets, list):
        return ""
    names: list[str] = []
    for target in targets:
        if isinstance(target, dict) and target.get("engine"):
            names.append(str(target["engine"]))
    return ", ".join(dict.fromkeys(names))


def _bridge_history_text(payload: dict[str, object]) -> str:
    custom = payload.get("custom") if isinstance(payload.get("custom"), dict) else {}
    history = custom.get("engine_export_bridges") if isinstance(custom, dict) else None
    if not isinstance(history, list):
        return ""
    names: list[str] = []
    for item in history:
        if isinstance(item, dict) and item.get("target_engine"):
            names.append(str(item["target_engine"]))
    return ", ".join(dict.fromkeys(names))


def _retarget_summary(target_engine: str, graph: EditGraph, report_payload: dict[str, object]) -> str:
    issues = _retarget_issues(report_payload)
    return f"{target_engine.title()} retarget plan: {len(graph.nodes)} nodes from {len(issues)} diagnostics"


def _retarget_report_text(
    target_engine: str,
    graph: EditGraph,
    report_payload: dict[str, object],
    *,
    after_report_payload: dict[str, object] | None = None,
) -> str:
    issues = _retarget_issues(report_payload)
    if after_report_payload is not None:
        comparison = _retarget_comparison(report_payload, after_report_payload)
        return _retarget_comparison_text(target_engine, graph, comparison, after_report_payload)
    if not issues:
        return f"{target_engine.title()} retarget plan: no retarget diagnostics; graph has {len(graph.nodes)} nodes."
    counts = _severity_counts(issues)
    headline = (
        f"{target_engine.title()} retarget plan: {len(graph.nodes)} nodes from "
        f"{len(issues)} diagnostics"
    )
    severity = ", ".join(f"{name}={count}" for name, count in counts.items() if count)
    examples = []
    for issue in issues[:3]:
        code = str(issue.get("code") or "diagnostic")
        suggestion = str(issue.get("suggestion") or issue.get("message") or "")
        examples.append(f"{code}: {suggestion}")
    parts = [headline]
    if severity:
        parts.append(severity)
    parts.extend(examples)
    return "\n".join(parts)


def _retarget_comparison_summary(target_engine: str, graph: EditGraph, comparison: dict[str, list[str]]) -> str:
    return (
        f"{target_engine.title()} retarget check: {len(comparison['resolved'])}/"
        f"{len(comparison['planned'])} planned diagnostics resolved after {len(graph.nodes)} nodes"
    )


def _retarget_comparison_text(
    target_engine: str,
    graph: EditGraph,
    comparison: dict[str, list[str]],
    after_report_payload: dict[str, object],
) -> str:
    headline = _retarget_comparison_summary(target_engine, graph, comparison)
    after_issues = _retarget_issues(after_report_payload)
    counts = _severity_counts(after_issues)
    severity = ", ".join(f"{name}={count}" for name, count in counts.items() if count)
    parts = [
        headline,
        (
            f"remaining={len(comparison['remaining'])}, "
            f"new={len(comparison['new'])}"
        ),
    ]
    if severity:
        parts.append(f"after severity: {severity}")
    if comparison["remaining"]:
        parts.append("Remaining: " + ", ".join(comparison["remaining"][:3]))
    if comparison["new"]:
        parts.append("New: " + ", ".join(comparison["new"][:3]))
    return "\n".join(parts)


def _retarget_comparison(
    planned_report: dict[str, object],
    after_report: dict[str, object],
) -> dict[str, list[str]]:
    planned = {_issue_key(issue) for issue in _retarget_issues(planned_report)}
    after = {_issue_key(issue) for issue in _retarget_issues(after_report)}
    return {
        "planned": sorted(planned),
        "resolved": sorted(planned - after),
        "remaining": sorted(planned & after),
        "new": sorted(after - planned),
    }


def _retarget_issues(report_payload: dict[str, object]) -> list[dict[str, object]]:
    issues = report_payload.get("issues")
    if not isinstance(issues, list):
        return []
    return [
        issue
        for issue in issues
        if isinstance(issue, dict) and str(issue.get("rule") or "").startswith("retarget.")
    ]


def _severity_counts(issues: list[dict[str, object]]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        severity = str(issue.get("severity") or "")
        if severity in counts:
            counts[severity] += 1
    return counts


def _issue_key(issue: dict[str, object]) -> str:
    return f"{issue.get('rule') or ''}:{issue.get('code') or ''}"


def _latest_planned_retarget_report(
    payloads: tuple[dict[str, object], ...],
    *,
    target_engine: str,
) -> dict[str, object]:
    for payload in payloads:
        details = payload.get("details")
        if not isinstance(details, dict):
            continue
        if str(details.get("retarget_target") or "") != target_engine:
            continue
        report = details.get("retarget_report")
        if isinstance(report, dict):
            return dict(report)
    return {}


__all__ = ["OperationGraphPanel"]
