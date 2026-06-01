# Qt GUI Architecture Notes For Ghost Forge

Sources scanned: Martin Fitzpatrick's PySide6 book, Lee Zhi Eng's Qt 6 cookbook, Mark Summerfield's PyQt book, and Ghost Rigger's Qt branch.

## Chapter Map Anchors

The Qt books repeatedly cluster around the same durable ideas:

- Application object, main windows, dialogs, widgets, layouts.
- Signals and slots as the UI coordination mechanism.
- QAction, menus, toolbars, and shortcuts for command routing.
- Model/view architecture for lists, trees, tables, filters, and inspectors.
- Designer/resource workflows, icons, styles, palettes, and QSS.
- Threads, process execution, and progress/cancel behavior for long-running work.

## Ghost Forge Applications

### Shell

Create a new `ghostforge_qt` package instead of forcing Qt into the Electron renderer. The shell should own:

- `QApplication` startup, logging, exception hooks, and settings.
- `QMainWindow` with dockable panels.
- QAction registry for commands such as import, save scene, unwrap, texture, audit, generate, export, and send to engine.
- Persistent layouts with `QSettings`.

### Panels

Use Qt model/view for data-heavy UI:

- Scene outliner: `QAbstractItemModel` or `QStandardItemModel`, with proxy filtering.
- Asset browser: filesystem-backed model plus metadata columns.
- Worker/model registry: table model showing runnable state, license, VRAM, required models, and cache status.
- Audit/results panel: tree model grouped by severity and rule.
- Manifest inspector: editable form mapped to a typed manifest model.

### Jobs

Long-running tasks must never block the UI thread. Use one of:

- direct `ghostforge_core.JobRunner` integration with Qt polling/signals,
- `QThreadPool`/`QRunnable` for local tasks,
- `QProcess` for isolated model workers.

Every job needs progress, cancellation, logs, artifact paths, and a final manifest.

### Dialogs

Dialogs should be thin. Business logic belongs in core services or controllers. Dialogs collect user intent, validate obvious UI constraints, and dispatch commands.

### Styling

Ghost Rigger's theme/layout system is a useful model. Ghost Forge should move from hard-coded React style objects to:

- tokenized colors and metrics,
- a theme loader,
- icon registry,
- layout persistence,
- accessibility checks for contrast and text fit.

## Architecture Rule

Qt widgets should not know how to generate meshes, unwrap UVs, or call AI models. They should bind to controllers/services that call `ghostforge_core`.

## First Tests To Add

- Main-window construction without GPU/model dependencies.
- QAction registry contains all core commands and shortcuts.
- Scene model add/select/remove persistence.
- Worker table correctly displays missing `torch` and stub fallback states.
- Job controller emits progress, completion, failure, and cancellation signals.
