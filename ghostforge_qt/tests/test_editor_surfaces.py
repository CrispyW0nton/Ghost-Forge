from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import numpy as np
import trimesh
from PySide6 import QtCore, QtGui, QtWidgets

from ghostforge_core.authoring import EditGraph, OperationNode
from ghostforge_qt.models.scene_model import SceneObjectRecord, TransformState
from ghostforge_qt.panels.content_browser import ContentBrowserPanel
from ghostforge_qt.panels.modeling_tools import ModelingToolsPanel
from ghostforge_qt.panels.theme_panel import ThemePanel
from ghostforge_qt.panels.viewport_panel import ViewportPanel
from ghostforge_qt.panels.workspace_modules import WorkspaceModulePanel
from ghostforge_qt.services.editable_mesh import EditableMeshHistory, EditableMeshSnapshot
from ghostforge_qt.services.project_service import ProjectService
from ghostforge_qt.services.scene_document import SceneDocumentService
from ghostforge_qt.services.mesh_operation_service import MeshOperationSelection, MeshOperationService
from ghostforge_qt.services.mesh_diagnostics import analyze_mesh
from ghostforge_qt.services.mesh_selection import MeshSelectionState
from ghostforge_qt.services.operation_history import (
    OperationHistory,
    SceneDeleteCommand,
    ScenePathCommand,
    SceneTransformCommand,
)
from ghostforge_qt.theme import Theme, ThemeLoader, ThemeManager, ThemeValidator, ThemeWatcher, built_in_themes
from ghostforge_qt.viewports.mesh_preview import load_mesh_preview
from ghostforge_qt.viewports.viewport_host import ViewportHost
from ghostforge_qt.models.viewport_model import ViewportDiagnosticsModel
from ghostforge_qt.viewports.navigation import VIEWPORT_NAVIGATION_HELP
from ghostforge_qt.viewports.navigation import (
    ViewportNavigationDragOrigin,
    ViewportNavigationState,
    apply_viewport_navigation_drag,
    viewport_navigation_mouse_action,
    viewport_wheel_zoom,
)
from ghostforge_qt.viewports.transform_gizmo import (
    TransformGizmoDragOrigin,
    TransformGizmoHandle,
    normalize_gizmo_orientation,
    normalize_gizmo_pivot,
    transform_gizmo_edit_from_drag,
)
from ghostforge_qt.viewports.viewcube_math import view_cube_panel_rect, view_cube_regions
from ghostforge_qt.layouts import WorkspaceLayoutLoader, default_workspace_layouts, load_workspace_layouts
from ghostforge_qt.workspace_watcher import WorkspaceResourceWatcher
from ghostforge_qt.workspaces import WorkspaceModuleLoader, default_workspace_modules, load_workspace_modules


def test_project_service_creates_project_folders(qapp, tmp_path):
    project = ProjectService(tmp_path / "project")

    state = project.state()

    assert state.root == (tmp_path / "project").resolve()
    for name in ("assets", "imports", "outputs", "references", "scenes"):
        assert state.dirs[name].is_dir()


def test_content_browser_roots_itself_at_project(qapp, tmp_path):
    project = ProjectService(tmp_path / "project")
    panel = ContentBrowserPanel(project)

    try:
        assert Path(panel.model.rootPath()) == project.root
        new_root = tmp_path / "another_project"
        project.set_root(new_root)
        assert Path(panel.model.rootPath()) == new_root.resolve()
    finally:
        panel.deleteLater()


def test_scene_document_service_round_trips_records(tmp_path):
    service = SceneDocumentService()
    project_root = tmp_path / "project"
    record = SceneObjectRecord(
        object_id="obj_cube",
        name="Cube",
        path=tmp_path / "cube.glb",
        asset_dir=project_root / "assets" / "obj_cube",
        manifest_path=project_root / "assets" / "obj_cube" / "asset_manifest.json",
        vertices=8,
        faces=12,
        watertight=True,
        transform=TransformState(
            translate=(1.0, 2.0, 3.0),
            rotate_euler_deg=(10.0, 20.0, 30.0),
            scale=(2.0, 2.0, 2.0),
        ),
        operations=("normalize_scale",),
        operation_graph=EditGraph(
            graph_id="obj_cube_graph",
            asset_id="obj_cube",
            name="Cube Graph",
            base_asset_path=str(tmp_path / "cube.glb"),
            nodes=(OperationNode(id="n1_recenter", kind="recenter", params={"pivot": "centroid"}),),
        ),
        operation_graph_history=(
            {
                "history_id": "obj_cube_graph_succeeded_0",
                "graph_id": "obj_cube_graph",
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_out.glb"),
                "duration_ms": 12.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "audit passed",
            },
            {
                "history_id": "obj_cube_graph_succeeded_1",
                "graph_id": "obj_cube_graph",
                "status": "succeeded",
                "output_path": str(tmp_path / "cube_blockout.glb"),
                "duration_ms": 7.0,
                "artifact_count": 1,
                "audit_badge": "passed",
                "message": "blockout passed",
            },
        ),
        operation_graph_comparison_pair={
            "left_history_id": "obj_cube_graph_succeeded_1",
            "right_history_id": "obj_cube_graph_succeeded_0",
        },
    )
    scene_path = service.default_scene_path(project_root, "test scene")

    service.write(scene_path, project_root=project_root, records=[record])
    loaded = service.read(scene_path)

    assert loaded.path == scene_path
    assert loaded.scene_id == "test_scene"
    assert loaded.project_root == project_root.resolve()
    assert len(loaded.records) == 1
    restored = loaded.records[0]
    assert restored.object_id == "obj_cube"
    assert restored.transform.translate == (1.0, 2.0, 3.0)
    assert restored.operations == ("normalize_scale",)
    assert restored.manifest_path == record.manifest_path
    assert restored.operation_graph is not None
    assert restored.operation_graph.graph_id == "obj_cube_graph"
    assert restored.operation_graph.nodes[0].kind == "recenter"
    assert restored.operation_graph_history[0]["audit_badge"] == "passed"
    assert restored.operation_graph_history[0]["history_id"] == "obj_cube_graph_succeeded_0"
    assert restored.operation_graph_history[0]["mcp_links"]["graph"] == "ghostforge://graphs/obj_cube_graph"
    assert (
        restored.operation_graph_history[0]["mcp_links"]["scene_object_graph_history"]
        == restored.operation_graph_history[0]["resource_uri"]
    )
    assert restored.operation_graph_comparison_pair == {
        "left_history_id": "obj_cube_graph_succeeded_1",
        "right_history_id": "obj_cube_graph_succeeded_0",
    }


def test_theme_manager_switches_builtin_themes(qapp):
    manager = ThemeManager()

    theme = manager.select("graphite_studio")

    assert theme.id == "graphite_studio"
    assert theme.color("window.background") == theme.color("window.bg")
    assert "QMainWindow" in manager.stylesheet(theme)
    assert "QTabBar::tab" in manager.stylesheet(theme)
    assert "QLabel#WorkspaceLayoutDiagnostics" in manager.stylesheet(theme)
    assert "QLabel#WorkspaceModuleDiagnostics" in manager.stylesheet(theme)
    assert manager.accessibility_report(theme) == []

    rigger_theme = manager.select("ghost_rigger_dark")
    manager.apply()

    assert rigger_theme.id == "ghost_rigger_dark"
    assert "GhostForgeGraphTabs" in manager.stylesheet(rigger_theme)
    assert QtWidgets.QApplication.palette().color(QtGui.QPalette.ColorRole.Window) == QtGui.QColor(
        rigger_theme.color("window.bg")
    )


