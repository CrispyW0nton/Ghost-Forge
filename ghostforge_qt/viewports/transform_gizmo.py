from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

from ghostforge_qt.models.scene_model import TransformState


AXIS_COMPONENTS: Mapping[str, int] = {"x": 0, "y": 1, "z": 2}
AXIS_WORLD_VECTORS: Mapping[str, tuple[float, float, float]] = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}
AXIS_LABELS: Mapping[str, str] = {"x": "X", "y": "Y", "z": "Z", "xy": "XY", "xz": "XZ", "yz": "YZ"}
AXIS_COLORS: Mapping[str, str] = {
    "x": "#d64b55",
    "y": "#55d47a",
    "z": "#4bb9ff",
    "xy": "#d9c44f",
    "xz": "#4fd4d9",
    "yz": "#d94fd2",
}
GIZMO_ORIENTATIONS: Mapping[str, str] = {"world": "World", "local": "Local"}
GIZMO_PIVOTS: Mapping[str, str] = {"bounds_center": "Bounds Center", "object_origin": "Object Origin"}


@dataclass(frozen=True)
class TransformGizmoHandle:
    axis: str
    start: tuple[float, float]
    end: tuple[float, float]
    pixels_per_unit: float
    kind: str = "axis"
    basis: tuple[tuple[str, tuple[float, float]], ...] = ()
    world_basis: tuple[tuple[str, tuple[float, float, float]], ...] = ()
    hit_radius: float = 10.0

    @property
    def label(self) -> str:
        return AXIS_LABELS.get(normalize_gizmo_axis(self.axis), str(self.axis).upper())

    @property
    def color(self) -> str:
        return AXIS_COLORS.get(normalize_gizmo_axis(self.axis), "#f4d35e")


@dataclass(frozen=True)
class TransformGizmoDragOrigin:
    object_id: str
    mode: str
    axis: str
    start_mouse: tuple[float, float]
    handle: TransformGizmoHandle
    start_transform: TransformState


@dataclass(frozen=True)
class TransformGizmoEdit:
    object_id: str
    mode: str
    axis: str
    transform: TransformState
    scalar_delta: float
    phase: str = "update"
    before_transform: TransformState | None = None


def normalize_gizmo_axis(value: object) -> str:
    text = str(value or "").strip().lower()
    axes = "".join(axis for axis in "xyz" if axis in text)
    return axes if axes else "x"


def normalize_gizmo_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in {"move", "rotate", "scale"} else "move"


def normalize_gizmo_orientation(value: object) -> str:
    key = str(value or "").strip().lower().replace(" ", "_")
    return key if key in GIZMO_ORIENTATIONS else "world"


def normalize_gizmo_pivot(value: object) -> str:
    key = str(value or "").strip().lower().replace(" ", "_")
    aliases = {
        "bounds": "bounds_center",
        "center": "bounds_center",
        "origin": "object_origin",
        "object": "object_origin",
    }
    key = aliases.get(key, key)
    return key if key in GIZMO_PIVOTS else "bounds_center"


def transform_gizmo_edit_from_drag(
    origin: TransformGizmoDragOrigin,
    current_mouse: tuple[float, float],
    *,
    snap: bool = False,
    phase: str = "update",
) -> TransformGizmoEdit:
    mode = normalize_gizmo_mode(origin.mode)
    axis = normalize_gizmo_axis(origin.axis)
    components = projected_axis_pixel_deltas(origin.handle, origin.start_mouse, current_mouse)
    if mode == "move":
        unit_deltas: dict[str, float] = {}
        for component_axis, pixel_delta in components.items():
            scalar = pixel_delta / max(1e-6, float(origin.handle.pixels_per_unit))
            unit_deltas[component_axis] = _snap(scalar, 0.25) if snap else scalar
        transform = _translate_axes(origin.start_transform, origin.handle, unit_deltas)
        values = list(unit_deltas.values())
        scalar_delta = values[0] if len(values) == 1 else math.sqrt(sum(delta * delta for delta in values))
    elif mode == "rotate":
        primary_axis = _primary_axis(axis)
        scalar_delta = components.get(primary_axis, next(iter(components.values()), 0.0)) * 0.5
        if snap:
            scalar_delta = _snap(scalar_delta, 5.0)
        transform = _rotate_axis(origin.start_transform, primary_axis, scalar_delta)
    else:
        primary_axis = _primary_axis(axis)
        scalar_delta = components.get(primary_axis, next(iter(components.values()), 0.0)) * 0.01
        transform = _scale_axis(origin.start_transform, primary_axis, scalar_delta, snap=snap)
    return TransformGizmoEdit(
        object_id=origin.object_id,
        mode=mode,
        axis=axis,
        transform=transform,
        scalar_delta=float(scalar_delta),
        phase=normalize_gizmo_edit_phase(phase),
        before_transform=origin.start_transform,
    )


def normalize_gizmo_edit_phase(value: object) -> str:
    phase = str(value or "").strip().lower()
    return phase if phase in {"begin", "update", "end", "cancel"} else "update"


