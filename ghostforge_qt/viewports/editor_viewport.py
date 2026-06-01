from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ghostforge_qt.theme.theme_model import Theme, built_in_themes

from .mesh_preview import MeshPreview, load_mesh_preview
from .renderer_interface import ViewportObject


@dataclass(frozen=True)
class ViewportPickResult:
    mode: str
    object_id: str
    object_name: str
    vertex_index: int | None = None
    edge: tuple[int, int] | None = None
    edge_index: int | None = None
    face_index: int | None = None
    element_index: int | None = None
    screen_distance: float = 0.0
    depth: float = 0.0
    additive: bool = False
    toggle: bool = False


@dataclass(frozen=True)
class ProjectedViewportObject:
    obj: ViewportObject
    mesh: MeshPreview
    projected: np.ndarray
    depth: np.ndarray


class ViewportCanvas(QtWidgets.QWidget):
    itemPicked = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.objects: list[ViewportObject] = []
        self.display_mode = "shaded"
        self.selection_mode = "object"
        self.transform_mode = "move"
        self.camera_preset = "perspective"
        self.theme = built_in_themes()["forge_dark"]
        self._mesh_cache: dict[Path, MeshPreview | Exception] = {}
        self.active_object_id: str | None = None
        self.selected_object_ids: set[str] = set()
        self.selected_vertices: set[int] = set()
        self.selected_edges: set[tuple[int, int]] = set()
        self.selected_faces: set[int] = set()
        self.selected_borders: set[int] = set()
        self.selected_elements: set[int] = set()
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)

    def set_theme(self, theme: Theme) -> None:
        self.theme = theme
        self.update()

    def set_objects(self, objects: list[ViewportObject]) -> None:
        self.objects = list(objects)
        self.update()

    def set_selection_state(
        self,
        *,
        active_object_id: str | None = None,
        object_ids: set[str] | None = None,
        vertices: set[int] | None = None,
        edges: set[tuple[int, int]] | None = None,
        faces: set[int] | None = None,
        borders: set[int] | None = None,
        elements: set[int] | None = None,
    ) -> None:
        self.active_object_id = active_object_id
        self.selected_object_ids = set(object_ids or ())
        self.selected_vertices = set(vertices or ())
        self.selected_edges = {tuple(sorted((int(a), int(b)))) for a, b in (edges or ())}
        self.selected_faces = set(faces or ())
        self.selected_borders = set(borders or ())
        self.selected_elements = set(elements or ())
        self.update()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            modifiers = event.modifiers()
            pick = self.pick_at(
                event.position(),
                additive=bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier),
                toggle=bool(modifiers & QtCore.Qt.KeyboardModifier.ControlModifier),
            )
            if pick is not None:
                self.itemPicked.emit(pick)
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(self.theme.color("viewport.bg")))
        self._draw_grid(painter, rect)
        self._draw_axes(painter, rect)
        self._draw_meshes(painter, rect)
        self._draw_overlay(painter, rect)
        painter.end()

    def _draw_grid(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        minor = QtGui.QPen(QtGui.QColor(self.theme.color("viewport.grid")), 1)
        major = QtGui.QPen(QtGui.QColor(self.theme.color("viewport.grid.major")), 1)
        center_x = rect.center().x()
        center_y = rect.center().y()
        step = 28
        for x in range(center_x % step, rect.width(), step):
            painter.setPen(major if abs(x - center_x) < 2 else minor)
            painter.drawLine(x, 0, x, rect.height())
        for y in range(center_y % step, rect.height(), step):
            painter.setPen(major if abs(y - center_y) < 2 else minor)
            painter.drawLine(0, y, rect.width(), y)

    def _draw_axes(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        origin = QtCore.QPoint(rect.center().x(), rect.center().y())
        axis_len = 90
        painter.setPen(QtGui.QPen(QtGui.QColor("#d64b55"), 3))
        painter.drawLine(origin, origin + QtCore.QPoint(axis_len, 0))
        painter.drawText(origin + QtCore.QPoint(axis_len + 8, 4), "X")
        painter.setPen(QtGui.QPen(QtGui.QColor("#55d47a"), 3))
        painter.drawLine(origin, origin + QtCore.QPoint(0, -axis_len))
        painter.drawText(origin + QtCore.QPoint(8, -axis_len - 6), "Y")
        painter.setPen(QtGui.QPen(QtGui.QColor("#4bb9ff"), 3))
        painter.drawLine(origin, origin + QtCore.QPoint(-54, 54))
        painter.drawText(origin + QtCore.QPoint(-74, 72), "Z")

    def _draw_overlay(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        painter.setPen(QtGui.QPen(QtGui.QColor(self.theme.color("text.primary"))))
        painter.setFont(QtGui.QFont("Segoe UI", 10))
        header = (
            f"{self.camera_preset.upper()} | {self.display_mode.upper()} | "
            f"{self.selection_mode.upper()} | {self.transform_mode.upper()}"
        )
        painter.drawText(14, 24, header)
        if not self.objects:
            painter.setPen(QtGui.QColor(self.theme.color("text.muted")))
            painter.setFont(QtGui.QFont("Segoe UI", 18))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "Import or generate a mesh")
            return
        card = QtCore.QRect(14, 42, min(360, rect.width() - 28), min(28 + len(self.objects) * 22, 300))
        painter.fillRect(card, QtGui.QColor(0, 0, 0, 95))
        painter.setPen(QtGui.QPen(QtGui.QColor(self.theme.color("panel.border"))))
        painter.drawRect(card)
        painter.setFont(QtGui.QFont("Segoe UI", 9))
        for i, obj in enumerate(self.objects[:10]):
            painter.setPen(QtGui.QColor(self.theme.color("accent.primary")))
            painter.drawText(card.left() + 10, card.top() + 24 + i * 22, obj.name)

    def _draw_meshes(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        frame = self.projected_objects(rect)
        if not frame:
            return
        for item in frame:
            if self.display_mode in {"shaded", "solid", "xray"}:
                self._draw_faces(painter, item.mesh, item.projected, item.depth)
            if self.display_mode in {"wireframe", "shaded", "xray", "uv"}:
                self._draw_edges(painter, item.mesh, item.projected)
        for item in frame:
            self._draw_selection_overlay(painter, item)

    def projected_objects(self, rect: QtCore.QRect | None = None) -> list[ProjectedViewportObject]:
        rect = rect or self.rect()
        if not self.objects or rect.width() <= 0 or rect.height() <= 0:
            return []
        previews = [(obj, self._preview_for(obj.path)) for obj in self.objects]
        valid = [(obj, mesh) for obj, mesh in previews if isinstance(mesh, MeshPreview)]
        if not valid:
            return []
        scene_min, scene_max = _scene_bounds(valid)
        scene_center = (scene_min + scene_max) * 0.5
        scene_extent = float(np.max(scene_max - scene_min)) or 1.0
        scale = min(rect.width(), rect.height()) * 0.62 / scene_extent
        out: list[ProjectedViewportObject] = []
        for obj, mesh in valid:
            points = _apply_transform(mesh.vertices - scene_center, obj.transform)
            projected, depth = _project(points, self.camera_preset, rect.center(), scale)
            out.append(ProjectedViewportObject(obj=obj, mesh=mesh, projected=projected, depth=depth))
        return out

    def pick_at(
        self,
        point,
        *,
        mode: str | None = None,
        additive: bool = False,
        toggle: bool = False,
    ) -> ViewportPickResult | None:  # type: ignore[no-untyped-def]
        mode = mode or self.selection_mode
        target = _point_array(point)
        frame = self.projected_objects()
        if mode == "vertex":
            return _pick_vertex(frame, target, mode=mode, additive=additive, toggle=toggle)
        if mode in {"edge", "border"}:
            return _pick_edge(frame, target, mode=mode, additive=additive, toggle=toggle)
        if mode in {"face", "element"}:
            return _pick_face(frame, target, mode=mode, additive=additive, toggle=toggle)
        return _pick_object(frame, target, additive=additive, toggle=toggle)

    def _preview_for(self, path: Path) -> MeshPreview | Exception:
        key = Path(path).resolve()
        cached = self._mesh_cache.get(key)
        if cached is not None:
            return cached
        try:
            cached = load_mesh_preview(key)
        except Exception as exc:
            cached = exc
        self._mesh_cache[key] = cached
        return cached

    def _draw_faces(self, painter: QtGui.QPainter, mesh: MeshPreview, projected: np.ndarray, depth: np.ndarray) -> None:
        if mesh.faces.size == 0:
            return
        face_depth = depth[mesh.faces].mean(axis=1)
        order = np.argsort(face_depth)
        base = QtGui.QColor(self.theme.color("accent.primary"))
        alpha = 60 if self.display_mode == "xray" else 115
        pen = QtGui.QPen(QtGui.QColor(0, 0, 0, 0))
        painter.setPen(pen)
        for face_index in order[-900:]:
            face = mesh.faces[face_index]
            pts = [QtCore.QPointF(float(projected[i, 0]), float(projected[i, 1])) for i in face]
            shade = int(80 + min(120, max(0, (face_depth[face_index] - face_depth.min()) * 12)))
            color = QtGui.QColor(base)
            color = color.lighter(max(80, min(180, shade)))
            color.setAlpha(alpha)
            painter.setBrush(QtGui.QBrush(color))
            painter.drawPolygon(QtGui.QPolygonF(pts))

    def _draw_edges(self, painter: QtGui.QPainter, mesh: MeshPreview, projected: np.ndarray) -> None:
        color = QtGui.QColor(self.theme.color("text.secondary"))
        color.setAlpha(160 if self.display_mode != "xray" else 95)
        painter.setPen(QtGui.QPen(color, 1))
        for a, b in mesh.edges[:9000]:
            painter.drawLine(
                QtCore.QPointF(float(projected[a, 0]), float(projected[a, 1])),
                QtCore.QPointF(float(projected[b, 0]), float(projected[b, 1])),
            )

    def _draw_selection_overlay(self, painter: QtGui.QPainter, item: ProjectedViewportObject) -> None:
        selected = item.obj.object_id in self.selected_object_ids or item.obj.object_id == self.active_object_id
        if not selected:
            return
        accent = QtGui.QColor(self.theme.color("accent.primary"))
        accent = accent.lighter(140)
        mins = item.projected.min(axis=0)
        maxes = item.projected.max(axis=0)
        bounds = QtCore.QRectF(
            float(mins[0]) - 6,
            float(mins[1]) - 6,
            float(maxes[0] - mins[0]) + 12,
            float(maxes[1] - mins[1]) + 12,
        )
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(accent, 2))
        painter.drawRect(bounds)

        if item.obj.object_id != self.active_object_id:
            return
        self._draw_selected_faces(painter, item, accent)
        self._draw_selected_edges(painter, item, accent)
        self._draw_selected_vertices(painter, item, accent)

    def _draw_selected_faces(
        self,
        painter: QtGui.QPainter,
        item: ProjectedViewportObject,
        color: QtGui.QColor,
    ) -> None:
        face_indices = set(self.selected_faces) | set(self.selected_elements)
        if not face_indices:
            return
        fill = QtGui.QColor(color)
        fill.setAlpha(120)
        painter.setPen(QtGui.QPen(color, 2))
        painter.setBrush(QtGui.QBrush(fill))
        for face_index in sorted(face_indices):
            if face_index < 0 or face_index >= len(item.mesh.faces):
                continue
            face = item.mesh.faces[face_index]
            pts = [QtCore.QPointF(float(item.projected[i, 0]), float(item.projected[i, 1])) for i in face]
            painter.drawPolygon(QtGui.QPolygonF(pts))

    def _draw_selected_edges(
        self,
        painter: QtGui.QPainter,
        item: ProjectedViewportObject,
        color: QtGui.QColor,
    ) -> None:
        edge_pairs = set(self.selected_edges)
        for edge_index in self.selected_borders:
            if 0 <= edge_index < len(item.mesh.edges):
                a, b = item.mesh.edges[edge_index]
                edge_pairs.add(tuple(sorted((int(a), int(b)))))
        if not edge_pairs:
            return
        painter.setPen(QtGui.QPen(color, 4))
        for a, b in edge_pairs:
            if a < 0 and 0 <= b < len(item.mesh.edges):
                a, b = item.mesh.edges[b]
            if a < 0 or b < 0 or a >= len(item.projected) or b >= len(item.projected):
                continue
            painter.drawLine(
                QtCore.QPointF(float(item.projected[a, 0]), float(item.projected[a, 1])),
                QtCore.QPointF(float(item.projected[b, 0]), float(item.projected[b, 1])),
            )

    def _draw_selected_vertices(
        self,
        painter: QtGui.QPainter,
        item: ProjectedViewportObject,
        color: QtGui.QColor,
    ) -> None:
        if not self.selected_vertices:
            return
        fill = QtGui.QColor(color)
        fill.setAlpha(210)
        painter.setPen(QtGui.QPen(QtGui.QColor("#0a0f18"), 1))
        painter.setBrush(QtGui.QBrush(fill))
        for vertex_index in sorted(self.selected_vertices):
            if vertex_index < 0 or vertex_index >= len(item.projected):
                continue
            x, y = item.projected[vertex_index]
            painter.drawEllipse(QtCore.QPointF(float(x), float(y)), 4.5, 4.5)


class EditorViewportRenderer(QtCore.QObject):
    itemPicked = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.canvas = ViewportCanvas()
        self.canvas.itemPicked.connect(self.itemPicked.emit)

    def widget(self) -> QtWidgets.QWidget:
        return self.canvas

    def set_objects(self, objects: list[ViewportObject]) -> None:
        self.canvas.set_objects(objects)

    def set_selection_state(self, **state) -> None:  # type: ignore[no-untyped-def]
        self.canvas.set_selection_state(**state)

    def set_display_mode(self, mode: str) -> None:
        self.canvas.display_mode = mode
        self.canvas.update()

    def set_selection_mode(self, mode: str) -> None:
        self.canvas.selection_mode = mode
        self.canvas.update()

    def set_transform_mode(self, mode: str) -> None:
        self.canvas.transform_mode = mode
        self.canvas.update()

    def set_camera_preset(self, preset: str) -> None:
        self.canvas.camera_preset = preset
        self.canvas.update()

    def set_theme(self, theme: Theme) -> None:
        self.canvas.set_theme(theme)

    def frame_all(self) -> None:
        self.canvas.update()


def _scene_bounds(items: list[tuple[ViewportObject, MeshPreview]]) -> tuple[np.ndarray, np.ndarray]:
    mins = []
    maxes = []
    for obj, mesh in items:
        corners = np.array(
            [
                [mesh.bounds_min[0], mesh.bounds_min[1], mesh.bounds_min[2]],
                [mesh.bounds_min[0], mesh.bounds_min[1], mesh.bounds_max[2]],
                [mesh.bounds_min[0], mesh.bounds_max[1], mesh.bounds_min[2]],
                [mesh.bounds_min[0], mesh.bounds_max[1], mesh.bounds_max[2]],
                [mesh.bounds_max[0], mesh.bounds_min[1], mesh.bounds_min[2]],
                [mesh.bounds_max[0], mesh.bounds_min[1], mesh.bounds_max[2]],
                [mesh.bounds_max[0], mesh.bounds_max[1], mesh.bounds_min[2]],
                [mesh.bounds_max[0], mesh.bounds_max[1], mesh.bounds_max[2]],
            ],
            dtype=float,
        )
        transformed = _apply_transform(corners, obj.transform)
        mins.append(transformed.min(axis=0))
        maxes.append(transformed.max(axis=0))
    return np.vstack(mins).min(axis=0), np.vstack(maxes).max(axis=0)


def _point_array(point) -> np.ndarray:  # type: ignore[no-untyped-def]
    if hasattr(point, "x") and hasattr(point, "y"):
        return np.array([float(point.x()), float(point.y())], dtype=float)
    return np.array([float(point[0]), float(point[1])], dtype=float)


def _pick_object(
    frame: list[ProjectedViewportObject],
    point: np.ndarray,
    *,
    additive: bool,
    toggle: bool,
) -> ViewportPickResult | None:
    face = _pick_face(frame, point, mode="object", additive=additive, toggle=toggle)
    if face is not None:
        return face
    candidates: list[tuple[float, float, ProjectedViewportObject]] = []
    for item in frame:
        mins = item.projected.min(axis=0)
        maxes = item.projected.max(axis=0)
        margin = 8.0
        inside = (
            mins[0] - margin <= point[0] <= maxes[0] + margin
            and mins[1] - margin <= point[1] <= maxes[1] + margin
        )
        if not inside:
            continue
        center = (mins + maxes) * 0.5
        distance = float(np.linalg.norm(point - center))
        depth = float(np.mean(item.depth)) if len(item.depth) else 0.0
        candidates.append((distance, -depth, item))
    if not candidates:
        return None
    distance, neg_depth, item = min(candidates, key=lambda value: (value[0], value[1]))
    return ViewportPickResult(
        mode="object",
        object_id=item.obj.object_id,
        object_name=item.obj.name,
        screen_distance=distance,
        depth=-neg_depth,
        additive=additive,
        toggle=toggle,
    )


def _pick_vertex(
    frame: list[ProjectedViewportObject],
    point: np.ndarray,
    *,
    mode: str,
    additive: bool,
    toggle: bool,
    threshold: float = 10.0,
) -> ViewportPickResult | None:
    candidates: list[tuple[float, float, ProjectedViewportObject, int]] = []
    for item in frame:
        if len(item.projected) == 0:
            continue
        distances = np.linalg.norm(item.projected - point, axis=1)
        vertex_index = int(np.argmin(distances))
        distance = float(distances[vertex_index])
        if distance <= threshold:
            depth = float(item.depth[vertex_index])
            candidates.append((distance, -depth, item, vertex_index))
    if not candidates:
        return None
    distance, neg_depth, item, vertex_index = min(candidates, key=lambda value: (value[0], value[1]))
    return ViewportPickResult(
        mode=mode,
        object_id=item.obj.object_id,
        object_name=item.obj.name,
        vertex_index=vertex_index,
        screen_distance=distance,
        depth=-neg_depth,
        additive=additive,
        toggle=toggle,
    )


def _pick_edge(
    frame: list[ProjectedViewportObject],
    point: np.ndarray,
    *,
    mode: str,
    additive: bool,
    toggle: bool,
    threshold: float = 8.0,
) -> ViewportPickResult | None:
    candidates: list[tuple[float, float, ProjectedViewportObject, int, tuple[int, int]]] = []
    for item in frame:
        for edge_index, pair in enumerate(item.mesh.edges[:9000]):
            a, b = int(pair[0]), int(pair[1])
            distance = _point_segment_distance(point, item.projected[a], item.projected[b])
            if distance <= threshold:
                depth = float((item.depth[a] + item.depth[b]) * 0.5)
                candidates.append((distance, -depth, item, edge_index, tuple(sorted((a, b)))))
    if not candidates:
        return None
    distance, neg_depth, item, edge_index, edge = min(candidates, key=lambda value: (value[0], value[1]))
    return ViewportPickResult(
        mode=mode,
        object_id=item.obj.object_id,
        object_name=item.obj.name,
        edge=edge,
        edge_index=edge_index,
        screen_distance=distance,
        depth=-neg_depth,
        additive=additive,
        toggle=toggle,
    )


def _pick_face(
    frame: list[ProjectedViewportObject],
    point: np.ndarray,
    *,
    mode: str,
    additive: bool,
    toggle: bool,
) -> ViewportPickResult | None:
    candidates: list[tuple[float, float, ProjectedViewportObject, int]] = []
    for item in frame:
        if item.mesh.faces.size == 0:
            continue
        face_depth = item.depth[item.mesh.faces].mean(axis=1)
        for face_index, face in enumerate(item.mesh.faces):
            tri = item.projected[face]
            if not _point_in_triangle(point, tri):
                continue
            center = tri.mean(axis=0)
            distance = float(np.linalg.norm(point - center))
            candidates.append((-float(face_depth[face_index]), distance, item, face_index))
    if not candidates:
        return None
    neg_depth, distance, item, face_index = min(candidates, key=lambda value: (value[0], value[1]))
    return ViewportPickResult(
        mode=mode,
        object_id=item.obj.object_id,
        object_name=item.obj.name,
        face_index=face_index if mode in {"face", "object"} else None,
        element_index=face_index if mode == "element" else None,
        screen_distance=distance,
        depth=-neg_depth,
        additive=additive,
        toggle=toggle,
    )


def _point_segment_distance(point: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab = b - a
    length_squared = float(np.dot(ab, ab))
    if length_squared <= 1e-9:
        return float(np.linalg.norm(point - a))
    t = max(0.0, min(1.0, float(np.dot(point - a, ab) / length_squared)))
    closest = a + ab * t
    return float(np.linalg.norm(point - closest))


def _point_in_triangle(point: np.ndarray, tri: np.ndarray) -> bool:
    a, b, c = tri
    v0 = c - a
    v1 = b - a
    v2 = point - a
    dot00 = float(np.dot(v0, v0))
    dot01 = float(np.dot(v0, v1))
    dot02 = float(np.dot(v0, v2))
    dot11 = float(np.dot(v1, v1))
    dot12 = float(np.dot(v1, v2))
    denom = dot00 * dot11 - dot01 * dot01
    if abs(denom) <= 1e-9:
        return False
    inv = 1.0 / denom
    u = (dot11 * dot02 - dot01 * dot12) * inv
    v = (dot00 * dot12 - dot01 * dot02) * inv
    eps = 1e-6
    return u >= -eps and v >= -eps and (u + v) <= 1.0 + eps


def _apply_transform(vertices: np.ndarray, transform) -> np.ndarray:  # type: ignore[no-untyped-def]
    out = np.array(vertices, dtype=float, copy=True)
    out *= np.asarray(transform.scale, dtype=float)
    rx, ry, rz = [math.radians(v) for v in transform.rotate_euler_deg]
    out = out @ _rot_x(rx).T @ _rot_y(ry).T @ _rot_z(rz).T
    out += np.asarray(transform.translate, dtype=float)
    return out


def _project(vertices: np.ndarray, preset: str, center: QtCore.QPoint, scale: float) -> tuple[np.ndarray, np.ndarray]:
    if preset == "front":
        x, y, depth = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    elif preset == "side":
        x, y, depth = vertices[:, 2], vertices[:, 1], vertices[:, 0]
    elif preset == "top":
        x, y, depth = vertices[:, 0], vertices[:, 2], vertices[:, 1]
    else:
        x = vertices[:, 0] - vertices[:, 2] * 0.38
        y = vertices[:, 1] + vertices[:, 2] * 0.22
        depth = vertices[:, 2] + vertices[:, 0] * 0.15
    projected = np.column_stack(
        [
            center.x() + x * scale,
            center.y() - y * scale,
        ]
    )
    return projected, depth


def _rot_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], dtype=float)


def _rot_y(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], dtype=float)


def _rot_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)