def test_theme_validator_reports_accessibility_contrast_warnings():
    base = built_in_themes()["forge_dark"]
    theme = Theme(
        id="low_contrast",
        name="Low Contrast",
        colors={
            **base.colors,
            "window.bg": "#111111",
            "panel.bg": "#111111",
            "panel.alt": "#111111",
            "input.bg": "#111111",
            "button.bg": "#111111",
            "text.primary": "#121212",
            "text.secondary": "#121212",
        },
        metrics=dict(base.metrics),
        mode=base.mode,
    )

    diagnostics = ThemeValidator().accessibility_diagnostics(theme)

    assert any(
        diagnostic.code == "contrast.low"
        and diagnostic.foreground_token == "text.primary"
        and diagnostic.background_token == "panel.bg"
        and diagnostic.ratio is not None
        and diagnostic.minimum is not None
        and diagnostic.ratio < diagnostic.minimum
        for diagnostic in diagnostics
    )
    assert any("expected at least 4.50:1" in diagnostic.message for diagnostic in diagnostics)


def test_theme_manager_loads_file_themes_with_diagnostics(qapp, tmp_path):
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    custom_theme = {
        "id": "night_shift",
        "name": "Night Shift",
        "version": "1.0",
        "mode": "dark",
        "description": "Test file theme",
        "colors": {
            "window.background": "#101418",
            "panel.bg": "#181d23",
            "viewport.bg": "#05080b",
            "accent.primary": "#ffcc66",
            "bad.token": "not-a-color",
        },
        "metrics": {
            "panel.spacing": 9,
            "input.height": 29,
            "bad_metric": "wide",
        },
    }
    (theme_dir / "night_shift.json").write_text(json.dumps(custom_theme), encoding="utf-8")
    (theme_dir / "studio.xml").write_text(
        """
        <theme id="xml_studio" name="XML Studio" version="1.0">
          <metadata>
            <mode>light</mode>
            <description>XML test theme</description>
          </metadata>
          <colors>
            <color name="window.bg" value="#eeeeee" />
            <color name="accent.primary" value="#336699" />
          </colors>
          <metrics>
            <metric name="toolbar.height" value="36" />
          </metrics>
        </theme>
        """,
        encoding="utf-8",
    )

    manager = ThemeManager(theme_dirs=(theme_dir,))

    file_ids = {theme.id for theme in manager.themes()}
    assert "night_shift" in file_ids
    assert "xml_studio" in file_ids

    theme = manager.select("night_shift")

    assert theme.color("window.bg") == "#101418"
    assert theme.color("window.background") == "#101418"
    assert theme.metric("panel_spacing") == 9
    assert theme.metric("input_height") == 29
    assert theme.source_path.endswith("night_shift.json")
    assert any("bad.token" in warning for warning in manager.diagnostics)
    assert any("bad_metric" in warning for warning in manager.diagnostics)


def test_theme_watcher_tracks_theme_files_and_manual_trigger(qapp, tmp_path):
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    theme_file = theme_dir / "live_theme.json"
    theme_file.write_text('{"id": "live_theme", "name": "Live Theme"}', encoding="utf-8")
    watcher = ThemeWatcher((theme_dir,), debounce_ms=1)
    changes: list[str] = []
    watcher.themesChanged.connect(lambda: changes.append("changed"))

    watcher.set_enabled(True)
    watched = watcher.watched_paths()

    assert theme_dir in watched
    assert theme_file in watched

    watcher.trigger_reload()

    assert changes == ["changed"]

    watcher.set_enabled(False)

    assert watcher.watched_paths() == ()


def test_theme_manager_live_reload_preserves_selection_and_emits(qapp, tmp_path):
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    theme_file = theme_dir / "live_theme.json"
    theme_file.write_text(
        json.dumps(
            {
                "id": "live_theme",
                "name": "Live Theme",
                "colors": {"accent.primary": "#224466"},
            }
        ),
        encoding="utf-8",
    )
    manager = ThemeManager(theme_dirs=(theme_dir,))
    manager.set_live_reload_enabled(True)
    manager.select("live_theme")
    reloaded: list[tuple[str, ...]] = []
    changed: list[str] = []
    manager.themesReloaded.connect(lambda themes: reloaded.append(tuple(theme.id for theme in themes)))
    manager.themeChanged.connect(lambda theme: changed.append(theme.color("accent.primary")))

    theme_file.write_text(
        json.dumps(
            {
                "id": "live_theme",
                "name": "Live Theme",
                "colors": {"accent.primary": "#88aa44"},
            }
        ),
        encoding="utf-8",
    )
    manager.theme_watcher.trigger_reload()

    assert reloaded
    assert "live_theme" in reloaded[-1]
    assert manager.current_theme().id == "live_theme"
    assert manager.current_theme().color("accent.primary") == "#88aa44"
    assert changed[-1] == "#88aa44"


def test_theme_panel_toggles_live_reload_and_refreshes_catalog(qapp, tmp_path):
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    manager = ThemeManager(theme_dirs=(theme_dir,))
    manager.set_live_reload_enabled(True)
    panel = ThemePanel(manager)

    try:
        assert panel.live_reload_check.isChecked()

        panel.live_reload_check.setChecked(False)

        assert not manager.live_reload_enabled()
        assert "Live reload: off" in panel.preview.text()

        panel.live_reload_check.setChecked(True)
        new_theme = theme_dir / "panel_theme.json"
        new_theme.write_text(
            json.dumps({"id": "panel_theme", "name": "Panel Theme"}),
            encoding="utf-8",
        )
        manager.theme_watcher.trigger_reload()

        assert manager.live_reload_enabled()
        assert panel.combo.findData("panel_theme") >= 0
        assert "Live reload: on" in panel.preview.text()
        assert "Watching:" in panel.preview.text()
    finally:
        panel.deleteLater()


def test_theme_manager_surfaces_file_theme_accessibility_diagnostics(qapp, tmp_path):
    theme_dir = tmp_path / "themes"
    theme_dir.mkdir()
    low_contrast = {
        "id": "flat_panel",
        "name": "Flat Panel",
        "colors": {
            "window.bg": "#202020",
            "panel.bg": "#202020",
            "panel.alt": "#202020",
            "input.bg": "#202020",
            "button.bg": "#202020",
            "text.primary": "#232323",
            "text.secondary": "#242424",
            "accent.primary": "#242424",
        },
    }
    (theme_dir / "flat_panel.json").write_text(json.dumps(low_contrast), encoding="utf-8")

    manager = ThemeManager(theme_dirs=(theme_dir,))
    manager.select("flat_panel")

    report = manager.accessibility_report("flat_panel")

    assert any(
        diagnostic.foreground_token == "text.primary" and diagnostic.background_token == "panel.bg"
        for diagnostic in report
    )
    assert any("Flat Panel: Contrast warning: text.primary on panel.bg" in warning for warning in manager.diagnostics)


