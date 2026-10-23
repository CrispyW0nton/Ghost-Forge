from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore


class ThemeWatcher(QtCore.QObject):
    """Qt-native watcher for file-backed theme resources."""

    themesChanged = QtCore.Signal()
    enabledChanged = QtCore.Signal(bool)
    watchedPathsChanged = QtCore.Signal(object)

    def __init__(
        self,
        theme_dirs: tuple[Path | str, ...],
        parent: QtCore.QObject | None = None,
        *,
        debounce_ms: int = 250,
        extensions: tuple[str, ...] = (".json", ".xml"),
    ) -> None:
        super().__init__(parent)
        self._theme_dirs = tuple(Path(path) for path in theme_dirs)
        self._extensions = tuple(ext.lower() for ext in extensions)
        self._enabled = False
        self._file_watcher = QtCore.QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._path_changed)
        self._file_watcher.directoryChanged.connect(self._path_changed)
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(max(1, int(debounce_ms)))
        self._debounce_timer.timeout.connect(self._emit_change)

    def theme_dirs(self) -> tuple[Path, ...]:
        return self._theme_dirs

    def set_theme_dirs(self, theme_dirs: tuple[Path | str, ...]) -> None:
        self._theme_dirs = tuple(Path(path) for path in theme_dirs)
        if self._enabled:
            self.refresh_watches()

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if self._enabled == enabled:
            if enabled:
                self.refresh_watches()
            return
        self._enabled = enabled
        if enabled:
            self.refresh_watches()
        else:
            self._debounce_timer.stop()
            self._clear_watches()
            self.watchedPathsChanged.emit(())
        self.enabledChanged.emit(enabled)

    def start(self) -> None:
        self.set_enabled(True)

    def stop(self) -> None:
        self.set_enabled(False)

    def watched_paths(self) -> tuple[Path, ...]:
        paths = [Path(path) for path in self._file_watcher.directories()]
        paths.extend(Path(path) for path in self._file_watcher.files())
        return tuple(sorted(paths, key=lambda path: str(path).lower()))

    def refresh_watches(self) -> tuple[Path, ...]:
        if not self._enabled:
            return ()
        self._clear_watches()
        paths = self._candidate_paths()
        if paths:
            self._file_watcher.addPaths([str(path) for path in paths])
        watched = self.watched_paths()
        self.watchedPathsChanged.emit(watched)
        return watched

    def trigger_reload(self, *, immediate: bool = True) -> None:
        if not self._enabled:
            return
        self.refresh_watches()
        if immediate:
            self._debounce_timer.stop()
            self.themesChanged.emit()
        else:
            self._debounce_timer.start()

    @QtCore.Slot(str)
    def _path_changed(self, _path: str) -> None:
        if not self._enabled:
            return
        self.refresh_watches()
        self._debounce_timer.start()

    @QtCore.Slot()
    def _emit_change(self) -> None:
        if not self._enabled:
            return
        self.refresh_watches()
        self.themesChanged.emit()

    def _candidate_paths(self) -> tuple[Path, ...]:
        paths: list[Path] = []
        for directory in self._theme_dirs:
            if not directory.exists() or not directory.is_dir():
                continue
            paths.append(directory)
            for child in sorted(directory.iterdir()):
                if child.is_file() and child.suffix.lower() in self._extensions:
                    paths.append(child)
        return tuple(paths)

    def _clear_watches(self) -> None:
        paths = [*self._file_watcher.files(), *self._file_watcher.directories()]
        if paths:
            self._file_watcher.removePaths(paths)
