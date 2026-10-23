from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from PySide6 import QtCore

VIEWPORT_ZOOM_MIN = 0.12
VIEWPORT_ZOOM_MAX = 8.0

VIEWPORT_CAMERA_PRESETS: tuple[tuple[str, str, str, str], ...] = (
    ("Perspective", "perspective", "P", "Perspective view"),
    ("Front", "front", "F", "Front view"),
    ("Back", "back", "B", "Back view"),
    ("Left", "left", "L", "Left view"),
    ("Right", "right", "R", "Right view"),
    ("Top", "top", "T", "Top view"),
    ("Bottom", "bottom", "Bo", "Bottom view"),
)

VIEWPORT_PROJECTION_MODES: Mapping[str, str] = {
    "perspective": "Perspective",
    "orthographic": "Orthographic",
}


@dataclass(frozen=True)
class ViewportNavigationProfile:
    key: str
    label: str
    summary: str


VIEWPORT_NAVIGATION_PROFILES: Mapping[str, ViewportNavigationProfile] = {
    "maya": ViewportNavigationProfile(
        key="maya",
        label="Maya",
        summary="Alt+LMB orbit, Alt+MMB pan, Alt+RMB zoom, wheel zoom",
    ),
    "blender": ViewportNavigationProfile(
        key="blender",
        label="Blender",
        summary="MMB orbit, Shift+MMB pan, Ctrl+MMB zoom, wheel zoom",
    ),
    "3dsmax": ViewportNavigationProfile(
        key="3dsmax",
        label="3ds Max",
        summary="Alt+MMB orbit, MMB pan, Alt+RMB zoom, wheel zoom",
    ),
}

DEFAULT_VIEWPORT_NAVIGATION_PROFILE = "maya"

VIEWPORT_NAVIGATION_HELP = """Ghost Forge viewport navigation:

Always available:
F: Frame all
.: Frame selected
R: Reset camera
W: Toggle wireframe
G or Alt+G: Toggle grid
Mouse wheel: Zoom

Maya profile:
Alt+Left Mouse: Orbit
Alt+Middle Mouse: Pan
Alt+Right Mouse: Zoom
A or F: Frame all

Blender profile:
Middle Mouse: Orbit
Shift+Middle Mouse: Pan
Ctrl+Middle Mouse: Zoom
1 / Ctrl+1: Front / Back
3 / Ctrl+3: Right / Left
7 / Ctrl+7: Top / Bottom
5: Toggle perspective / orthographic projection
Home: Frame all

3ds Max profile:
Alt+Middle Mouse: Orbit
Middle Mouse: Pan
Alt+Right Mouse: Zoom
Shift+F: Front
Shift+T: Top
Shift+L: Left
Shift+P: Perspective
Z: Frame all
"""


@dataclass
class ViewportNavigationState:
    profile: str = DEFAULT_VIEWPORT_NAVIGATION_PROFILE
    camera_preset: str = "perspective"
    projection_mode: str = "perspective"
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    orbit_yaw_deg: float = -32.0
    orbit_pitch_deg: float = 22.0
    grid_visible: bool = True
    snap_enabled: bool = False

    def reset(self) -> None:
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self.orbit_yaw_deg = -32.0
        self.orbit_pitch_deg = 22.0

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": normalize_viewport_navigation_profile(self.profile),
            "camera_preset": str(self.camera_preset or "perspective"),
            "projection_mode": normalize_viewport_projection_mode(self.projection_mode),
            "zoom": float(self.zoom),
            "pan_x": float(self.pan_x),
            "pan_y": float(self.pan_y),
            "orbit_yaw_deg": float(self.orbit_yaw_deg),
            "orbit_pitch_deg": float(self.orbit_pitch_deg),
            "grid_visible": bool(self.grid_visible),
            "snap_enabled": bool(self.snap_enabled),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object] | None) -> "ViewportNavigationState":
        data = dict(payload or {})
        state = cls(profile=normalize_viewport_navigation_profile(data.get("profile")))
        state.camera_preset = _string_value(data.get("camera_preset"), "perspective")
        state.projection_mode = normalize_viewport_projection_mode(data.get("projection_mode"))
        state.zoom = _float_value(data.get("zoom"), 1.0)
        state.pan_x = _float_value(data.get("pan_x"), 0.0)
        state.pan_y = _float_value(data.get("pan_y"), 0.0)
        state.orbit_yaw_deg = _float_value(data.get("orbit_yaw_deg"), -32.0)
        state.orbit_pitch_deg = _float_value(data.get("orbit_pitch_deg"), 22.0)
        state.grid_visible = _bool_value(data.get("grid_visible"), True)
        state.snap_enabled = _bool_value(data.get("snap_enabled"), False)
        return state


