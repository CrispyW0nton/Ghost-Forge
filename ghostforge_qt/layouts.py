from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from PySide6 import QtCore


@dataclass(frozen=True)
class PanelLayout:
    dock_id: str
    area: str = "left"
    visible: bool = True
    min_width: int = 180
    preferred_width: int = 300
    min_height: int = 90
    preferred_height: int = 220


@dataclass(frozen=True)
class DockGroupLayout:
    group_id: str
    area: str = "left"
    mode: str = "tabbed"
    active: str = ""
    docks: tuple[str, ...] = ()


@dataclass(frozen=True)
class ViewportLayout:
    min_width: int = 760
    preferred_width: int = 1040
    toolbar_visible: bool = True
    bottom_strip_visible: bool = True


@dataclass(frozen=True)
class ToolbarLayout:
    main_visible: bool = True
    workspace_visible: bool = True
    workspace_button_mode: str = "textBesideIcon"
    workspace_icon_size: int = 18

    def summary(self) -> str:
        visible = "visible" if self.workspace_visible else "hidden"
        return f"{self.workspace_button_mode}, {self.workspace_icon_size}px, {visible}"


@dataclass(frozen=True)
class WorkspaceLayout:
    layout_id: str
    name: str
    module_id: str
    version: str = "1.0"
    main_width: int = 1680
    main_height: int = 980
    viewport: ViewportLayout = field(default_factory=ViewportLayout)
    toolbar: ToolbarLayout = field(default_factory=ToolbarLayout)
    panels: dict[str, PanelLayout] = field(default_factory=dict)
    dock_groups: tuple[DockGroupLayout, ...] = ()
    spacing: dict[str, int] = field(default_factory=dict)
    preset: bool = False
    source_path: str = ""
    warnings: tuple[str, ...] = ()

    def panel(self, dock_id: str) -> PanelLayout:
        return self.panels.get(dock_id, PanelLayout(dock_id=dock_id, visible=False))

    def spacing_value(self, token: str, default: int = 0) -> int:
        try:
            return int(self.spacing.get(token, default))
        except (TypeError, ValueError):
            return int(default)

    def summary(self) -> str:
        visible_count = sum(1 for panel in self.panels.values() if panel.visible)
        return (
            f"{self.name}: {visible_count} panels, viewport {self.viewport.min_width}/"
            f"{self.viewport.preferred_width}px, "
            f"toolbar {self.toolbar.summary()}"
        )


ALL_DOCK_IDS = (
    "workspace",
    "viewport",
    "scene",
    "content",
    "modeling",
    "graph",
    "workers",
    "jobs",
    "properties",
    "audit",
    "theme",
)

VALID_DOCK_AREAS = {"left", "right", "bottom", "top"}
VALID_DOCK_GROUP_MODES = {"tabbed", "horizontal", "vertical"}
VALID_TOOL_BUTTON_MODES = {
    "iconOnly",
    "textOnly",
    "iconText",
    "textBesideIcon",
    "textUnderIcon",
    "followStyle",
}


@dataclass(frozen=True)
class WorkspaceLayoutLoadResult:
    layouts: dict[str, WorkspaceLayout]
    available_layouts: dict[str, tuple[WorkspaceLayout, ...]] = field(default_factory=dict)
    selected_layout_ids: dict[str, str] = field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()
    layout_dirs: tuple[Path, ...] = ()


