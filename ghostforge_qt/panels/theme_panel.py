from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.theme import ThemeManager


class ThemePanel(QtWidgets.QWidget):
    def __init__(self, manager: ThemeManager, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.combo = QtWidgets.QComboBox()
        self.combo.currentIndexChanged.connect(self._select_current)

        self.reload_button = QtWidgets.QPushButton("Reload Themes")
        self.reload_button.clicked.connect(self.reload_themes)
        self.live_reload_check = QtWidgets.QCheckBox("Live Reload")
        self.live_reload_check.setChecked(self.manager.live_reload_enabled())
        self.live_reload_check.toggled.connect(self._set_live_reload)

        self.preview = QtWidgets.QLabel()
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(80)
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        self.diagnostics = QtWidgets.QPlainTextEdit()
        self.diagnostics.setReadOnly(True)
        self.diagnostics.setMaximumHeight(110)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QtWidgets.QLabel("Theme"))
        layout.addWidget(self.combo)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.reload_button)
        controls.addWidget(self.live_reload_check)
        controls.addStretch(1)
        layout.addLayout(controls)
        layout.addWidget(self.preview)
        layout.addWidget(self.diagnostics)
        layout.addStretch(1)
        self.manager.themesReloaded.connect(self._themes_reloaded)
        self.manager.liveReloadChanged.connect(self._sync_live_reload)
        self.manager.watchedThemePathsChanged.connect(self._watched_paths_changed)
        self._populate_combo()
        self.refresh_preview()

    @QtCore.Slot()
    def _select_current(self) -> None:
        raw_theme_id = self.combo.currentData()
        if raw_theme_id is None:
            return
        theme_id = str(raw_theme_id)
        self.manager.select(theme_id)
        self.manager.apply()
        self.refresh_preview()

    @QtCore.Slot(bool)
    def _set_live_reload(self, enabled: bool) -> None:
        self.manager.set_live_reload_enabled(enabled)
        self.refresh_preview()

    @QtCore.Slot(bool)
    def _sync_live_reload(self, enabled: bool) -> None:
        blocked = self.live_reload_check.blockSignals(True)
        self.live_reload_check.setChecked(enabled)
        self.live_reload_check.blockSignals(blocked)
        self.refresh_preview()

    @QtCore.Slot(object)
    def _themes_reloaded(self, _themes: object) -> None:
        self._populate_combo()
        self.refresh_preview()

    @QtCore.Slot(object)
    def _watched_paths_changed(self, _paths: object) -> None:
        self.refresh_preview()

    @QtCore.Slot()
    def reload_themes(self) -> None:
        selected = self.manager.current_theme().id
        self.manager.reload()
        self._populate_combo(selected_id=selected)
        raw_theme_id = self.combo.currentData()
        if raw_theme_id is not None:
            self.manager.select(str(raw_theme_id))
            self.manager.apply()
        self.refresh_preview()

    def _populate_combo(self, *, selected_id: str | None = None) -> None:
        current = selected_id or self.manager.current_theme().id
        blocked = self.combo.blockSignals(True)
        self.combo.clear()
        for theme in self.manager.themes():
            label = theme.name if not theme.source_path else f"{theme.name} [file]"
            self.combo.addItem(label, theme.id)
        idx = self.combo.findData(current)
        if idx < 0:
            idx = self.combo.findData(self.manager.current_theme().id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(blocked)

    def refresh_preview(self) -> None:
        theme = self.manager.current_theme()
        source = theme.source_path or "built-in"
        accessibility_warnings = self.manager.accessibility_report(theme)
        warning_count = len(theme.warnings) + len(accessibility_warnings)
        accessibility = "pass" if not accessibility_warnings else f"{len(accessibility_warnings)} contrast warnings"
        live_reload = "on" if self.manager.live_reload_enabled() else "off"
        watch_count = len(self.manager.watched_theme_paths())
        self.preview.setText(
            f"{theme.name}\n"
            f"{theme.description}\n"
            f"Viewport: {theme.color('viewport.bg')}\n"
            f"Accent: {theme.color('accent.primary')}\n"
            f"Panel spacing: {theme.metric('panel_spacing', 6)}\n"
            f"Source: {source}\n"
            f"Accessibility: {accessibility}\n"
            f"Warnings: {warning_count}\n"
            f"Live reload: {live_reload}\n"
            f"Watching: {watch_count} paths"
        )
        self.diagnostics.setPlainText("\n".join(self.manager.diagnostics) or "No theme diagnostics.")
