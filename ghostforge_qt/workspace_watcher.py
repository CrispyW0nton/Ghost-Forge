from __future__ import annotations

from pathlib import Path

from PySide6 import QtCore


class WorkspaceResourceWatcher(QtCore.QObject):
    """Watch file-backed workspace module and layout resources."""

    modulesChanged = QtCore.Signal()
    layoutsChanged = QtCore.Signal()
    enabledChanged = QtCore.Signal(bool)
    watchedPathsChanged = QtCore.Signal(object)

    def __init__(
        self,
        module_dirs: tuple[Path | str, ...],
        layout_dirs: tuple[Path | str, ...],
        parent: QtCore.QObject | None = None,
        *,
        debounce_ms: int = 250,
        extensions: tuple[str, ...] = (".json", ".xml"),
    ) -> None:
        super().__init__(parent)
        self._module_dirs = tuple(Path(path) for path in module_dirs)
        self._layout_dirs = tuple(Path(path) for path in layout_dirs)
        self._extensions = tuple(ext.lower() for ext in extensions)
        self._enabled = False
        self._pending: set[str] = set()
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._path_changed)
        self._watcher.directoryChanged.connect(self._path_changed)
        self._debounce_timer = QtCore.QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(max(1, int(debounce_ms)))
        self._debounce_timer.timeout.connect(self._emit_changes)

    def module_dirs(self) -> tuple[Path, ...]:
        return self._module_dirs

    def layout_dirs(self) -> tuple[Path, ...]:
        return self._layout_dirs

    def set_dirs(
        self,
        *,
        module_dirs: tuple[Path | str, ...] | None = None,
        layout_dirs: tuple[Path | str, ...] | None = None,
    ) -> None:
        if module_dirs is not None:
            self._module_dirs = tuple(Path(path) for path in module_dirs)
        if layout_dirs is not None:
            self._layout_dirs = tuple(Path(path) for path in layout_dirs)
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
            self._pending.clear()
            self._debounce_timer.stop()
            self._clear_watches()
            self.watchedPathsChanged.emit(())
        self.enabledChanged.emit(enabled)

    def watched_paths(self) -> tuple[Path, ...]:
        paths = [Path(path) for path in self._watcher.directories()]
        paths.extend(Path(path) for path in self._watcher.files())
        return tuple(sorted(paths, key=lambda path: str(path).lower()))

    def refresh_watches(self) -> tuple[Path, ...]:
        if not self._enabled:
            return ()
        self._clear_watches()
        paths = (*self._candidate_paths(self._module_dirs), *self._candidate_paths(self._layout_dirs))
        if paths:
            self._watcher.addPaths([str(path) for path in paths])
        watched = self.watched_paths()
        self.watchedPathsChanged.emit(watched)
        return watched

    def trigger_reload(self, resource: str = "all", *, immediate: bool = True) -> None:
        if not self._enabled:
            return
        if resource in {"all", "modules", "module"}:
            self._pending.add("modules")
        if resource in {"all", "layouts", "layout"}:
            self._pending.add("layouts")
        self.refresh_watches()
        if not self._pending:
            return
        if immediate:
            self._debounce_timer.stop()
            self._emit_changes()
        else:
            self._debounce_timer.start()

    @QtCore.Slot(str)
    def _path_changed(self, path: str) -> None:
        if not self._enabled:
            return
        resource = self._resource_for_path(Path(path))
        if resource:
            self._pending.add(resource)
        self.refresh_watches()
        if self._pending:
            self._debounce_timer.start()

    @QtCore.Slot()
    def _emit_changes(self) -> None:
        if not self._enabled:
            return
        pending = set(self._pending)
        self._pending.clear()
        self.refresh_watches()
        if "modules" in pending:
            self.modulesChanged.emit()
        if "layouts" in pending:
            self.layoutsChanged.emit()

    def _candidate_paths(self, directories: tuple[Path, ...]) -> tuple[Path, ...]:
        paths: list[Path] = []
        for directory in directories:
            if not directory.exists() or not directory.is_dir():
                continue
            paths.append(directory)
            for child in sorted(directory.iterdir()):
                if child.is_file() and child.suffix.lower() in self._extensions:
                    paths.append(child)
        return tuple(paths)

    def _resource_for_path(self, path: Path) -> str:
        for directory in self._module_dirs:
            if _is_path_or_child(path, directory):
                return "modules"
        for directory in self._layout_dirs:
            if _is_path_or_child(path, directory):
                return "layouts"
        return ""

    def _clear_watches(self) -> None:
        paths = [*self._watcher.files(), *self._watcher.directories()]
        if paths:
            self._watcher.removePaths(paths)


def _is_path_or_child(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
        return True
    except ValueError:
        return False
    except OSError:
        return path == directory
