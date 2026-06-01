from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtWidgets

from ghostforge_core.authoring import EditGraph, EvaluationResult
from ghostforge_qt.models.operation_graph_model import OperationGraphModel, OperationPaletteModel
from ghostforge_qt.models.scene_model import SceneObjectRecord
from ghostforge_qt.services.core_bridge import CoreBridge, OperationRow


class OperationGraphPanel(QtWidgets.QWidget):
    graphChanged = QtCore.Signal(object)
    evaluateRequested = QtCore.Signal()

    def __init__(self, bridge: CoreBridge, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.bridge = bridge
        self.palette_model = OperationPaletteModel(parent=self)
        self.graph_model = OperationGraphModel(parent=self)
        self.active_object = QtWidgets.QLabel("-")
        self.active_object.setWordWrap(True)
        self.prompt = QtWidgets.QLineEdit()
        self.prompt.setPlaceholderText("Prompt")
        self.reference_path = QtWidgets.QLineEdit()
        self.reference_path.setPlaceholderText("Reference image path")
        self.worker = QtWidgets.QComboBox()
        self.status = QtWidgets.QLabel("Ready")
        self.status.setWordWrap(True)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        context = QtWidgets.QGroupBox("Context")
        context_form = QtWidgets.QFormLayout(context)
        context_form.addRow("Active", self.active_object)
        context_form.addRow("Prompt", self.prompt)
        context_form.addRow("Reference", self.reference_path)
        context_form.addRow("Worker", self.worker)
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
        self.evaluate_button = QtWidgets.QPushButton("Evaluate")
        self.refresh_button.clicked.connect(self.refresh)
        self.add_button.clicked.connect(self.add_selected_operation)
        self.remove_button.clicked.connect(self.remove_selected_node)
        self.evaluate_button.clicked.connect(self.evaluateRequested.emit)
        for button in (self.refresh_button, self.add_button, self.remove_button, self.evaluate_button):
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
        root.addWidget(self.status)

    @QtCore.Slot()
    def refresh(self) -> None:
        rows = self.bridge.list_operations()
        self.palette_model.set_rows(rows)
        self._refresh_workers(rows)
        if rows:
            self.palette_view.selectRow(0)
        self.status.setText(f"{len(rows)} operations available.")

    def _refresh_workers(self, operations: list[OperationRow]) -> None:
        current = self.worker.currentData()
        self.worker.clear()
        self.worker.addItem("Auto", "")
        names = sorted({name for row in operations for name in row.workers})
        for name in names:
            self.worker.addItem(name, name)
        if current:
            index = self.worker.findData(current)
            if index >= 0:
                self.worker.setCurrentIndex(index)

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
        node = self.graph_model.append_operation(operation, self._params_for(operation))
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

    def _params_for(self, operation: OperationRow) -> dict[str, object]:
        params: dict[str, object] = {}
        worker_name = str(self.worker.currentData() or "")
        if operation.capability is not None and worker_name:
            params["worker"] = worker_name
        prompt = self.prompt.text().strip()
        if operation.kind in {"generate_text_to_3d", "worker_texture_mesh"} and prompt:
            params["prompt"] = prompt
        if operation.kind == "generate_image_to_3d":
            ref = self.reference_path.text().strip()
            if ref:
                params["input_image_path"] = str(Path(ref))
            if prompt:
                params["prompt"] = prompt
        return params

    def graph(self) -> EditGraph:
        return self.graph_model.graph()

    def set_graph(self, graph: EditGraph, *, emit: bool = True) -> None:
        self.graph_model.set_graph(graph)
        if emit:
            self.graphChanged.emit(graph)

    def reset_graph(self, *, graph_id: str | None = None) -> None:
        graph = EditGraph(graph_id=graph_id or self.graph_model.graph().graph_id, name="Qt Operation Graph")
        self.set_graph(graph, emit=False)

    def set_evaluation_result(self, result: EvaluationResult) -> None:
        self.graph_model.set_evaluation_result(result)
        self.status.setText(f"Graph {result.status}: {len(result.steps)} steps.")

    def set_active_object(self, record: SceneObjectRecord | None) -> None:
        if record is None:
            self.active_object.setText("-")
            return
        self.active_object.setText(f"{record.name} ({record.object_id})")


__all__ = ["OperationGraphPanel"]