@dataclass(frozen=True)
class ViewportNavigationDragOrigin:
    action: str
    pan_x: float
    pan_y: float
    orbit_yaw_deg: float
    orbit_pitch_deg: float
    zoom: float

    @classmethod
    def from_state(cls, action: str, state: ViewportNavigationState) -> "ViewportNavigationDragOrigin":
        return cls(
            action=str(action or "").strip().lower(),
            pan_x=float(state.pan_x),
            pan_y=float(state.pan_y),
            orbit_yaw_deg=float(state.orbit_yaw_deg),
            orbit_pitch_deg=float(state.orbit_pitch_deg),
            zoom=float(state.zoom),
        )


def normalize_viewport_navigation_profile(value: object) -> str:
    key = str(value or "").strip().lower().replace(" ", "").replace("_", "")
    aliases = {
        "3dmax": "3dsmax",
        "3ds": "3dsmax",
        "max": "3dsmax",
        "3dsmax": "3dsmax",
        "blender": "blender",
        "maya": "maya",
    }
    return aliases.get(key, DEFAULT_VIEWPORT_NAVIGATION_PROFILE)


def viewport_profile_label(value: object) -> str:
    key = normalize_viewport_navigation_profile(value)
    return VIEWPORT_NAVIGATION_PROFILES[key].label


def normalize_viewport_projection_mode(value: object) -> str:
    key = str(value or "").strip().lower().replace(" ", "").replace("_", "")
    aliases = {
        "persp": "perspective",
        "perspective": "perspective",
        "ortho": "orthographic",
        "orthographic": "orthographic",
        "orthogonal": "orthographic",
    }
    return aliases.get(key, "perspective")


def viewport_projection_label(value: object) -> str:
    key = normalize_viewport_projection_mode(value)
    return VIEWPORT_PROJECTION_MODES[key]


def has_modifier(modifiers: QtCore.Qt.KeyboardModifiers, modifier: QtCore.Qt.KeyboardModifier) -> bool:
    return bool(modifiers & modifier)


def viewport_navigation_mouse_action(
    profile: object,
    button: QtCore.Qt.MouseButton,
    modifiers: QtCore.Qt.KeyboardModifiers,
) -> str:
    key = normalize_viewport_navigation_profile(profile)
    alt = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.AltModifier)
    shift = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ShiftModifier)
    ctrl = has_modifier(modifiers, QtCore.Qt.KeyboardModifier.ControlModifier)
    if key == "maya":
        if alt and button == QtCore.Qt.MouseButton.LeftButton:
            return "orbit"
        if alt and button == QtCore.Qt.MouseButton.MiddleButton:
            return "pan"
        if alt and button == QtCore.Qt.MouseButton.RightButton:
            return "zoom"
    if key == "blender":
        if button == QtCore.Qt.MouseButton.MiddleButton and shift:
            return "pan"
        if button == QtCore.Qt.MouseButton.MiddleButton and ctrl:
            return "zoom"
        if button == QtCore.Qt.MouseButton.MiddleButton:
            return "orbit"
    if key == "3dsmax":
        if alt and button == QtCore.Qt.MouseButton.MiddleButton:
            return "orbit"
        if button == QtCore.Qt.MouseButton.MiddleButton:
            return "pan"
        if alt and button == QtCore.Qt.MouseButton.RightButton:
            return "zoom"
    return ""


def apply_viewport_navigation_drag(
    state: ViewportNavigationState,
    origin: ViewportNavigationDragOrigin,
    delta_x: float,
    delta_y: float,
) -> bool:
    action = str(origin.action or "").strip().lower()
    if action == "pan":
        state.pan_x = origin.pan_x + float(delta_x)
        state.pan_y = origin.pan_y + float(delta_y)
        return True
    if action == "orbit":
        state.camera_preset = "perspective"
        state.orbit_yaw_deg = origin.orbit_yaw_deg + float(delta_x) * 0.35
        state.orbit_pitch_deg = max(-85.0, min(85.0, origin.orbit_pitch_deg + float(delta_y) * 0.25))
        return True
    if action == "zoom":
        state.zoom = clamp_viewport_zoom(origin.zoom * (1.0 + float(-delta_y) * 0.01))
        return True
    return False


def viewport_wheel_zoom(current_zoom: float, angle_delta_y: float) -> float:
    return clamp_viewport_zoom(float(current_zoom) * (1.0 + float(angle_delta_y) / 1200.0))


def clamp_viewport_zoom(value: float) -> float:
    return max(VIEWPORT_ZOOM_MIN, min(VIEWPORT_ZOOM_MAX, float(value)))


def _string_value(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _float_value(value: object, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _bool_value(value: object, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return fallback
    return bool(value)
