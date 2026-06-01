from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from .theme_model import Theme, built_in_themes


class ThemeManager(QtCore.QObject):
    themeChanged = QtCore.Signal(object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QtCore.QSettings("Ghost Forge", "Ghost Forge")
        self._themes = built_in_themes()
        selected = str(self._settings.value("theme/current", "forge_dark"))
        self._current = self._themes.get(selected, self._themes["forge_dark"])

    def themes(self) -> list[Theme]:
        return sorted(self._themes.values(), key=lambda theme: theme.name)

    def current_theme(self) -> Theme:
        return self._current

    def select(self, theme_id: str) -> Theme:
        self._current = self._themes.get(theme_id, self._themes["forge_dark"])
        self._settings.setValue("theme/current", self._current.id)
        self.themeChanged.emit(self._current)
        return self._current

    def apply(self, widget: QtWidgets.QWidget | None = None) -> None:
        target = widget or QtWidgets.QApplication.instance()
        if target is not None:
            target.setStyleSheet(self.stylesheet(self._current))

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
        QMenu::item:selected {{
            background: {t.color('selection.bg')};
        }}
        QTableView, QTreeView, QListView, QTextEdit, QPlainTextEdit {{
            background: {t.color('panel.bg')};
            alternate-background-color: {t.color('panel.alt')};
            color: {t.color('text.primary')};
            border: 1px solid {t.color('panel.border')};
            gridline-color: {t.color('panel.border')};
            selection-background-color: {t.color('selection.bg')};
        }}
        QHeaderView::section {{
            background: {t.color('panel.alt')};
            color: {t.color('text.secondary')};
            border: 1px solid {t.color('panel.border')};
            padding: 4px;
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
            border: 1px solid {t.color('panel.border')};
            border-radius: 4px;
            margin-top: 10px;
            padding: {spacing}px;
        }}
        QGroupBox::title {{
            color: {t.color('text.secondary')};
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
        }}
        """
