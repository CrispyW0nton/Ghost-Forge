from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .theme_loader import ThemeLoader
from .theme_model import Theme, built_in_themes
from .theme_validator import ThemeDiagnostic
from .theme_watcher import ThemeWatcher


class ThemeManager(QtCore.QObject):
    themeChanged = QtCore.Signal(object)
    themesReloaded = QtCore.Signal(object)
    liveReloadChanged = QtCore.Signal(bool)
    watchedThemePathsChanged = QtCore.Signal(object)

    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        *,
        theme_dirs: tuple[Path | str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = QtCore.QSettings("Ghost Forge", "Ghost Forge")
        self._theme_dirs = tuple(Path(path) for path in (theme_dirs or _default_theme_dirs()))
        self.loader = ThemeLoader()
        self._themes: dict[str, Theme] = {}
        self._aware_widgets: list[QtWidgets.QWidget] = []
        self.diagnostics: list[str] = []
        self.reload()
        selected = str(self._settings.value("theme/current", "forge_dark"))
        self._current = self._themes.get(selected, self._themes["forge_dark"])
        self.theme_watcher = ThemeWatcher(self._theme_dirs, self)
        self.theme_watcher.themesChanged.connect(self.reload_and_notify)
        self.theme_watcher.enabledChanged.connect(self.liveReloadChanged)
        self.theme_watcher.watchedPathsChanged.connect(self.watchedThemePathsChanged)
        self.theme_watcher.set_enabled(_settings_bool(self._settings, "theme/live_reload", True))

    def themes(self) -> list[Theme]:
        return sorted(self._themes.values(), key=lambda theme: theme.name)

    def current_theme(self) -> Theme:
        return self._current

    def theme_dirs(self) -> tuple[Path, ...]:
        return self._theme_dirs

    def live_reload_enabled(self) -> bool:
        return self.theme_watcher.is_enabled()

    def watched_theme_paths(self) -> tuple[Path, ...]:
        return self.theme_watcher.watched_paths()

    def set_live_reload_enabled(self, enabled: bool) -> None:
        self._settings.setValue("theme/live_reload", bool(enabled))
        self.theme_watcher.set_enabled(bool(enabled))

    def reload(self) -> None:
        themes = built_in_themes()
        diagnostics: list[str] = []
        base_theme = themes["forge_dark"]
        for directory in self._theme_dirs:
            loaded = self.loader.load_dir(directory, base_theme=base_theme)
            for theme_id, theme in loaded.items():
                if theme_id in themes:
                    diagnostics.append(f"Theme '{theme_id}' from {theme.source_path} overrides an existing theme.")
                themes[theme_id] = theme
        for theme in themes.values():
            diagnostics.extend(f"{theme.name}: {warning}" for warning in theme.warnings)
            diagnostics.extend(
                f"{theme.name}: {diagnostic.as_warning()}"
                for diagnostic in self.loader.validator.accessibility_diagnostics(theme)
            )
        self._themes = themes
        self.diagnostics = diagnostics
        current = getattr(self, "_current", None)
        if current is not None:
            self._current = self._themes.get(current.id, self._themes["forge_dark"])
        watcher = getattr(self, "theme_watcher", None)
        if watcher is not None and watcher.is_enabled():
            watcher.refresh_watches()

    @QtCore.Slot()
    def reload_and_notify(self) -> Theme:
        self.reload()
        self.themesReloaded.emit(self.themes())
        self.themeChanged.emit(self._current)
        return self._current

    def select(self, theme_id: str) -> Theme:
        self._current = self._themes.get(theme_id, self._themes["forge_dark"])
        self._settings.setValue("theme/current", self._current.id)
        self.themeChanged.emit(self._current)
        return self._current

    def register_theme_aware_widget(self, widget: QtWidgets.QWidget) -> None:
        if widget in self._aware_widgets:
            return
        self._aware_widgets.append(widget)
        widget.destroyed.connect(lambda _obj=None, w=widget: self.unregister_theme_aware_widget(w))

    def unregister_theme_aware_widget(self, widget: QtWidgets.QWidget) -> None:
        try:
            self._aware_widgets.remove(widget)
        except ValueError:
            pass

    def accessibility_report(self, theme: Theme | str | None = None) -> list[ThemeDiagnostic]:
        if isinstance(theme, Theme):
            target = theme
        elif isinstance(theme, str):
            target = self._themes.get(theme, self._current)
        else:
            target = self._current
        return self.loader.validator.accessibility_diagnostics(target)

    def apply(self, widget: QtWidgets.QWidget | None = None) -> None:
        target = widget or QtWidgets.QApplication.instance()
        if target is not None:
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.setPalette(self.palette(self._current))
            target.setStyleSheet(self.stylesheet(self._current))
            self._notify_theme_aware_widgets(self._current, widget)

    def _notify_theme_aware_widgets(self, theme: Theme, root: QtWidgets.QWidget | None = None) -> None:
        widgets: list[QtWidgets.QWidget] = []
        if root is not None:
            widgets.append(root)
            widgets.extend(root.findChildren(QtWidgets.QWidget))
        widgets.extend(widget for widget in self._aware_widgets if widget is not None)
        seen: set[int] = set()
        for widget in widgets:
            marker = id(widget)
            if marker in seen:
                continue
            seen.add(marker)
            hook = getattr(widget, "apply_ghost_theme", None)
            if callable(hook):
                hook(theme)

    def palette(self, theme: Theme | None = None) -> QtGui.QPalette:
        t = theme or self._current
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(t.color("window.background", t.color("window.bg"))))
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(t.color("text.primary")))
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(t.color("input.background", t.color("input.bg"))))
        palette.setColor(QtGui.QPalette.ColorRole.AlternateBase, QtGui.QColor(t.color("panel.backgroundAlt", t.color("panel.alt"))))
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipBase, QtGui.QColor(t.color("panel.backgroundAlt", t.color("panel.alt"))))
        palette.setColor(QtGui.QPalette.ColorRole.ToolTipText, QtGui.QColor(t.color("text.primary")))
        palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(t.color("text.primary")))
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(t.color("button.background", t.color("button.bg"))))
        palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(t.color("button.text", t.color("text.primary"))))
        palette.setColor(QtGui.QPalette.ColorRole.BrightText, QtGui.QColor(t.color("accent.danger")))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(t.color("selection.background", t.color("selection.bg"))))
        palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(t.color("selection.text", "#ffffff")))
        return palette

    def stylesheet(self, theme: Theme | None = None) -> str:
        t = theme or self._current
        margin = t.metric("panel_margin", 6)
        spacing = t.metric("panel_spacing", 6)
        input_h = t.metric("input_height", 26)
        return f"""
        QMainWindow, QWidget {{
            background: {t.color('window.bg')};
            color: {t.color('text.primary')};
        }}
        QDockWidget {{
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
            color: {t.color('text.primary')};
        }}
        QDockWidget::title {{
            background: {t.color('panel.alt')};
            color: {t.color('text.primary')};
            border: 1px solid {t.color('panel.border')};
            padding-left: {margin}px;
            height: {t.metric('dock_title_height', 24)}px;
        }}
        QMenuBar, QMenu, QToolBar, QStatusBar {{
            background: {t.color('panel.bg')};
            color: {t.color('text.primary')};
            border-color: {t.color('panel.border')};
        }}
        QMenuBar {{
            border-bottom: 1px solid {t.color('panel.border')};
        }}
        QMenuBar::item {{
            background: transparent;
            padding: 3px 7px;
        }}
        QMenuBar::item:selected {{
            background: {t.color('button.hover')};
        }}
        QToolBar {{
            spacing: 4px;
            padding: 3px 6px;
            border: 0;
            border-bottom: 1px solid {t.color('panel.border')};
        }}
        QToolBar::separator {{
            background: {t.color('panel.border')};
            width: 1px;
            margin: 4px;
        }}
        QMenu::item:selected {{
            background: {t.color('selection.bg')};
        }}
        QTableView, QTreeView, QListView, QTextEdit, QPlainTextEdit, QScrollArea {{
            background: {t.color('table.background', t.color('panel.bg'))};
            alternate-background-color: {t.color('panel.backgroundAlt', t.color('panel.alt'))};
            color: {t.color('table.text', t.color('text.primary'))};
            border: 1px solid {t.color('panel.border')};
            gridline-color: {t.color('table.grid', t.color('panel.border'))};
            selection-background-color: {t.color('selection.background', t.color('selection.bg'))};
        }}
        QHeaderView::section {{
            background: {t.color('table.headerBackground', t.color('panel.alt'))};
            color: {t.color('table.headerText', t.color('text.secondary'))};
            border: 1px solid {t.color('table.grid', t.color('panel.border'))};
            padding: 4px;
        }}
        QTabWidget::pane {{
            background: {t.color('panel.bg')};
            border: 1px solid {t.color('panel.border')};
        }}
        QTabBar::tab {{
            background: {t.color('panel.alt')};
            color: {t.color('text.secondary')};
            border: 1px solid {t.color('panel.border')};
            padding: 5px 10px;
            min-height: 18px;
        }}
        QTabBar::tab:selected {{
            background: {t.color('tab.selectedBackground', t.color('panel.bg'))};
            color: {t.color('tab.selectedText', t.color('text.primary'))};
            border-bottom-color: {t.color('tab.selectedBackground', t.color('panel.bg'))};
        }}
        QTabBar::tab:hover {{
            color: {t.color('accent.primary')};
            background: {t.color('button.hover')};
        }}
        QPushButton, QToolButton {{
            min-height: {input_h}px;
            background: {t.color('button.bg')};
            color: {t.color('text.primary')};
            border: 1px solid {t.color('panel.border')};
            border-radius: 4px;
            padding: 3px 8px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background: {t.color('button.hover')};
        }}
        QPushButton:checked, QToolButton:checked {{
            background: {t.color('button.checked')};
            border-color: {t.color('accent.primary')};
        }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
            min-height: {input_h}px;
            background: {t.color('input.bg')};
            color: {t.color('text.primary')};
            border: 1px solid {t.color('panel.border')};
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QGroupBox {{
            border: 1px solid {t.color('groupbox.border', t.color('panel.border'))};
            border-radius: 4px;
            margin-top: 10px;
            padding: {spacing}px;
        }}
        QGroupBox::title {{
            color: {t.color('groupbox.title', t.color('text.secondary'))};
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        QProgressBar {{
            background: {t.color('input.background', t.color('input.bg'))};
            color: {t.color('text.primary')};
            border: 1px solid {t.color('panel.border')};
            border-radius: 3px;
            text-align: center;
            min-height: 16px;
        }}
        QProgressBar::chunk {{
            background: {t.color('accent.primary')};
            border-radius: 2px;
        }}
        QSplitter::handle, QMainWindow::separator {{
            background: {t.color('panel.border')};
        }}
        QMainWindow::separator {{
            width: 6px;
            height: 6px;
        }}
        QSplitter::handle:hover, QMainWindow::separator:hover {{
            background: {t.color('accent.secondary')};
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {t.color('panel.bg')};
            border: 0;
            margin: 0;
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {t.color('panel.border')};
            border-radius: 3px;
            min-height: 22px;
            min-width: 22px;
        }}
        QScrollBar::handle:hover {{
            background: {t.color('accent.secondary')};
        }}
        QLabel#WorkspaceModuleSummary {{
            background: {t.color('panel.alt')};
            color: {t.color('text.secondary')};
            border: 1px solid {t.color('panel.border')};
            padding: {spacing}px;
        }}
        QLabel#WorkspaceLayoutDiagnostics, QLabel#WorkspaceModuleDiagnostics, QLabel#WorkspaceResourceWatch {{
            background: {t.color('panel.bg')};
            color: {t.color('text.secondary')};
            border: 1px solid {t.color('panel.border')};
            padding: {spacing}px;
        }}
        QFrame#GhostForgeViewportToolbar {{
            background: {t.color('panel.bg')};
            border-bottom: 1px solid {t.color('panel.border')};
        }}
        QLabel#GhostForgeViewportToolbarLabel {{
            color: {t.color('text.muted')};
            font-size: 9pt;
        }}
        QFrame#GhostForgeViewportStatusStrip {{
            background: {t.color('panel.alt')};
            color: {t.color('text.secondary')};
            border-top: 1px solid {t.color('panel.border')};
        }}
        QFrame#GhostForgeViewportStatusStrip QLabel {{
            color: {t.color('text.secondary')};
            font-family: Consolas, monospace;
            font-size: 9pt;
        }}
        QFrame#GhostForgeEditorBottomStrip {{
            background: {t.color('panel.bg')};
            color: {t.color('text.secondary')};
            border-top: 1px solid {t.color('panel.border')};
            border-bottom: 1px solid {t.color('panel.border')};
        }}
        QFrame#GhostForgeEditorBottomStrip QLabel {{
            color: {t.color('text.secondary')};
            font-family: Consolas, monospace;
            font-size: 9pt;
        }}
        QFrame#GhostForgeEditorBottomStripSeparator {{
            background: {t.color('panel.border')};
            border: 0;
        }}
        QTabWidget#GhostForgeGraphTabs::pane {{
            border: 1px solid {t.color('panel.border')};
            background: {t.color('panel.bg')};
        }}
        QTabWidget#GhostForgeGraphTabs QTabBar::tab {{
            min-width: {t.metric('tab.width', 74)}px;
            min-height: {t.metric('tab.height', 18)}px;
            padding: {t.metric('tab.paddingY', 4)}px {t.metric('tab.paddingX', 9)}px;
        }}
        QLabel#GhostForgePanelSectionLabel {{
            color: {t.color('accent.primary')};
            font-weight: bold;
            padding: 2px 0;
        }}
        QScrollArea#GhostForgePanelScrollArea {{
            border: 0;
            background: transparent;
        }}
        """


def _default_theme_dirs() -> tuple[Path, ...]:
    package_root = Path(__file__).resolve().parents[1]
    cwd = Path.cwd()
    return (
        package_root / "themes",
        cwd / "config" / "themes",
        cwd / "themes",
        Path.home() / ".ghostforge" / "themes",
    )


def _settings_bool(settings: QtCore.QSettings, key: str, default: bool) -> bool:
    raw = settings.value(key, default)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() not in {"0", "false", "no", "off"}
    return bool(raw)