def test_theme_loader_returns_invalid_theme_without_crashing(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<theme", encoding="utf-8")
    loader = ThemeLoader()

    theme = loader.load_file(path)

    assert theme is not None
    assert theme.id == "broken"
    assert theme.version == "invalid"
    assert theme.warnings


def test_workspace_layout_loader_merges_file_overrides_with_diagnostics(tmp_path):
    layout_dir = tmp_path / "workspace_layouts"
    layout_dir.mkdir()
    override = {
        "layout_id": "modeling_compact_test",
        "name": "Modeling Compact Test",
        "module_id": "modeling",
        "main_width": 1440,
        "viewport": {"min_width": 700},
        "toolbar": {
            "workspace_button_mode": "iconOnly",
            "workspace_icon_size": 16,
        },
        "panels": {
            "scene": {"visible": False},
            "workers": {"visible": True, "area": "right"},
            "not_a_panel": {"visible": True},
        },
        "dock_groups": [
            {
                "group_id": "modeling_compact_left",
                "area": "left",
                "mode": "tabbed",
                "active": "content",
                "docks": ["workspace", "content", "modeling"],
            }
        ],
        "spacing": {"panelSpacing": 3, "badSpacing": "wide"},
    }
    (layout_dir / "modeling_compact.json").write_text(json.dumps(override), encoding="utf-8")
    (layout_dir / "broken.json").write_text("{", encoding="utf-8")

    result = load_workspace_layouts(layout_dirs=(layout_dir,))
    layout = result.layouts["modeling"]

    assert layout.layout_id == "modeling_compact_test"
    assert layout.name == "Modeling Compact Test"
    assert layout.main_width == 1440
    assert layout.viewport.min_width == 700
    assert layout.viewport.preferred_width == default_workspace_layouts()["modeling"].viewport.preferred_width
    assert layout.viewport.bottom_strip_visible is True
    assert layout.toolbar.workspace_button_mode == "iconOnly"
    assert layout.toolbar.workspace_icon_size == 16
    assert layout.panel("scene").visible is False
    assert layout.panel("workers").visible is True
    assert layout.panel("workers").area == "right"
    assert layout.panel("content").visible is True
    assert layout.dock_groups[0].group_id == "modeling_compact_left"
    assert layout.spacing_value("panelSpacing") == 3
    assert [item.layout_id for item in result.available_layouts["modeling"]] == [
        "modeling_default",
        "modeling_compact_test",
    ]
    assert any("not_a_panel" in warning for warning in layout.warnings)
    assert any("badSpacing" in warning for warning in layout.warnings)
    assert any("Could not parse workspace layout JSON" in warning for warning in result.diagnostics)
    assert any("overrides Modeling Studio" in warning for warning in result.diagnostics)


def test_workspace_layout_loader_catalogs_presets_without_auto_applying(tmp_path):
    layout_dir = tmp_path / "workspace_layouts"
    layout_dir.mkdir()
    preset = {
        "layout_id": "modeling_compact_preset_test",
        "name": "Modeling Compact Preset Test",
        "module_id": "modeling",
        "preset": True,
        "viewport": {"min_width": 740},
        "toolbar": {
            "workspace_button_mode": "iconOnly",
            "workspace_icon_size": 14,
        },
        "spacing": {"panelSpacing": 3},
    }
    (layout_dir / "modeling_compact_preset.json").write_text(json.dumps(preset), encoding="utf-8")

    result = load_workspace_layouts(layout_dirs=(layout_dir,))

    assert result.layouts["modeling"].layout_id == "modeling_default"
    assert [item.layout_id for item in result.available_layouts["modeling"]] == [
        "modeling_default",
        "modeling_compact_preset_test",
    ]
    assert not any("overrides Modeling Studio" in warning for warning in result.diagnostics)

    selected = load_workspace_layouts(
        layout_dirs=(layout_dir,),
        selected_layout_ids={"modeling": "modeling_compact_preset_test"},
    )

    assert selected.layouts["modeling"].layout_id == "modeling_compact_preset_test"
    assert selected.layouts["modeling"].viewport.min_width == 740
    assert selected.layouts["modeling"].toolbar.workspace_icon_size == 14
    assert selected.selected_layout_ids["modeling"] == "modeling_compact_preset_test"


def test_workspace_layout_loader_reads_xml_layouts(tmp_path):
    path = tmp_path / "uv_dense.xml"
    path.write_text(
        """
        <workspaceLayout id="uv_dense" name="UV Dense" version="1" module="uv_materials">
          <mainWindow width="1500" height="880" />
          <toolbars>
            <toolbar id="main" visible="true" />
            <toolbar id="workspace" visible="true" buttonMode="textUnderIcon" iconSize="17" />
          </toolbars>
          <panels>
            <panel id="content" area="left" visible="true" preferredWidth="360" />
            <panel id="audit" area="right" visible="false" />
          </panels>
          <dockLayout>
            <group id="uv_left" area="left" mode="tabbed" active="content">
              <dock id="workspace" />
              <dock id="content" />
              <dock id="graph" />
            </group>
          </dockLayout>
          <viewport>
            <region id="mainViewport" minWidth="760" preferredWidth="980" />
            <toolbar visible="true" buttonMode="textUnderIcon" />
            <bottomStrip visible="false" />
          </viewport>
        </workspaceLayout>
        """,
        encoding="utf-8",
    )

    loader = WorkspaceLayoutLoader(default_workspace_layouts())
    layout = loader.load_file(path)

    assert layout is not None
    assert layout.module_id == "uv_materials"
    assert layout.layout_id == "uv_dense"
    assert layout.main_width == 1500
    assert layout.main_height == 880
    assert layout.toolbar.workspace_button_mode == "textUnderIcon"
    assert layout.toolbar.workspace_icon_size == 17
    assert layout.viewport.min_width == 760
    assert layout.viewport.preferred_width == 980
    assert layout.viewport.bottom_strip_visible is False
    assert layout.panel("audit").visible is False
    assert layout.dock_groups[0].docks == ("workspace", "content", "graph")


def test_workspace_module_loader_reads_json_and_xml_modules(tmp_path):
    module_dir = tmp_path / "workspace_modules"
    module_dir.mkdir()
    (module_dir / "modeling_plus.json").write_text(
        json.dumps(
            {
                "module_id": "modeling",
                "label": "Modeling Plus",
                "summary": "Custom modeling shell.",
                "status": "custom",
                "primary_dock_ids": ["viewport", "scene", "modeling", "graph"],
                "secondary_dock_ids": ["theme", "not_a_dock"],
                "toolbar_action_ids": ["file.import_mesh", "view.frame_all"],
                "viewport_defaults": {
                    "display_mode": "xray",
                    "selection_mode": "face",
                    "transform_mode": "move",
                    "navigation_profile": "blender",
                    "gizmo_orientation": "local",
                    "gizmo_pivot": "object_origin",
                },
            }
        ),
        encoding="utf-8",
    )
    (module_dir / "paint_room.xml").write_text(
        """
        <workspaceModule id="paint_room" label="Paint Room" status="custom" shortcut="Ctrl+7">
          <summary>Texture painting and material review.</summary>
          <primaryDocks>
            <dock id="viewport" />
            <dock id="content" />
            <dock id="properties" />
          </primaryDocks>
          <toolbarActions>
            <action id="asset.texture" />
          </toolbarActions>
          <viewportDefaults displayMode="solid" selectionMode="face" navigationProfile="maya" />
        </workspaceModule>
        """,
        encoding="utf-8",
    )
    (module_dir / "broken.json").write_text("{not json", encoding="utf-8")

    result = load_workspace_modules(module_dirs=(module_dir,))
    modules = {module.module_id: module for module in result.modules}

    assert modules["modeling"].label == "Modeling Plus"
    assert modules["modeling"].viewport_defaults.display_mode == "xray"
    assert modules["modeling"].viewport_defaults.gizmo_orientation == "local"
    assert modules["modeling"].viewport_defaults.gizmo_pivot == "object_origin"
    assert modules["modeling"].source_path is not None
    assert any("not_a_dock" in warning for warning in modules["modeling"].warnings)
    assert modules["paint_room"].primary_dock_ids == ("viewport", "content", "properties")
    assert modules["paint_room"].toolbar_action_ids == ("asset.texture",)
    assert modules["paint_room"].shortcut == "Ctrl+7"
    assert any("Could not parse workspace module JSON" in warning for warning in result.diagnostics)
    assert any("Custom workspace module 'paint_room'" in warning for warning in result.diagnostics)

    loader = WorkspaceModuleLoader(default_workspace_modules())
    assert loader.load_file(module_dir / "paint_room.xml") is not None


def test_workspace_resource_watcher_tracks_modules_and_layouts(qapp, tmp_path):
    module_dir = tmp_path / "workspace_modules"
    layout_dir = tmp_path / "workspace_layouts"
    module_dir.mkdir()
    layout_dir.mkdir()
    module_file = module_dir / "paint_room.json"
    layout_file = layout_dir / "paint_room_layout.xml"
    module_file.write_text('{"module_id": "paint_room"}', encoding="utf-8")
    layout_file.write_text('<workspaceLayout module_id="paint_room" />', encoding="utf-8")
    watcher = WorkspaceResourceWatcher((module_dir,), (layout_dir,), debounce_ms=1)
    modules: list[str] = []
    layouts: list[str] = []
    watcher.modulesChanged.connect(lambda: modules.append("modules"))
    watcher.layoutsChanged.connect(lambda: layouts.append("layouts"))

    watcher.set_enabled(True)
    watched = watcher.watched_paths()

    assert module_dir in watched
    assert layout_dir in watched
    assert module_file in watched
    assert layout_file in watched

    watcher.trigger_reload("modules")
    watcher.trigger_reload("layouts")

    assert modules == ["modules"]
    assert layouts == ["layouts"]

    watcher.set_enabled(False)

    assert watcher.watched_paths() == ()


def test_workspace_module_panel_lists_universal_modules(qapp):
    layouts = default_workspace_layouts()
    generation_preset = replace(
        layouts["generation"],
        layout_id="generation_wide_test",
        name="Generation Wide Test",
    )
    available = {module_id: (layout,) for module_id, layout in layouts.items()}
    available["generation"] = (layouts["generation"], generation_preset)
    panel = WorkspaceModulePanel(default_workspace_modules(), layouts, available)
    activated: list[str] = []
    module_reloaded: list[bool] = []
    reloaded: list[bool] = []
    selected_layouts: list[tuple[str, str]] = []
    panel.moduleActivated.connect(activated.append)
    panel.moduleReloadRequested.connect(lambda: module_reloaded.append(True))
    panel.layoutReloadRequested.connect(lambda: reloaded.append(True))
    panel.layoutSelected.connect(lambda module_id, layout_id: selected_layouts.append((module_id, layout_id)))
    live_reload: list[bool] = []
    panel.liveReloadToggled.connect(live_reload.append)

    try:
        assert panel.model.rowCount() >= 6
        assert panel.model.columnCount() == 5
        assert "shaded / object / move" in panel.summary.text()
        assert "Layout:" in panel.summary.text()
        assert "toolbar textBesideIcon" in panel.summary.text()
        assert panel.layout_combo.currentData() == "modeling_default"
        assert "Layout diagnostics: clean." in panel.layout_diagnostics.text()
        assert "live reload off" in panel.resource_watch_label.text()
        assert panel.select_module("generation")
        assert panel.current_module_id() == "generation"
        assert "AI worker status" in panel.summary.text()
        assert "Viewport:" in panel.summary.text()
        assert "Generation Studio" in panel.summary.text()
        assert panel.layout_combo.count() == 2
        assert panel.layout_combo.currentData() == "generation_default"
        assert "textBesideIcon" in panel.model.data(panel.model.index(1, 4))

        panel.set_layouts(
            {**layouts, "generation": generation_preset},
            available_layouts=available,
            layout_diagnostics=("custom layout warning",),
        )

        assert panel.current_module_id() == "generation"
        assert panel.layout_combo.currentData() == "generation_wide_test"
        assert "custom layout warning" in panel.layout_diagnostics.text()

        panel.layout_combo.setCurrentIndex(0)
        panel.set_resource_watch_state(True, ("workspace_modules/modeling.json", "workspace_layouts/modeling.json"))
        panel.live_reload_check.setChecked(False)
        panel.activate_current()
        panel.reload_modules_button.click()
        panel.reload_layouts_button.click()

        assert activated == ["generation"]
        assert module_reloaded == [True]
        assert reloaded == [True]
        assert "Module diagnostics: clean." in panel.module_diagnostics.text()
        assert "watching 2 paths" in panel.resource_watch_label.text()
        assert live_reload == [False]
        assert selected_layouts == [("generation", "generation_default")]
    finally:
        panel.deleteLater()


def test_viewport_host_updates_modes_and_theme(qapp):
    viewport = ViewportHost()
    manager = ThemeManager()

    try:
        viewport.set_selection_mode("face")
        viewport.set_transform_mode("rotate")
        viewport.set_display_mode("wireframe")
        viewport.set_navigation_profile("blender")
        viewport.set_camera_preset("bottom")
        viewport.set_projection_mode("orthographic")
        viewport.set_grid_visible(False)
        viewport.set_snap_enabled(True)
        viewport.set_view_cube_visible(False)
        viewport.apply_theme(manager.select("studio_light"))

        canvas = viewport.renderer.canvas
        assert canvas.selection_mode == "face"
        assert canvas.transform_mode == "rotate"
        assert canvas.display_mode == "wireframe"
        assert canvas.navigation.profile == "blender"
        assert canvas.camera_preset == "bottom"
        assert canvas.navigation.projection_mode == "orthographic"
        assert viewport.camera_combo.currentData() == "bottom"
        assert viewport.snap_view_buttons["bottom"].isChecked() is True
        assert viewport.projection_button.text() == "Ortho"
        assert "Blender profile" in viewport.navigation_combo.toolTip()
        assert VIEWPORT_NAVIGATION_HELP in viewport.navigation_combo.toolTip()
        assert canvas.navigation.grid_visible is False
        assert canvas.navigation.snap_enabled is True
        assert canvas.view_cube_visible is False
        assert canvas.theme.id == "studio_light"
    finally:
        viewport.deleteLater()


def test_viewport_diagnostics_model_formats_renderer_state(qapp):
    model = ViewportDiagnosticsModel()

    model.set_diagnostics(
        {
            "backend_id": "cpu_projected",
            "renderer_name": "CPU Projected Viewport",
            "available": True,
            "supports_scene_meshes": True,
            "supports_object_picking": True,
            "supports_frame_selected": True,
            "supports_subobject_selection": True,
            "supports_gizmo_interaction": False,
            "supports_gizmo_plane_handles": True,
            "supports_projection_modes": True,
            "object_count": 2,
            "mesh_count": 2,
            "vertex_count": 16,
            "edge_count": 24,
            "face_count": 12,
            "display_mode": "wireframe",
            "selection_mode": "face",
            "transform_mode": "move",
            "gizmo_orientation": "local",
            "gizmo_pivot": "object_origin",
            "camera_preset": "top",
            "projection_mode_label": "Orthographic",
            "navigation_profile_label": "Blender",
            "zoom": 1.25,
            "grid_visible": False,
            "snap_enabled": True,
            "view_cube_visible": True,
            "selection_counts": {"objects": 1, "faces": 3},
        }
    )

    rows = {(row.category, row.name): row.value for row in model.rows()}

    assert model.rowCount() >= 20
    assert rows[("Renderer", "Name")] == "CPU Projected Viewport"
    assert rows[("Capabilities", "Frame Selected")] == "yes"
    assert rows[("Capabilities", "Gizmo Interaction")] == "no"
    assert rows[("Capabilities", "Gizmo Plane Handles")] == "yes"
    assert rows[("Scene", "Vertices")] == "16"
    assert rows[("Mode", "Gizmo Orientation")] == "local"
    assert rows[("Mode", "Gizmo Pivot")] == "object_origin"
    assert rows[("Camera", "Projection")] == "Orthographic"
    assert rows[("Camera", "Navigation")] == "Blender"
    assert rows[("Camera", "Zoom")] == "1.25x"
    assert rows[("Selection", "Faces")] == "3"


def test_viewport_panel_controls_host_and_renders_diagnostics(qapp):
    viewport = ViewportHost()
    panel = ViewportPanel(viewport)
    try:
        panel.display_combo.setCurrentText("wireframe")
        panel.selection_combo.setCurrentText("face")
        panel.transform_combo.setCurrentText("rotate")
        panel.gizmo_orientation_combo.setCurrentIndex(panel.gizmo_orientation_combo.findData("local"))
        panel.gizmo_pivot_combo.setCurrentIndex(panel.gizmo_pivot_combo.findData("object_origin"))
        panel.navigation_combo.setCurrentIndex(panel.navigation_combo.findData("blender"))
        panel.camera_combo.setCurrentIndex(panel.camera_combo.findData("top"))
        panel.projection_button.setChecked(True)
        panel.grid_check.setChecked(False)
        panel.snap_check.setChecked(True)
        panel.view_cube_check.setChecked(False)

        canvas = viewport.renderer.canvas

        assert canvas.display_mode == "wireframe"
        assert canvas.selection_mode == "face"
        assert canvas.transform_mode == "rotate"
        assert canvas.gizmo_orientation == "local"
        assert canvas.gizmo_pivot == "object_origin"
        assert canvas.navigation.profile == "blender"
        assert canvas.camera_preset == "top"
        assert canvas.navigation.projection_mode == "orthographic"
        assert canvas.navigation.grid_visible is False
        assert canvas.navigation.snap_enabled is True
        assert canvas.view_cube_visible is False
        assert "CPU Projected Viewport" in panel.summary.text()
        assert panel.model.rowCount() > 0

        viewport.set_display_mode("xray")
        viewport.set_camera_preset("front")
        viewport.set_projection_mode("perspective")
        viewport.set_gizmo_orientation("world")
        viewport.set_gizmo_pivot("bounds_center")

        assert panel.display_combo.currentText() == "xray"
        assert panel.camera_combo.currentData() == "front"
        assert panel.gizmo_orientation_combo.currentData() == "world"
        assert panel.gizmo_pivot_combo.currentData() == "bounds_center"
        assert panel.snap_view_buttons["front"].isChecked() is True
        assert panel.projection_button.text() == "Persp"
    finally:
        panel.deleteLater()
        viewport.deleteLater()


def test_viewport_snap_view_buttons_sync_host_panel_and_renderer(qapp):
    viewport = ViewportHost()
    panel = ViewportPanel(viewport)
    try:
        viewport.snap_view_buttons["top"].click()

        canvas = viewport.renderer.canvas
        assert canvas.camera_preset == "top"
        assert viewport.camera_combo.currentData() == "top"
        assert viewport.snap_view_buttons["top"].isChecked() is True
        assert panel.camera_combo.currentData() == "top"
        assert panel.snap_view_buttons["top"].isChecked() is True

        panel.snap_view_buttons["left"].click()

        assert canvas.camera_preset == "left"
        assert viewport.camera_combo.currentData() == "left"
        assert viewport.snap_view_buttons["left"].isChecked() is True
        assert panel.camera_combo.currentData() == "left"

        viewport.projection_button.setChecked(True)

        assert canvas.navigation.projection_mode == "orthographic"
        assert viewport.navigation_state()["projection_mode"] == "orthographic"
        assert panel.projection_button.text() == "Ortho"
        assert viewport.viewport_diagnostics()["projection_mode"] == "orthographic"

        panel.projection_button.setChecked(False)

        assert canvas.navigation.projection_mode == "perspective"
        assert viewport.projection_button.text() == "Persp"
    finally:
        panel.deleteLater()
        viewport.deleteLater()


def test_viewport_frame_selected_recenters_object_and_subobject(qapp, tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(path)
    viewport = ViewportHost()
    left = SceneObjectRecord(
        object_id="obj_left",
        name="Left",
        path=path,
        transform=TransformState(translate=(-4.0, 0.0, 0.0)),
    )
    right = SceneObjectRecord(
        object_id="obj_right",
        name="Right",
        path=path,
        transform=TransformState(translate=(4.0, 0.0, 0.0)),
    )

    try:
        viewport.resize(800, 520)
        viewport.renderer.canvas.resize(800, 520)
        viewport.set_scene_records([left, right])
        viewport.set_selection_state(
            MeshSelectionState(active_object_id="obj_right", selected_object_ids={"obj_right"})
        )
        canvas = viewport.renderer.canvas
        canvas.navigation.zoom = 0.5
        canvas.navigation.pan_x = -180.0
        canvas.navigation.pan_y = 90.0

        assert viewport.frame_selected() is True

        active = next(item for item in canvas.projected_objects() if item.obj.object_id == "obj_right")
        active_center = active.projected.mean(axis=0)
        viewport_center = np.array([canvas.rect().center().x(), canvas.rect().center().y()], dtype=float)

        assert np.linalg.norm(active_center - viewport_center) < 3.0
        assert canvas.navigation.zoom > 0.5
        diagnostics = viewport.viewport_diagnostics()
        assert diagnostics["supports_frame_selected"] is True
        assert diagnostics["frame_selection_available"] is True

        viewport.set_selection_state(
            MeshSelectionState(
                active_object_id="obj_right",
                selected_object_ids={"obj_right"},
                selected_vertices={0},
            )
        )
        canvas.navigation.zoom = 1.0
        canvas.navigation.pan_x = 120.0
        canvas.navigation.pan_y = -75.0

        assert viewport.frame_selected() is True

        active = next(item for item in canvas.projected_objects() if item.obj.object_id == "obj_right")
        vertex_point = active.projected[0]

        assert np.linalg.norm(vertex_point - viewport_center) < 3.0
    finally:
        viewport.deleteLater()


def test_viewport_navigation_state_round_trips_and_profile_shortcuts(qapp):
    viewport = ViewportHost()
    restored = ViewportHost()
    try:
        viewport.set_navigation_profile("blender")
        canvas = viewport.renderer.canvas
        canvas.navigation.zoom = 2.25
        canvas.navigation.pan_x = 31.0
        canvas.navigation.pan_y = -12.0
        canvas.navigation.orbit_yaw_deg = 44.0
        canvas.navigation.orbit_pitch_deg = 18.0

        back_event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_1,
            QtCore.Qt.KeyboardModifier.ControlModifier,
        )
        canvas.keyPressEvent(back_event)

        assert canvas.camera_preset == "back"
        assert viewport.camera_combo.currentData() == "back"

        projection_event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_5,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        canvas.keyPressEvent(projection_event)

        assert canvas.navigation.projection_mode == "orthographic"

        state = viewport.navigation_state()
        state["display_mode"] = "xray"
        state["grid_visible"] = False
        state["snap_enabled"] = True
        state["view_cube_visible"] = False
        state["gizmo_orientation"] = "local"
        state["gizmo_pivot"] = "object_origin"

        restored.restore_navigation_state(state)
        restored_canvas = restored.renderer.canvas

        assert restored_canvas.navigation.profile == "blender"
        assert restored_canvas.camera_preset == "back"
        assert restored_canvas.navigation.projection_mode == "orthographic"
        assert restored_canvas.display_mode == "xray"
        assert restored_canvas.navigation.zoom == 2.25
        assert restored_canvas.navigation.pan_x == 31.0
        assert restored_canvas.navigation.pan_y == -12.0
        assert restored_canvas.navigation.grid_visible is False
        assert restored_canvas.navigation.snap_enabled is True
        assert restored_canvas.view_cube_visible is False
        assert restored_canvas.gizmo_orientation == "local"
        assert restored_canvas.gizmo_pivot == "object_origin"
        assert restored.camera_combo.currentData() == "back"
        assert restored.projection_button.text() == "Ortho"
        assert restored.grid_button.isChecked() is False
        assert restored.snap_button.isChecked() is True
        assert restored.gizmo_orientation_combo.currentData() == "local"
        assert restored.gizmo_pivot_combo.currentData() == "object_origin"

        canvas.navigation.zoom = 3.0
        canvas.navigation.pan_x = 40.0
        frame_selected_event = QtGui.QKeyEvent(
            QtCore.QEvent.Type.KeyPress,
            QtCore.Qt.Key.Key_Period,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        canvas.keyPressEvent(frame_selected_event)

        assert canvas.navigation.zoom == 1.0
        assert canvas.navigation.pan_x == 0.0
    finally:
        viewport.deleteLater()
        restored.deleteLater()


def test_viewport_navigation_mouse_profiles_and_drag_math(qapp):
    alt = QtCore.Qt.KeyboardModifier.AltModifier
    shift = QtCore.Qt.KeyboardModifier.ShiftModifier
    ctrl = QtCore.Qt.KeyboardModifier.ControlModifier
    none = QtCore.Qt.KeyboardModifier.NoModifier

    assert viewport_navigation_mouse_action("maya", QtCore.Qt.MouseButton.LeftButton, alt) == "orbit"
    assert viewport_navigation_mouse_action("maya", QtCore.Qt.MouseButton.MiddleButton, alt) == "pan"
    assert viewport_navigation_mouse_action("maya", QtCore.Qt.MouseButton.RightButton, alt) == "zoom"
    assert viewport_navigation_mouse_action("blender", QtCore.Qt.MouseButton.MiddleButton, none) == "orbit"
    assert viewport_navigation_mouse_action("blender", QtCore.Qt.MouseButton.MiddleButton, shift) == "pan"
    assert viewport_navigation_mouse_action("blender", QtCore.Qt.MouseButton.MiddleButton, ctrl) == "zoom"
    assert viewport_navigation_mouse_action("3dsmax", QtCore.Qt.MouseButton.MiddleButton, alt) == "orbit"
    assert viewport_navigation_mouse_action("3dsmax", QtCore.Qt.MouseButton.MiddleButton, none) == "pan"
    assert viewport_navigation_mouse_action("3dsmax", QtCore.Qt.MouseButton.RightButton, alt) == "zoom"

    state = ViewportNavigationState(profile="maya")
    pan_origin = ViewportNavigationDragOrigin.from_state("pan", state)
    assert apply_viewport_navigation_drag(state, pan_origin, 24.0, -12.0)
    assert state.pan_x == 24.0
    assert state.pan_y == -12.0

    orbit_origin = ViewportNavigationDragOrigin.from_state("orbit", state)
    assert apply_viewport_navigation_drag(state, orbit_origin, 20.0, 400.0)
    assert state.camera_preset == "perspective"
    assert round(state.orbit_yaw_deg, 2) == round(orbit_origin.orbit_yaw_deg + 7.0, 2)
    assert state.orbit_pitch_deg == 85.0

    zoom_origin = ViewportNavigationDragOrigin.from_state("zoom", state)
    assert apply_viewport_navigation_drag(state, zoom_origin, 0.0, -50.0)
    assert round(state.zoom, 2) == round(zoom_origin.zoom * 1.5, 2)
    assert viewport_wheel_zoom(1.0, 120.0) == 1.1
    assert viewport_wheel_zoom(1.0, -5000.0) == 0.12


def test_transform_gizmo_drag_math_move_rotate_scale():
    assert normalize_gizmo_orientation("local") == "local"
    assert normalize_gizmo_pivot("origin") == "object_origin"
    handle = TransformGizmoHandle(
        axis="x",
        start=(100.0, 100.0),
        end=(160.0, 100.0),
        pixels_per_unit=30.0,
        basis=(("x", (1.0, 0.0)),),
        world_basis=(("x", (1.0, 0.0, 0.0)),),
    )
    base = TransformState()

    move = transform_gizmo_edit_from_drag(
        TransformGizmoDragOrigin("obj_cube", "move", "x", (100.0, 100.0), handle, base),
        (160.0, 100.0),
    )
    rotate = transform_gizmo_edit_from_drag(
        TransformGizmoDragOrigin("obj_cube", "rotate", "x", (100.0, 100.0), handle, base),
        (120.0, 100.0),
        snap=True,
    )
    scale = transform_gizmo_edit_from_drag(
        TransformGizmoDragOrigin("obj_cube", "scale", "x", (100.0, 100.0), handle, base),
        (130.0, 100.0),
    )

    assert move.transform.translate == (2.0, 0.0, 0.0)
    assert move.phase == "update"
    assert move.before_transform == base
    assert rotate.transform.rotate_euler_deg == (10.0, 0.0, 0.0)
    assert round(scale.transform.scale[0], 2) == 1.3


def test_transform_gizmo_plane_drag_moves_two_axes():
    handle = TransformGizmoHandle(
        axis="xy",
        start=(100.0, 100.0),
        end=(124.0, 76.0),
        pixels_per_unit=24.0,
        kind="plane",
        basis=(("x", (1.0, 0.0)), ("y", (0.0, -1.0))),
        world_basis=(("x", (1.0, 0.0, 0.0)), ("y", (0.0, 1.0, 0.0))),
        hit_radius=11.0,
    )
    edit = transform_gizmo_edit_from_drag(
        TransformGizmoDragOrigin("obj_cube", "move", "xy", (100.0, 100.0), handle, TransformState()),
        (124.0, 76.0),
        phase="end",
    )

    assert edit.axis == "xy"
    assert edit.phase == "end"
    assert edit.transform.translate == (1.0, 1.0, 0.0)


def test_viewport_transform_gizmo_emits_object_transform_edits(qapp, tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(path)
    viewport = ViewportHost()
    record = SceneObjectRecord(object_id="obj_cube", name="Cube", path=path)
    edits = []
    viewport.transformEdited.connect(edits.append)

    try:
        viewport.resize(640, 480)
        viewport.renderer.canvas.resize(640, 480)
        viewport.set_scene_records([record])
        viewport.set_transform_mode("move")
        state = MeshSelectionState(active_object_id="obj_cube", selected_object_ids={"obj_cube"})
        viewport.set_selection_state(state)

        canvas = viewport.renderer.canvas
        handles = canvas.transform_gizmo_handles()

        assert set(handles) == {"x", "y", "z", "xy", "xz", "yz"}
        assert viewport.viewport_diagnostics()["supports_gizmo_interaction"] is True
        assert viewport.viewport_diagnostics()["supports_gizmo_plane_handles"] is True
        assert viewport.viewport_diagnostics()["transform_gizmo_visible"] is True

        start = QtCore.QPointF(*handles["x"].start)
        end = QtCore.QPointF(handles["x"].end[0], handles["x"].end[1])
        press = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonPress,
            start,
            start,
            start,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        move = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove,
            end,
            end,
            end,
            QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        release = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonRelease,
            end,
            end,
            end,
            QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier,
        )
        canvas.mousePressEvent(press)
        canvas.mouseMoveEvent(move)
        canvas.mouseReleaseEvent(release)

        assert edits
        assert edits[-1].object_id == "obj_cube"
        assert edits[-1].mode == "move"
        assert edits[-1].axis == "x"
        assert edits[-1].phase == "end"
        assert edits[-1].before_transform == TransformState()
        assert edits[-1].transform.translate[0] > 0.0
    finally:
        viewport.deleteLater()


def test_viewport_status_strip_reports_diagnostics_and_selection(qapp, tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(path)
    viewport = ViewportHost()
    record = SceneObjectRecord(object_id="obj_cube", name="Cube", path=path)

    try:
        viewport.resize(640, 480)
        viewport.renderer.canvas.resize(640, 480)
        viewport.set_scene_records([record])
        viewport.set_display_mode("xray")
        viewport.set_camera_preset("top")
        viewport.set_projection_mode("orthographic")
        viewport.set_navigation_profile("3dsmax")

        state = MeshSelectionState(
            active_object_id="obj_cube",
            selected_object_ids={"obj_cube"},
            selected_vertices={0, 1},
            selected_edges={(0, 1)},
            selected_faces={0},
        )
        viewport.set_selection_state(state)

        diagnostics = viewport.refresh_diagnostics()

        assert viewport.layout().stretch(1) == 1
        assert viewport.status_strip.maximumHeight() <= 28
        assert viewport.status_strip.sizePolicy().verticalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed
        assert viewport.renderer.widget().sizePolicy().verticalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
        assert diagnostics["backend_id"] == "cpu_projected"
        assert diagnostics["supports_object_picking"] is True
        assert diagnostics["supports_gizmo_interaction"] is True
        assert diagnostics["object_count"] == 1
        assert diagnostics["vertex_count"] == 8
        assert diagnostics["face_count"] == 12
        assert diagnostics["selection_counts"]["vertices"] == 2
        assert "CPU Projected Viewport" in viewport.renderer_status_label.text()
        assert "1 objects" in viewport.scene_stats_label.text()
        assert "8 verts" in viewport.scene_stats_label.text()
        assert "xray" in viewport.mode_status_label.text()
        assert "Top" in viewport.camera_status_label.text()
        assert "Orthographic" in viewport.camera_status_label.text()
        assert "3ds Max" in viewport.camera_status_label.text()
        assert "vertices:2" in viewport.selection_status_label.text()

        viewport.status_strip_button.setChecked(False)
        assert viewport.status_strip.isHidden()
        viewport.status_strip_button.setChecked(True)
        assert not viewport.status_strip.isHidden()
    finally:
        viewport.deleteLater()


def test_viewport_view_cube_hit_testing_and_presets(qapp):
    viewport = ViewportHost()
    try:
        viewport.resize(640, 480)
        canvas = viewport.renderer.canvas
        canvas.resize(640, 480)
        panel = view_cube_panel_rect(canvas.rect())
        regions = view_cube_regions(panel)

        front = canvas.view_cube_region_at(regions["front"].rect.center())

        assert front is not None
        assert front.key == "front"

        canvas.activate_view_cube_region("right")
        assert canvas.camera_preset == "right"
        assert canvas.navigation.camera_preset == "right"

        canvas.activate_view_cube_region("bottom")
        assert canvas.camera_preset == "bottom"

        canvas.navigation.zoom = 2.5
        canvas.navigation.pan_x = 25.0
        canvas.activate_view_cube_region("home")

        assert canvas.camera_preset == "perspective"
        assert canvas.navigation.zoom == 1.0
        assert canvas.navigation.pan_x == 0.0
    finally:
        viewport.deleteLater()


def test_viewport_canvas_picks_projected_object_vertex_and_edge(qapp, tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(path)
    viewport = ViewportHost()
    record = SceneObjectRecord(object_id="obj_cube", name="Cube", path=path)

    try:
        viewport.resize(640, 480)
        viewport.renderer.canvas.resize(640, 480)
        viewport.set_scene_records([record])
        canvas = viewport.renderer.canvas
        frame = canvas.projected_objects()
        assert len(frame) == 1

        center = frame[0].projected.mean(axis=0)
        object_pick = canvas.pick_at(QtCore.QPointF(float(center[0]), float(center[1])), mode="object")
        assert object_pick is not None
        assert object_pick.object_id == "obj_cube"

        vertex_point = frame[0].projected[0]
        vertex_pick = canvas.pick_at(
            QtCore.QPointF(float(vertex_point[0]), float(vertex_point[1])),
            mode="vertex",
        )
        assert vertex_pick is not None
        assert vertex_pick.vertex_index == 0

        a, b = frame[0].mesh.edges[0]
        midpoint = (frame[0].projected[a] + frame[0].projected[b]) * 0.5
        edge_pick = canvas.pick_at(QtCore.QPointF(float(midpoint[0]), float(midpoint[1])), mode="edge")
        assert edge_pick is not None
        assert edge_pick.edge == tuple(sorted((int(a), int(b))))

        border_pick = canvas.pick_at(QtCore.QPointF(float(midpoint[0]), float(midpoint[1])), mode="border")
        assert border_pick is not None
        assert border_pick.edge_index is not None

        face = frame[0].mesh.faces[0]
        face_center = frame[0].projected[face].mean(axis=0)
        face_pick = canvas.pick_at(QtCore.QPointF(float(face_center[0]), float(face_center[1])), mode="face")
        assert face_pick is not None
        assert face_pick.face_index is not None

        element_pick = canvas.pick_at(QtCore.QPointF(float(face_center[0]), float(face_center[1])), mode="element")
        assert element_pick is not None
        assert element_pick.element_index is not None
    finally:
        viewport.deleteLater()


def test_mesh_preview_loads_real_geometry(tmp_path):
    path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(path)

    preview = load_mesh_preview(path)

    assert len(preview.vertices) == 8
    assert len(preview.faces) == 12
    assert len(preview.edges) >= 12
    assert preview.extent == 3


def test_mesh_operation_service_writes_normalized_output(tmp_path):
    input_path = tmp_path / "wide.glb"
    trimesh.creation.box(extents=(2, 4, 8)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply("normalize_scale", input_path)

    assert result.path.exists()
    assert result.info.faces == 12
    assert max(result.info.size or []) <= 1.000001


def test_mesh_operation_service_writes_smooth_and_subdivide_outputs(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    smooth = service.apply("smooth_laplacian", input_path, smooth_iterations=1)
    subdivide = service.apply("subdivide", input_path, subdivide_iterations=1)

    assert smooth.path.exists()
    assert subdivide.path.exists()
    assert subdivide.info.faces > 12


def test_mesh_operation_service_deletes_selected_face(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "delete",
        input_path,
        selection=MeshOperationSelection(mode="face", faces={0}),
    )

    assert result.path.exists()
    assert result.info.faces == 11


def test_mesh_operation_service_welds_selected_vertices(tmp_path):
    input_path = tmp_path / "quad.glb"
    mesh = trimesh.Trimesh(
        vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        faces=[(0, 1, 2), (1, 3, 2)],
        process=False,
    )
    mesh.export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "weld",
        input_path,
        selection=MeshOperationSelection(mode="vertex", vertices={0, 1}),
    )

    assert result.path.exists()
    assert result.info.vertices == 3
    assert result.info.faces == 1


def test_mesh_operation_service_flips_selected_face_normals(tmp_path):
    input_path = tmp_path / "quad.glb"
    mesh = trimesh.Trimesh(
        vertices=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
        faces=[(0, 1, 2), (1, 3, 2)],
        process=False,
    )
    mesh.export(input_path)
    service = MeshOperationService(tmp_path / "outputs")

    result = service.apply(
        "flip_normals",
        input_path,
        selection=MeshOperationSelection(mode="face", faces={0}),
    )
    reloaded = trimesh.load(str(result.path), force="mesh", process=False)

    assert result.path.exists()
    assert reloaded.face_normals[0][2] < 0
    assert reloaded.face_normals[1][2] > 0


def test_mesh_diagnostics_reports_topology_summary(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)

    summary = analyze_mesh(input_path)

    assert summary.vertices == 8
    assert summary.faces == 12
    assert summary.edges >= 12
    assert summary.connected_elements == 1
    assert summary.warning_text


def test_editable_mesh_snapshot_builds_stable_topology(tmp_path):
    input_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(input_path)

    snapshot = EditableMeshSnapshot.from_path(input_path)
    validation = snapshot.validate()

    assert snapshot.vertex_order[0] == "v_000000"
    assert snapshot.face_order[0] == "f_000000"
    assert snapshot.vertex_count == 8
    assert snapshot.face_count == 12
    assert snapshot.edge_count >= 18
    assert validation.status == "passed"
    assert snapshot.face_neighbors("f_000000")


def test_editable_mesh_validation_and_components_for_open_mesh():
    snapshot = EditableMeshSnapshot.from_arrays(
        np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (3.0, 0.0, 0.0),
                (4.0, 0.0, 0.0),
                (3.0, 1.0, 0.0),
            ]
        ),
        np.asarray([(0, 1, 2), (3, 4, 5)]),
    )

    validation = snapshot.validate()

    assert validation.status == "warnings"
    assert "boundary edges" in " ".join(validation.warnings)
    assert snapshot.connected_face_component("f_000000") == {"f_000000"}
    assert snapshot.connected_face_component("f_000001") == {"f_000001"}


def test_editable_mesh_history_deletes_faces_and_undoes():
    snapshot = EditableMeshSnapshot.from_arrays(
        np.asarray(
            [
                (0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0),
                (0.0, 1.0, 0.0),
                (1.0, 1.0, 0.0),
            ]
        ),
        np.asarray([(0, 1, 2), (1, 3, 2)]),
    )
    history = EditableMeshHistory(snapshot)
    shared_edge_before = _edge_for_vertices(snapshot, "v_000001", "v_000002")

    delta = history.delete_faces({"f_000000"})

    assert delta.removed_face_ids == ("f_000000",)
    assert history.current.face_order == ("f_000001",)
    assert "v_000000" not in history.current.vertices
    assert _edge_for_vertices(history.current, "v_000001", "v_000002") == shared_edge_before
    assert history.undo() == delta
    assert history.current.face_count == 2
    assert history.redo() == delta
    assert history.current.face_count == 1


def _edge_for_vertices(snapshot: EditableMeshSnapshot, a: str, b: str) -> str | None:
    target = tuple(sorted((a, b)))
    for edge in snapshot.edges.values():
        if tuple(sorted(edge.vertex_ids)) == target:
            return edge.id
    return None


def test_mesh_selection_state_counts_and_mode_clear():
    state = MeshSelectionState(active_object_id="obj")
    state.selected_vertices = {1, 2, 3}
    state.set_mode("face")

    assert state.selected_vertices == set()
    assert state.mode == "face"
    assert state.counts()["vertices"] == 0


def test_operation_history_undo_redo_path_commands(tmp_path):
    history = OperationHistory()
    command = ScenePathCommand(
        label="normalize_scale",
        object_id="obj",
        before_path=tmp_path / "before.glb",
        after_path=tmp_path / "after.glb",
    )

    history.record(command)

    assert history.undo() == command
    assert history.redo() == command


def test_operation_history_undo_redo_transform_commands():
    history = OperationHistory()
    command = SceneTransformCommand(
        label="move_gizmo_x",
        object_id="obj",
        before_transform=TransformState(),
        after_transform=TransformState(translate=(1.5, 0.0, 0.0)),
    )

    history.record(command)

    assert history.undo() == command
    assert history.redo() == command


def test_operation_history_undo_redo_scene_delete_commands(tmp_path):
    history = OperationHistory()
    record = SceneObjectRecord(object_id="obj", name="Cube", path=tmp_path / "cube.glb")
    command = SceneDeleteCommand(label="delete_scene_objects", rows=(0,), records=(record,))

    history.record(command)

    assert history.undo() == command
    assert history.redo() == command


def test_modeling_tools_uses_tabbed_scrollable_layout(qapp):
    panel = ModelingToolsPanel()
    try:
        assert panel.tabs.count() == 3
        assert [panel.tabs.tabText(index) for index in range(panel.tabs.count())] == [
            "Select",
            "Transform",
            "Mesh Ops",
        ]
        assert panel.findChild(QtWidgets.QScrollArea, "GhostForgeModelingSelectScroll") is not None
        assert panel.findChild(QtWidgets.QScrollArea, "GhostForgeModelingTransformScroll") is not None
        assert panel.findChild(QtWidgets.QScrollArea, "GhostForgeModelingMeshOpsScroll") is not None
        assert "delete_scene" in panel._command_buttons
        assert "delete_generated" in panel._command_buttons
    finally:
        panel.deleteLater()


def test_modeling_tools_emit_viewport_modes(qapp):
    panel = ModelingToolsPanel()
    seen: list[tuple[str, str]] = []
    panel.selectionModeRequested.connect(lambda mode: seen.append(("selection", mode)))
    panel.transformModeRequested.connect(lambda mode: seen.append(("transform", mode)))

    try:
        panel._selection_buttons["face"].click()
        panel._transform_buttons["scale"].click()

        assert ("selection", "face") in seen
        assert ("transform", "scale") in seen
    finally:
        panel.deleteLater()


def test_modeling_tools_emit_transform_edits(qapp):
    panel = ModelingToolsPanel()
    seen = []
    panel.transformEdited.connect(seen.append)

    try:
        panel._translate["X"].setValue(3.5)

        assert seen
        assert seen[-1].translate[0] == 3.5
    finally:
        panel.deleteLater()


def test_modeling_tools_exposes_operation_options(qapp):
    panel = ModelingToolsPanel()
    try:
        panel.decimate_ratio.setValue(0.25)
        panel.smooth_iterations.setValue(7)

        options = panel.operation_options()

        assert options["target_ratio"] == 0.25
        assert options["smooth_iterations"] == 7
    finally:
        panel.deleteLater()
