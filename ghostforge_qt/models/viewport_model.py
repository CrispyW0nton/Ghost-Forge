from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore


@dataclass(frozen=True)
class ViewportDiagnosticRow:
    category: str
    name: str
    value: str


class ViewportDiagnosticsModel(QtCore.QAbstractTableModel):
    """Model-backed renderer and viewport state diagnostics."""

    HEADERS = ("Category", "Metric", "Value")

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._rows: tuple[ViewportDiagnosticRow, ...] = ()

    def rowCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QtCore.QModelIndex = QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index: QtCore.QModelIndex, role: int = QtCore.Qt.ItemDataRole.DisplayRole):  # noqa: ANN001, N802
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        if role in {QtCore.Qt.ItemDataRole.DisplayRole, QtCore.Qt.ItemDataRole.EditRole}:
            if index.column() == 0:
                return row.category
            if index.column() == 1:
                return row.name
            if index.column() == 2:
                return row.value
        if role == QtCore.Qt.ItemDataRole.ToolTipRole:
            return f"{row.category}: {row.name} = {row.value}"
        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ):
        if orientation == QtCore.Qt.Orientation.Horizontal and role == QtCore.Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return QtCore.Qt.ItemFlag.NoItemFlags
        return QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable

    def rows(self) -> tuple[ViewportDiagnosticRow, ...]:
        return self._rows

    def set_diagnostics(self, diagnostics: dict[str, object]) -> None:
        rows = _diagnostic_rows(diagnostics)
        self.beginResetModel()
        self._rows = tuple(rows)
        self.endResetModel()


def _diagnostic_rows(diagnostics: dict[str, object]) -> list[ViewportDiagnosticRow]:
    selection = diagnostics.get("selection_counts")
    selection_counts = selection if isinstance(selection, dict) else {}
    cache_errors = diagnostics.get("cache_errors")
    error_text = ", ".join(str(item) for item in cache_errors[:3]) if isinstance(cache_errors, list) else ""
    rows = [
        ViewportDiagnosticRow("Renderer", "Backend", str(diagnostics.get("backend_id") or "-")),
        ViewportDiagnosticRow("Renderer", "Name", str(diagnostics.get("renderer_name") or "-")),
        ViewportDiagnosticRow("Renderer", "Available", _bool_text(bool(diagnostics.get("available", True)))),
        ViewportDiagnosticRow(
            "Capabilities",
            "Scene Meshes",
            _bool_text(bool(diagnostics.get("supports_scene_meshes", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Object Picking",
            _bool_text(bool(diagnostics.get("supports_object_picking", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Frame Selected",
            _bool_text(bool(diagnostics.get("supports_frame_selected", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Sub-object Selection",
            _bool_text(bool(diagnostics.get("supports_subobject_selection", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Gizmo Interaction",
            _bool_text(bool(diagnostics.get("supports_gizmo_interaction", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Gizmo Plane Handles",
            _bool_text(bool(diagnostics.get("supports_gizmo_plane_handles", False))),
        ),
        ViewportDiagnosticRow(
            "Capabilities",
            "Projection Modes",
            _bool_text(bool(diagnostics.get("supports_projection_modes", False))),
        ),
        ViewportDiagnosticRow("Scene", "Objects", str(int(diagnostics.get("object_count") or 0))),
        ViewportDiagnosticRow("Scene", "Meshes", str(int(diagnostics.get("mesh_count") or 0))),
        ViewportDiagnosticRow("Scene", "Vertices", str(int(diagnostics.get("vertex_count") or 0))),
        ViewportDiagnosticRow("Scene", "Edges", str(int(diagnostics.get("edge_count") or 0))),
        ViewportDiagnosticRow("Scene", "Faces", str(int(diagnostics.get("face_count") or 0))),
        ViewportDiagnosticRow("Scene", "Cache Errors", str(int(diagnostics.get("cache_error_count") or 0))),
        ViewportDiagnosticRow("Mode", "Display", str(diagnostics.get("display_mode") or "-")),
        ViewportDiagnosticRow("Mode", "Selection", str(diagnostics.get("selection_mode") or "-")),
        ViewportDiagnosticRow("Mode", "Transform", str(diagnostics.get("transform_mode") or "-")),
        ViewportDiagnosticRow("Mode", "Gizmo Orientation", str(diagnostics.get("gizmo_orientation") or "-")),
        ViewportDiagnosticRow("Mode", "Gizmo Pivot", str(diagnostics.get("gizmo_pivot") or "-")),
        ViewportDiagnosticRow(
            "Mode",
            "Transform Gizmo",
            _bool_text(bool(diagnostics.get("transform_gizmo_visible", False))),
        ),
        ViewportDiagnosticRow("Mode", "Active Gizmo Axis", str(diagnostics.get("active_gizmo_axis") or "-")),
        ViewportDiagnosticRow("Camera", "Preset", str(diagnostics.get("camera_preset") or "-")),
        ViewportDiagnosticRow(
            "Camera",
            "Projection",
            str(diagnostics.get("projection_mode_label") or diagnostics.get("projection_mode") or "-"),
        ),
        ViewportDiagnosticRow(
            "Camera",
            "Navigation",
            str(diagnostics.get("navigation_profile_label") or diagnostics.get("navigation_profile") or "-"),
        ),
        ViewportDiagnosticRow("Camera", "Zoom", f"{float(diagnostics.get('zoom') or 1.0):.2f}x"),
        ViewportDiagnosticRow("Overlays", "Grid", _bool_text(bool(diagnostics.get("grid_visible", False)))),
        ViewportDiagnosticRow("Overlays", "Snap", _bool_text(bool(diagnostics.get("snap_enabled", False)))),
        ViewportDiagnosticRow("Overlays", "ViewCube", _bool_text(bool(diagnostics.get("view_cube_visible", False)))),
        ViewportDiagnosticRow("Selection", "Active Object", str(diagnostics.get("active_object_id") or "-")),
    ]
    for key in ("objects", "vertices", "edges", "faces", "borders", "elements"):
        rows.append(ViewportDiagnosticRow("Selection", key.title(), str(int(selection_counts.get(key) or 0))))
    if error_text:
        rows.append(ViewportDiagnosticRow("Scene", "Cache Error Preview", error_text))
    return rows


def _bool_text(value: bool) -> str:
    return "yes" if value else "no"
