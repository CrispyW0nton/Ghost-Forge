from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6 import QtCore, QtGui, QtWidgets


@dataclass(frozen=True)
class IconDescriptor:
    """Small universal icon descriptor for Ghost Forge Qt actions."""

    name: str
    glyph: str
    accent: str
    standard_pixmap: str | None = None


ICON_DESCRIPTORS: dict[str, IconDescriptor] = {
    "new_scene": IconDescriptor("new_scene", "N", "#3f8cff", "SP_FileIcon"),
    "open": IconDescriptor("open", "O", "#4aa3df", "SP_DirOpenIcon"),
    "import": IconDescriptor("import", "I", "#55a868", "SP_ArrowDown"),
    "save": IconDescriptor("save", "S", "#5b8def", "SP_DialogSaveButton"),
    "quit": IconDescriptor("quit", "Q", "#d66a6a", "SP_DialogCloseButton"),
    "undo": IconDescriptor("undo", "U", "#b78bfa", "SP_ArrowBack"),
    "redo": IconDescriptor("redo", "R", "#b78bfa", "SP_ArrowForward"),
    "delete": IconDescriptor("delete", "D", "#de6a73", "SP_TrashIcon"),
    "refresh": IconDescriptor("refresh", "R", "#55b6c2", "SP_BrowserReload"),
    "frame": IconDescriptor("frame", "F", "#d9a441", "SP_TitleBarMaxButton"),
    "layout": IconDescriptor("layout", "L", "#8aa0b8", "SP_ComputerIcon"),
    "unwrap": IconDescriptor("unwrap", "UV", "#d6b85a", None),
    "texture": IconDescriptor("texture", "T", "#d7824b", "SP_FileDialogDetailedView"),
    "audit": IconDescriptor("audit", "A", "#de6a73", "SP_MessageBoxWarning"),
    "bridge": IconDescriptor("bridge", "B", "#62b679", "SP_DialogApplyButton"),
    "workers": IconDescriptor("workers", "W", "#55a6d9", "SP_ComputerIcon"),
    "help": IconDescriptor("help", "?", "#7da9ff", "SP_MessageBoxInformation"),
    "workspace_modeling": IconDescriptor("workspace_modeling", "M", "#57a773", None),
    "workspace_generation": IconDescriptor("workspace_generation", "G", "#5d9cec", None),
    "workspace_uv_materials": IconDescriptor("workspace_uv_materials", "UV", "#d6a742", None),
    "workspace_sculpt_retopo": IconDescriptor("workspace_sculpt_retopo", "S", "#c07bdc", None),
    "workspace_rig_animation": IconDescriptor("workspace_rig_animation", "R", "#ef7d68", None),
    "workspace_audit_handoff": IconDescriptor("workspace_audit_handoff", "H", "#65b587", None),
    "workspace": IconDescriptor("workspace", "W", "#7187a8", None),
}


ACTION_ICON_NAMES: dict[str, str] = {
    "file.new_scene": "new_scene",
    "file.open_project": "open",
    "file.open_scene": "open",
    "file.import_mesh": "import",
    "file.save_scene": "save",
    "file.save_scene_as": "save",
    "file.quit": "quit",
    "edit.undo": "undo",
    "edit.redo": "redo",
    "edit.delete_selection": "delete",
    "view.refresh_runtime": "refresh",
    "view.frame_all": "frame",
    "view.save_layout": "layout",
    "view.reset_layout": "layout",
    "asset.unwrap": "unwrap",
    "asset.texture": "texture",
    "asset.audit": "audit",
    "asset.export_bridge": "bridge",
    "asset.delete_generated": "delete",
    "tools.worker_models": "workers",
    "help.about": "help",
    "workspace.modeling": "workspace_modeling",
    "workspace.generation": "workspace_generation",
    "workspace.uv_materials": "workspace_uv_materials",
    "workspace.sculpt_retopo": "workspace_sculpt_retopo",
    "workspace.rig_animation": "workspace_rig_animation",
    "workspace.audit_handoff": "workspace_audit_handoff",
}


LABEL_ICON_ALIASES: tuple[tuple[str, str], ...] = (
    ("new", "new_scene"),
    ("open", "open"),
    ("import", "import"),
    ("save", "save"),
    ("undo", "undo"),
    ("redo", "redo"),
    ("delete", "delete"),
    ("remove", "delete"),
    ("refresh", "refresh"),
    ("frame", "frame"),
    ("layout", "layout"),
    ("unwrap", "unwrap"),
    ("texture", "texture"),
    ("audit", "audit"),
    ("bridge", "bridge"),
    ("worker", "workers"),
    ("about", "help"),
)


class ActionIconRegistry:
    """Ghost Rigger-inspired icon lookup for universal Ghost Forge commands."""

    def __init__(self, owner: QtWidgets.QWidget | None = None, *, size: int = 18) -> None:
        self.owner = owner
        self.size = size
        self._cache: dict[tuple[str, int], QtGui.QIcon] = {}

    def icon_for_action(self, action_id: str, label: str, *, size: int | None = None) -> QtGui.QIcon:
        icon_name = icon_name_for_action(action_id, label)
        return self.icon(icon_name, size=size)

    def icon(self, name: str, *, size: int | None = None) -> QtGui.QIcon:
        icon_size = size or self.size
        key = (name, icon_size)
        if key in self._cache:
            return self._cache[key]
        descriptor = ICON_DESCRIPTORS.get(name) or ICON_DESCRIPTORS["workspace"]
        icon = self._standard_icon(descriptor)
        if icon.isNull():
            icon = self._glyph_icon(descriptor, icon_size)
        self._cache[key] = icon
        return icon

    def _standard_icon(self, descriptor: IconDescriptor) -> QtGui.QIcon:
        if not descriptor.standard_pixmap:
            return QtGui.QIcon()
        enum_value = getattr(QtWidgets.QStyle.StandardPixmap, descriptor.standard_pixmap, None)
        if enum_value is None:
            return QtGui.QIcon()
        style = self.owner.style() if self.owner is not None else QtWidgets.QApplication.style()
        return style.standardIcon(enum_value) if style is not None else QtGui.QIcon()

    def _glyph_icon(self, descriptor: IconDescriptor, size: int) -> QtGui.QIcon:
        pixmap = QtGui.QPixmap(size, size)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        rect = QtCore.QRectF(1.0, 1.0, float(size - 2), float(size - 2))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 44), 1))
        painter.setBrush(QtGui.QColor(descriptor.accent))
        painter.drawRoundedRect(rect, 4.0, 4.0)
        font = painter.font()
        font.setBold(True)
        font.setPointSizeF(max(6.0, size * (0.34 if len(descriptor.glyph) > 1 else 0.48)))
        painter.setFont(font)
        painter.setPen(QtGui.QColor("#ffffff"))
        painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, descriptor.glyph)
        painter.end()
        return QtGui.QIcon(pixmap)


def icon_name_for_action(action_id: str, label: str = "") -> str:
    if action_id in ACTION_ICON_NAMES:
        return ACTION_ICON_NAMES[action_id]
    if action_id.startswith("workspace."):
        return "workspace"
    normalized = re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()
    for prefix, icon_name in LABEL_ICON_ALIASES:
        if normalized.startswith(prefix):
            return icon_name
    return "workspace"


__all__ = [
    "ACTION_ICON_NAMES",
    "ActionIconRegistry",
    "IconDescriptor",
    "ICON_DESCRIPTORS",
    "icon_name_for_action",
]
