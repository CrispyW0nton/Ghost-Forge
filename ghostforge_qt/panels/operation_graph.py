from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_core.authoring import EditGraph, EvaluationResult
from ghostforge_core.types import JobHandle
from ghostforge_qt.models.operation_graph_model import (
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

    def __init__(self, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.palette_model = OperationPaletteModel(parent=self)
        self.graph_model = OperationGraphModel(parent=self)
        self.history_model = OperationGraphHistoryModel(parent=self)
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
        if emit:
            self.graphChanged.emit(graph)

    def reset_graph(self, *, graph_id: str | None = None) -> None:
        graph = EditGraph(graph_id=graph_id or self.graph_model.graph().graph_id, name="Qt Operation Graph")
        self.set_graph(graph, emit=False)
        self.history_model.clear()

    def set_evaluation_result(self, result: EvaluationResult, payload: dict[str, object] | None = None) -> None:
        self._last_result = result
        self._last_payload = dict(payload or result.model_dump(mode="json"))
        self.graph_model.set_evaluation_result(result, payload=payload)
        self.history_model.append_result(result, payload=payload)
        self.status.setText(f"Graph {result.status}: {len(result.steps)} steps.")
        self.audit_button.setEnabled(True)
        failed_row = self.graph_model.first_failed_row()
        if failed_row is not None:
            self.graph_view.selectRow(failed_row)
            self.status.setText(f"Graph failed at row {failed_row + 1}.")

    def apply_audit_manifest(self, manifest_payload: dict[str, object], *, message: str = "") -> None:
        if self._last_result is None:
            self.audit_status.setText(message or "Audit complete.")
            return
        payload = dict(self._last_payload or self._last_result.model_dump(mode="json"))
        payload["manifest"] = dict(manifest_payload)
        self._last_payload = payload
        self.graph_model.set_evaluation_result(self._last_result, payload=payload)
        self.history_model.append_result(self._last_result, payload=payload, message=message or "audit refreshed")
        self.audit_status.setText(message or "Audit refreshed graph result.")

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

    def set_history_payloads(self, payloads: tuple[dict[str, object], ...] | list[dict[str, object]]) -> None:
        self.history_model.set_payloads(payloads)

    def history_payloads(self) -> tuple[dict[str, object], ...]:
        return self.history_model.payloads()

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


__all__ = ["OperationGraphPanel"]
