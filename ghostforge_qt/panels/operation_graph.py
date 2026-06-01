from __future__ import annotations

import json
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from ghostforge_core.authoring import EditGraph, EvaluationResult
from ghostforge_core.scene_links import (
    compare_graph_history_payloads,
    graph_history_comparison_resource_uri_from_payloads,
)
from ghostforge_core.types import JobHandle
from ghostforge_qt.models.operation_graph_model import (
    GraphHistoryDeltaModel,
    GraphHistoryDeltaRow,
    GraphResultResource,
    GraphResultResourceModel,
    OperationGraphHistoryModel,
    OperationGraphModel,
    OperationPaletteModel,
    RetargetDiagnosticModel,
    RetargetDiagnosticRow,
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
    historyComparisonLinkCopied = QtCore.Signal(str)
    historyComparisonPairChanged = QtCore.Signal(object)

    def __init__(self, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.palette_model = OperationPaletteModel(parent=self)
        self.graph_model = OperationGraphModel(parent=self)
        self.history_model = OperationGraphHistoryModel(parent=self)
        self.resource_model = GraphResultResourceModel(parent=self)
        self.history_delta_model = GraphHistoryDeltaModel(parent=self)
        self.retarget_model = RetargetDiagnosticModel(parent=self)
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
        self._resource_rows: tuple[GraphResultResource, ...] = ()
        self._last_history_comparison: dict[str, object] | None = None
        self._last_history_comparison_uri: str = ""
        self._history_comparison_pair_ids: tuple[str, str] | None = None
        self._history_comparison_pair_locked = False
        self._syncing_history_comparison_controls = False
        self._operations_by_kind: dict[str, OperationRow] = {}
        self._graph_editing_enabled = True
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
        self.move_up_button = QtWidgets.QPushButton("Move Up")
        self.move_down_button = QtWidgets.QPushButton("Move Down")
        self.toggle_node_button = QtWidgets.QPushButton("Disable Node")
        self.move_up_button.setEnabled(False)
        self.move_down_button.setEnabled(False)
        self.toggle_node_button.setEnabled(False)
        self.apply_params_button = QtWidgets.QPushButton("Apply Params")
        self.evaluate_button = QtWidgets.QPushButton("Evaluate")
        self.refresh_button.clicked.connect(self.refresh)
        self.add_button.clicked.connect(self.add_selected_operation)
        self.remove_button.clicked.connect(self.remove_selected_node)
        self.move_up_button.clicked.connect(lambda _checked=False: self.move_selected_node(-1))
        self.move_down_button.clicked.connect(lambda _checked=False: self.move_selected_node(1))
        self.toggle_node_button.clicked.connect(self.toggle_selected_node_enabled)
        self.apply_params_button.clicked.connect(self.apply_selected_node_params)
        self.evaluate_button.clicked.connect(self.evaluateRequested.emit)
        for button in (
            self.refresh_button,
            self.add_button,
            self.remove_button,
            self.move_up_button,
            self.move_down_button,
            self.toggle_node_button,
            self.apply_params_button,
            self.evaluate_button,
        ):
            button_row.addWidget(button)
        root.addLayout(button_row)

        self.graph_view = QtWidgets.QTableView()
        self.graph_view.setModel(self.graph_model)
        self.graph_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.graph_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.graph_view.setDragEnabled(True)
        self.graph_view.setAcceptDrops(True)
        self.graph_view.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.graph_view.setDragDropOverwriteMode(False)
        self.graph_view.setDefaultDropAction(QtCore.Qt.DropAction.MoveAction)
        self.graph_view.setDropIndicatorShown(True)
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
        self.history_comparison = QtWidgets.QLabel("Need at least two history rows to compare.")
        self.history_compare_left = QtWidgets.QComboBox()
        self.history_compare_right = QtWidgets.QComboBox()
        self.history_comparison_uri = QtWidgets.QLabel("-")
        self.copy_history_comparison_link_button = QtWidgets.QPushButton("Copy Compare URI")
        self.copy_history_comparison_link_button.setEnabled(False)
        for label in (
            self.result_summary,
            self.result_output,
            self.result_artifacts,
            self.result_manifests,
            self.result_readiness,
            self.retarget_diagnostics,
            self.history_comparison,
            self.history_comparison_uri,
        ):
            label.setWordWrap(True)
        self.history_comparison.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.history_comparison_uri.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        inspector_layout.addRow("Result", self.result_summary)
        inspector_layout.addRow("Output", self.result_output)
        inspector_layout.addRow("Artifacts", self.result_artifacts)
        inspector_layout.addRow("Manifests", self.result_manifests)
        inspector_layout.addRow("Readiness", self.result_readiness)
        inspector_layout.addRow("Retarget", self.retarget_diagnostics)
        self.retarget_view = QtWidgets.QTableView()
        self.retarget_view.setModel(self.retarget_model)
        self.retarget_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.retarget_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.retarget_view.horizontalHeader().setStretchLastSection(True)
        self.retarget_view.verticalHeader().hide()
        self.retarget_view.setMinimumHeight(76)
        inspector_layout.addRow("Retarget Diff", self.retarget_view)
        compare_row = QtWidgets.QHBoxLayout()
        compare_row.addWidget(QtWidgets.QLabel("From"))
        compare_row.addWidget(self.history_compare_left, 1)
        compare_row.addWidget(QtWidgets.QLabel("To"))
        compare_row.addWidget(self.history_compare_right, 1)
        inspector_layout.addRow("Compare", compare_row)
        inspector_layout.addRow("History Delta", self.history_comparison)
        self.history_delta_view = QtWidgets.QTableView()
        self.history_delta_view.setModel(self.history_delta_model)
        self.history_delta_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_delta_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.history_delta_view.horizontalHeader().setStretchLastSection(True)
        self.history_delta_view.verticalHeader().hide()
        self.history_delta_view.setMinimumHeight(96)
        inspector_layout.addRow("Delta Table", self.history_delta_view)
        comparison_link_row = QtWidgets.QHBoxLayout()
        comparison_link_row.addWidget(self.history_comparison_uri, 1)
        comparison_link_row.addWidget(self.copy_history_comparison_link_button)
        inspector_layout.addRow("MCP Compare", comparison_link_row)
        self.resource_filter = QtWidgets.QComboBox()
        for label, kind in (
            ("All", "all"),
            ("Outputs", "output"),
            ("Artifacts", "artifact"),
            ("Manifests", "manifest"),
            ("Asset Dirs", "asset_dir"),
            ("Audits", "audit_history"),
            ("Bridges", "bridge"),
        ):
            self.resource_filter.addItem(label, kind)
        inspector_layout.addRow("Filter", self.resource_filter)
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
        self.graph_model.rowsMoved.connect(lambda *_: self._graph_rows_reordered())
        self.history_view.selectionModel().selectionChanged.connect(lambda *_: self._refresh_result_inspector())
        self.history_compare_left.currentIndexChanged.connect(lambda *_: self._history_comparison_pair_changed())
        self.history_compare_right.currentIndexChanged.connect(lambda *_: self._history_comparison_pair_changed())
        self.copy_history_comparison_link_button.clicked.connect(self.copy_history_comparison_link)
        self.resource_filter.currentIndexChanged.connect(lambda *_: self._refresh_resource_table())
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
            self._refresh_node_action_buttons()

    @QtCore.Slot(int)
    def move_selected_node(self, offset: int) -> None:
        row = self._selected_graph_row()
        if row is None:
            self.status.setText("Select a graph node.")
            return
        target_row = row + offset
        moved = self.graph_model.move_row(row, target_row)
        if moved is None:
            self.status.setText("Graph node cannot move further.")
            return
        self.graph_view.selectRow(target_row)
        self._sync_parameter_form_to_graph()
        self._refresh_node_action_buttons()
        direction = "up" if offset < 0 else "down"
        self.status.setText(f"Moved {moved.kind} {direction}.")

    def _graph_rows_reordered(self) -> None:
        self._sync_parameter_form_to_graph()
        self._refresh_node_action_buttons()
        self.graphChanged.emit(self.graph_model.graph())

    @QtCore.Slot()
    def toggle_selected_node_enabled(self) -> None:
        row = self._selected_graph_row()
        if row is None:
            self.status.setText("Select a graph node.")
            return
        node = self.graph_model.node_at(row)
        if node is None:
            self.status.setText("Selected graph node no longer exists.")
            return
        updated = self.graph_model.set_node_enabled(row, not node.enabled)
        if updated is None:
            self.status.setText("Selected graph node no longer exists.")
            return
        state = "enabled" if updated.enabled else "disabled"
        self.status.setText(f"{updated.kind} {state}.")
        self._refresh_node_action_buttons()
        self.graphChanged.emit(self.graph_model.graph())

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
            self._history_comparison_pair_ids = None
            self._history_comparison_pair_locked = False
        self.graph_model.set_graph(graph)
        self._sync_parameter_form_to_graph()
        self._refresh_node_action_buttons()
        self._refresh_result_inspector()
        if emit:
            self.graphChanged.emit(graph)

    def reset_graph(self, *, graph_id: str | None = None) -> None:
        graph = EditGraph(graph_id=graph_id or self.graph_model.graph().graph_id, name="Qt Operation Graph")
        self.set_graph(graph, emit=False)
        self.history_model.clear()
        self._history_comparison_pair_ids = None
        self._history_comparison_pair_locked = False
        self._clear_retarget_plan()
        self._refresh_result_inspector()

    def set_evaluation_result(self, result: EvaluationResult, payload: dict[str, object] | None = None) -> None:
        self._last_result = result
        self._last_payload = dict(payload or result.model_dump(mode="json"))
        self.graph_model.set_evaluation_result(result, payload=payload)
        self._history_comparison_pair_ids = None
        self._history_comparison_pair_locked = False
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
        self._history_comparison_pair_ids = None
        self._history_comparison_pair_locked = False
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

    def set_history_comparison_pair(self, pair: dict[str, object] | None) -> None:
        self._history_comparison_pair_ids = _history_comparison_pair_ids_from_payload(pair)
        self._history_comparison_pair_locked = self._history_comparison_pair_ids is not None
        self._refresh_history_comparison()

    def history_comparison_pair(self) -> dict[str, str]:
        pair = _history_comparison_pair_for_indices(
            self.history_model.payloads(),
            _combo_int_data(self.history_compare_left),
            _combo_int_data(self.history_compare_right),
        )
        return pair or {}

    def selected_history_comparison(self) -> dict[str, object] | None:
        if self._last_history_comparison is None:
            return None
        return dict(self._last_history_comparison)

    def selected_history_comparison_resource_uri(self) -> str:
        return self._last_history_comparison_uri

    @QtCore.Slot()
    def copy_history_comparison_link(self) -> None:
        uri = self.selected_history_comparison_resource_uri()
        if not uri:
            self.status.setText("No graph-history comparison URI available.")
            return
        QtGui.QGuiApplication.clipboard().setText(uri)
        self.status.setText("Copied graph-history comparison URI.")
        self.historyComparisonLinkCopied.emit(uri)

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
        self._history_comparison_pair_ids = None
        self._history_comparison_pair_locked = False
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
        self._history_comparison_pair_ids = None
        self._history_comparison_pair_locked = False
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
        self._refresh_node_action_buttons()
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

    def _selected_history_index(self) -> int | None:
        selection = self.history_view.selectionModel()
        if selection is not None and selection.hasSelection():
            row = selection.selectedRows()[0].row()
            if 0 <= row < self.history_model.rowCount():
                return row
        return 0 if self.history_model.rowCount() else None

    def _selected_history_row(self):
        row = self._selected_history_index()
        if row is None:
            return None
        return self.history_model.row_at(row)

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
        self._graph_editing_enabled = enabled
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.apply_params_button.setEnabled(enabled)
        self.evaluate_button.setEnabled(enabled)
        self.parameter_form.setEnabled(enabled)
        self._refresh_node_action_buttons()

    def _refresh_node_action_buttons(self) -> None:
        row = self._selected_graph_row()
        node = self.graph_model.node_at(row) if row is not None else None
        count = self.graph_model.rowCount()
        self.move_up_button.setEnabled(self._graph_editing_enabled and row is not None and row > 0)
        self.move_down_button.setEnabled(self._graph_editing_enabled and row is not None and row < count - 1)
        self.toggle_node_button.setEnabled(self._graph_editing_enabled and node is not None)
        self.toggle_node_button.setText("Enable Node" if node is not None and not node.enabled else "Disable Node")

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

        self._refresh_history_comparison()
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
        self._refresh_retarget_table()
        self._resource_rows = self.selected_result_resources()
        self._refresh_resource_table()
        can_bridge = self._manifest_engine_ready()
        self.create_unity_bridge_button.setEnabled(can_bridge)
        self.create_unreal_bridge_button.setEnabled(can_bridge)
        can_plan = self._manifest_payload is not None and bool(self._asset_dir)
        self.plan_unity_retarget_button.setEnabled(can_plan)
        self.plan_unreal_retarget_button.setEnabled(can_plan)

    def _refresh_history_comparison(self) -> None:
        selected_index = self._selected_history_index()
        payloads = self.history_model.payloads()
        self._sync_history_comparison_controls(payloads, selected_index=selected_index)
        self._refresh_history_comparison_from_controls(payloads, selected_index=selected_index)

    @QtCore.Slot()
    def _history_comparison_pair_changed(self) -> None:
        if self._syncing_history_comparison_controls:
            return
        self._refresh_history_comparison_from_controls(
            self.history_model.payloads(),
            selected_index=self._selected_history_index(),
        )
        self._history_comparison_pair_locked = self._history_comparison_pair_ids is not None
        self.historyComparisonPairChanged.emit(self.history_comparison_pair())

    def _sync_history_comparison_controls(
        self,
        payloads: tuple[dict[str, object], ...],
        *,
        selected_index: int | None,
    ) -> None:
        self._syncing_history_comparison_controls = True
        try:
            for combo in (self.history_compare_left, self.history_compare_right):
                combo.blockSignals(True)
                combo.clear()
                for index, payload in enumerate(payloads):
                    combo.addItem(_history_combo_label(index, payload), index)
                combo.setEnabled(len(payloads) >= 2)
                combo.blockSignals(False)

            pair = (
                _history_comparison_indices_for_ids(payloads, self._history_comparison_pair_ids)
                if self._history_comparison_pair_locked
                else None
            )
            if pair is None:
                pair = _default_history_comparison_pair(
                    selected_index,
                    history_count=len(payloads),
                )
            left_index, right_index = pair
            _set_combo_data(self.history_compare_left, left_index)
            _set_combo_data(self.history_compare_right, right_index)
        finally:
            self._syncing_history_comparison_controls = False

    def _refresh_history_comparison_from_controls(
        self,
        payloads: tuple[dict[str, object], ...],
        *,
        selected_index: int | None,
    ) -> None:
        left_index = _combo_int_data(self.history_compare_left)
        right_index = _combo_int_data(self.history_compare_right)
        comparison: dict[str, object] | None = None
        uri = ""
        if (
            left_index is not None
            and right_index is not None
            and left_index != right_index
            and 0 <= left_index < len(payloads)
            and 0 <= right_index < len(payloads)
        ):
            comparison = compare_graph_history_payloads(payloads[left_index], payloads[right_index])
            uri = graph_history_comparison_resource_uri_from_payloads(payloads[left_index], payloads[right_index])
        self._history_comparison_pair_ids = _history_comparison_pair_ids_from_indices(
            payloads,
            left_index,
            right_index,
        )
        self._last_history_comparison = comparison
        self._last_history_comparison_uri = uri
        self.history_delta_model.set_rows(_history_delta_rows(comparison))
        if self.history_delta_model.rowCount():
            self.history_delta_view.selectRow(0)
        else:
            self.history_delta_view.clearSelection()
        self.history_comparison.setText(
            _history_comparison_text(
                comparison,
                selected_index=selected_index,
                history_count=len(payloads),
                left_index=left_index,
                right_index=right_index,
            )
        )
        self.history_comparison_uri.setText(uri or "-")
        self.copy_history_comparison_link_button.setEnabled(bool(uri))

    def _refresh_retarget_table(self) -> None:
        rows = _retarget_diagnostic_rows(
            self._retarget_report_payload,
            after_report_payload=self._retarget_after_report_payload,
        )
        self.retarget_model.set_rows(rows)
        if rows:
            self.retarget_view.selectRow(0)
        else:
            self.retarget_view.clearSelection()

    def _refresh_resource_table(self) -> None:
        current = self.selected_result_resource()
        current_key = _resource_key(current) if current is not None else None
        rows = self._filtered_resource_rows()
        self.resource_model.set_rows(rows)
        if rows:
            row_to_select = 0
            if current_key is not None:
                for row, resource in enumerate(rows):
                    if _resource_key(resource) == current_key:
                        row_to_select = row
                        break
            self.resource_view.selectRow(row_to_select)
        else:
            self.resource_view.clearSelection()
        self._refresh_resource_selection()

    def _filtered_resource_rows(self) -> tuple[GraphResultResource, ...]:
        kind = str(self.resource_filter.currentData() or "all")
        if kind == "all":
            return self._resource_rows
        return tuple(resource for resource in self._resource_rows if resource.kind == kind)

    def _refresh_resource_selection(self) -> None:
        self._refresh_resource_buttons()
        resource = self.selected_result_resource()
        text = _resource_detail_text(resource)
        package_text = _bridge_package_file_detail(resource)
        if package_text:
            text = f"{text}\n{package_text}"
        self.resource_details.setText(text)

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


def _combo_int_data(combo: QtWidgets.QComboBox) -> int | None:
    value = combo.currentData()
    if isinstance(value, int):
        return value
    return None


def _set_combo_data(combo: QtWidgets.QComboBox, value: int | None) -> None:
    if value is None:
        combo.setCurrentIndex(-1)
        return
    index = combo.findData(value)
    combo.setCurrentIndex(index)


def _history_comparison_pair_ids_from_payload(pair: dict[str, object] | None) -> tuple[str, str] | None:
    if not isinstance(pair, dict):
        return None
    left = str(pair.get("left_history_id") or "")
    right = str(pair.get("right_history_id") or "")
    if not left or not right or left == right:
        return None
    return left, right


def _history_comparison_indices_for_ids(
    payloads: tuple[dict[str, object], ...],
    pair: tuple[str, str] | None,
) -> tuple[int | None, int | None] | None:
    if pair is None:
        return None
    left_id, right_id = pair
    left_index = right_index = None
    for index, payload in enumerate(payloads):
        history_id = str(payload.get("history_id") or "")
        if history_id == left_id:
            left_index = index
        if history_id == right_id:
            right_index = index
    if left_index is None or right_index is None or left_index == right_index:
        return None
    return left_index, right_index


def _history_comparison_pair_ids_from_indices(
    payloads: tuple[dict[str, object], ...],
    left_index: int | None,
    right_index: int | None,
) -> tuple[str, str] | None:
    pair = _history_comparison_pair_for_indices(payloads, left_index, right_index)
    if pair is None:
        return None
    return pair["left_history_id"], pair["right_history_id"]


def _history_comparison_pair_for_indices(
    payloads: tuple[dict[str, object], ...],
    left_index: int | None,
    right_index: int | None,
) -> dict[str, str] | None:
    left_id = _history_id_at_index(payloads, left_index)
    right_id = _history_id_at_index(payloads, right_index)
    if not left_id or not right_id or left_id == right_id:
        return None
    return {"left_history_id": left_id, "right_history_id": right_id}


def _history_id_at_index(payloads: tuple[dict[str, object], ...], index: int | None) -> str:
    if index is None or index < 0 or index >= len(payloads):
        return ""
    return str(payloads[index].get("history_id") or "")


def _default_history_comparison_pair(
    selected_index: int | None,
    *,
    history_count: int,
) -> tuple[int | None, int | None]:
    if selected_index is None or history_count < 2:
        return None, None
    if selected_index + 1 < history_count:
        return selected_index + 1, selected_index
    return selected_index, selected_index


def _history_combo_label(index: int, payload: dict[str, object]) -> str:
    history_id = str(payload.get("history_id") or "")
    graph_id = str(payload.get("graph_id") or "graph")
    status = str(payload.get("status") or "history")
    label = history_id or graph_id
    if len(label) > 42:
        label = f"{label[:18]}...{label[-18:]}"
    return f"{index + 1}. {label} ({status})"


def _history_delta_rows(comparison: dict[str, object] | None) -> tuple[GraphHistoryDeltaRow, ...]:
    if not isinstance(comparison, dict) or not comparison.get("has_changes"):
        return ()
    rows: list[GraphHistoryDeltaRow] = []
    _append_history_field_delta_rows(rows, "Field", comparison.get("changed_fields"))

    detail_changes = comparison.get("detail_changes")
    if isinstance(detail_changes, dict):
        for key, label in (
            ("artifact_paths", "Artifact Paths"),
            ("asset_dirs", "Asset Dirs"),
            ("manifest_paths", "Manifest Paths"),
            ("bridge_paths", "Bridge Paths"),
            ("retarget_resolved", "Retarget Resolved"),
            ("retarget_remaining", "Retarget Remaining"),
            ("retarget_new", "Retarget New"),
        ):
            _append_history_list_delta_rows(
                rows,
                _history_delta_area_for_key(key),
                label,
                detail_changes.get(key),
            )

    audit_changes = comparison.get("audit_changes")
    if isinstance(audit_changes, dict):
        _append_history_field_delta_rows(rows, "Audit", audit_changes.get("changed_fields"))
        _append_history_list_delta_rows(
            rows,
            "Audit",
            "Issues",
            {
                "added": audit_changes.get("issues_added"),
                "removed": audit_changes.get("issues_removed"),
            },
        )
    return tuple(rows)


def _append_history_field_delta_rows(
    rows: list[GraphHistoryDeltaRow],
    area: str,
    changes: object,
) -> None:
    if not isinstance(changes, dict):
        return
    for key, change in changes.items():
        if not isinstance(change, dict):
            continue
        label = str(key).replace("_", " ").title()
        rows.append(
            GraphHistoryDeltaRow(
                area,
                label,
                "changed",
                f"{_comparison_value_text(change.get('left'))} -> {_comparison_value_text(change.get('right'))}",
                "changed",
            )
        )


def _append_history_list_delta_rows(
    rows: list[GraphHistoryDeltaRow],
    area: str,
    label: str,
    change: object,
) -> None:
    if not isinstance(change, dict):
        return
    added = change.get("added")
    removed = change.get("removed")
    if isinstance(added, list) and added:
        rows.append(GraphHistoryDeltaRow(area, label, "added", _comparison_list_text(added), "added"))
    if isinstance(removed, list) and removed:
        rows.append(GraphHistoryDeltaRow(area, label, "removed", _comparison_list_text(removed), "removed"))


def _history_delta_area_for_key(key: str) -> str:
    if key.startswith("retarget_"):
        return "Retarget"
    return "Resource"


def _history_comparison_text(
    comparison: dict[str, object] | None,
    *,
    selected_index: int | None,
    history_count: int,
    left_index: int | None = None,
    right_index: int | None = None,
) -> str:
    if history_count < 2:
        return "Need at least two history rows to compare graph history."
    if selected_index is None:
        return "No graph history row selected for comparison."
    if left_index == right_index:
        return "Choose two different graph history rows to compare."
    if comparison is None:
        return "Choose two graph history rows with saved comparison payloads."

    left = comparison.get("left") if isinstance(comparison.get("left"), dict) else {}
    right = comparison.get("right") if isinstance(comparison.get("right"), dict) else {}
    left_fallback = f"row {(left_index or 0) + 1}" if left_index is not None else "left row"
    right_fallback = f"row {(right_index or 0) + 1}" if right_index is not None else "right row"
    left_label = _history_summary_label(left, fallback=left_fallback)
    right_label = _history_summary_label(right, fallback=right_fallback)
    heading = "Previous -> Selected"
    if not (
        selected_index is not None
        and left_index == selected_index + 1
        and right_index == selected_index
    ):
        heading = "Comparison Pair"
    lines = [f"{heading}: {left_label} -> {right_label}"]
    if not comparison.get("has_changes"):
        lines.append("No manifest, resource, audit, or retarget deltas detected.")
        return "\n".join(lines)

    _append_field_change_lines(lines, comparison.get("changed_fields"))
    detail_changes = comparison.get("detail_changes")
    if isinstance(detail_changes, dict):
        for key, label in (
            ("artifact_paths", "Artifact Paths"),
            ("asset_dirs", "Asset Dirs"),
            ("manifest_paths", "Manifest Paths"),
            ("bridge_paths", "Bridge Paths"),
            ("retarget_resolved", "Retarget Resolved"),
            ("retarget_remaining", "Retarget Remaining"),
            ("retarget_new", "Retarget New"),
        ):
            _append_list_delta_lines(lines, label, detail_changes.get(key))

    audit_changes = comparison.get("audit_changes")
    if isinstance(audit_changes, dict):
        _append_field_change_lines(lines, audit_changes.get("changed_fields"), prefix="Audit ")
        _append_list_delta_lines(
            lines,
            "Audit Issues",
            {
                "added": audit_changes.get("issues_added"),
                "removed": audit_changes.get("issues_removed"),
            },
        )
    return "\n".join(lines)


def _history_summary_label(summary: object, *, fallback: str) -> str:
    if not isinstance(summary, dict):
        return fallback
    history_id = str(summary.get("history_id") or "")
    graph_id = str(summary.get("graph_id") or "")
    status = str(summary.get("status") or "history")
    base = history_id or graph_id or fallback
    return f"{base} ({status})"


def _append_field_change_lines(
    lines: list[str],
    changes: object,
    *,
    prefix: str = "",
) -> None:
    if not isinstance(changes, dict):
        return
    for key, change in changes.items():
        if not isinstance(change, dict):
            continue
        label = str(key).replace("_", " ").title()
        lines.append(
            f"- {prefix}{label}: {_comparison_value_text(change.get('left'))} -> "
            f"{_comparison_value_text(change.get('right'))}"
        )


def _append_list_delta_lines(lines: list[str], label: str, change: object) -> None:
    if not isinstance(change, dict):
        return
    added = change.get("added")
    removed = change.get("removed")
    if isinstance(added, list) and added:
        lines.append(f"- {label} Added: {_comparison_list_text(added)}")
    if isinstance(removed, list) and removed:
        lines.append(f"- {label} Removed: {_comparison_list_text(removed)}")


def _comparison_list_text(items: list[object], *, limit: int = 4) -> str:
    values = [_comparison_value_text(item) for item in items[:limit]]
    if len(items) > limit:
        values.append(f"+{len(items) - limit} more")
    return "; ".join(values)


def _comparison_value_text(value: object) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, dict):
        severity = str(value.get("severity") or "")
        rule = str(value.get("rule") or "")
        code = str(value.get("code") or "")
        target = str(value.get("target") or "")
        message = str(value.get("message") or "")
        if rule or code or message:
            prefix = " ".join(part for part in (severity, f"{rule}:{code}" if rule else code) if part).strip()
            if target:
                prefix = f"{prefix} [{target}]".strip()
            return f"{prefix}: {message}".strip(": ")
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, list):
        return _comparison_list_text(value)
    return str(value)


