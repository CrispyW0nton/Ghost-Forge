from __future__ import annotations

from dataclasses import dataclass

from PySide6 import QtCore


VIEW_CUBE_PANEL_WIDTH = 136
VIEW_CUBE_PANEL_HEIGHT = 148
VIEW_CUBE_MARGIN = 12


@dataclass(frozen=True)
class ViewCubeRegion:
    key: str
    label: str
    rect: QtCore.QRectF


FACE_LABELS = {
    "top": "TOP",
    "front": "FRONT",
    "right": "RIGHT",
    "left": "LEFT",
    "bottom": "BOTTOM",
    "back": "BACK",
    "home": "HOME",
    "perspective": "PERSP",
}

FACE_PRESETS = {"top", "front", "right", "left", "bottom", "back"}


def view_cube_panel_rect(bounds: QtCore.QRect) -> QtCore.QRectF:
    width = min(VIEW_CUBE_PANEL_WIDTH, max(112, bounds.width() - 2 * VIEW_CUBE_MARGIN))
    height = min(VIEW_CUBE_PANEL_HEIGHT, max(128, bounds.height() - 2 * VIEW_CUBE_MARGIN))
    x = bounds.right() - width - VIEW_CUBE_MARGIN
    y = bounds.top() + VIEW_CUBE_MARGIN
    if x < bounds.left() + VIEW_CUBE_MARGIN:
        x = bounds.left() + VIEW_CUBE_MARGIN
    return QtCore.QRectF(float(x), float(y), float(width), float(height))


def view_cube_regions(panel: QtCore.QRectF) -> dict[str, ViewCubeRegion]:
    x = panel.left()
    y = panel.top()
    scale_x = panel.width() / VIEW_CUBE_PANEL_WIDTH
    scale_y = panel.height() / VIEW_CUBE_PANEL_HEIGHT

    def rect(rx: float, ry: float, rw: float, rh: float) -> QtCore.QRectF:
        return QtCore.QRectF(
            x + rx * scale_x,
            y + ry * scale_y,
            rw * scale_x,
            rh * scale_y,
        )

    entries = {
        "top": rect(45, 12, 46, 24),
        "front": rect(38, 40, 52, 38),
        "right": rect(93, 40, 31, 38),
        "left": rect(12, 40, 23, 38),
        "bottom": rect(45, 82, 46, 22),
        "home": rect(12, 114, 30, 22),
        "back": rect(48, 114, 40, 22),
        "perspective": rect(94, 114, 30, 22),
    }
    return {key: ViewCubeRegion(key=key, label=FACE_LABELS[key], rect=value) for key, value in entries.items()}


def hit_test_view_cube(point: QtCore.QPointF, bounds: QtCore.QRect) -> ViewCubeRegion | None:
    panel = view_cube_panel_rect(bounds)
    if not panel.contains(point):
        return None
    for region in view_cube_regions(panel).values():
        if region.rect.contains(point):
            return region
    return None
