from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
import xml.etree.ElementTree as ET


KNOWN_WORKSPACE_DOCK_IDS: tuple[str, ...] = (
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


@dataclass(frozen=True)
class WorkspaceViewportDefaults:
    display_mode: str = "shaded"
    selection_mode: str = "object"
    transform_mode: str = "move"
    navigation_profile: str = "maya"
    camera_preset: str | None = None
    projection_mode: str | None = "perspective"
    grid_visible: bool | None = True
    snap_enabled: bool | None = False
    view_cube_visible: bool | None = True
    gizmo_orientation: str | None = "world"
    gizmo_pivot: str | None = "bounds_center"

    def summary(self) -> str:
        parts = [
            self.display_mode,
            self.selection_mode,
            self.transform_mode,
            self.navigation_profile,
        ]
        toggles = []
        if self.grid_visible is not None:
            toggles.append("grid" if self.grid_visible else "grid off")
        if self.snap_enabled is not None:
            toggles.append("snap" if self.snap_enabled else "snap off")
        if self.view_cube_visible is not None:
            toggles.append("cube" if self.view_cube_visible else "cube off")
        if self.gizmo_orientation:
            toggles.append(f"{self.gizmo_orientation} axes")
        if self.gizmo_pivot:
            toggles.append(str(self.gizmo_pivot).replace("_", " "))
        if self.camera_preset:
            toggles.append(self.camera_preset)
        if self.projection_mode:
            toggles.append(self.projection_mode)
        return " / ".join((*parts, ", ".join(toggles)))


@dataclass(frozen=True)
class WorkspaceModule:
    """Universal Ghost Forge workspace definition.

    This mirrors Ghost Rigger's module-editor separation without importing its
    KOTOR-specific assumptions: a workspace declares the panels and commands
    that make a production mode feel coherent.
    """

    module_id: str
    label: str
    summary: str
    status: str
    primary_dock_ids: tuple[str, ...]
    secondary_dock_ids: tuple[str, ...] = ()
    toolbar_action_ids: tuple[str, ...] = ()
    viewport_defaults: WorkspaceViewportDefaults = WorkspaceViewportDefaults()
    shortcut: str | None = None
    source_path: Path | None = None
    warnings: tuple[str, ...] = ()

    @property
    def action_id(self) -> str:
        return f"workspace.{self.module_id}"

    @property
    def dock_ids(self) -> tuple[str, ...]:
        return (*self.primary_dock_ids, *self.secondary_dock_ids)


def default_workspace_modules() -> tuple[WorkspaceModule, ...]:
    return (
        WorkspaceModule(
            module_id="modeling",
            label="Modeling",
            summary="Scene, content, viewport, direct mesh tools, and the non-destructive operation graph.",
            status="foundation",
            primary_dock_ids=("viewport", "scene", "content", "modeling", "graph"),
            secondary_dock_ids=("properties",),
            toolbar_action_ids=(
                "file.import_mesh",
                "edit.delete_selection",
                "edit.undo",
                "edit.redo",
                "view.frame_all",
                "view.frame_selected",
            ),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="shaded",
                selection_mode="object",
                transform_mode="move",
                navigation_profile="maya",
                grid_visible=True,
                snap_enabled=False,
            ),
            shortcut="Ctrl+1",
        ),
        WorkspaceModule(
            module_id="generation",
            label="Generation",
            summary="AI worker status, source nodes, graph jobs, generated artifacts, and project assets.",
            status="foundation",
            primary_dock_ids=("viewport", "content", "graph", "workers", "jobs"),
            secondary_dock_ids=("properties", "audit"),
            toolbar_action_ids=("view.refresh_runtime", "tools.worker_models"),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="shaded",
                selection_mode="object",
                transform_mode="move",
                navigation_profile="maya",
                grid_visible=True,
                snap_enabled=False,
            ),
            shortcut="Ctrl+2",
        ),
        WorkspaceModule(
            module_id="uv_materials",
            label="UV & Materials",
            summary="UV, material, texture, checker, bake, and graph-driven texture operations.",
            status="planned",
            primary_dock_ids=("viewport", "content", "graph", "properties"),
            secondary_dock_ids=("audit",),
            toolbar_action_ids=("asset.unwrap", "asset.texture"),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="uv",
                selection_mode="face",
                transform_mode="move",
                navigation_profile="blender",
                projection_mode="orthographic",
                grid_visible=False,
                snap_enabled=False,
            ),
            shortcut="Ctrl+3",
        ),
        WorkspaceModule(
            module_id="sculpt_retopo",
            label="Sculpt & Retopo",
            summary="Brushes, masks, remesh, decimate, retopo, projection, and topology diagnostics.",
            status="planned",
            primary_dock_ids=("viewport", "modeling", "graph", "properties"),
            secondary_dock_ids=("audit",),
            toolbar_action_ids=("view.frame_all", "view.frame_selected"),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="xray",
                selection_mode="face",
                transform_mode="move",
                navigation_profile="maya",
                grid_visible=True,
                snap_enabled=True,
            ),
            shortcut="Ctrl+4",
        ),
        WorkspaceModule(
            module_id="rig_animation",
            label="Rig & Animation",
            summary="Skeletons, skinning, constraints, retargeting, and animation timelines.",
            status="planned",
            primary_dock_ids=("viewport", "scene", "graph", "properties"),
            secondary_dock_ids=("audit",),
            toolbar_action_ids=("view.frame_all", "view.frame_selected"),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="solid",
                selection_mode="object",
                transform_mode="rotate",
                navigation_profile="maya",
                grid_visible=True,
                snap_enabled=False,
            ),
            shortcut="Ctrl+5",
        ),
        WorkspaceModule(
            module_id="audit_handoff",
            label="Audit & Handoff",
            summary="Validation, manifest evidence, bridge packages, Unity and Unreal handoff readiness.",
            status="foundation",
            primary_dock_ids=("viewport", "graph", "audit", "jobs"),
            secondary_dock_ids=("workers", "properties", "content"),
            toolbar_action_ids=("asset.audit", "asset.export_bridge", "view.refresh_runtime"),
            viewport_defaults=WorkspaceViewportDefaults(
                display_mode="xray",
                selection_mode="object",
                transform_mode="move",
                navigation_profile="3dsmax",
                projection_mode="orthographic",
                grid_visible=False,
                snap_enabled=False,
            ),
            shortcut="Ctrl+6",
        ),
    )


