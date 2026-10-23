from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from ghostforge_qt.theme.theme_model import Theme, built_in_themes
from ghostforge_qt.viewports.navigation import (
    DEFAULT_VIEWPORT_NAVIGATION_PROFILE,
    ViewportNavigationDragOrigin,
    ViewportNavigationState,
    apply_viewport_navigation_drag,
    clamp_viewport_zoom,
    has_modifier,
    normalize_viewport_navigation_profile,
    normalize_viewport_projection_mode,
    viewport_navigation_mouse_action,
    viewport_projection_label,
    viewport_profile_label,
    viewport_wheel_zoom,
)
from ghostforge_qt.viewports.transform_gizmo import (
    TransformGizmoDragOrigin,
    TransformGizmoHandle,
    handle_distance_to_point,
    normalize_gizmo_orientation,
    normalize_gizmo_pivot,
    transform_gizmo_edit_from_drag,
)
from ghostforge_qt.viewports.viewcube_math import (
    FACE_PRESETS,
    ViewCubeRegion,
    hit_test_view_cube,
    view_cube_panel_rect,
    view_cube_regions,
)

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
    cameraPresetChanged = QtCore.Signal(str)
    displayModeChanged = QtCore.Signal(str)
    navigationProfileChanged = QtCore.Signal(str)
    projectionModeChanged = QtCore.Signal(str)
    gridVisibilityChanged = QtCore.Signal(bool)
    snapChanged = QtCore.Signal(bool)
    viewCubeVisibilityChanged = QtCore.Signal(bool)
    gizmoOrientationChanged = QtCore.Signal(str)
    gizmoPivotChanged = QtCore.Signal(str)
    navigationStateChanged = QtCore.Signal(object)
    transformEdited = QtCore.Signal(object)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.objects: list[ViewportObject] = []
        self.display_mode = "shaded"
        self.selection_mode = "object"
        self.transform_mode = "move"
        self.gizmo_orientation = "world"
        self.gizmo_pivot = "bounds_center"
        self.camera_preset = "perspective"
        self.view_cube_visible = True
        self.navigation = ViewportNavigationState(profile=DEFAULT_VIEWPORT_NAVIGATION_PROFILE)
        self._drag_action = ""
        self._drag_origin = QtCore.QPointF()
        self._drag_navigation_origin: ViewportNavigationDragOrigin | None = None
        self._gizmo_drag_origin: TransformGizmoDragOrigin | None = None
        self._active_gizmo_axis = ""
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
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)

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
            region = self.view_cube_region_at(event.position())
            if region is not None:
                self.activate_view_cube_region(region.key)
                event.accept()
                return
            handle = self.transform_gizmo_handle_at(event.position())
            if handle is not None and self.active_object_id:
                active = self._viewport_object_by_id(self.active_object_id)
                if active is not None:
                    self._gizmo_drag_origin = TransformGizmoDragOrigin(
                        object_id=active.object_id,
                        mode=self.transform_mode,
                        axis=handle.axis,
                        start_mouse=(float(event.position().x()), float(event.position().y())),
                        handle=handle,
                        start_transform=active.transform,
                    )
                    self._active_gizmo_axis = handle.axis
                    self.setCursor(QtCore.Qt.CursorShape.SizeAllCursor)
                    event.accept()
                    return
        nav_action = self._navigation_action(event.button(), event.modifiers())
        if nav_action:
            self._drag_action = nav_action
            self._drag_origin = event.position()
            self._drag_navigation_origin = ViewportNavigationDragOrigin.from_state(nav_action, self.navigation)
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
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

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._gizmo_drag_origin is not None:
            edit = transform_gizmo_edit_from_drag(
                self._gizmo_drag_origin,
                (float(event.position().x()), float(event.position().y())),
                snap=bool(self.navigation.snap_enabled),
                phase="update",
            )
            self.transformEdited.emit(edit)
            self.update()
            event.accept()
            return
        if self._drag_action and self._drag_navigation_origin is not None:
            delta = event.position() - self._drag_origin
            if apply_viewport_navigation_drag(
                self.navigation,
                self._drag_navigation_origin,
                float(delta.x()),
                float(delta.y()),
            ):
                if self._drag_action == "orbit":
                    self.camera_preset = "perspective"
                    self.cameraPresetChanged.emit("perspective")
                self.update()
                self._emit_navigation_state_changed()
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._gizmo_drag_origin is not None:
            edit = transform_gizmo_edit_from_drag(
                self._gizmo_drag_origin,
                (float(event.position().x()), float(event.position().y())),
                snap=bool(self.navigation.snap_enabled),
                phase="end",
            )
            self.transformEdited.emit(edit)
            self._gizmo_drag_origin = None
            self._active_gizmo_axis = ""
            self.unsetCursor()
            self.update()
            event.accept()
            return
        if self._drag_action:
            self._drag_action = ""
            self._drag_navigation_origin = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        delta = float(event.angleDelta().y())
        if abs(delta) > 0:
            self.navigation.zoom = viewport_wheel_zoom(self.navigation.zoom, delta)
            self.update()
            self._emit_navigation_state_changed()
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        key = event.key()
        command = self._navigation_key_command(key, event.modifiers())
        if command == "frame_all":
            self.frame_all()
            event.accept()
            return
        if command == "frame_selected":
            self.frame_selected()
            event.accept()
            return
        if command == "reset_camera":
            self.reset_camera()
            event.accept()
            return
        if command == "toggle_grid":
            self.set_grid_visible(not self.navigation.grid_visible)
            event.accept()
            return
        if command == "toggle_wireframe":
            self.set_display_mode("shaded" if self.display_mode == "wireframe" else "wireframe")
            event.accept()
            return
        if command == "toggle_projection":
            self.set_projection_mode(
                "orthographic" if self.navigation.projection_mode == "perspective" else "perspective"
            )
            event.accept()
            return
        if command.startswith("camera:"):
            self.set_camera_preset(command.split(":", 1)[1])
            event.accept()
            return
        super().keyPressEvent(event)

    def set_display_mode(self, mode: str) -> None:
        value = str(mode or "").strip().lower()
        if value not in {"shaded", "wireframe", "solid", "uv", "xray"}:
            value = "shaded"
        changed = self.display_mode != value
        self.display_mode = value
        self.update()
        if changed:
            self.displayModeChanged.emit(value)
            self._emit_navigation_state_changed()

    def set_selection_mode(self, mode: str) -> None:
        value = str(mode or "").strip().lower()
        if value not in {"object", "vertex", "edge", "border", "face", "element"}:
            value = "object"
        self.selection_mode = value
        self.update()

    def set_transform_mode(self, mode: str) -> None:
        value = str(mode or "").strip().lower()
        if value not in {"move", "rotate", "scale", "pivot"}:
            value = "move"
        self.transform_mode = value
        self.update()

    def set_gizmo_orientation(self, orientation: object) -> None:
        value = normalize_gizmo_orientation(orientation)
        changed = self.gizmo_orientation != value
        self.gizmo_orientation = value
        self.update()
        if changed:
            self.gizmoOrientationChanged.emit(value)
            self._emit_navigation_state_changed()

    def set_gizmo_pivot(self, pivot: object) -> None:
        value = normalize_gizmo_pivot(pivot)
        changed = self.gizmo_pivot != value
        self.gizmo_pivot = value
        self.update()
        if changed:
            self.gizmoPivotChanged.emit(value)
            self._emit_navigation_state_changed()

    def navigation_state(self) -> dict[str, object]:
        state = self.navigation.to_dict()
        state.update(
            {
                "camera_preset": self.camera_preset,
                "display_mode": self.display_mode,
                "selection_mode": self.selection_mode,
                "transform_mode": self.transform_mode,
                "gizmo_orientation": self.gizmo_orientation,
                "gizmo_pivot": self.gizmo_pivot,
                "view_cube_visible": self.view_cube_visible,
            }
        )
        return state

    def diagnostics(self) -> dict[str, object]:
        previews = [(obj, self._preview_for(obj.path)) for obj in self.objects]
        valid = [(obj, mesh) for obj, mesh in previews if isinstance(mesh, MeshPreview)]
        errors = [str(mesh) for _obj, mesh in previews if isinstance(mesh, Exception)]
        vertex_count = sum(len(mesh.vertices) for _obj, mesh in valid)
        face_count = sum(len(mesh.faces) for _obj, mesh in valid)
        edge_count = sum(len(mesh.edges) for _obj, mesh in valid)
        selection_counts = {
            "objects": len(self.selected_object_ids),
            "vertices": len(self.selected_vertices),
            "edges": len(self.selected_edges),
            "faces": len(self.selected_faces),
            "borders": len(self.selected_borders),
            "elements": len(self.selected_elements),
        }
        return {
            "backend_id": "cpu_projected",
            "renderer_name": "CPU Projected Viewport",
            "available": True,
            "diagnostic_only": False,
            "supports_scene_meshes": True,
            "supports_grid": True,
            "supports_overlays": True,
            "supports_object_picking": True,
            "supports_frame_selected": True,
            "supports_subobject_selection": True,
            "supports_gizmo_drawing": True,
            "supports_gizmo_interaction": True,
            "supports_gizmo_plane_handles": True,
            "supports_projection_modes": True,
            "supports_perspective_projection": True,
            "supports_orthographic_projection": True,
            "object_count": len(self.objects),
            "mesh_count": len(valid),
            "vertex_count": int(vertex_count),
            "edge_count": int(edge_count),
            "face_count": int(face_count),
            "cache_error_count": len(errors),
            "cache_errors": errors[:5],
            "display_mode": self.display_mode,
            "selection_mode": self.selection_mode,
            "transform_mode": self.transform_mode,
            "gizmo_orientation": self.gizmo_orientation,
            "gizmo_pivot": self.gizmo_pivot,
            "camera_preset": self.camera_preset,
            "projection_mode": self.navigation.projection_mode,
            "projection_mode_label": viewport_projection_label(self.navigation.projection_mode),
            "navigation_profile": self.navigation.profile,
            "navigation_profile_label": viewport_profile_label(self.navigation.profile),
            "transform_gizmo_visible": bool(self.transform_gizmo_handles()),
            "active_gizmo_axis": self._active_gizmo_axis,
            "zoom": float(self.navigation.zoom),
            "grid_visible": bool(self.navigation.grid_visible),
            "snap_enabled": bool(self.navigation.snap_enabled),
            "view_cube_visible": bool(self.view_cube_visible),
            "frame_selection_available": self._selected_projected_points() is not None,
            "active_object_id": self.active_object_id or "",
            "selection_counts": selection_counts,
            "canvas_size": (int(self.width()), int(self.height())),
        }

    def restore_navigation_state(self, payload: dict[str, object] | None) -> None:
        data = payload or {}
        state = ViewportNavigationState.from_dict(data)
        self.navigation = state
        self.set_selection_mode(str(data.get("selection_mode") or self.selection_mode))
        self.set_transform_mode(str(data.get("transform_mode") or self.transform_mode))
        self.set_gizmo_orientation(data.get("gizmo_orientation") or self.gizmo_orientation)
        self.set_gizmo_pivot(data.get("gizmo_pivot") or self.gizmo_pivot)
        self.set_display_mode(str(data.get("display_mode") or self.display_mode))
        self.set_camera_preset(str(data.get("camera_preset") or state.camera_preset))
        self.set_projection_mode(state.projection_mode)
        self.set_grid_visible(state.grid_visible)
        self.set_snap_enabled(state.snap_enabled)
        self.set_view_cube_visible(bool(data.get("view_cube_visible", self.view_cube_visible)))
        self.set_navigation_profile(state.profile)
        self._emit_navigation_state_changed()

    def _navigation_key_command(
        self,
        key: int,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> str:
        alt = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.AltModifier)
        shift = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ShiftModifier)
        ctrl = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ControlModifier)
        profile = normalize_viewport_navigation_profile(self.navigation.profile)
        if key == QtCore.Qt.Key.Key_R:
            return "reset_camera"
        if key == QtCore.Qt.Key.Key_Period and not modifiers:
            return "frame_selected"
        if key == QtCore.Qt.Key.Key_W:
            return "toggle_wireframe"
        if key == QtCore.Qt.Key.Key_G and (alt or not modifiers):
            return "toggle_grid"
        if key == QtCore.Qt.Key.Key_F:
            if profile == "3dsmax" and shift:
                return "camera:front"
            return "frame_all"
        if profile == "maya" and key == QtCore.Qt.Key.Key_A and not modifiers:
            return "frame_all"
        if profile == "blender":
            if key == QtCore.Qt.Key.Key_Home:
                return "frame_all"
            if key == QtCore.Qt.Key.Key_1:
                return "camera:back" if ctrl else "camera:front"
            if key == QtCore.Qt.Key.Key_3:
                return "camera:left" if ctrl else "camera:right"
            if key == QtCore.Qt.Key.Key_7:
                return "camera:bottom" if ctrl else "camera:top"
            if key == QtCore.Qt.Key.Key_5 and not modifiers:
                return "toggle_projection"
        if profile == "3dsmax":
            if key == QtCore.Qt.Key.Key_Z and not modifiers:
                return "frame_all"
            if shift and key == QtCore.Qt.Key.Key_T:
                return "camera:top"
            if shift and key == QtCore.Qt.Key.Key_L:
                return "camera:left"
            if shift and key == QtCore.Qt.Key.Key_P:
                return "camera:perspective"
        return ""

    def _emit_navigation_state_changed(self) -> None:
        self.navigationStateChanged.emit(self.navigation_state())

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        painter.fillRect(rect, QtGui.QColor(self.theme.color("viewport.bg")))
        if self.navigation.grid_visible:
            self._draw_grid(painter, rect)
        self._draw_axes(painter, rect)
        self._draw_meshes(painter, rect)
        self._draw_transform_gizmo(painter)
        self._draw_overlay(painter, rect)
        if self.view_cube_visible:
            self._draw_view_cube(painter, rect)
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
            f"{self.camera_preset.upper()} {self.navigation.projection_mode.upper()} | {self.display_mode.upper()} | "
            f"{self.selection_mode.upper()} | {self.transform_mode.upper()}"
        )
        painter.drawText(14, 24, header)
        nav = f"NAV {self.navigation.profile.upper()} | ZOOM {self.navigation.zoom:.2f}x"
        painter.setPen(QtGui.QColor(self.theme.color("text.secondary")))
        painter.drawText(max(14, rect.width() - 250), 24, nav)
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
        scale = min(rect.width(), rect.height()) * 0.62 * self.navigation.zoom / scene_extent
        center = rect.center() + QtCore.QPoint(int(self.navigation.pan_x), int(self.navigation.pan_y))
        out: list[ProjectedViewportObject] = []
        for obj, mesh in valid:
            points = _apply_transform(mesh.vertices - scene_center, obj.transform)
            projected, depth = _project(
                points,
                self.camera_preset,
                center,
                scale,
                yaw_deg=self.navigation.orbit_yaw_deg,
                pitch_deg=self.navigation.orbit_pitch_deg,
                projection_mode=self.navigation.projection_mode,
                scene_extent=scene_extent,
            )
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

    def transform_gizmo_handles(self) -> dict[str, TransformGizmoHandle]:
        if self.transform_mode not in {"move", "rotate", "scale"}:
            return {}
        active_id = self.active_object_id or next(iter(self.selected_object_ids), "")
        if not active_id:
            return {}
        frame = self.projected_objects()
        active_item = next((item for item in frame if item.obj.object_id == active_id), None)
        if active_item is None or active_item.projected.size == 0:
            return {}
        anchor = self._gizmo_anchor(active_item)
        context = self._projection_context()
        pixels_per_unit = max(1.0, context[2] if context is not None else 60.0)
        world_basis = self._gizmo_world_basis(active_item.obj.transform)
        directions = self._gizmo_axis_screen_directions(world_basis)
        length = 66.0
        handles: dict[str, TransformGizmoHandle] = {}
        for axis, direction in directions.items():
            handles[axis] = TransformGizmoHandle(
                axis=axis,
                start=anchor,
                end=(anchor[0] + direction[0] * length, anchor[1] + direction[1] * length),
                pixels_per_unit=pixels_per_unit,
                basis=((axis, direction),),
                world_basis=((axis, tuple(float(v) for v in world_basis[axis])),),
                hit_radius=10.0,
            )
        if self.transform_mode == "move":
            plane_distance = 24.0
            for plane_axis, axis_a, axis_b in (("xy", "x", "y"), ("xz", "x", "z"), ("yz", "y", "z")):
                dir_a = directions[axis_a]
                dir_b = directions[axis_b]
                center = (
                    anchor[0] + (dir_a[0] + dir_b[0]) * plane_distance,
                    anchor[1] + (dir_a[1] + dir_b[1]) * plane_distance,
                )
                handles[plane_axis] = TransformGizmoHandle(
                    axis=plane_axis,
                    start=anchor,
                    end=center,
                    pixels_per_unit=pixels_per_unit,
                    kind="plane",
                    basis=((axis_a, dir_a), (axis_b, dir_b)),
                    world_basis=(
                        (axis_a, tuple(float(v) for v in world_basis[axis_a])),
                        (axis_b, tuple(float(v) for v in world_basis[axis_b])),
                    ),
                    hit_radius=11.0,
                )
        return handles

    def transform_gizmo_handle_at(self, point, *, threshold: float = 10.0) -> TransformGizmoHandle | None:  # type: ignore[no-untyped-def]
        target = (float(point.x()), float(point.y())) if hasattr(point, "x") else (float(point[0]), float(point[1]))
        candidates = [
            (handle_distance_to_point(handle, target), handle)
            for handle in self.transform_gizmo_handles().values()
        ]
        if not candidates:
            return None
        distance, handle = min(candidates, key=lambda item: item[0])
        return handle if distance <= threshold else None

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

    def _viewport_object_by_id(self, object_id: str) -> ViewportObject | None:
        for obj in self.objects:
            if obj.object_id == object_id:
                return obj
        return None

    def _projection_context(self) -> tuple[np.ndarray, np.ndarray, float, float] | None:
        rect = self.rect()
        if not self.objects or rect.width() <= 0 or rect.height() <= 0:
            return None
        previews = [(obj, self._preview_for(obj.path)) for obj in self.objects]
        valid = [(obj, mesh) for obj, mesh in previews if isinstance(mesh, MeshPreview)]
        if not valid:
            return None
        scene_min, scene_max = _scene_bounds(valid)
        scene_extent = float(np.max(scene_max - scene_min)) or 1.0
        scale = min(rect.width(), rect.height()) * 0.62 * self.navigation.zoom / scene_extent
        return scene_min, scene_max, float(scale), scene_extent

    def _gizmo_anchor(self, active_item: ProjectedViewportObject) -> tuple[float, float]:
        if self.gizmo_pivot == "object_origin":
            context = self._projection_context()
            if context is not None:
                rect = self.rect()
                center = rect.center() + QtCore.QPoint(int(self.navigation.pan_x), int(self.navigation.pan_y))
                scale = context[2]
                scene_extent = context[3]
                origin = _apply_transform(np.zeros((1, 3), dtype=float), active_item.obj.transform)
                projected, _depth = _project(
                    origin,
                    self.camera_preset,
                    center,
                    scale,
                    yaw_deg=self.navigation.orbit_yaw_deg,
                    pitch_deg=self.navigation.orbit_pitch_deg,
                    projection_mode=self.navigation.projection_mode,
                    scene_extent=scene_extent,
                )
                if projected.size:
                    return (float(projected[0, 0]), float(projected[0, 1]))
        mins = active_item.projected.min(axis=0)
        maxes = active_item.projected.max(axis=0)
        return ((float(mins[0]) + float(maxes[0])) * 0.5, (float(mins[1]) + float(maxes[1])) * 0.5)

    def _gizmo_world_basis(self, transform) -> dict[str, np.ndarray]:  # type: ignore[no-untyped-def]
        basis = {
            "x": np.array([1.0, 0.0, 0.0], dtype=float),
            "y": np.array([0.0, 1.0, 0.0], dtype=float),
            "z": np.array([0.0, 0.0, 1.0], dtype=float),
        }
        if self.gizmo_orientation != "local":
            return basis
        rx, ry, rz = [math.radians(v) for v in transform.rotate_euler_deg]
        rotation = _rot_x(rx).T @ _rot_y(ry).T @ _rot_z(rz).T
        return {axis: vector @ rotation for axis, vector in basis.items()}

    def _gizmo_axis_screen_directions(
        self,
        basis: dict[str, np.ndarray] | None = None,
    ) -> dict[str, tuple[float, float]]:
        context = self._projection_context()
        scale = context[2] if context is not None else 80.0
        scene_extent = context[3] if context is not None else 1.0
        basis = basis or {
            "x": np.array([1.0, 0.0, 0.0], dtype=float),
            "y": np.array([0.0, 1.0, 0.0], dtype=float),
            "z": np.array([0.0, 0.0, 1.0], dtype=float),
        }
        fallback = {
            "x": (1.0, 0.0),
            "y": (0.0, -1.0),
            "z": (-0.72, 0.72),
        }
        directions: dict[str, tuple[float, float]] = {}
        center = QtCore.QPoint(0, 0)
        length = max(0.25, scene_extent * 0.25)
        for axis, vec in basis.items():
            projected, _depth = _project(
                np.vstack((np.zeros(3, dtype=float), vec * length)),
                self.camera_preset,
                center,
                scale,
                yaw_deg=self.navigation.orbit_yaw_deg,
                pitch_deg=self.navigation.orbit_pitch_deg,
                projection_mode=self.navigation.projection_mode,
                scene_extent=scene_extent,
            )
            delta = projected[1] - projected[0]
            norm = float(np.linalg.norm(delta))
            if norm <= 1e-6:
                directions[axis] = fallback[axis]
            else:
                directions[axis] = (float(delta[0] / norm), float(delta[1] / norm))
        return directions

    def set_navigation_profile(self, profile: object) -> None:
        key = normalize_viewport_navigation_profile(profile)
        changed = self.navigation.profile != key
        self.navigation.profile = key
        self.update()
        if changed:
            self.navigationProfileChanged.emit(key)
            self._emit_navigation_state_changed()

    def set_projection_mode(self, mode: object) -> None:
        key = normalize_viewport_projection_mode(mode)
        changed = self.navigation.projection_mode != key
        self.navigation.projection_mode = key
        self.update()
        if changed:
            self.projectionModeChanged.emit(key)
            self._emit_navigation_state_changed()

    def set_grid_visible(self, visible: bool) -> None:
        value = bool(visible)
        changed = self.navigation.grid_visible != value
        self.navigation.grid_visible = value
        self.update()
        if changed:
            self.gridVisibilityChanged.emit(value)
            self._emit_navigation_state_changed()

    def set_snap_enabled(self, enabled: bool) -> None:
        value = bool(enabled)
        changed = self.navigation.snap_enabled != value
        self.navigation.snap_enabled = value
        self.update()
        if changed:
            self.snapChanged.emit(value)
            self._emit_navigation_state_changed()

    def set_view_cube_visible(self, visible: bool) -> None:
        value = bool(visible)
        changed = self.view_cube_visible != value
        self.view_cube_visible = value
        self.update()
        if changed:
            self.viewCubeVisibilityChanged.emit(value)
            self._emit_navigation_state_changed()

    def set_camera_preset(self, preset: str) -> None:
        value = str(preset or "").strip().lower()
        aliases = {
            "side": "right",
            "persp": "perspective",
        }
        value = aliases.get(value, value)
        if value not in {*FACE_PRESETS, "perspective"}:
            value = "perspective"
        self.camera_preset = value
        self.navigation.camera_preset = value
        if value == "perspective":
            self.navigation.orbit_yaw_deg = self.navigation.orbit_yaw_deg or -32.0
            self.navigation.orbit_pitch_deg = self.navigation.orbit_pitch_deg or 22.0
        self.update()
        self.cameraPresetChanged.emit(value)
        self._emit_navigation_state_changed()

    def reset_camera(self) -> None:
        self.navigation.reset()
        self.set_camera_preset("perspective")
        self.update()

    def frame_all(self) -> None:
        self.navigation.pan_x = 0.0
        self.navigation.pan_y = 0.0
        self.navigation.zoom = 1.0
        self.update()
        self._emit_navigation_state_changed()

    def frame_selected(self) -> bool:
        points = self._selected_projected_points()
        if points is None:
            self.frame_all()
            return False
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        mins = points.min(axis=0)
        maxes = points.max(axis=0)
        width = max(1.0, float(maxes[0] - mins[0]))
        height = max(1.0, float(maxes[1] - mins[1]))
        target_ratio = min(rect.width() * 0.62 / width, rect.height() * 0.62 / height)
        if not math.isfinite(target_ratio) or target_ratio <= 0:
            return False
        self.navigation.zoom = clamp_viewport_zoom(self.navigation.zoom * target_ratio)
        points = self._selected_projected_points()
        if points is None:
            return False
        mins = points.min(axis=0)
        maxes = points.max(axis=0)
        selection_center = (mins + maxes) * 0.5
        viewport_center = np.array([float(rect.center().x()), float(rect.center().y())], dtype=float)
        delta = viewport_center - selection_center
        self.navigation.pan_x += float(delta[0])
        self.navigation.pan_y += float(delta[1])
        self.update()
        self._emit_navigation_state_changed()
        return True

    def _selected_projected_points(self, rect: QtCore.QRect | None = None) -> np.ndarray | None:
        frame = self.projected_objects(rect)
        if not frame:
            return None
        active_id = self.active_object_id or next(iter(self.selected_object_ids), "")
        object_ids = set(self.selected_object_ids)
        if active_id:
            object_ids.add(active_id)
        if not object_ids:
            return None
        has_subselection = any(
            (
                self.selected_vertices,
                self.selected_edges,
                self.selected_faces,
                self.selected_borders,
                self.selected_elements,
            )
        )
        point_sets: list[np.ndarray] = []
        for item in frame:
            if item.obj.object_id == active_id and has_subselection:
                sub_points = self._subselection_projected_points(item)
                if sub_points is not None:
                    point_sets.append(sub_points)
                    continue
            if item.obj.object_id in object_ids and item.projected.size:
                point_sets.append(item.projected)
        if not point_sets and active_id:
            active_item = next((item for item in frame if item.obj.object_id == active_id), None)
            if active_item is not None and active_item.projected.size:
                point_sets.append(active_item.projected)
        if not point_sets:
            return None
        return np.vstack(point_sets)

    def _subselection_projected_points(self, item: ProjectedViewportObject) -> np.ndarray | None:
        point_sets: list[np.ndarray] = []
        if self.selected_vertices:
            indices = [idx for idx in self.selected_vertices if 0 <= idx < len(item.projected)]
            if indices:
                point_sets.append(item.projected[indices])
        edge_pairs = set(self.selected_edges)
        for edge_index in self.selected_borders:
            if 0 <= edge_index < len(item.mesh.edges):
                a, b = item.mesh.edges[edge_index]
                edge_pairs.add(tuple(sorted((int(a), int(b)))))
        edge_indices: set[int] = set()
        for a, b in edge_pairs:
            if 0 <= a < len(item.projected):
                edge_indices.add(int(a))
            if 0 <= b < len(item.projected):
                edge_indices.add(int(b))
        if edge_indices:
            point_sets.append(item.projected[sorted(edge_indices)])
        face_indices = set(self.selected_faces) | set(self.selected_elements)
        vertex_indices: set[int] = set()
        for face_index in face_indices:
            if 0 <= face_index < len(item.mesh.faces):
                vertex_indices.update(int(index) for index in item.mesh.faces[face_index])
        if vertex_indices:
            point_sets.append(item.projected[sorted(vertex_indices)])
        if not point_sets:
            return None
        return np.vstack(point_sets)

    def _navigation_action(
        self,
        button: QtCore.Qt.MouseButton,
        modifiers: QtCore.Qt.KeyboardModifiers,
    ) -> str:
        profile = normalize_viewport_navigation_profile(self.navigation.profile)
        alt = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.AltModifier)
        shift = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ShiftModifier)
        ctrl = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ControlModifier)
        if profile == "maya":
            if alt and button == QtCore.Qt.MouseButton.LeftButton:
                return "orbit"
            if alt and button == QtCore.Qt.MouseButton.MiddleButton:
                return "pan"
            if alt and button == QtCore.Qt.MouseButton.RightButton:
                return "zoom"
        elif profile == "blender":
            if button == QtCore.Qt.MouseButton.MiddleButton and shift:
                return "pan"
            if button == QtCore.Qt.MouseButton.MiddleButton and ctrl:
                return "zoom"
            if button == QtCore.Qt.MouseButton.MiddleButton:
                return "orbit"
        elif profile == "3dsmax":
            if alt and button == QtCore.Qt.MouseButton.MiddleButton:
                return "orbit"
            if button == QtCore.Qt.MouseButton.MiddleButton:
                return "pan"
            if alt and button == QtCore.Qt.MouseButton.RightButton:
                return "zoom"
        return ""

    def view_cube_region_at(self, point) -> ViewCubeRegion | None:  # type: ignore[no-untyped-def]
        if not self.view_cube_visible:
            return None
        return hit_test_view_cube(_pointf(point), self.rect())

    def activate_view_cube_region(self, key: str) -> None:
        if key == "home":
            self.reset_camera()
            self.frame_all()
            return
        if key == "perspective":
            self.set_projection_mode("perspective")
            self.set_camera_preset("perspective")
            return
        if key in FACE_PRESETS:
            self.set_camera_preset(key)

    def _draw_view_cube(self, painter: QtGui.QPainter, rect: QtCore.QRect) -> None:
        panel = view_cube_panel_rect(rect)
        regions = view_cube_regions(panel)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        panel_bg = QtGui.QColor(self.theme.color("panel.alt"))
        panel_bg.setAlpha(176)
        painter.setPen(QtGui.QPen(QtGui.QColor(self.theme.color("panel.border")), 1))
        painter.setBrush(panel_bg)
        painter.drawRoundedRect(panel, 7, 7)

        line = QtGui.QColor(self.theme.color("text.secondary"))
        accent = QtGui.QColor(self.theme.color("accent.primary"))
        face = QtGui.QColor(self.theme.color("button.bg"))
        active = QtGui.QColor(self.theme.color("button.checked"))
        for key in ("top", "left", "front", "right", "bottom", "home", "back", "perspective"):
            region = regions[key]
            fill = QtGui.QColor(active if key == self.camera_preset else face)
            if key in {"home", "perspective"}:
                fill = QtGui.QColor(self.theme.color("panel.bg"))
            if key == "perspective" and self.camera_preset == "perspective":
                fill = QtGui.QColor(active)
            painter.setPen(QtGui.QPen(accent if key == self.camera_preset else line, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(region.rect, 4, 4)
            painter.setPen(QtGui.QColor(self.theme.color("text.primary")))
            font = painter.font()
            font.setPointSize(7 if key not in {"front", "perspective"} else 6)
            font.setBold(key in {"front", self.camera_preset})
            painter.setFont(font)
            painter.drawText(region.rect, QtCore.Qt.AlignmentFlag.AlignCenter, region.label)

        painter.setPen(QtGui.QPen(line, 1))
        painter.drawLine(regions["top"].rect.center(), regions["front"].rect.center())
        painter.drawLine(regions["front"].rect.center(), regions["right"].rect.center())
        painter.drawLine(regions["front"].rect.center(), regions["left"].rect.center())
        painter.drawLine(regions["front"].rect.center(), regions["bottom"].rect.center())
        painter.restore()

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

    def _draw_transform_gizmo(self, painter: QtGui.QPainter) -> None:
        handles = self.transform_gizmo_handles()
        if not handles:
            return
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        ordered_handles = [
            *[(axis, handle) for axis, handle in handles.items() if handle.kind == "plane"],
            *[(axis, handle) for axis, handle in handles.items() if handle.kind != "plane"],
        ]
        for axis, handle in ordered_handles:
            color = QtGui.QColor(handle.color)
            if axis == self._active_gizmo_axis:
                color = color.lighter(145)
            start = QtCore.QPointF(float(handle.start[0]), float(handle.start[1]))
            end = QtCore.QPointF(float(handle.end[0]), float(handle.end[1]))
            if handle.kind == "plane":
                fill = QtGui.QColor(color)
                fill.setAlpha(80 if axis != self._active_gizmo_axis else 130)
                painter.setBrush(QtGui.QBrush(fill))
                painter.setPen(QtGui.QPen(color, 2 if axis == self._active_gizmo_axis else 1))
                radius = float(handle.hit_radius)
                painter.drawRect(QtCore.QRectF(end.x() - radius, end.y() - radius, radius * 2, radius * 2))
                painter.setPen(QtGui.QPen(QtGui.QColor(self.theme.color("viewport.bg")), 1))
                painter.setFont(QtGui.QFont("Segoe UI", 7, QtGui.QFont.Weight.Bold))
                painter.drawText(
                    QtCore.QRectF(end.x() - radius, end.y() - radius, radius * 2, radius * 2),
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                    handle.label,
                )
                continue
            painter.setPen(QtGui.QPen(color, 4 if axis == self._active_gizmo_axis else 3))
            painter.drawLine(start, end)
            painter.setBrush(QtGui.QBrush(color))
            if self.transform_mode == "scale":
                painter.drawRect(QtCore.QRectF(end.x() - 5, end.y() - 5, 10, 10))
            else:
                painter.drawEllipse(end, 5.5, 5.5)
            painter.setPen(QtGui.QPen(QtGui.QColor(self.theme.color("viewport.bg")), 1))
            painter.setFont(QtGui.QFont("Segoe UI", 8, QtGui.QFont.Weight.Bold))
            label_rect = QtCore.QRectF(end.x() - 9, end.y() - 9, 18, 18)
            painter.drawText(label_rect, QtCore.Qt.AlignmentFlag.AlignCenter, handle.label)
        painter.restore()

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
    cameraPresetChanged = QtCore.Signal(str)
    displayModeChanged = QtCore.Signal(str)
    navigationProfileChanged = QtCore.Signal(str)
    projectionModeChanged = QtCore.Signal(str)
    gridVisibilityChanged = QtCore.Signal(bool)
    snapChanged = QtCore.Signal(bool)
    viewCubeVisibilityChanged = QtCore.Signal(bool)
    gizmoOrientationChanged = QtCore.Signal(str)
    gizmoPivotChanged = QtCore.Signal(str)
    navigationStateChanged = QtCore.Signal(object)
    transformEdited = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.canvas = ViewportCanvas()
        self.canvas.itemPicked.connect(self.itemPicked.emit)
        self.canvas.cameraPresetChanged.connect(self.cameraPresetChanged.emit)
        self.canvas.displayModeChanged.connect(self.displayModeChanged.emit)
        self.canvas.navigationProfileChanged.connect(self.navigationProfileChanged.emit)
        self.canvas.projectionModeChanged.connect(self.projectionModeChanged.emit)
        self.canvas.gridVisibilityChanged.connect(self.gridVisibilityChanged.emit)
        self.canvas.snapChanged.connect(self.snapChanged.emit)
        self.canvas.viewCubeVisibilityChanged.connect(self.viewCubeVisibilityChanged.emit)
        self.canvas.gizmoOrientationChanged.connect(self.gizmoOrientationChanged.emit)
        self.canvas.gizmoPivotChanged.connect(self.gizmoPivotChanged.emit)
        self.canvas.navigationStateChanged.connect(self.navigationStateChanged.emit)
        self.canvas.transformEdited.connect(self.transformEdited.emit)

    def widget(self) -> QtWidgets.QWidget:
        return self.canvas

    def set_objects(self, objects: list[ViewportObject]) -> None:
        self.canvas.set_objects(objects)

    def set_selection_state(self, **state) -> None:  # type: ignore[no-untyped-def]
        self.canvas.set_selection_state(**state)

    def set_display_mode(self, mode: str) -> None:
        self.canvas.set_display_mode(mode)

    def set_selection_mode(self, mode: str) -> None:
        self.canvas.set_selection_mode(mode)

    def set_transform_mode(self, mode: str) -> None:
        self.canvas.set_transform_mode(mode)

    def set_gizmo_orientation(self, orientation: object) -> None:
        self.canvas.set_gizmo_orientation(orientation)

    def set_gizmo_pivot(self, pivot: object) -> None:
        self.canvas.set_gizmo_pivot(pivot)

    def set_camera_preset(self, preset: str) -> None:
        self.canvas.set_camera_preset(preset)

    def set_navigation_profile(self, profile: object) -> None:
        self.canvas.set_navigation_profile(profile)

    def set_projection_mode(self, mode: object) -> None:
        self.canvas.set_projection_mode(mode)

    def set_grid_visible(self, visible: bool) -> None:
        self.canvas.set_grid_visible(visible)

    def set_snap_enabled(self, enabled: bool) -> None:
        self.canvas.set_snap_enabled(enabled)

    def set_view_cube_visible(self, visible: bool) -> None:
        self.canvas.set_view_cube_visible(visible)

    def set_theme(self, theme: Theme) -> None:
        self.canvas.set_theme(theme)

    def frame_all(self) -> None:
        self.canvas.frame_all()

    def frame_selected(self) -> bool:
        return self.canvas.frame_selected()

    def reset_camera(self) -> None:
        self.canvas.reset_camera()

    def navigation_state(self) -> dict[str, object]:
        return self.canvas.navigation_state()

    def restore_navigation_state(self, payload: dict[str, object] | None) -> None:
        self.canvas.restore_navigation_state(payload)

    def diagnostics(self) -> dict[str, object]:
        return self.canvas.diagnostics()


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


def _pointf(point) -> QtCore.QPointF:  # type: ignore[no-untyped-def]
    if isinstance(point, QtCore.QPointF):
        return point
    if isinstance(point, QtCore.QPoint):
        return QtCore.QPointF(point)
    if hasattr(point, "x") and hasattr(point, "y"):
        return QtCore.QPointF(float(point.x()), float(point.y()))
    return QtCore.QPointF(float(point[0]), float(point[1]))


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


def _project(
    vertices: np.ndarray,
    preset: str,
    center: QtCore.QPoint,
    scale: float,
    *,
    yaw_deg: float = -32.0,
    pitch_deg: float = 22.0,
    projection_mode: str = "perspective",
    scene_extent: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    if preset == "front":
        x, y, depth = vertices[:, 0], vertices[:, 1], vertices[:, 2]
    elif preset == "back":
        x, y, depth = -vertices[:, 0], vertices[:, 1], -vertices[:, 2]
    elif preset in {"side", "right"}:
        x, y, depth = vertices[:, 2], vertices[:, 1], vertices[:, 0]
    elif preset == "left":
        x, y, depth = -vertices[:, 2], vertices[:, 1], -vertices[:, 0]
    elif preset == "top":
        x, y, depth = vertices[:, 0], vertices[:, 2], vertices[:, 1]
    elif preset == "bottom":
        x, y, depth = vertices[:, 0], -vertices[:, 2], -vertices[:, 1]
    else:
        yaw = math.radians(yaw_deg)
        pitch = math.radians(pitch_deg)
        view = vertices @ _rot_y(yaw).T @ _rot_x(pitch).T
        x = view[:, 0]
        y = view[:, 1]
        depth = view[:, 2]
        if normalize_viewport_projection_mode(projection_mode) == "perspective":
            focal = max(float(scene_extent) * 3.0, 1.0)
            near = max(float(scene_extent) * 0.2, 0.2)
            divisor = np.maximum(near, focal - depth)
            perspective = focal / divisor
            x = x * perspective
            y = y * perspective
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
