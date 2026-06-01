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
- Operation graph: palette and stack models over the core authoring registry, including source/process type, worker capability status, node parameters, and evaluation result status.
- Audit/results panel: tree model grouped by severity and rule.
- Manifest inspector: editable form mapped to a typed manifest model.

### Jobs

Long-running tasks must never block the UI thread. Use one of:

- direct `ghostforge_core.JobRunner` integration with Qt polling/signals,
- `QThreadPool`/`QRunnable` for local tasks,
- `QProcess` for isolated model workers.

Every job needs progress, cancellation, logs, artifact paths, and a final manifest.

Authoring graph evaluation now follows this rule in the Qt shell: the graph
panel submits an `evaluate_edit_graph` job through `CoreBridge`, the job panel
polls durable job state, and the main window applies terminal results back into
the scene model, graph panel, manifest, topology panel, and undo history. This
keeps hosted/local worker graph execution out of the event loop while preserving
the artist-facing edit stack. The graph panel must also show the active job id,
progress stage/message, cancellation state, terminal failure, and retry affordance
so long-running AI or retopo jobs feel inspectable rather than mysterious.

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

Operation graph UI follows the same rule: panels list and collect node intent,
while `CoreBridge` evaluates `ghostforge_core.authoring.EditGraph` through the
shared operation registry. This keeps the desktop editor, MCP server, and
headless tests on the same graph contract.

Node parameter editing should be generated from `OperationDescriptor.params_schema`
rather than hand-coded per widget. The schema is already the contract used by
core evaluation and MCP discovery, so Qt forms should render strings, paths,
numbers, booleans, enums, vectors, JSON extras, and worker choices from the same
descriptor. This prevents the desktop editor from drifting away from headless
graph execution as operations are added.

Graph result display should stay model-backed too. Evaluation payloads already
contain per-node status and worker side effects keyed by node id, so the graph
table should render artifact badges, manifest links, and failed-node focus from
that payload rather than from ad hoc UI state. Audit badges can extend the same
column once graph evaluations attach audit history. Result history should be a
model-backed table over the same evaluation payloads, summarizing graph id,
status, output, artifact count, audit badge, and the first actionable message.
Graph-linked audit actions should submit durable `audit_asset` jobs through
`CoreBridge`, then refresh badges/history from the manifest after the audit
persists `validation` and `custom['audit_history']`.

Scene persistence must include graph intent, not only evaluated output paths.
When a user saves a `.gforge` scene, each object that has a modifier/operation
graph should retain the graph id, nodes, parameters, base asset, and last-known
link to the core graph store so reopening the project restores the editable
stack rather than just the baked mesh.

Graph result history is part of that same scene-document contract. Evaluation
and audit rows are model data, not transient labels, so the Qt shell now stores
per-object graph history payloads in `.gforge` files and reloads them into the
operation-graph panel when the object is selected. This keeps audit/readiness
context attached to the authored asset across sessions.

## First Tests To Add

- Main-window construction without GPU/model dependencies.
- QAction registry contains all core commands and shortcuts.
- Scene model add/select/remove persistence.
- Worker table correctly displays missing `torch` and stub fallback states.
- Operation graph model displays available/source/worker nodes and records evaluation status.
- Scene save/open round-trips per-object operation graphs and restores the graph panel.
- Job controller emits progress, completion, failure, and cancellation signals.
- Qt graph jobs update scene objects or create source-generated objects on completion without blocking the UI thread.
- Operation graph parameter forms render from operation descriptors and can add/edit node parameters without operation-specific widget code.
- Operation graph jobs expose progress, cancel, failure, and retry states in the graph panel.
- Operation graph results surface per-node artifacts/manifests and focus the first failed node after evaluation.
- Operation graph result history and audit badges render from manifest/evaluation payloads rather than local-only UI text.
- Operation graph audit actions run through durable core audit jobs and refresh from the persisted manifest.
- Scene save/open restores operation graph result history and audit badges.
