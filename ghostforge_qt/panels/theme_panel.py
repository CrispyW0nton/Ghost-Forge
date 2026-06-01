from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ghostforge_qt.theme import ThemeManager


class ThemePanel(QtWidgets.QWidget):
    def __init__(self, manager: ThemeManager, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.combo = QtWidgets.QComboBox()
        for theme in self.manager.themes():
            self.combo.addItem(theme.name, theme.id)
        idx = self.combo.findData(self.manager.current_theme().id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.currentIndexChanged.connect(self._select_current)

        self.preview = QtWidgets.QLabel()
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(80)
        self.preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(QtWidgets.QLabel("Theme"))
        layout.addWidget(self.combo)
        layout.addWidget(self.preview)
        layout.addStretch(1)
        self.refresh_preview()

    @QtCore.Slot()
    def _select_current(self) -> None:
        theme_id = str(self.combo.currentData())
        self.manager.select(theme_id)
        self.manager.apply()
        self.refresh_preview()

    def refresh_preview(self) -> None:
        theme = self.manager.current_theme()
        self.preview.setText(
            f"{theme.name}\n"
            f"Viewport: {theme.color('viewport.bg')}\n"
            f"Accent: {theme.color('accent.primary')}\n"
            f"Panel spacing: {theme.metric('panel_spacing', 6)}"
        )