def workspace_module_by_id(module_id: str, modules: tuple[WorkspaceModule, ...] | None = None) -> WorkspaceModule:
    available = modules or default_workspace_modules()
    for module in available:
        if module.module_id == module_id:
            return module
    raise KeyError(module_id)


@dataclass(frozen=True)
class WorkspaceModuleLoadResult:
    modules: tuple[WorkspaceModule, ...]
    diagnostics: tuple[str, ...] = ()
    module_dirs: tuple[Path, ...] = ()


class WorkspaceModuleLoader:
    """Load universal Ghost Forge workspace modules from JSON or XML files.

    This follows Ghost Rigger's file-backed module/layout lesson while keeping
    the actual module ids and dock ids universal to Ghost Forge.
    """

    def __init__(self, base_modules: tuple[WorkspaceModule, ...] | None = None) -> None:
        self.base_modules = {module.module_id: module for module in (base_modules or default_workspace_modules())}
        self.diagnostics: list[str] = []

    def load_file(self, path: Path) -> WorkspaceModule | None:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".json":
            return self._load_json(path)
        if suffix == ".xml":
            return self._load_xml(path)
        return None

    def load_all_dir(self, directory: Path | str) -> tuple[WorkspaceModule, ...]:
        root = Path(directory)
        if not root.is_dir():
            return ()
        modules: list[WorkspaceModule] = []
        for path in sorted((*root.glob("*.json"), *root.glob("*.xml"))):
            module = self.load_file(path)
            if module is not None:
                modules.append(module)
        return tuple(modules)

    def _load_json(self, path: Path) -> WorkspaceModule | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.diagnostics.append(f"{path.name}: Could not parse workspace module JSON: {exc}")
            return None
        if not isinstance(payload, dict):
            self.diagnostics.append(f"{path.name}: Workspace module JSON root must be an object.")
            return None
        return self._module_from_payload(payload, path=path)

    def _load_xml(self, path: Path) -> WorkspaceModule | None:
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.diagnostics.append(f"{path.name}: Could not parse workspace module XML: {exc}")
            return None
        if root.tag not in {"workspaceModule", "module", "workspace"}:
            self.diagnostics.append(f"{path.name}: Root element must be <workspaceModule>, <module>, or <workspace>.")
            return None
        payload: dict[str, object] = {
            "module_id": root.get("module_id") or root.get("moduleId") or root.get("id") or path.stem,
            "label": root.get("label") or root.get("name"),
            "status": root.get("status"),
            "shortcut": root.get("shortcut"),
        }
        summary = root.findtext("summary")
        if summary:
            payload["summary"] = summary.strip()
        payload["primary_dock_ids"] = _xml_item_values(root, "./primaryDocks/dock")
        payload["secondary_dock_ids"] = _xml_item_values(root, "./secondaryDocks/dock")
        payload["toolbar_action_ids"] = _xml_item_values(root, "./toolbarActions/action")
        viewport = root.find("viewportDefaults")
        if viewport is not None:
            payload["viewport_defaults"] = dict(viewport.attrib)
        return self._module_from_payload(payload, path=path)

    def _module_from_payload(self, payload: Mapping[str, object], *, path: Path) -> WorkspaceModule | None:
        module_id = _text(
            payload.get("module_id")
            or payload.get("moduleId")
            or payload.get("id")
            or payload.get("workspace_id")
            or payload.get("workspaceId")
        )
        if not module_id:
            self.diagnostics.append(f"{path.name}: Workspace module is missing module_id.")
            return None
        base = self.base_modules.get(
            module_id,
            WorkspaceModule(
                module_id=module_id,
                label=module_id.replace("_", " ").title(),
                summary="Custom workspace module.",
                status="custom",
                primary_dock_ids=("viewport",),
            ),
        )
        viewport_payload = payload.get("viewport_defaults") or payload.get("viewportDefaults") or payload.get("viewport")
        viewport_defaults = _viewport_defaults_from_payload(viewport_payload, base.viewport_defaults)
        primary_dock_ids = _tuple_value(
            payload.get("primary_dock_ids") or payload.get("primaryDockIds") or payload.get("primaryDocks"),
            base.primary_dock_ids,
        )
        secondary_dock_ids = _tuple_value(
            payload.get("secondary_dock_ids") or payload.get("secondaryDockIds") or payload.get("secondaryDocks"),
            base.secondary_dock_ids,
        )
        toolbar_action_ids = _tuple_value(
            payload.get("toolbar_action_ids") or payload.get("toolbarActionIds") or payload.get("toolbarActions"),
            base.toolbar_action_ids,
        )
        warnings = _module_warnings(module_id, primary_dock_ids, secondary_dock_ids)
        module = WorkspaceModule(
            module_id=module_id,
            label=_text(payload.get("label") or payload.get("name"), base.label),
            summary=_text(payload.get("summary"), base.summary),
            status=_text(payload.get("status"), base.status),
            primary_dock_ids=primary_dock_ids,
            secondary_dock_ids=secondary_dock_ids,
            toolbar_action_ids=toolbar_action_ids,
            viewport_defaults=viewport_defaults,
            shortcut=_optional_text(payload.get("shortcut"), base.shortcut),
            source_path=path,
            warnings=tuple(warnings),
        )
        self.diagnostics.extend(f"{path.name}: {warning}" for warning in warnings)
        return module