def projected_axis_pixel_deltas(
    handle: TransformGizmoHandle,
    start_mouse: tuple[float, float],
    current_mouse: tuple[float, float],
) -> dict[str, float]:
    sx, sy = start_mouse
    cx, cy = current_mouse
    dx = float(cx) - float(sx)
    dy = float(cy) - float(sy)
    basis = _normalized_screen_basis(handle)
    if len(basis) >= 2:
        axis_a, vec_a = basis[0]
        axis_b, vec_b = basis[1]
        ax, ay = vec_a
        bx, by = vec_b
        det = ax * by - ay * bx
        if abs(det) > 1e-6 and math.isfinite(det):
            return {
                axis_a: (dx * by - dy * bx) / det,
                axis_b: (ax * dy - ay * dx) / det,
            }
    if basis:
        return {axis: dx * vec[0] + dy * vec[1] for axis, vec in basis}
    return {_primary_axis(handle.axis): projected_pixel_delta(handle, start_mouse, current_mouse)}


def projected_pixel_delta(
    handle: TransformGizmoHandle,
    start_mouse: tuple[float, float],
    current_mouse: tuple[float, float],
) -> float:
    components = projected_axis_pixel_deltas(handle, start_mouse, current_mouse) if handle.basis else {}
    if components:
        return next(iter(components.values()))
    sx, sy = start_mouse
    cx, cy = current_mouse
    dx = float(cx) - float(sx)
    dy = float(cy) - float(sy)
    hx = float(handle.end[0]) - float(handle.start[0])
    hy = float(handle.end[1]) - float(handle.start[1])
    length = math.hypot(hx, hy)
    if length <= 1e-6 or not math.isfinite(length):
        return dx
    return (dx * hx + dy * hy) / length


def handle_distance_to_point(handle: TransformGizmoHandle, point: tuple[float, float]) -> float:
    px, py = point
    if str(handle.kind or "axis") == "plane":
        cx, cy = handle.end
        radius = max(4.0, float(handle.hit_radius))
        dx = max(abs(float(px) - float(cx)) - radius, 0.0)
        dy = max(abs(float(py) - float(cy)) - radius, 0.0)
        return math.hypot(dx, dy)
    ax, ay = handle.start
    bx, by = handle.end
    abx = bx - ax
    aby = by - ay
    length_squared = abx * abx + aby * aby
    if length_squared <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / length_squared))
    closest_x = ax + abx * t
    closest_y = ay + aby * t
    return math.hypot(px - closest_x, py - closest_y)


def _translate_axes(
    transform: TransformState,
    handle: TransformGizmoHandle,
    deltas: Mapping[str, float],
) -> TransformState:
    values = list(transform.translate)
    world_vectors = _world_basis(handle)
    for axis, delta in deltas.items():
        vector = world_vectors.get(axis, AXIS_WORLD_VECTORS.get(axis, (1.0, 0.0, 0.0)))
        for index in range(3):
            values[index] = float(values[index]) + float(vector[index]) * float(delta)
    return TransformState(
        translate=tuple(values),
        rotate_euler_deg=transform.rotate_euler_deg,
        scale=transform.scale,
    )


def _rotate_axis(transform: TransformState, axis: str, delta_deg: float) -> TransformState:
    values = list(transform.rotate_euler_deg)
    values[AXIS_COMPONENTS[axis]] = float(values[AXIS_COMPONENTS[axis]]) + float(delta_deg)
    return TransformState(
        translate=transform.translate,
        rotate_euler_deg=tuple(values),
        scale=transform.scale,
    )


def _scale_axis(transform: TransformState, axis: str, delta_factor: float, *, snap: bool) -> TransformState:
    values = list(transform.scale)
    index = AXIS_COMPONENTS[axis]
    factor = max(0.05, 1.0 + float(delta_factor))
    values[index] = max(0.001, float(values[index]) * factor)
    if snap:
        values[index] = max(0.001, _snap(values[index], 0.1))
    return TransformState(
        translate=transform.translate,
        rotate_euler_deg=transform.rotate_euler_deg,
        scale=tuple(values),
    )


def _snap(value: float, step: float) -> float:
    if step <= 0:
        return float(value)
    return round(float(value) / float(step)) * float(step)


def _normalized_screen_basis(handle: TransformGizmoHandle) -> tuple[tuple[str, tuple[float, float]], ...]:
    if handle.basis:
        raw = handle.basis
    else:
        hx = float(handle.end[0]) - float(handle.start[0])
        hy = float(handle.end[1]) - float(handle.start[1])
        raw = ((_primary_axis(handle.axis), (hx, hy)),)
    out: list[tuple[str, tuple[float, float]]] = []
    for axis, vector in raw:
        key = _primary_axis(axis)
        vx, vy = float(vector[0]), float(vector[1])
        length = math.hypot(vx, vy)
        if length <= 1e-6 or not math.isfinite(length):
            continue
        out.append((key, (vx / length, vy / length)))
    return tuple(out)


def _world_basis(handle: TransformGizmoHandle) -> dict[str, tuple[float, float, float]]:
    vectors: dict[str, tuple[float, float, float]] = {}
    for axis, vector in handle.world_basis:
        key = _primary_axis(axis)
        if len(vector) < 3:
            continue
        vx, vy, vz = float(vector[0]), float(vector[1]), float(vector[2])
        length = math.sqrt(vx * vx + vy * vy + vz * vz)
        if length <= 1e-9 or not math.isfinite(length):
            continue
        vectors[key] = (vx / length, vy / length, vz / length)
    return vectors


def _primary_axis(value: object) -> str:
    axis = normalize_gizmo_axis(value)
    return axis[0] if axis else "x"