def _first_resource_path(resources: tuple[GraphResultResource, ...], kind: str) -> str:
    for resource in resources:
        if resource.kind == kind:
            return resource.path
    return ""


def _resource_key(resource: GraphResultResource) -> tuple[str, str, str]:
    return (resource.kind, resource.path, resource.source)


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


def _bridge_package_file_detail(
    resource: GraphResultResource | None,
    *,
    max_bytes: int = 256_000,
) -> str:
    if resource is None or resource.kind != "bridge" or not resource.path:
        return ""
    path = Path(resource.path)
    lines: list[str] = []
    try:
        if not path.exists():
            return ""
        if path.stat().st_size > max_bytes:
            return "Bridge Package JSON:\n- file_status=too_large"
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return f"Bridge Package JSON:\n- file_status=unreadable: {exc}"
    if not isinstance(payload, dict):
        return "Bridge Package JSON:\n- file_status=not_an_object"

    for key in (
        "bridge_version",
        "target_engine",
        "asset_id",
        "asset_path",
        "manifest_path",
        "target_path",
        "recommended_mcp_server",
        "recommended_tool",
        "created_at",
    ):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            lines.append(f"{key}={value}")

    manifest = payload.get("manifest")
    if isinstance(manifest, dict):
        validation = manifest.get("validation") if isinstance(manifest.get("validation"), dict) else {}
        status = validation.get("status") if isinstance(validation, dict) else None
        if status:
            lines.append(f"manifest_validation={status}")
        artifacts = manifest.get("artifacts")
        if isinstance(artifacts, list):
            lines.append(f"manifest_artifacts={len(artifacts)}")

    notes = payload.get("notes")
    if notes:
        lines.append(f"notes={notes}")
    if not lines:
        return "Bridge Package JSON:\n- file_status=empty"
    return "Bridge Package JSON:\n" + "\n".join(f"- {line}" for line in lines)


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
        parts.append("Remaining families: " + _retarget_family_text(comparison["remaining"]))
    if comparison["new"]:
        parts.append("New: " + ", ".join(comparison["new"][:3]))
        parts.append("New families: " + _retarget_family_text(comparison["new"]))
    return "\n".join(parts)