def load_workspace_modules(
    module_dirs: tuple[Path | str, ...] | None = None,
    *,
    base_modules: tuple[WorkspaceModule, ...] | None = None,
) -> WorkspaceModuleLoadResult:
    modules = list(base_modules or default_workspace_modules())
    module_index = {module.module_id: index for index, module in enumerate(modules)}
    diagnostics: list[str] = []
    dirs = tuple(Path(path) for path in (module_dirs or default_workspace_module_dirs()))
    for directory in dirs:
        loader = WorkspaceModuleLoader(tuple(modules))
        loaded_modules = loader.load_all_dir(directory)
        diagnostics.extend(loader.diagnostics)
        for module in loaded_modules:
            if module.module_id in module_index:
                modules[module_index[module.module_id]] = module
                diagnostics.append(f"Workspace module '{module.module_id}' loaded from {module.source_path}.")
            else:
                module_index[module.module_id] = len(modules)
                modules.append(module)
                diagnostics.append(f"Custom workspace module '{module.module_id}' loaded from {module.source_path}.")
    return WorkspaceModuleLoadResult(modules=tuple(modules), diagnostics=tuple(diagnostics), module_dirs=dirs)


def default_workspace_module_dirs() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parent
    cwd = Path.cwd()
    return (
        package_root / "workspace_modules",
        cwd / "config" / "workspace_modules",
        cwd / "workspace_modules",
        Path.home() / ".ghostforge" / "workspace_modules",
    )


