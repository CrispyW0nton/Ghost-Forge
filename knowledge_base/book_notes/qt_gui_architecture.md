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

Graph-result inspection should stay attached to the same panel/model contract.
The Qt shell now reads the selected scene object's manifest into the graph
panel, summarizes the active result, node artifacts, manifest path, audit
status, engine targets, and bridge history, and exposes Unity/Unreal bridge
buttons only when manifest validation is not blocking. The buttons emit intent;
`MainWindow` and `CoreBridge` perform the manifest-gated package creation.

Retarget planning follows the same signal/service rule. The graph panel exposes
Unity/Unreal retarget plan requests from the result inspector, but it does not
inspect audit diagnostics itself. `CoreBridge` calls the shared
`ghostforge_core.retarget` planner, `MainWindow` attaches the returned
`EditGraph` to the selected scene object, and normal graph evaluation handles
the actual mesh rewrite.

Retarget diagnostics should be shown in the same inspector instead of hidden in
logs. The planner returns an `AuditReport`, so Qt stores a planned history row
and renders the retarget-specific issue codes, severities, and suggestions next
to the graph that was generated from them.

That diagnostic payload must survive save/open too. Planned retarget history
rows now carry structured `details` with the target engine and planner report,
so `.gforge` scene reload can restore the graph and the explanatory diagnostic
summary together.

Retarget verification should be model data rather than a transient toast. After
a retarget graph finishes, the Qt shell now asks `CoreBridge` to re-run the
target-engine retarget audit, stores a verified history row, and renders which
planned diagnostics were resolved, which remain, and which new issues appeared.
That keeps the graph inspector useful as an edit loop, not just a pre-export
warning list.

Graph result file actions should follow the same signal/service split. History
rows now retain structured output, artifact, asset-directory, and manifest
paths, while the panel exposes open/reveal buttons and emits path intent. The
main window owns `QDesktopServices` handoff. This keeps the result inspector
testable headlessly and lets saved scenes restore actionable graph resources.

The inspector resource list is now model-backed. `GraphResultResourceModel`
normalizes output meshes, texture artifacts, manifests, and asset directories
into rows with kind/source/path columns, so the UI can offer selected-resource
open/reveal actions and still restore those rows from graph history after
scene reload.

Manifest-backed resources should appear in the same table. The inspector now
adds bridge-package rows from `engine.bridge.*` artifacts and
`custom.engine_export_bridges`, plus audit-history rows pointing back to the
manifest with preset/status source text. History payloads retain bridge paths
and latest audit summary so reopen can restore the same resource surface.

Selected resource metadata belongs beside the resource table, not in tooltips
alone. Graph result resources now carry a small details payload, and the Qt
panel renders that payload in a selectable details label. Bridge rows show
target engine, recommended MCP server/tool, and direct-call status; audit rows
show preset, status, counts, timing, and manifest path context.

Manifest rows now expose compact validation and provenance drill-down data too.
The details payload includes asset id, validation status/counts, short issue
code summaries from the manifest validation report, artifact/provenance counts,
and the latest provenance step chain. This gives the graph inspector a first
real manifest-debug surface without forcing users to open raw JSON for every
readiness question.

The drill-down now carries list detail as structured UI text. Validation report
issues render by severity with code, location, and message, while provenance
steps render in order with kind, short job id, and timing when available. This
keeps the details label useful for real triage while the manifest file remains
the authoritative full record.

Audit and bridge rows now carry list detail too. Audit resources render issue
lines from the persisted audit report, and bridge resources render a compact
package preview with target engine, recommended MCP server/tool, direct-call
flag, and package path. The same details persist in graph history so reopen
keeps the handoff/debug context.

The resource table now has a kind filter over the same model-backed rows.
Artists and agents can isolate outputs, artifacts, manifests, asset directories,
audit evidence, or bridge packages without losing the full result-path context
used by the open/reveal actions. This follows the Qt model/view rule: filter UI
state changes table presentation, while resource identity and action routing
remain stable.

Bridge rows now read the selected bridge package JSON when it is locally
available and render a compact preview beside the manifest history fields. The
panel shows version, target engine, asset id, asset/manifest paths, target path,
recommended MCP server/tool, embedded manifest validation, artifact count, and
notes instead of forcing users to open raw JSON for basic handoff triage.

Retarget verification now has a model-backed diff view. The summary label still
states how many planned diagnostics resolved, but a table lists planned,
remaining, newly introduced, and resolved retarget rows with severity, rule,
code, target, message, and suggestion. Remaining and new rows sort first so the
next correction target is immediately visible after a graph evaluation.

Operation graph nodes can now be enabled or disabled from the Qt panel without
removing them. The button updates the immutable `OperationNode.enabled` state
through `OperationGraphModel`, clears stale evaluation badges, emits the normal
`graphChanged` signal, and keeps the node parameters intact. This is the first
true modifier-stack bypass control in the desktop editor.

Operation graph node order can now be changed from the Qt panel as well. Move
Up/Move Down buttons update the immutable `EditGraph.nodes` order through the
model, clear stale evaluation state, keep the moved node selected, and emit the
same graph-change signal as other node edits. This is the model-layer groundwork
for later drag-and-drop stack reordering.

