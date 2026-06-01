from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass

from PySide6 import QtCore, QtGui

from ghostforge_core.authoring import EditGraph, EvaluationResult, OperationNode
from ghostforge_qt.services.core_bridge import OperationRow


class OperationPaletteModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Kind", "Type", "Status", "Workers", "Summary")
    OperationRole = QtCore.Qt.ItemDataRole.UserRole + 1
    KindRole = QtCore.Qt.ItemDataRole.UserRole + 2
    StatusRole = QtCore.Qt.ItemDataRole.UserRole + 3

    def __init__(self, rows: list[OperationRow] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = rows or []

    def set_rows(self, rows: list[OperationRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == self.OperationRole:
            return row
        if role == self.KindRole:
            return row.kind
        if role == self.StatusRole:
            return row.status
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() == 2:
            return QtGui.QBrush(_status_color(row.status))
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            row.kind,
            row.operation_type,
            row.status,
            ", ".join(row.workers) or "-",
            row.summary,
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def row_at(self, row: int) -> OperationRow | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def rows(self) -> list[OperationRow]:
        return list(self._rows)


class OperationGraphModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Enabled", "Kind", "Label", "Status", "Artifacts", "Manifest/Audit", "Params")
    NodeRole = QtCore.Qt.ItemDataRole.UserRole + 1
    NodeIdRole = QtCore.Qt.ItemDataRole.UserRole + 2
    StatusRole = QtCore.Qt.ItemDataRole.UserRole + 3
    ArtifactRole = QtCore.Qt.ItemDataRole.UserRole + 4
    ManifestRole = QtCore.Qt.ItemDataRole.UserRole + 5

    def __init__(self, graph: EditGraph | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._graph = graph or EditGraph(graph_id=f"qt_{uuid.uuid4().hex[:10]}", name="Qt Operation Graph")
        self._step_status: dict[str, str] = {}
        self._step_errors: dict[str, str] = {}
        self._node_artifacts: dict[str, tuple[str, ...]] = {}
        self._node_artifact_paths: dict[str, tuple[str, ...]] = {}
        self._node_manifest_paths: dict[str, tuple[str, ...]] = {}
        self._node_audit_badges: dict[str, str] = {}

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._graph.nodes)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        node = self._graph.nodes[index.row()]
        status = self._step_status.get(node.id, "pending")
        if role == self.NodeRole:
            return node
        if role == self.NodeIdRole:
            return node.id
        if role == self.StatusRole:
            return status
        if role == self.ArtifactRole:
            return self._node_artifact_paths.get(node.id, ())
        if role == self.ManifestRole:
            return self._node_manifest_paths.get(node.id, ())
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() == 3:
            return QtGui.QBrush(_status_color(status))
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() in {4, 5}:
            return QtGui.QBrush(_badge_color(index.column(), node, self))
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return _node_tooltip(node, self)
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            "yes" if node.enabled else "no",
            node.kind,
            node.label or node.kind,
            status,
            ", ".join(self._node_artifacts.get(node.id, ())) or "-",
            self._manifest_audit_text(node.id),
            _params_text(node.params),
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def graph(self) -> EditGraph:
        return self._graph

    def set_graph(self, graph: EditGraph) -> None:
        self.beginResetModel()
        self._graph = graph
        self._clear_evaluation_state()
        self.endResetModel()

    def append_operation(self, operation: OperationRow, params: dict[str, object] | None = None) -> OperationNode:
        node_id = _node_id(operation.kind, len(self._graph.nodes) + 1)
        node = OperationNode(
            id=node_id,
            kind=operation.kind,
            label=operation.label,
            params=params or {},
        )
        self.beginInsertRows(QtCore.QModelIndex(), len(self._graph.nodes), len(self._graph.nodes))
        self._graph = self._graph.with_nodes([*self._graph.nodes, node])
        self.endInsertRows()
        return node

    def remove_row(self, row: int) -> OperationNode | None:
        if row < 0 or row >= len(self._graph.nodes):
            return None
        nodes = list(self._graph.nodes)
        self.beginRemoveRows(QtCore.QModelIndex(), row, row)
        removed = nodes.pop(row)
        self._graph = self._graph.with_nodes(nodes)
        self._step_status.pop(removed.id, None)
        self._step_errors.pop(removed.id, None)
        self._node_artifacts.pop(removed.id, None)
        self._node_artifact_paths.pop(removed.id, None)
        self._node_manifest_paths.pop(removed.id, None)
        self._node_audit_badges.pop(removed.id, None)
        self.endRemoveRows()
        return removed

    def update_node_params(self, row: int, params: dict[str, object]) -> OperationNode | None:
        if row < 0 or row >= len(self._graph.nodes):
            return None
        nodes = list(self._graph.nodes)
        nodes[row] = nodes[row].model_copy(update={"params": dict(params)})
        self._graph = self._graph.with_nodes(nodes)
        self._step_status.pop(nodes[row].id, None)
        self._step_errors.pop(nodes[row].id, None)
        self._node_artifacts.pop(nodes[row].id, None)
        self._node_artifact_paths.pop(nodes[row].id, None)
        self._node_manifest_paths.pop(nodes[row].id, None)
        self._node_audit_badges.pop(nodes[row].id, None)
        self.dataChanged.emit(self.index(row, 0), self.index(row, self.columnCount() - 1), [])
        return nodes[row]

    def clear(self) -> None:
        if not self._graph.nodes:
            return
        self.beginResetModel()
        self._graph = self._graph.model_copy(update={"nodes": ()})
        self._clear_evaluation_state()
        self.endResetModel()

    def set_evaluation_result(self, result: EvaluationResult, payload: dict[str, object] | None = None) -> None:
        self._step_status = {step.node_id: step.status for step in result.steps}
        self._step_errors = {step.node_id: step.error or "" for step in result.steps if step.error}
        self._set_side_effect_badges(dict(payload or result.model_dump(mode="json")))
        if self.rowCount():
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, self.columnCount() - 1), [])

    def node_at(self, row: int) -> OperationNode | None:
        if row < 0 or row >= len(self._graph.nodes):
            return None
        return self._graph.nodes[row]

    def first_failed_row(self) -> int | None:
        for row, node in enumerate(self._graph.nodes):
            if self._step_status.get(node.id) == "failed":
                return row
        return None

    def _clear_evaluation_state(self) -> None:
        self._step_status.clear()
        self._step_errors.clear()
        self._node_artifacts.clear()
        self._node_artifact_paths.clear()
        self._node_manifest_paths.clear()
        self._node_audit_badges.clear()

    def _set_side_effect_badges(self, payload: dict[str, object]) -> None:
        self._node_artifacts.clear()
        self._node_artifact_paths.clear()
        self._node_manifest_paths.clear()
        self._node_audit_badges.clear()
        audit_badge = _manifest_audit_badge(payload.get("manifest"))
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        side_effects = metadata.get("side_effects") if isinstance(metadata, dict) else None
        if not isinstance(side_effects, list):
            return
        artifact_labels: dict[str, list[str]] = {}
        artifact_paths: dict[str, list[str]] = {}
        manifest_paths: dict[str, list[str]] = {}
        audit_badges: dict[str, str] = {}
        for effect in side_effects:
            if not isinstance(effect, dict):
                continue
            node_id = str(effect.get("node_id") or "")
            if not node_id:
                continue
            if effect.get("output_mesh"):
                artifact_labels.setdefault(node_id, []).append("mesh")
                artifact_paths.setdefault(node_id, []).append(str(effect["output_mesh"]))
            if effect.get("texture_map"):
                artifact_labels.setdefault(node_id, []).append("texture")
                artifact_paths.setdefault(node_id, []).append(str(effect["texture_map"]))
            if effect.get("asset_dir"):
                artifact_paths.setdefault(node_id, []).append(str(effect["asset_dir"]))
            if effect.get("manifest_path"):
                manifest_paths.setdefault(node_id, []).append(str(effect["manifest_path"]))
                if audit_badge:
                    audit_badges[node_id] = audit_badge
        self._node_artifacts = {key: tuple(dict.fromkeys(values)) for key, values in artifact_labels.items()}
        self._node_artifact_paths = {key: tuple(dict.fromkeys(values)) for key, values in artifact_paths.items()}
        self._node_manifest_paths = {key: tuple(dict.fromkeys(values)) for key, values in manifest_paths.items()}
        self._node_audit_badges = audit_badges

    def _manifest_audit_text(self, node_id: str) -> str:
        if not self._node_manifest_paths.get(node_id):
            return "-"
        badge = self._node_audit_badges.get(node_id)
        return f"manifest/{badge}" if badge else "manifest"


@dataclass(frozen=True)
class GraphEvaluationHistoryRow:
    graph_id: str
    status: str
    output_path: str
    duration_ms: float
    artifact_count: int
    audit_badge: str
    message: str


class OperationGraphHistoryModel(QtCore.QAbstractTableModel):
    COLUMNS = ("Graph", "Status", "Output", "Artifacts", "Audit", "Message")

    def __init__(self, rows: list[GraphEvaluationHistoryRow] | None = None, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows = rows or []

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == QtCore.Qt.ItemDataRole.ForegroundRole and index.column() in {1, 4}:
            return QtGui.QBrush(_status_color(row.status if index.column() == 1 else row.audit_badge))
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return row.message
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        values = (
            row.graph_id,
            row.status,
            row.output_path or "-",
            str(row.artifact_count),
            row.audit_badge or "-",
            row.message,
        )
        return values[index.column()]

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if role == QtCore.Qt.ItemDataRole.DisplayRole and orientation == QtCore.Qt.Orientation.Horizontal:
            return self.COLUMNS[section]
        return None

    def append_result(
        self,
        result: EvaluationResult,
        *,
        payload: dict[str, object] | None = None,
        message: str = "",
        limit: int = 25,
    ) -> GraphEvaluationHistoryRow:
        payload = payload or result.model_dump(mode="json")
        row = GraphEvaluationHistoryRow(
            graph_id=result.graph_id,
            status=result.status,
            output_path=str(result.output_path or ""),
            duration_ms=float(result.duration_ms or 0.0),
            artifact_count=_artifact_count(payload),
            audit_badge=_manifest_audit_badge(payload.get("manifest")),
            message=message or _result_message(result),
        )
        self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
        self._rows.insert(0, row)
        self.endInsertRows()
        if len(self._rows) > limit:
            self.beginRemoveRows(QtCore.QModelIndex(), limit, len(self._rows) - 1)
            del self._rows[limit:]
            self.endRemoveRows()
        return row

    def set_rows(self, rows: list[GraphEvaluationHistoryRow]) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def set_payloads(self, payloads: list[dict[str, object]] | tuple[dict[str, object], ...]) -> None:
        rows: list[GraphEvaluationHistoryRow] = []
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            rows.append(_history_row_from_payload(payload))
        self.set_rows(rows)

    def rows(self) -> list[GraphEvaluationHistoryRow]:
        return list(self._rows)

    def payloads(self) -> tuple[dict[str, object], ...]:
        return tuple(asdict(row) for row in self._rows)

    def row_at(self, row: int) -> GraphEvaluationHistoryRow | None:
        if row < 0 or row >= len(self._rows):
            return None
        return self._rows[row]

    def clear(self) -> None:
        if not self._rows:
            return
        self.beginResetModel()
        self._rows.clear()
        self.endResetModel()


def _node_id(kind: str, index: int) -> str:
    safe_kind = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in kind)
    return f"n{index}_{safe_kind[:40]}"


def _params_text(params: dict[str, object]) -> str:
    if not params:
        return "-"
    return json.dumps(params, sort_keys=True)


def _status_color(status: str) -> QtGui.QColor:
    if status in {"available", "runnable", "succeeded", "passed"}:
        return QtGui.QColor("#1F8F3A")
    if status in {"stub", "pending", "skipped", "warnings"}:
        return QtGui.QColor("#B9822B")
    return QtGui.QColor("#B34848")


def _badge_color(column: int, node: OperationNode, model: OperationGraphModel) -> QtGui.QColor:
    if column == 4 and model._node_artifacts.get(node.id):
        return QtGui.QColor("#2F6FB0")
    if column == 5 and model._node_audit_badges.get(node.id):
        return _status_color(model._node_audit_badges[node.id])
    if column == 5 and model._node_manifest_paths.get(node.id):
        return QtGui.QColor("#1F8F3A")
    return QtGui.QColor("#777777")


def _node_tooltip(node: OperationNode, model: OperationGraphModel) -> str:
    parts: list[str] = []
    if model._step_errors.get(node.id):
        parts.append(model._step_errors[node.id])
    if node.notes:
        parts.append(node.notes)
    artifact_paths = model._node_artifact_paths.get(node.id, ())
    if artifact_paths:
        parts.append("Artifacts:\n" + "\n".join(artifact_paths))
    manifest_paths = model._node_manifest_paths.get(node.id, ())
    if manifest_paths:
        parts.append("Manifests:\n" + "\n".join(manifest_paths))
    audit_badge = model._node_audit_badges.get(node.id)
    if audit_badge:
        parts.append(f"Audit: {audit_badge}")
    return "\n\n".join(parts)


def _manifest_audit_badge(manifest_payload: object) -> str:
    if not isinstance(manifest_payload, dict):
        return ""
    custom = manifest_payload.get("custom")
    if isinstance(custom, dict):
        history = custom.get("audit_history")
        if isinstance(history, list) and history:
            latest = history[-1]
            if isinstance(latest, dict) and latest.get("status"):
                return str(latest["status"])
    validation = manifest_payload.get("validation")
    if isinstance(validation, dict):
        status = validation.get("status")
        if status:
            return str(status)
    return ""


def _artifact_count(payload: dict[str, object]) -> int:
    manifest = payload.get("manifest")
    if isinstance(manifest, dict) and isinstance(manifest.get("artifacts"), list):
        return len(manifest["artifacts"])
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    side_effects = metadata.get("side_effects") if isinstance(metadata, dict) else None
    if not isinstance(side_effects, list):
        return 0
    count = 0
    for effect in side_effects:
        if not isinstance(effect, dict):
            continue
        count += 1 if effect.get("output_mesh") else 0
        count += 1 if effect.get("texture_map") else 0
    return count


def _result_message(result: EvaluationResult) -> str:
    failed = [step for step in result.steps if step.status == "failed"]
    if failed:
        first = failed[0]
        return first.error or f"{first.kind} failed"
    return f"{len(result.steps)} steps, {result.duration_ms:.0f} ms"


def _history_row_from_payload(payload: dict[str, object]) -> GraphEvaluationHistoryRow:
    return GraphEvaluationHistoryRow(
        graph_id=str(payload.get("graph_id") or ""),
        status=str(payload.get("status") or "skipped"),
        output_path=str(payload.get("output_path") or ""),
        duration_ms=float(payload.get("duration_ms") or 0.0),
        artifact_count=int(payload.get("artifact_count") or 0),
        audit_badge=str(payload.get("audit_badge") or ""),
        message=str(payload.get("message") or ""),
    )


__all__ = [
    "GraphEvaluationHistoryRow",
    "OperationGraphHistoryModel",
    "OperationGraphModel",
    "OperationPaletteModel",
]