def _viewport_defaults_from_payload(
    payload: object,
    base: WorkspaceViewportDefaults,
) -> WorkspaceViewportDefaults:
    if not isinstance(payload, Mapping):
        return base
    return WorkspaceViewportDefaults(
        display_mode=_text(payload.get("display_mode") or payload.get("displayMode"), base.display_mode),
        selection_mode=_text(payload.get("selection_mode") or payload.get("selectionMode"), base.selection_mode),
        transform_mode=_text(payload.get("transform_mode") or payload.get("transformMode"), base.transform_mode),
        navigation_profile=_text(
            payload.get("navigation_profile") or payload.get("navigationProfile"),
            base.navigation_profile,
        ),
        camera_preset=_optional_text(payload.get("camera_preset") or payload.get("cameraPreset"), base.camera_preset),
        projection_mode=_optional_text(
            payload.get("projection_mode") or payload.get("projectionMode"),
            base.projection_mode,
        ),
        grid_visible=_optional_bool(payload.get("grid_visible") or payload.get("gridVisible"), base.grid_visible),
        snap_enabled=_optional_bool(payload.get("snap_enabled") or payload.get("snapEnabled"), base.snap_enabled),
        view_cube_visible=_optional_bool(
            payload.get("view_cube_visible") or payload.get("viewCubeVisible"),
            base.view_cube_visible,
        ),
        gizmo_orientation=_optional_text(
            payload.get("gizmo_orientation") or payload.get("gizmoOrientation"),
            base.gizmo_orientation,
        ),
        gizmo_pivot=_optional_text(payload.get("gizmo_pivot") or payload.get("gizmoPivot"), base.gizmo_pivot),
    )


def _module_warnings(module_id: str, primary: tuple[str, ...], secondary: tuple[str, ...]) -> list[str]:
    warnings: list[str] = []
    if not primary:
        warnings.append(f"Workspace module '{module_id}' has no primary docks; viewport fallback will be weak.")
    unknown_docks = sorted({dock for dock in (*primary, *secondary) if dock not in KNOWN_WORKSPACE_DOCK_IDS})
    if unknown_docks:
        warnings.append(f"Workspace module '{module_id}' references unknown docks: {', '.join(unknown_docks)}.")
    return warnings


def _tuple_value(value: object, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return fallback
    if isinstance(value, str):
        items = value.replace(";", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        return fallback
    out = tuple(str(item).strip() for item in items if str(item).strip())
    return out


def _xml_item_values(root: ET.Element, path: str) -> tuple[str, ...]:
    values: list[str] = []
    for item in root.findall(path):
        value = item.get("id") or item.get("action_id") or item.get("actionId") or item.text
        if value and str(value).strip():
            values.append(str(value).strip())
    return tuple(values)


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _optional_text(value: object, fallback: str | None = None) -> str | None:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or None


def _optional_bool(value: object, fallback: bool | None) -> bool | None:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"none", "null", ""}:
        return None
    return text in {"1", "true", "yes", "on"}