Drag/drop graph reordering is now wired through that same model path. The graph
table uses Qt internal move mode and `OperationGraphModel` exposes move-only
MIME/drop behavior, so dragging a row updates the immutable graph order and
emits `graphChanged` rather than only rearranging the visual table.

Descriptor-generated path parameters now render as a reusable Qt path picker
instead of a plain string field. The form infers file/folder intent from
operation schema fields such as `type: path`, `format: directory`, and
`*_dir`/`*_path` names, then still returns simple string values to the graph
model. This follows the Qt form/dialog guidance: the widget improves input
ergonomics, while the schema and core graph remain the source of truth.

Descriptor-generated presets now sit on `OperationDescriptor` as shared
metadata. The Qt form renders a preset combo only when descriptors provide
presets, applies the default preset for new nodes, and writes values through
the same widgets used for manual editing. Existing nodes keep their authored
params when reopened, while agents can inspect the same preset metadata through
MCP operation descriptors.

Saved scene graph history now carries stable resource identity too. The Qt
scene document service assigns a scene id, annotates each graph-history row
with a deterministic `history_id`, and stores MCP links back to the graph,
last evaluation, scene, and object-history row. This keeps save/open behavior
useful for artists while giving agents a durable address for the same row.

Graph-history comparison now follows the same model/view rule. The Qt result
inspector preserves `history_id`, `resource_uri`, and `mcp_links` on restored
history rows, then renders a previous-to-selected delta through the shared
`compare_graph_history_payloads()` helper. The widget only presents the
comparison text; the core helper owns the audit, artifact, bridge, and retarget
delta contract used by MCP.

Graph-history comparison is now selectable rather than only adjacent. The Qt
inspector exposes From/To combo boxes over the saved history model, computes the
matching MCP comparison resource URI from the selected payloads, and copies that
URI through a button/signal. This keeps the UI affordance thin while making the
same saved resource address usable by an artist and an agent.

Graph-history deltas now have a dedicated model-backed summary table. The panel
still keeps the prose label for quick reading, but `GraphHistoryDeltaModel`
breaks changed fields, resource path additions/removals, audit count/issue
changes, and retarget list deltas into rows. This follows the Qt book guidance:
structured evidence belongs in table models so it can be tested, filtered, and
expanded later.

The active graph-history comparison pair is now scene state, not widget memory.
`SceneObjectRecord` stores the selected left/right history ids, the scene
document service validates them against persisted graph-history rows, and the
main window restores them after reopening a `.gforge` file. This keeps combo-box
state thin while preserving the artist's diagnostic context as document data.

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
- Operation graph result inspector shows manifest readiness and routes Unity/Unreal bridge creation through core services.
- Operation graph result inspector routes Unity/Unreal retarget planning through the shared core planner and restores the generated graph in the editor.
- Operation graph result inspector records planned retarget history rows and displays retarget audit diagnostics.
- Scene save/open restores planned retarget diagnostic payloads into the graph result inspector.
- Completed retarget graph evaluations compare planned and post-evaluation diagnostics and persist the verified result row.
- Graph result history persists output/artifact/manifest/asset-directory paths and the inspector emits open/reveal path actions without launching the OS in panel tests.
- Graph result resource rows are model-backed and distinguish artifacts from asset directories when driving selected open/reveal actions.
- Graph result resources include manifest-derived bridge package rows and audit-history rows that restore from saved graph history.
- Selected graph result resources display metadata drill-down for bridge handoff, audit evidence, manifest summary, and output context.
- Manifest graph result resource details summarize validation issue codes and latest provenance steps.
- Manifest graph result resource details render validation issue lists and provenance step lists for selected-resource triage.
- Audit and bridge graph result resources render persisted audit issue lists and bridge package preview fields.
- Graph result resource filters isolate output, artifact, manifest, asset-directory, audit, and bridge rows without breaking global open/reveal path actions.
- Bridge graph result resources preview readable `ghostforge_bridge_<engine>.json` package fields and restore that preview from saved graph history paths.
- Retarget diagnostic diffs render planned, remaining, new, and resolved rows from persisted report payloads, with remaining/new diagnostics focused first.
- Operation graph node enable/disable controls preserve node parameters, clear stale evaluation state, and emit updated graph intent.
- Operation graph node reorder controls preserve node parameters, clear stale evaluation state, keep selection on the moved node, and emit updated graph intent.
- Operation graph drag/drop reorder uses model MIME/drop behavior and emits updated graph intent.
- Descriptor-generated operation parameter forms render file and folder path pickers while preserving plain string graph payloads.
- Operation descriptors expose parameter presets that Qt can apply without hand-coded per-operation branches.
- Scene save/open annotates graph-history rows with stable IDs and MCP links for agent inspection.
- Qt graph result inspector preserves graph-history resource IDs and displays shared-core history deltas for the selected row versus the previous row.
- Qt graph result inspector can compare explicit graph-history pairs and copy the matching MCP comparison URI without losing model-backed history state.
- Qt graph result inspector renders graph-history comparison evidence in a model-backed delta table.
- Scene save/open persists the active graph-history comparison pair and restores the matching From/To controls.