def _retarget_diagnostic_rows(
    report_payload: dict[str, object] | None,
    *,
    after_report_payload: dict[str, object] | None = None,
) -> tuple[RetargetDiagnosticRow, ...]:
    if not isinstance(report_payload, dict):
        return ()
    planned = _retarget_issues_by_key(report_payload)
    if after_report_payload is None:
        rows = [
            _retarget_row_from_issue(issue, state="planned", source="planned")
            for issue in planned.values()
        ]
        return tuple(sorted(rows, key=_retarget_row_sort_key))

    after = _retarget_issues_by_key(after_report_payload)
    rows: list[RetargetDiagnosticRow] = []
    for key in sorted(planned.keys() & after.keys()):
        rows.append(_retarget_row_from_issue(after[key], state="remaining", source="after"))
    for key in sorted(after.keys() - planned.keys()):
        rows.append(_retarget_row_from_issue(after[key], state="new", source="after"))
    for key in sorted(planned.keys() - after.keys()):
        rows.append(_retarget_row_from_issue(planned[key], state="resolved", source="planned"))
    return tuple(sorted(rows, key=_retarget_row_sort_key))


def _retarget_row_from_issue(
    issue: dict[str, object],
    *,
    state: str,
    source: str,
) -> RetargetDiagnosticRow:
    return RetargetDiagnosticRow(
        state=state,
        severity=str(issue.get("severity") or ""),
        rule=str(issue.get("rule") or ""),
        code=str(issue.get("code") or "diagnostic"),
        target=str(issue.get("target") or issue.get("location") or ""),
        message=str(issue.get("message") or ""),
        suggestion=str(issue.get("suggestion") or ""),
        source=source,
    )


def _retarget_row_sort_key(row: RetargetDiagnosticRow) -> tuple[int, int, str, str]:
    state_order = {"remaining": 0, "new": 1, "planned": 2, "resolved": 3}
    severity_order = {"error": 0, "warning": 1, "info": 2}
    return (
        state_order.get(row.state, 9),
        severity_order.get(row.severity, 9),
        row.rule,
        row.code,
    )


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


def _retarget_issues_by_key(report_payload: dict[str, object]) -> dict[str, dict[str, object]]:
    return {_issue_key(issue): issue for issue in _retarget_issues(report_payload)}


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


def _retarget_family_text(keys: list[str]) -> str:
    families: list[str] = []
    for key in keys:
        family = key.split(":", 1)[0]
        if family and family not in families:
            families.append(family)
    return ", ".join(families)


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