def default_workspace_layouts() -> dict[str, WorkspaceLayout]:
    base = _base_panel_map()
    return {
        "modeling": WorkspaceLayout(
            layout_id="modeling_default",
            name="Modeling Studio",
            module_id="modeling",
            main_width=1720,
            main_height=980,
            viewport=ViewportLayout(min_width=820, preferred_width=1080),
            toolbar=ToolbarLayout(workspace_button_mode="textBesideIcon", workspace_icon_size=18),
            spacing=_base_spacing(),
            panels=_merge_panels(
                base,
                visible=("scene", "content", "modeling", "graph", "jobs", "properties"),
                hidden=("workspace", "viewport", "workers", "audit", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("model_left_rail", "left", "vertical", "scene", ("scene", "content")),
                DockGroupLayout(
                    "model_right_tools",
                    "right",
                    "tabbed",
                    "modeling",
                    ("modeling", "properties", "graph"),
                ),
                DockGroupLayout("model_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
            ),
        ),
        "generation": WorkspaceLayout(
            layout_id="generation_default",
            name="Generation Studio",
            module_id="generation",
            main_width=1760,
            main_height=1020,
            viewport=ViewportLayout(min_width=820, preferred_width=1100),
            toolbar=ToolbarLayout(workspace_button_mode="textBesideIcon", workspace_icon_size=18),
            spacing=_base_spacing(),
            panels=_merge_panels(
                base,
                visible=("content", "graph", "workers", "jobs", "properties", "audit"),
                hidden=("workspace", "viewport", "scene", "modeling", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("generation_left", "left", "vertical", "content", ("content", "workers")),
                DockGroupLayout("generation_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
                DockGroupLayout("generation_right", "right", "tabbed", "graph", ("graph", "properties", "audit")),
            ),
        ),
        "uv_materials": WorkspaceLayout(
            layout_id="uv_materials_default",
            name="UV And Materials Studio",
            module_id="uv_materials",
            main_width=1680,
            main_height=960,
            viewport=ViewportLayout(min_width=800, preferred_width=1060),
            toolbar=ToolbarLayout(workspace_button_mode="iconText", workspace_icon_size=18),
            spacing=_base_spacing(),
            panels=_merge_panels(
                base,
                visible=("content", "graph", "properties", "audit", "jobs"),
                hidden=("workspace", "viewport", "scene", "modeling", "workers", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("uv_left", "left", "tabbed", "content", ("content",)),
                DockGroupLayout("uv_right", "right", "tabbed", "properties", ("properties", "graph", "audit")),
                DockGroupLayout("uv_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
            ),
        ),
        "sculpt_retopo": WorkspaceLayout(
            layout_id="sculpt_retopo_default",
            name="Sculpt And Retopo Studio",
            module_id="sculpt_retopo",
            main_width=1680,
            main_height=960,
            viewport=ViewportLayout(min_width=860, preferred_width=1140),
            toolbar=ToolbarLayout(workspace_button_mode="iconOnly", workspace_icon_size=20),
            spacing={**_base_spacing(), "margin": 4, "panelSpacing": 4, "toolbarSpacing": 3, "inputHeight": 24, "tableRowHeight": 21},
            panels=_merge_panels(
                base,
                visible=("modeling", "graph", "properties", "audit", "jobs"),
                hidden=("workspace", "viewport", "scene", "content", "workers", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("sculpt_left", "left", "tabbed", "modeling", ("modeling",)),
                DockGroupLayout("sculpt_right", "right", "tabbed", "properties", ("properties", "graph", "audit")),
                DockGroupLayout("sculpt_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
            ),
        ),
        "rig_animation": WorkspaceLayout(
            layout_id="rig_animation_default",
            name="Rig And Animation Studio",
            module_id="rig_animation",
            main_width=1700,
            main_height=980,
            viewport=ViewportLayout(min_width=820, preferred_width=1080),
            toolbar=ToolbarLayout(workspace_button_mode="textUnderIcon", workspace_icon_size=18),
            spacing=_base_spacing(),
            panels=_merge_panels(
                base,
                visible=("scene", "graph", "properties", "audit", "jobs"),
                hidden=("workspace", "viewport", "content", "modeling", "workers", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("rig_left", "left", "tabbed", "scene", ("scene",)),
                DockGroupLayout("rig_right", "right", "tabbed", "properties", ("properties", "graph", "audit")),
                DockGroupLayout("rig_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
            ),
        ),
        "audit_handoff": WorkspaceLayout(
            layout_id="audit_handoff_default",
            name="Audit And Handoff Studio",
            module_id="audit_handoff",
            main_width=1760,
            main_height=1020,
            viewport=ViewportLayout(min_width=780, preferred_width=1040),
            toolbar=ToolbarLayout(workspace_button_mode="textBesideIcon", workspace_icon_size=18),
            spacing=_base_spacing(),
            panels=_merge_panels(
                base,
                visible=("content", "graph", "workers", "jobs", "properties", "audit"),
                hidden=("workspace", "viewport", "scene", "modeling", "theme"),
            ),
            dock_groups=(
                DockGroupLayout("handoff_left", "left", "vertical", "content", ("content", "workers")),
                DockGroupLayout("handoff_bottom", "bottom", "tabbed", "jobs", ("jobs",)),
                DockGroupLayout("handoff_right", "right", "tabbed", "audit", ("audit", "properties", "graph")),
            ),
        ),
    }


def dock_area(value: str) -> QtCore.Qt.DockWidgetArea:
    return {
        "left": QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
        "right": QtCore.Qt.DockWidgetArea.RightDockWidgetArea,
        "bottom": QtCore.Qt.DockWidgetArea.BottomDockWidgetArea,
        "top": QtCore.Qt.DockWidgetArea.TopDockWidgetArea,
    }.get(str(value or "").strip().lower(), QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)


def tool_button_style(value: str) -> QtCore.Qt.ToolButtonStyle:
    key = str(value or "").strip().lower().replace("_", "").replace("-", "")
    return {
        "icononly": QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly,
        "textonly": QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly,
        "icontext": QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
        "textbesideicon": QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
        "textundericon": QtCore.Qt.ToolButtonStyle.ToolButtonTextUnderIcon,
        "followstyle": QtCore.Qt.ToolButtonStyle.ToolButtonFollowStyle,
    }.get(key, QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)


class WorkspaceLayoutLoader:
    """Load workspace layout overrides from JSON or XML files.

    The format intentionally preserves the useful Ghost Rigger layout ideas
    while keeping Ghost Forge's module ids, dock ids, and universal workflow
    vocabulary.
    """

    def __init__(self, base_layouts: dict[str, WorkspaceLayout] | None = None) -> None:
        self.base_layouts = dict(base_layouts or default_workspace_layouts())
        self.diagnostics: list[str] = []

    def load_file(self, path: Path) -> WorkspaceLayout | None:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._load_json(path)
        if suffix == ".xml":
            return self._load_xml(path)
        return None

    def load_dir(self, directory: Path) -> dict[str, WorkspaceLayout]:
        loaded: dict[str, WorkspaceLayout] = {}
        for layout in self.load_all_dir(directory):
            loaded[layout.module_id] = layout
        return loaded

    def load_all_dir(self, directory: Path) -> tuple[WorkspaceLayout, ...]:
        loaded: list[WorkspaceLayout] = []
        directory = Path(directory)
        if not directory.exists():
            return ()
        for path in sorted([*directory.glob("*.json"), *directory.glob("*.xml")]):
            layout = self.load_file(path)
            if layout is None:
                continue
            loaded.append(layout)
        return tuple(loaded)

    def _load_json(self, path: Path) -> WorkspaceLayout | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.diagnostics.append(f"{path.name}: Could not parse workspace layout JSON: {exc}")
            return None
        if not isinstance(payload, dict):
            self.diagnostics.append(f"{path.name}: Workspace layout JSON root must be an object.")
            return None
        return self._layout_from_payload(payload, path=path)

    def _load_xml(self, path: Path) -> WorkspaceLayout | None:
        try:
            root = ET.parse(path).getroot()
        except Exception as exc:
            self.diagnostics.append(f"{path.name}: Could not parse workspace layout XML: {exc}")
            return None
        if root.tag not in {"layout", "workspaceLayout"}:
            self.diagnostics.append(f"{path.name}: Root element must be <layout> or <workspaceLayout>.")
            return None
        payload: dict[str, object] = {
            "layout_id": (root.get("id") or path.stem).strip(),
            "name": (root.get("name") or path.stem).strip(),
            "version": (root.get("version") or "1.0").strip(),
            "module_id": (
                root.get("module_id")
                or root.get("moduleId")
                or root.get("module")
                or ""
            ).strip(),
        }
        main_window = root.find("mainWindow")
        if main_window is not None:
            payload["main_width"] = main_window.get("width")
            payload["main_height"] = main_window.get("height")

        toolbar_payload: dict[str, object] = {}
        for toolbar in root.findall("./toolbars/toolbar"):
            toolbar_id = (toolbar.get("id") or "").strip().lower()
            if toolbar_id == "main":
                toolbar_payload["main_visible"] = toolbar.get("visible")
            if toolbar_id in {"workspace", "viewport"}:
                toolbar_payload["workspace_visible"] = toolbar.get("visible")
                toolbar_payload["workspace_button_mode"] = toolbar.get("buttonMode")
                toolbar_payload["workspace_icon_size"] = toolbar.get("iconSize")
        viewport_toolbar = root.find("./viewport/toolbar")
        if viewport_toolbar is not None:
            toolbar_payload.setdefault("workspace_visible", viewport_toolbar.get("visible"))
            toolbar_payload.setdefault("workspace_button_mode", viewport_toolbar.get("buttonMode"))
        if toolbar_payload:
            payload["toolbar"] = toolbar_payload

        viewport_region = root.find("./viewport/region")
        viewport_payload: dict[str, object] = {}
        if viewport_region is not None:
            viewport_payload["min_width"] = viewport_region.get("minWidth")
            viewport_payload["preferred_width"] = viewport_region.get("preferredWidth")
        if viewport_toolbar is not None:
            viewport_payload["toolbar_visible"] = viewport_toolbar.get("visible")
        bottom_strip = root.find("./viewport/bottomStrip")
        if bottom_strip is not None:
            viewport_payload["bottom_strip_visible"] = bottom_strip.get("visible")
        if viewport_payload:
            payload["viewport"] = viewport_payload

        panels: dict[str, object] = {}
        for panel in root.findall("./panels/panel"):
            panel_id = (panel.get("id") or "").strip()
            if not panel_id:
                continue
            panels[panel_id] = {
                "area": panel.get("area") or panel.get("region"),
                "visible": panel.get("visible"),
                "min_width": panel.get("minWidth"),
                "preferred_width": panel.get("preferredWidth"),
                "min_height": panel.get("minHeight"),
                "preferred_height": panel.get("preferredHeight"),
            }
        if panels:
            payload["panels"] = panels

        dock_groups: list[dict[str, object]] = []
        for group in root.findall("./dockLayout/group"):
            docks = [
                (dock.get("id") or "").strip()
                for dock in group.findall("./dock")
                if (dock.get("id") or "").strip()
            ]
            dock_groups.append(
                {
                    "group_id": group.get("id"),
                    "area": group.get("area"),
                    "mode": group.get("mode"),
                    "active": group.get("active"),
                    "docks": docks,
                }
            )
        if dock_groups:
            payload["dock_groups"] = dock_groups

        spacing: dict[str, object] = {}
        spacing_root = root.find("spacing")
        if spacing_root is not None:
            for child in list(spacing_root):
                spacing[child.tag] = child.get("value")
        if spacing:
            payload["spacing"] = spacing
        return self._layout_from_payload(payload, path=path)

    def _layout_from_payload(self, payload: dict[str, object], *, path: Path) -> WorkspaceLayout | None:
        warnings: list[str] = []
        module_id = str(
            payload.get("module_id")
            or payload.get("moduleId")
            or payload.get("module")
            or ""
        ).strip()
        if not module_id:
            self.diagnostics.append(f"{path.name}: Workspace layout is missing module_id.")
            return None
        base = self.base_layouts.get(module_id) or WorkspaceLayout(
            layout_id=f"{module_id}_default",
            name=f"{module_id} Default",
            module_id=module_id,
            panels=_base_panel_map(),
        )
        layout = WorkspaceLayout(
            layout_id=str(payload.get("layout_id") or payload.get("id") or base.layout_id).strip() or base.layout_id,
            name=str(payload.get("name") or base.name).strip() or base.name,
            module_id=module_id,
            version=str(payload.get("version") or base.version).strip() or base.version,
            main_width=_int(payload.get("main_width"), base.main_width),
            main_height=_int(payload.get("main_height"), base.main_height),
            viewport=_viewport_from_payload(payload.get("viewport"), base.viewport, path.name, warnings),
            toolbar=_toolbar_from_payload(payload.get("toolbar"), base.toolbar, path.name, warnings),
            panels=_panels_from_payload(payload.get("panels"), base.panels, path.name, warnings),
            dock_groups=_dock_groups_from_payload(payload.get("dock_groups"), base.dock_groups, path.name, warnings),
            spacing=_spacing_from_payload(payload.get("spacing"), base.spacing, path.name, warnings),
            preset=_bool(_pick(payload, "preset", "selectable", "isPreset"), False),
            source_path=str(path),
            warnings=tuple(warnings),
        )
        self.diagnostics.extend(f"{layout.name}: {warning}" for warning in layout.warnings)
        return layout


def load_workspace_layouts(
    layout_dirs: tuple[Path | str, ...] | None = None,
    *,
    base_layouts: dict[str, WorkspaceLayout] | None = None,
    selected_layout_ids: dict[str, str] | None = None,
) -> WorkspaceLayoutLoadResult:
    layouts = dict(base_layouts or default_workspace_layouts())
    available: dict[str, list[WorkspaceLayout]] = {
        module_id: [layout] for module_id, layout in layouts.items()
    }
    selected = {str(key): str(value) for key, value in (selected_layout_ids or {}).items() if value}
    diagnostics: list[str] = []
    dirs = tuple(Path(path) for path in (layout_dirs or default_workspace_layout_dirs()))
    for directory in dirs:
        loader = WorkspaceLayoutLoader(layouts)
        loaded_layouts = loader.load_all_dir(directory)
        diagnostics.extend(loader.diagnostics)
        for layout in loaded_layouts:
            available.setdefault(layout.module_id, [])
            _append_unique_layout(available[layout.module_id], layout)
            selected_layout_id = selected.get(layout.module_id)
            if selected_layout_id == layout.layout_id:
                layouts[layout.module_id] = layout
                diagnostics.append(
                    f"Workspace layout preset '{layout.name}' selected for '{layout.module_id}' from {layout.source_path}."
                )
                continue
            if selected_layout_id:
                continue
            if layout.preset:
                continue
            if layout.module_id in layouts:
                diagnostics.append(
                    f"Workspace layout for '{layout.module_id}' from {layout.source_path} overrides {layouts[layout.module_id].name}."
                )
            layouts[layout.module_id] = layout

    for module_id, layout_id in selected.items():
        if not any(layout.layout_id == layout_id for layout in available.get(module_id, ())):
            diagnostics.append(f"Selected workspace layout '{layout_id}' for '{module_id}' is unavailable; using fallback.")

    effective_ids = {module_id: layout.layout_id for module_id, layout in layouts.items()}
    return WorkspaceLayoutLoadResult(
        layouts=layouts,
        available_layouts={module_id: tuple(items) for module_id, items in available.items()},
        selected_layout_ids=effective_ids,
        diagnostics=tuple(diagnostics),
        layout_dirs=dirs,
    )


def default_workspace_layout_dirs() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parent
    cwd = Path.cwd()
    return (
        package_root / "workspace_layouts",
        cwd / "config" / "workspace_layouts",
        cwd / "workspace_layouts",
        Path.home() / ".ghostforge" / "workspace_layouts",
    )


def _append_unique_layout(layouts: list[WorkspaceLayout], layout: WorkspaceLayout) -> None:
    for index, existing in enumerate(layouts):
        if existing.layout_id == layout.layout_id:
            layouts[index] = layout
            return
    layouts.append(layout)


def settings_scope_for_path(path: Path) -> str:
    raw = str(Path(path).resolve())
    return "".join(ch if ch.isalnum() else "_" for ch in raw).strip("_") or "default"


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _pick(mapping: dict[str, object], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return int(default)


def _safe_area(value: object, default: str, source: str, warnings: list[str]) -> str:
    area = str(value or default).strip().lower() or default
    if area not in VALID_DOCK_AREAS:
        warnings.append(f"{source}: unsupported dock area '{area}', using '{default}'.")
        return default
    return area


def _safe_group_mode(value: object, default: str, source: str, warnings: list[str]) -> str:
    mode = str(value or default).strip().lower() or default
    if mode not in VALID_DOCK_GROUP_MODES:
        warnings.append(f"{source}: unsupported dock group mode '{mode}', using '{default}'.")
        return default
    return mode


def _safe_button_mode(value: object, default: str, source: str, warnings: list[str]) -> str:
    mode = str(value or default).strip() or default
    if mode not in VALID_TOOL_BUTTON_MODES:
        warnings.append(f"{source}: unsupported toolbar button mode '{mode}', using '{default}'.")
        return default
    return mode


def _viewport_from_payload(
    value: object,
    base: ViewportLayout,
    source: str,
    warnings: list[str],
) -> ViewportLayout:
    if not isinstance(value, dict):
        return base
    return ViewportLayout(
        min_width=max(320, _int(_pick(value, "min_width", "minWidth"), base.min_width)),
        preferred_width=max(
            420,
            _int(_pick(value, "preferred_width", "preferredWidth"), base.preferred_width),
        ),
        toolbar_visible=_bool(_pick(value, "toolbar_visible", "toolbarVisible"), base.toolbar_visible),
        bottom_strip_visible=_bool(
            _pick(value, "bottom_strip_visible", "bottomStripVisible"),
            base.bottom_strip_visible,
        ),
    )


def _toolbar_from_payload(
    value: object,
    base: ToolbarLayout,
    source: str,
    warnings: list[str],
) -> ToolbarLayout:
    if not isinstance(value, dict):
        return base
    return ToolbarLayout(
        main_visible=_bool(_pick(value, "main_visible", "mainVisible"), base.main_visible),
        workspace_visible=_bool(
            _pick(value, "workspace_visible", "workspaceVisible"),
            base.workspace_visible,
        ),
        workspace_button_mode=_safe_button_mode(
            _pick(value, "workspace_button_mode", "workspaceButtonMode", "buttonMode"),
            base.workspace_button_mode,
            source,
            warnings,
        ),
        workspace_icon_size=max(
            8,
            _int(_pick(value, "workspace_icon_size", "workspaceIconSize", "iconSize"), base.workspace_icon_size),
        ),
    )


def _panels_from_payload(
    value: object,
    base: dict[str, PanelLayout],
    source: str,
    warnings: list[str],
) -> dict[str, PanelLayout]:
    panels = dict(base)
    if not isinstance(value, dict):
        return panels
    for dock_id, raw in value.items():
        key = str(dock_id or "").strip()
        if key not in ALL_DOCK_IDS:
            warnings.append(f"{source}: unsupported dock id '{key}' in panels; skipping.")
            continue
        if not isinstance(raw, dict):
            warnings.append(f"{source}: panel '{key}' must be an object; skipping.")
            continue
        base_panel = panels.get(key, PanelLayout(dock_id=key))
        panels[key] = PanelLayout(
            dock_id=key,
            area=_safe_area(_pick(raw, "area", "region"), base_panel.area, source, warnings),
            visible=_bool(_pick(raw, "visible"), base_panel.visible),
            min_width=max(80, _int(_pick(raw, "min_width", "minWidth"), base_panel.min_width)),
            preferred_width=max(80, _int(_pick(raw, "preferred_width", "preferredWidth"), base_panel.preferred_width)),
            min_height=max(40, _int(_pick(raw, "min_height", "minHeight"), base_panel.min_height)),
            preferred_height=max(40, _int(_pick(raw, "preferred_height", "preferredHeight"), base_panel.preferred_height)),
        )
    return panels


def _dock_groups_from_payload(
    value: object,
    base: tuple[DockGroupLayout, ...],
    source: str,
    warnings: list[str],
) -> tuple[DockGroupLayout, ...]:
    if not isinstance(value, list):
        return base
    groups: list[DockGroupLayout] = []
    for raw in value:
        if not isinstance(raw, dict):
            warnings.append(f"{source}: dock group must be an object; skipping.")
            continue
        dock_values = raw.get("docks") or ()
        docks = tuple(
            str(dock).strip()
            for dock in dock_values
            if str(dock).strip() in ALL_DOCK_IDS
        )
        if not docks:
            warnings.append(f"{source}: dock group has no supported dock ids; skipping.")
            continue
        group_id = str(raw.get("group_id") or raw.get("groupId") or raw.get("id") or docks[0]).strip()
        active = str(raw.get("active") or docks[0]).strip()
        groups.append(
            DockGroupLayout(
                group_id=group_id,
                area=_safe_area(raw.get("area"), "left", source, warnings),
                mode=_safe_group_mode(raw.get("mode"), "tabbed", source, warnings),
                active=active if active in docks else docks[0],
                docks=docks,
            )
        )
    return tuple(groups) if groups else base


def _spacing_from_payload(
    value: object,
    base: dict[str, int],
    source: str,
    warnings: list[str],
) -> dict[str, int]:
    spacing = dict(base)
    if not isinstance(value, dict):
        return spacing
    for key, raw in value.items():
        token = str(key or "").strip()
        if not token:
            continue
        try:
            spacing[token] = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            warnings.append(f"{source}: spacing token '{token}' must be an integer; skipping.")
    return spacing


def _base_panel_map() -> dict[str, PanelLayout]:
    return {
        "workspace": PanelLayout("workspace", "left", False, 220, 280, 120, 240),
        "viewport": PanelLayout("viewport", "right", False, 240, 320, 160, 320),
        "scene": PanelLayout("scene", "left", True, 240, 300, 140, 320),
        "content": PanelLayout("content", "left", True, 260, 340, 140, 320),
        "modeling": PanelLayout("modeling", "right", True, 280, 360, 160, 360),
        "graph": PanelLayout("graph", "right", True, 340, 460, 200, 440),
        "workers": PanelLayout("workers", "left", False, 280, 360, 160, 340),
        "jobs": PanelLayout("jobs", "bottom", True, 260, 980, 120, 180),
        "properties": PanelLayout("properties", "right", True, 300, 380, 160, 420),
        "audit": PanelLayout("audit", "right", False, 300, 380, 160, 340),
        "theme": PanelLayout("theme", "right", False, 240, 320, 120, 260),
    }


def _base_spacing() -> dict[str, int]:
    return {
        "margin": 6,
        "panelSpacing": 6,
        "toolbarSpacing": 4,
        "inputHeight": 26,
        "tableRowHeight": 23,
        "treeRowHeight": 23,
        "tabHeight": 18,
        "tabPaddingX": 10,
        "tabPaddingY": 5,
        "groupboxMargin": 10,
        "groupboxSpacing": 6,
        "bottomStripHeight": 32,
        "splitterHandleWidth": 6,
        "viewportHardMinWidth": 680,
        "viewportHardMinHeight": 320,
        "dockHardMinWidth": 180,
        "dockHardMinHeight": 90,
    }


def _merge_panels(
    base: dict[str, PanelLayout],
    *,
    visible: tuple[str, ...],
    hidden: tuple[str, ...],
) -> dict[str, PanelLayout]:
    visible_ids = set(visible)
    hidden_ids = set(hidden)
    out: dict[str, PanelLayout] = {}
    for dock_id in ALL_DOCK_IDS:
        panel = base[dock_id]
        out[dock_id] = PanelLayout(
            dock_id=panel.dock_id,
            area=panel.area,
            visible=(dock_id in visible_ids) or (panel.visible and dock_id not in hidden_ids),
            min_width=panel.min_width,
            preferred_width=panel.preferred_width,
            min_height=panel.min_height,
            preferred_height=panel.preferred_height,
        )
    return out
