# Ghost Forge Knowledge Iteration Log

## 2026-05-31 Initial Audit And Bible Seed

Scanned the provided Qt, game-engine, and graphics-math books by metadata and outlines. Created the first Ghost Forge knowledge base, current-state audit, Qt migration plan, and development bible.

Design decisions captured:

- Qt should become the primary desktop shell, but `ghostforge_core` should remain the shared domain layer.
- The UI must expose capability honesty for AI workers: runnable, missing dependency, CPU fallback, or stub.
- Ghost Rigger's stronger pattern is a Qt shell with typed panels, renderer abstraction, controller/service boundaries, theme/layout systems, and headless tests.
- Ghost Forge should compete first as an AI-native asset pipeline and editor foundation, not as a Blender/Maya replacement.

Verification run:

- `python -m pytest`: 515 passed, 3 skipped.
- `npm install`: completed; npm reported 15 vulnerabilities.
- `npm run build`: passed after dependency install.
- `npm audit --omit=dev`: 3 production vulnerabilities: `axios`, `follow-redirects`, `electron`.
- `npm run lint`: failed because ESLint 9 requires `eslint.config.js`.

## 2026-05-31 Qt Migration Slice 1

Started the PySide6 migration as a parallel desktop shell rather than replacing the Electron prototype immediately.

Book/Ghost Rigger principles applied:

- QAction registry for command routing.
- QMainWindow plus dockable panels for editor layout.
- Qt model/view for scene, worker, and job data.
- CoreBridge service boundary so widgets do not call model workers or storage directly.
- Honest capability display for runnable, missing, and stub workers.
- Renderer boundary with a null viewport first, so OpenGL/wgpu work can land behind a stable interface.

Added first Qt tests for:

- CoreBridge runtime/worker snapshots.
- Scene and worker table models.
- Main window construction and registered editor actions.

## 2026-05-31 Qt Editor Surface Slice 2

Added the first Ghost Forge-native editor surfaces inspired by Ghost Rigger but generalized for project-based work:

- ThemeManager with built-in Forge Dark and Studio Light themes, stylesheet generation, persistence through QSettings, and a Theme dock.
- ProjectService and Content Browser rooted at a Ghost Forge project folder rather than a game install/library.
- Editor viewport foundation with painted grid, XYZ axes, camera/display/selection/transform controls, object overlay, and theme application.
- Modeling Tools dock with object/sub-object selection modes, transform modes, and staged modeling operations.

Book/Ghost Rigger principles applied:

- Model/view content browser over filesystem data.
- Viewport state is explicit and testable.
- Theme/layout tokens are separated from individual widgets.
- Modeling operations should be command-routed and operation-graph-ready before deep mesh editing is added.

Tests added for project folder creation, content browser root changes, theme switching, viewport mode/theme state, modeling tool signals, and main-window panel wiring.

## 2026-05-31 Qt Viewport And Modeling Slice 3

Started closing the gap between a foundational viewport and a practical DCC viewport:

- Added mesh preview loading through `trimesh`, including scene concatenation, downsampled face previews, unique edge extraction, and bounds.
- Upgraded the Qt viewport from object-name overlay to CPU-projected mesh rendering with faces, wire edges, camera presets, display modes, transforms, and theme-aware drawing.
- Added document-side `TransformState` on scene objects and transform type-in controls in the Modeling dock.
- Added a `MeshOperationService` for safe CPU cleanup operations that write new GLB outputs into the project: recalculate normals, flip normals, remove isolated vertices, normalize scale, and decimate when a backend is installed.

Book/Ghost Rigger principles applied:

- Viewport state belongs in testable document/controller data, not transient paint code.
- Mesh operations should produce deterministic output artifacts and preserve the source mesh.
- The editor should expose selection/transform/modeling modes before deep sub-object editing, then wire each command into real operation services as the core matures.

Tests added for mesh preview loading, normalize-scale output generation, scene transform persistence, and transform type-in signaling.

## 2026-05-31 Universal Mesh Tools Slice 4

Adapted more of Ghost Rigger's useful mesh-tool architecture into Ghost Forge without KOTOR-specific assumptions:

- Added universal `MeshSelectionState` with object/sub-object modes and count reporting.
- Added `MeshTopologySummary` diagnostics over `trimesh` geometry: vertices, faces, edges, borders, non-manifold edges, isolated vertices, duplicate vertices, degenerate faces, connected elements, and warning text.
- Added `OperationHistory` path-swap commands so generated mesh-operation outputs can be undone/redone without mutating the source file.
- Expanded Modeling Tools with selection commands, operation options, and live mesh status.
- Expanded real operations to include weld/merge vertices, smooth Laplacian, subdivide, recenter, and apply material, in addition to the previous cleanup operations.

Book/Ghost Rigger principles applied:

- Selection state, topology, and history should be explicit editor services.
- Destructive-style edits should remain artifact-producing and undoable at the scene/document level.
- The panel should show active mesh, selection mode/counts, topology counts, and warnings so artists can understand mesh health while editing.

Tests added for topology diagnostics, selection state clearing/counts, operation history undo/redo, operation options, smooth/subdivide outputs, and main-window operation undo/redo.

## 2026-05-31 DCC Competitor Research Roadmap

Reviewed the current Ghost Forge Qt state against official/current capability surfaces for Blender, Maya, ZBrush, and RizomUV, then drafted `knowledge_base/roadmap/dcc_competitor_roadmap.md`.

Book/knowledge-base principles reinforced:

- The Qt books point us back to command routing, model/view state, settings, resources, and non-blocking work rather than widget-heavy feature sprawl.
- Game-engine architecture pushes Ghost Forge toward explicit assets, manifests, jobs, debug panels, repeatable export, and pipeline automation.
- The graphics/math books make viewport picking, transforms, coordinate conventions, quaternions, UVs, and numeric tolerance the next hard foundation.
- Competitor research confirms that Ghost Forge should first differentiate as an AI-native asset foundry and pipeline editor, then grow into Blender/Maya-style breadth through a durable document model, topology layer, renderer, UV workspace, material system, sculpt/retopo, animation/rigging, and extensibility.

Near-term implementation direction:

- Scene persistence and manifests.
- Ray-based picking and selection highlighting.
- Selection-aware mesh operations.
- Editable topology model and delta undo.
- UV workspace MVP.
- Core-owned operation/modifier graph.

## 2026-05-31 DCC Capability Research Refresh

Deepened the competitor research with current public docs for Blender 4.5, Maya 2026, ZBrush 2026, and RizomUV 2025, then cross-checked the roadmap against the project bible, current Qt code, and the user-provided Qt/math/engine books.

Design decisions reinforced:

- Scene/document persistence is the next enabling slice because every Blender/Maya-style operator, Maya-style pipeline hook, RizomUV-style UV state, and ZBrush-style remesh variant depends on stable resource identity.
- UV workflow should become an inspectable editor/audit surface with packing, density, distortion, overlap, padding, and manifest settings.
- Retopo/remesh should become guided, provenance-bearing variant generation with quality metrics instead of a vague optimization command.
- AI features must remain behind worker probes, sample runs, manifests, and audit gates.

Knowledge base additions:

- `knowledge_base/research/dcc_capability_research_2026-05-31.md`
- `knowledge_base/roadmap/dcc_competitor_roadmap.md` updated with current-source deltas and an immediate scene/document slice.

## 2026-05-31 Roadmap Slice 1 Scene Persistence

Commenced roadmap implementation with the DCC spine rather than another visual-only tool pass.

Added:

- Versioned `.gforge` scene document read/write service with project root, coordinate policy, object paths, transforms, topology stats, operation labels, asset directories, and manifest paths.
- Scene model support for loading full records and preserving asset/manifest links.
- Main-window `Open Scene`, `Save Scene`, and `Save Scene As` wiring through the QAction registry.
- Import/modeling manifest updates under the active project so scene objects point at current `asset_manifest.json` contracts.
- Operation history clearing on new/load so undo stacks do not leak across documents.

Book/roadmap principles applied:

- Qt actions and model/view state remain the editor command spine.
- Game-engine asset contracts now show up in the desktop scene rather than only at export time.
- Graphics/math coordinate policy is stored in the scene document, giving future picking/export work a place to anchor units and axes.

Verification:

- Focused persistence tests: 2 passed.
- Full Qt suite: 22 passed.
- Full Python suite: 537 passed, 3 skipped.

## 2026-05-31 Roadmap Slice 2 Viewport Picking

Implemented the first professional viewport interaction layer on top of the current CPU-projected Qt viewport.

Added:

- `ViewportPickResult` and reusable projected-frame data so paint, tests, and mouse picking use the same transform/projection contract.
- Left-click picking for object, vertex, edge, border, face, and element seed modes, including Shift additive and Ctrl toggle intent flags.
- Viewport selection highlighting for selected objects plus active vertex/edge/border/face/element selections.
- `ViewportHost.itemPicked` signal forwarding from the renderer.
- Main-window pick handling that updates the scene outliner, `MeshSelectionState`, modeling status panel, topology context, and viewport highlight state.
- Headless tests for projected picking modes and main-window selection propagation.

Book/roadmap principles applied:

- Picking is now explicit editor data, not transient paint-code behavior.
- The current implementation uses the same CPU projection as rendering, which is honest for this stage and testable.
- Future OpenGL/wgpu work can keep the same pick-result contract while replacing the projection/hit-test backend with real camera rays and acceleration structures.

Verification:

- Focused picking tests: 2 passed.
- Full Qt suite: 24 passed.
- Full Python suite: 539 passed, 3 skipped.

## 2026-05-31 Roadmap Slice 3 Selection-Aware Mesh Operations

Started converting the modeling panel from whole-object cleanup buttons into sub-object-aware editing commands.

Added:

- `MeshOperationSelection` snapshot payload for passing picked vertices, edges, borders, faces, and element seeds into CPU mesh operations.
- Selection-aware `delete` operation that removes selected faces, faces adjacent to selected edges, faces adjacent to selected vertices, or connected components seeded by element selection.
- Selection-aware `weld` operation that collapses selected vertices, or the endpoints of selected edges, into a single welded vertex and drops degenerate faces.
- Selection-aware `flip_normals` path that reverses only selected face windings; whole-mesh invert remains available when no sub-object selection exists.
- Main-window operation routing that passes `MeshSelectionState` into the operation service, clears stale sub-object selections after topology-changing edits, updates manifests, and preserves undo/redo path swapping.
- Selection provenance in `asset_manifest.json` operation steps, so selected-edit commands leave an audit trail.

Book/roadmap principles applied:

- Mesh operations are explicit, artifact-producing, and reversible at the scene/document level for now.
- Selection state now affects geometry, which is the first practical bridge from viewport picking toward an editable mesh core.
- Provenance records the selected sub-object inputs so later audit/debug surfaces can explain how an output mesh was produced.

Verification so far:

- Focused selected-operation tests: 5 passed.
- Full Qt suite: 28 passed.
- Full Python suite: 543 passed, 3 skipped.

## 2026-05-31 Roadmap Slice 4 Editable Mesh Core Foundation

Added the first in-memory editable topology model so Ghost Forge can move beyond output-file-only mesh edits.

Added:

- `EditableMeshSnapshot` with stable vertex IDs, edge IDs, face IDs, source path, explicit vertex/edge/face orders, and conversion to/from arrays or mesh files.
- `EditableVertex`, `EditableEdge`, and `EditableFace` records with adjacency links: vertex-to-edge, vertex-to-face, edge-to-face, face-to-edge.
- Topology validation for empty meshes, missing references, duplicate face vertices, zero-area faces, boundary edges, non-manifold edges, and isolated vertices.
- Face-neighbor and connected-component traversal.
- `MeshEditDelta` and `EditableMeshHistory` for true in-memory undo/redo of face deletion, while preserving stable IDs for untouched vertices, faces, and edges.
- Tests for stable topology IDs, validation warnings, connected components, edge ID preservation after deletion, and delta undo/redo.

Book/roadmap principles applied:

- Mesh editing now has a testable document-side topology contract instead of relying only on transient `trimesh` operations.
- Stable IDs and adjacency create the foundation for future edit tools such as dissolve, bridge, bevel, connect, detach, and modifier graph nodes.
- Delta undo is introduced in memory first; the current artifact-producing scene path remains intact until the editor document can safely become the primary source of truth.

Verification so far:

- Focused editable mesh tests: 3 passed.
- Full Qt suite: 31 passed.
- Full Python suite: 546 passed, 3 skipped.

## 2026-06-01 Tripo MCP Content Generation Slice

Added the MCP protocol books to the development bible and scanned them for recurring implementation themes around tools, resources, context, transport, security, authentication, and integration.

Design decisions applied:

- Tripo AI is modeled as a hosted `text_to_3d` worker in `ghostforge_core`, not as a GUI-only or MCP-only shortcut.
- Tripo credentials are environment/keyring-facing state. Raw keys must not be accepted into manifests, job specs, bridge packages, or knowledge-base notes.
- MCP game-generation workflows should use narrow tools and durable jobs, then preserve context through manifests, vertical-slice run state, and engine bridge packages.
- Unity-MCP-Ghost and Unreal-MCP-Ghost remain engine-specific import/repair surfaces; Ghost Forge owns prompt provenance, generated assets, audits, and bridge package creation.

Knowledge base additions:

- `knowledge_base/book_notes/mcp_integration.md`
- `knowledge_base/roadmap/tripo_mcp_engine_workflow.md`

Implementation direction:

- Register `tripo_api` as an env-gated hosted worker.
- Expose `submit_text_to_3d` with Tripo H3 smart mesh options.
- Allow vertical-slice assets to use `strategy="text_to_3d"` with `generation_extras`.
- Redact secret-shaped fields before writing manifest provenance.

## 2026-06-01 Graph-Native Worker Operations Slice

Continued the DCC roadmap by moving AI generation and worker processing into
the authoring graph rather than leaving it as a separate job-only pathway.

Book/roadmap principles applied:

- Game-engine asset pipeline design favors explicit resources, manifests,
  provenance, and debuggable state for every generated artifact.
- MCP guidance favors narrow schema-first tools over hidden mutable context;
  graph worker nodes are now durable operations that Qt, MCP, and headless
  automation can all inspect.
- Blender/Maya-style modifier/history workflows need generation, retopo, and
  texturing to participate in the same operation stack as cleanup/modeling.

Added:

- Source operation kinds for text-to-3D and image-to-3D graph nodes.
- Worker process nodes for mesh refinement/retopo and mesh texturing.
- Buffered and streaming graph evaluation support for graphs that begin with
  a source node and have no base mesh.
- Side-effect metadata linking graph nodes to worker output meshes, texture
  maps, worker names, asset directories, and emitted manifests.

Verification:

- Focused authoring worker/evaluator tests: 42 passed.

## 2026-06-01 Qt Operation Graph Dock Slice

Moved the new core graph capabilities into the PySide6 editor shell instead of
leaving them as backend-only affordances.

Book/roadmap principles applied:

- Qt model/view is the right shape for both operation palettes and graph stacks.
- Widgets stay thin: the panel collects node intent, while `CoreBridge` talks to
  `ghostforge_core.authoring.evaluate_graph`.
- Capability honesty belongs in the UI: worker-backed source/process operations
  now show runnable/stub/missing status derived from the worker registry.

Added:

- `OperationPaletteModel` and `OperationGraphModel` for available operations,
  graph nodes, parameter snapshots, and evaluation status.
- `OperationGraphPanel` dock with operation palette, node stack, prompt/reference
  fields, worker selection, add/remove, refresh, and evaluate commands.
- Main-window graph evaluation for selected-mesh process graphs and source-node
  graphs that create a new scene object.
- Manifest provenance for graph evaluations, including graph id, node steps,
  source mode, and worker side effects.

Verification so far:

- Focused Qt bridge/model/main-window tests: 15 passed.

## 2026-06-01 Scene Graph Persistence Slice

Turned the operation graph from a transient Qt panel state into durable scene
and core graph data.

Book/roadmap principles applied:

- Qt scene save/open should preserve user intent, not only baked artifacts.
- Game-engine resource architecture treats graphs as authored resources with
  identity, persistence, and repeatable evaluation.
- Keeping graphs in the `.gforge` scene and the core `EditGraphStore` gives the
  future MCP surface the same graph ids and node stacks the desktop editor uses.

Added:

- Optional per-object `EditGraph` on `SceneObjectRecord`.
- `.gforge` serialization/deserialization for operation graphs.
- `CoreBridge.save_authoring_graph` plus automatic graph/evaluation persistence
  when Qt evaluates a graph.
- Main-window wiring that stores graph edits on the selected scene object and
  restores the graph dock when reopening a saved scene.

Verification so far:

- Focused Qt scene/graph tests: 37 passed.

## 2026-06-01 MCP Graph Parity Slice

Extended the MCP surface so AI agents can inspect and evaluate the same
authoring graphs now used by Qt.

Book/roadmap principles applied:

- MCP tools mutate and resources expose durable inspectable state.
- Capability honesty applies to graph operations, not only standalone worker
  job submission.
- Source-worker graph evaluation must preserve graph ids, worker side effects,
  output paths, and manifest provenance so engine handoff can trust the result.

Added:

- Enriched `list_operations` payloads with operation type, capability,
  capability status, and matching worker probe state.
- MCP resources for operation descriptors, graph list, graph detail, and last
  graph evaluation.
- Graph evaluation persistence when MCP callers pass input/output overrides.
- Manifest side-effect handling for worker graph operations under
  `custom['graph_worker_operations']`, plus worker output/texture artifacts.
- End-to-end MCP test for evaluating an image-to-3D source graph without a base
  mesh and applying worker side effects to the final manifest.

Verification so far:

- Focused MCP graph/worker tests: 20 passed.

## 2026-06-01 Graph Evaluation Jobs Slice

Moved graph evaluation onto the shared durable job runner so long-running worker
graphs can be submitted, monitored, and resumed by MCP and Qt-facing services.

Book/roadmap principles applied:

- Game-engine tools should keep pipeline work outside the UI loop and preserve
  progress/results in durable stores.
- MCP agents need job ids and resources for resuming context instead of relying
  on a synchronous call staying open.
- Worker-backed graph operations now receive the job reporter/cancel token
  through `OperationContext`, keeping progress and cooperative cancellation
  available as graph execution grows heavier.

Added:

- `EvaluateGraphRequest` and `run_evaluate_graph` job handler.
- Bootstrap registration for `evaluate_edit_graph` as both a core registry
  operation and a job-runner kind.
- MCP `submit_evaluate_edit_graph` tool that returns a durable job handle.
- Qt `CoreBridge.submit_authoring_graph_evaluation` hook for non-blocking graph
  evaluation wiring.
- Core test proving graph jobs persist output and last evaluation state.

Verification so far:

- Focused graph job/MCP/Qt bridge tests: 20 passed.

## 2026-06-01 Qt Graph Job Completion Slice

Connected the Qt operation-graph dock to durable job completion so graph
evaluation no longer behaves like a blocking UI callback.

Book/roadmap principles applied:

- Qt widgets remain thin and receive completed state through controller/service
  boundaries.
- Game-engine pipeline work should emit durable job payloads that can update
  resources, manifests, diagnostics, and history after the fact.
- Graph jobs are shared core resources, so the same result can be inspected by
  Qt, MCP, tests, and future engine handoff flows.

Added:

- Main-window tracking for submitted graph evaluation job ids.
- Completion handling that applies successful graph jobs back into selected
  scene objects or creates source-generated scene objects.
- Manifest/provenance writes, topology refresh, graph panel status updates, and
  undo history entries from durable graph job payloads.
- Qt tests that poll the job controller until graph jobs settle before checking
  scene and manifest state.

Verification so far:

- Focused Qt graph completion tests: 12 passed.
- Full project verification after README/roadmap updates: 569 passed, 3 skipped.

## 2026-06-01 Descriptor-Driven Graph Params Slice

Replaced the hard-coded prompt/reference/worker controls in the Qt graph panel
with a schema-driven parameter form backed by operation descriptors.

Book/roadmap principles applied:

- Qt model/view panels should render typed data and collect intent without
  duplicating core operation logic.
- Operation descriptors are the shared contract for core evaluation, MCP
  discovery, and desktop graph editing.
- Growing toward a DCC modifier stack requires editable node parameters that
  survive graph persistence and remain independent of KOTOR or provider-specific
  assumptions.

Added:

- `OperationParameterForm` for descriptor-rendered string, path, int, float,
  bool, enum, vector, scalar/vector, JSON object, and worker-choice parameters.
- `OperationGraphModel.update_node_params` for immutable node-param edits that
  invalidate stale evaluation status.
- Graph panel add/edit wiring so selected operation descriptors create nodes
  with typed params and selected graph nodes can update their params.
- Focused Qt tests for descriptor parsing, add-node params, edit-node params,
  and required-parameter validation.

Verification so far:

- Focused operation graph parameter tests: 8 passed.
- Full project verification: 572 passed, 3 skipped.

## 2026-06-01 Graph Job Lifecycle UI Slice

Made queued graph evaluation visible and interruptible in the Qt graph panel.

Book/roadmap principles applied:

- Long-running jobs should show progress, cancellation, logs/state, and terminal
  outcomes outside the UI thread.
- Durable core job handles are the shared boundary for Qt and MCP; the graph UI
  should mirror those handles instead of inventing local-only state.
- A DCC-class modifier graph needs honest failure and retry affordances before
  hosted AI, retopo, and texture workers become routine.

Added:

- Operation-graph job strip with active job id, progress bar, stage/message,
  cancel button, terminal failed/cancelled/succeeded state, and retry control.
- Main-window wiring from `JobController.jobsChanged` into graph job progress,
  terminal completion, failure, cancellation, and cancel requests.
- Focused tests proving graph progress display, cancel signal emission,
  terminal retry state, success status display, and cancel routing.

Verification so far:

- Focused graph panel/MainWindow lifecycle tests: 13 passed.
- Full project verification: 574 passed, 3 skipped.

## 2026-06-01 Graph Result Badge Slice

Added per-node graph result affordances so evaluation reports are easier to act
on inside the Qt modifier graph.

Book/roadmap principles applied:

- Graph evaluation side effects are resource metadata, not incidental UI text.
- Model/view tables should expose artifact and manifest state through roles,
  display columns, and tooltips so future inspector/actions can reuse them.
- Failed graph evaluations should move the editor's attention to the failed
  node instead of making the artist hunt through logs.

Added:

- Operation graph columns for artifact badges and manifest/audit-ready badges.
- Per-node artifact paths, manifest paths, and tooltips derived from
  `EvaluationResult.metadata['side_effects']`.
- Failed-node focus when graph evaluation returns failed node steps.
- Focused tests for model badge roles/tooltips and panel failed-node focus.

Verification so far:

- Focused graph result badge tests: 20 passed.
- Full project verification: 576 passed, 3 skipped.

## 2026-06-01 Graph Audit And History Slice

Extended the graph result surface from one-shot badges into audit-aware result
history.

Book/roadmap principles applied:

- Manifest validation and audit history are the authoritative readiness signal;
  UI badges should read from manifest/evaluation payloads.
- Result history belongs in a model/view table so future graph inspectors, MCP
  resources, and persistence can reuse the same row contract.
- The operation graph should show enough recent evaluation context for an
  artist or agent to compare runs without searching job logs.

Added:

- `OperationGraphHistoryModel` with graph id, status, output path, artifact
  count, audit badge, and message columns.
- Manifest/audit badge extraction from `manifest.validation.status` and latest
  `manifest.custom['audit_history']` entry when present.
- Graph panel result-history table populated from evaluation payloads.
- Focused tests for audit badge extraction, history rows, and panel history
  updates.

Verification so far:

- Focused graph audit/history tests: 22 passed.
- Full project verification: 578 passed, 3 skipped.

## 2026-06-01 Graph-Linked Audit Action Slice

Connected the graph result surface to the core audit pipeline instead of leaving
audit badges as passive manifest display.

Book/roadmap principles applied:

- Audit readiness must be persisted through manifests, not computed as local UI
  state.
- Qt should submit long-running validation work as durable core jobs and then
  re-read the manifest to refresh the visible result.
- The graph panel is becoming a production modifier stack surface: evaluate,
  inspect, audit, retry, and follow provenance from the same UI.

Added:

- `CoreBridge.submit_audit_asset` wrapper over the shared `audit_asset` job.
- Graph-panel audit action, audit job status text, and manifest refresh hook.
- Main-window audit job context tracking, progress/terminal wiring, and
  manifest re-read after successful audit.
- Focused tests for bridge submission, panel audit request/refresh, and a full
  graph-evaluate-then-audit Qt flow that persists audit history.

Verification so far:

- Focused graph-linked audit tests: 20 passed.
- Full project verification: 580 passed, 3 skipped.

## 2026-06-01 Graph History Persistence Slice

Persisted operation-graph result history as part of the Qt scene document
contract.

Book/roadmap principles applied:

- Qt model/view data should survive save/open when it represents document
  state, not just widget chrome.
- Game-engine resource pipelines need repeatable provenance and validation
  context attached to the asset across sessions.
- A DCC-class modifier graph should restore its last evaluation and audit
  context when an artist reopens a project.

Added:

- Per-object `operation_graph_history` on scene records.
- `.gforge` write/read support for graph result history payloads.
- Main-window storage of graph history after evaluation, graph edits, and
  graph-linked audit refresh.
- Operation-graph panel/model payload round-tripping for restored history rows.
- Focused tests for scene document, graph panel, and main-window save/open
  restoration of history and audit badges.

Verification so far:

- Focused Qt persistence tests: 37 passed.
- Full project verification: 581 passed, 3 skipped.

## 2026-06-01 Graph Result Inspector And Bridge Slice

Started turning graph results into inspectable, engine-ready pipeline resources
inside the Qt editor.

Book/roadmap principles applied:

- Qt widgets should emit user intent while services/controllers perform
  pipeline work.
- Engine handoff must be manifest-driven and deterministic, with Unity/Unreal
  bridge packages produced by the shared core contract rather than direct
  editor-side calls.
- Graph evaluation history should lead to action: inspect artifacts, read audit
  readiness, and package validated outputs for downstream engine MCPs.

Added:

- Result inspector in the Qt operation-graph panel with selected result output,
  selected node artifact/manifest paths, manifest validation status, engine
  targets, and bridge history.
- Manifest-gated Unity/Unreal bridge buttons that are disabled when audit
  validation is failed or missing.
- `CoreBridge.create_engine_export_bridge` wrapper over the core offline export
  bridge contract.
- Main-window bridge creation handler that reads the selected asset manifest,
  blocks failed audit states, writes project bridge packages, refreshes the
  manifest-backed inspector, and keeps Unity/Unreal editor work downstream.
- Focused tests for bridge package creation, inspector readiness gates, bridge
  signals, and main-window manifest-backed bridge creation.

Verification so far:

- Focused graph inspector/bridge tests: 24 passed.
- Full project verification: 584 passed, 3 skipped.

## 2026-06-01 Graph Result Retarget Planning Slice

Connected Qt graph results to the shared core retarget planner that MCP already
uses.

Book/roadmap principles applied:

- Engine fix-up should be an authored operation graph, not a hidden export
  mutation.
- Qt panels emit intent; `CoreBridge` and `MainWindow` own core calls, scene
  attachment, graph persistence, and status reporting.
- Unity/Unreal handoff is more trustworthy when retarget diagnostics become
  visible graph nodes before bridge package creation.

Added:

- Result-inspector buttons for Unity and Unreal retarget planning.
- `CoreBridge.plan_engine_retarget_graph` wrapper over
  `ghostforge_core.retarget.plan_retarget_graph_for_asset`.
- Main-window retarget handler that creates a stable per-object retarget graph
  id, assigns output path/base path, saves the graph to the core store, and
  attaches it to the selected scene object.
- Focused tests for core planning, panel retarget signals, and main-window
  scene graph attachment.

Verification so far:

- Focused graph retarget planning tests: 26 passed.
- Full project verification: 586 passed, 3 skipped.

## 2026-06-01 Graph Retarget Diagnostics Slice

Made retarget planning inspectable instead of leaving the generated graph
unexplained.

Book/roadmap principles applied:

- Debuggability is a product feature for tools pipelines.
- Retargeting should remain graph-native and diagnostics-driven, not a hidden
  export-side mutation.
- Qt model/view state should expose structured report data that MCP and future
  inspectors can reason about.

Added:

- Planned graph history rows via `OperationGraphHistoryModel.append_payload`.
- Retarget diagnostics in the graph result inspector, filtered to `retarget.*`
  audit issues and showing issue counts, severity counts, codes, and
  suggestions.
- Main-window retarget planning now forwards the planner `AuditReport` payload
  into the graph panel before storing the scene object's graph history.
- Focused tests for planned history rows, retarget diagnostic filtering, and
  main-window persisted planned history.

Verification so far:

- Focused graph retarget diagnostics tests: 29 passed.
- Full project verification: 588 passed, 3 skipped.

## 2026-06-01 Retarget Diagnostics Persistence Slice

Moved retarget planner diagnostics from session-only UI state into persisted
graph history payloads.

Book/roadmap principles applied:

- Pipeline diagnostics are resource state when they explain why an operation
  graph exists.
- Scene documents should restore graph intent, result context, and audit
  evidence together.
- Qt model/view history should remain extensible enough for MCP and future
  inspectors to consume structured details, not just display text.

Added:

- Optional structured `details` on graph history rows.
- Retarget plan history details containing `retarget_target`,
  `retarget_report`, and generated node kinds.
- Inspector restoration of retarget diagnostics from saved history payloads.
- Save/open coverage proving planned retarget diagnostics survive `.gforge`
  scene persistence.

Verification so far:

- Focused retarget diagnostics persistence tests: 29 passed.
- Full project verification: 588 passed, 3 skipped.

## 2026-06-01 Retarget Diagnostic Comparison Slice

Turned retarget planning into a visible edit loop by comparing planner
diagnostics against the asset state after the generated retarget graph runs.

Book/roadmap principles applied:

- Tool pipelines need post-operation validation, not only preflight warnings.
- Retargeting remains more trustworthy when the evidence is persisted as
  resource history instead of UI-only labels.
- Qt panels should render structured state while `CoreBridge` and core audits
  own the actual validation work.

Added:

- `CoreBridge.lint_engine_retarget` for Unity/Unreal retarget-only audits.
- Post-evaluation retarget comparison in the Qt graph inspector, including
  resolved, remaining, and newly introduced diagnostic keys.
- Verified graph history rows that persist the planned report, after report,
  comparison buckets, target engine, and generated retarget node kinds.
- Main-window completion handling that records the comparison after retarget
  graph jobs update the selected scene object.
- Focused tests for bridge linting, graph-panel comparison rendering/restoring,
  and main-window comparison recording after graph evaluation.

Verification so far:

- Focused retarget comparison tests: 29 passed.
- Qt suite: 59 passed.
- Full project verification: 590 passed, 3 skipped.

## 2026-06-01 Graph Result File Actions Slice

Made graph outputs more like real pipeline resources by exposing file actions
from the Qt result inspector.

Book/roadmap principles applied:

- Model/view rows should carry structured resource state instead of forcing the
  UI to rediscover paths from labels.
- Qt widgets emit user intent; shell/controllers own desktop integration.
- Asset-pipeline tools need quick access to build products, manifests, audit
  evidence, and side-effect artifacts.

Added:

- Structured graph-history details for output-related paths: artifact paths,
  manifest paths, and asset directories discovered from side effects and
  manifest artifacts.
- Result-inspector buttons for opening outputs, opening artifacts, opening
  manifest/audit files, revealing outputs, and revealing asset directories.
- Main-window slots that route graph-result path actions through
  `QDesktopServices`, with missing-path status messages.
- Focused tests for history path payloads, inspector path signals/restoration,
  and main-window open/reveal dispatch without launching the OS.

Verification so far:

- Focused graph result file-action tests: 32 passed.
- Qt suite: 61 passed.
- Full project verification: 592 passed, 3 skipped.

## 2026-06-01 Graph Result Resource List Slice

Deepened graph-result file actions into a model-backed resource browser inside
the Qt operation-graph inspector.

Book/roadmap principles applied:

- Resource identity should be explicit in tools pipelines.
- Qt model/view is the right shape for selectable artifact/manifest rows.
- Desktop integration belongs in the shell while panels emit path intent.

Added:

- `GraphResultResourceModel` with kind/source/path columns for output meshes,
  side-effect artifacts, manifests, and asset directories.
- A resource table in the result inspector plus selected-resource open/reveal
  buttons.
- Categorization that prevents asset directories from being treated as mesh or
  texture artifacts even when older node side-effect roles expose them through
  artifact paths.
- Main-window reveal routing that can use Windows Explorer file selection for
  files while preserving folder-open fallback behavior.
- Focused tests for the resource model, resource selection/open/reveal signals,
  save/open restoration from history payloads, and main-window reveal dispatch.

Verification so far:

- Focused graph result resource-list tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Bridge And Audit Resource Rows Slice

Extended graph-result resources so manifest-backed handoff and validation
evidence are visible in the same Qt inspector table as generated artifacts.

Book/roadmap principles applied:

- Engine handoff packages are first-class pipeline outputs, not side notes.
- Audit evidence should travel with the asset resource and be restorable from
  scene history.
- Model/view resource rows make future drill-down inspectors possible without
  changing graph evaluation payloads.

Added:

- Bridge resource rows from manifest `engine.bridge.*` artifacts and
  `custom.engine_export_bridges[*].package_path`.
- Audit-history resource rows from latest `custom.audit_history`, pointing back
  to the manifest with preset/status source text.
- History details for `bridge_paths` and latest audit summary so reopened graph
  history can recreate bridge/audit resource rows.
- Focused tests proving bridge/audit rows appear in the resource table and
  restore from persisted graph-history payloads.

Verification so far:

- Focused bridge/audit resource tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Graph Resource Metadata Drill-Down Slice

Turned graph-result resource rows into small inspectable records rather than
path-only launch targets.

Book/roadmap principles applied:

- Debug/profiling surfaces are product features in tools pipelines.
- Manifest resources should carry enough context for users and MCP peers to
  understand readiness without opening raw JSON first.
- Qt model/view rows can expose compact details while the shell still owns file
  open/reveal integration.

Added:

- Details payloads on `GraphResultResource` rows.
- Resource details label in the operation-graph inspector.
- Bridge metadata drill-down: target engine, recommended MCP server/tool,
  created-at/direct-call fields when available.
- Audit metadata drill-down: preset, status, counts, timing, and manifest path
  context, restored from saved graph history.
- Focused tests for model tooltips and live/restored bridge/audit details.

Verification so far:

- Focused graph resource drill-down tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Manifest Validation Provenance Drill-Down Slice

Extended selected manifest resource details so graph results show why an asset
is ready or blocked and which operation trail produced it.

Book/roadmap principles applied:

- Manifest-driven pipelines should surface validation and provenance evidence
  directly in editor tooling.
- Debug surfaces should answer the first readiness question before a user opens
  raw JSON.
- Qt widgets can render compact summaries while preserving full manifest files
  as the authoritative source.

Added:

- Manifest resource details for asset id, validation status/counts,
  validation issue code summaries, artifact/provenance counts, audit/bridge
  history counts, and latest provenance step chains.
- Focused Qt coverage for validation issue summaries and provenance drill-down
  in the graph-result resource inspector.

Verification so far:

- Focused manifest validation/provenance drill-down tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Manifest Issue And Provenance Lists Slice

Expanded selected manifest resource details from compact summaries into useful
triage lists.

Book/roadmap principles applied:

- Tooling should expose build/validation evidence directly where users inspect
  graph outputs.
- Manifest data should remain authoritative, while Qt presents a readable
  subset for quick decisions.
- Provenance is part of the asset contract and should be visible beside
  validation state.

Added:

- Validation issue lists grouped by manifest report severity, including code,
  location, and message when available.
- Ordered provenance step lists with operation kind, short job id, and timing
  hints when available.
- List-aware resource detail rendering in the Qt graph-result inspector.
- Focused tests for issue-list and provenance-list rendering.

Verification so far:

- Focused manifest issue/provenance list tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Audit And Bridge Resource Drill-Down Slice

Completed the current graph-result resource drill-down loop by giving audit and
bridge rows their own persisted list/detail views.

Book/roadmap principles applied:

- Engine handoff packages are pipeline resources and should expose the contract
  a downstream MCP importer needs.
- Audit history is not just a pass/fail badge; selected rows should show the
  evidence that drove readiness decisions.
- Scene-restored history should preserve enough context for debugging without
  requiring a fresh audit or bridge package write.

Added:

- Persisted bridge package preview lines from `custom.engine_export_bridges`.
- Persisted audit issue lines from latest `custom.audit_history`.
- Selected-resource rendering for audit issue lists and bridge package preview
  fields in the Qt graph-result inspector.
- Focused tests proving live and restored bridge/audit rows keep the same
  details.

Verification so far:

- Focused audit/bridge resource drill-down tests: 33 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Graph Resource Filter Slice

Added focused resource filtering to the Qt graph-result inspector so generated
asset outputs, artifacts, manifests, asset directories, audit evidence, and
bridge handoff packages can be isolated without leaving the graph panel.

Book/roadmap principles applied:

- Qt model/view filters should change presentation while keeping resource
  identity and command routing stable.
- Tool pipelines need fast ways to isolate build products, evidence, and
  handoff packages when debugging readiness.
- Manifest-driven actions should keep deterministic full-resource context even
  when a user filters the visible table.

Added:

- A graph-result resource filter combo for all/output/artifact/manifest/
  asset-directory/audit/bridge rows.
- A preserved full resource row set behind the filtered table so output,
  artifact, manifest, and asset-directory open/reveal actions still work from
  the complete result context.
- Focused Qt coverage for every resource filter family and the global output
  path action after filtering.

Verification so far:

- Focused graph resource filter test: 1 passed.
- Operation graph panel tests: 9 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Retarget Diagnostic Diff Slice

Turned retarget verification from a summary-only label into a model-backed diff
surface in the Qt graph-result inspector.

Book/roadmap principles applied:

- Retarget verification is a pipeline event and should preserve comparison
  evidence, not just a toast or status line.
- Qt model/view surfaces make diagnostic tables testable and restorable from
  scene/history payloads.
- Remaining and newly introduced target-engine diagnostics are the next
  artist/agent action targets, so they should sort ahead of resolved evidence.

Added:

- `RetargetDiagnosticModel` and row data for planned, remaining, new, and
  resolved diagnostics.
- A retarget diff table in the graph-result inspector showing state, severity,
  rule, code, target, message, and suggestion.
- Retarget comparison summaries that name remaining and new diagnostic
  families.
- Focused tests proving planned rows, ordered remaining/new/resolved rows, and
  restored history diff rows.

Verification so far:

- Focused retarget diagnostics diff test: 1 passed.
- Focused retarget model/panel tests: 2 passed.
- Operation graph model and panel tests: 20 passed.
- Qt suite: 63 passed.
- Full project verification: 594 passed, 3 skipped.

## 2026-06-01 Bridge Package JSON Preview Slice

Added compact bridge package JSON preview to the Qt graph-result inspector so a
selected Unity/Unreal bridge row can show the external handoff contract without
requiring users to open the raw JSON file.

Book/roadmap principles applied:

- Engine handoff should remain deterministic, offline, and inspectable.
- Debug surfaces should expose enough package evidence for readiness triage
  without bypassing the manifest or bridge package file as the authority.
- Qt panels can enrich selected-resource details while keeping actions routed
  through the existing signal/service boundary.

Added:

- Safe selected bridge-package JSON reading with a compact preview of bridge
  version, target engine, asset id, asset path, manifest path, target path,
  recommended MCP server/tool, created timestamp, embedded manifest validation,
  artifact count, and notes.
- Focused test coverage for live and restored bridge resource previews from a
  realistic `ghostforge_bridge_unity.json` fixture.

Verification so far:

- Focused bridge package preview test: 1 passed.
- Operation graph panel tests: 9 passed.
- Qt suite: 62 passed.
- Full project verification: 593 passed, 3 skipped.

## 2026-06-01 Operation Graph Node Bypass Slice

Added per-node enable/disable controls to the Qt operation graph so users can
bypass a modifier/operation without deleting the authored node or losing its
parameters.

Book/roadmap principles applied:

- Non-destructive graph intent should remain editable and repeatable.
- Qt controls should mutate the model through typed methods and emit normal
  graph-change signals instead of hiding state in the widget.
- Changing graph intent invalidates stale evaluation badges and status.

Added:

- `OperationGraphModel.set_node_enabled()` for immutable node enabled-state
  updates.
- A Qt graph-panel `Enable Node` / `Disable Node` button that follows selected
  node state and is disabled while graph jobs are running.
- Focused model and panel tests proving disabled/enabled display, parameter
  preservation, stale evaluation reset, and graph-change emission.

Verification so far:

- Focused node bypass tests: 2 passed.
- Operation graph model and panel tests: 20 passed.
- Qt suite: 63 passed.
- Full project verification: 594 passed, 3 skipped.

## 2026-06-01 Operation Graph Reorder Slice

Added explicit graph node reordering controls to the Qt operation graph so the
non-destructive stack order can change without deleting and recreating nodes.

Book/roadmap principles applied:

- The authoring schema defines graph evaluation as an ordered enabled-node
  list, so order must be directly editable in the UI.
- Reordering graph intent invalidates previous evaluation state and should use
  the same model/signal path as parameter edits and node bypass.
- Model-level reorder support is the groundwork for later drag-and-drop.

Added:

- `OperationGraphModel.move_row()` for immutable node-list reordering.
- Move Up / Move Down buttons in the Qt operation graph panel.
- Selection preservation on the moved node and boundary-aware button states.
- Focused model/panel tests proving reordered ids, preserved params, stale
  evaluation reset, selection preservation, and graph-change emission.

Verification so far:

- Focused graph reorder tests: 2 passed.
- Operation graph model and panel tests: 22 passed.
- Qt suite: 65 passed.
- Full project verification: 596 passed, 3 skipped.

## 2026-06-01 Operation Graph Drag Reorder Slice

Extended graph node reordering from toolbar buttons to Qt model-backed
drag/drop behavior.

Book/roadmap principles applied:

- Qt model/view drag/drop should mutate the underlying resource model, not just
  shuffle visible rows.
- Modifier stack order is authored graph intent and must remain shared between
  desktop UI, saved scenes, MCP inspection, and graph evaluation.
- Drag/drop is a UI gesture; `OperationGraphModel` remains the owner of graph
  order changes.

Added:

- Move-only MIME/drop support for graph node rows in `OperationGraphModel`.
- Qt internal move configuration for the operation graph table.
- `rowsMoved` handling in the panel that emits `graphChanged` for drag-driven
  reorders.
- Focused tests proving model drop behavior, panel drag/drop configuration,
  and graph-change emission from a simulated drop.

Verification so far:

- Focused drag/drop reorder tests: 2 passed.
- Operation graph model and panel tests: 22 passed.
- Qt suite: 65 passed.
- Full project verification: 596 passed, 3 skipped.

## 2026-06-01 Operation Parameter Path Picker Slice

Upgraded descriptor-generated graph parameter editing so path-like operation
fields render as file/folder picker controls instead of plain string fields.

Book/roadmap principles applied:

- Qt forms should stay schema-driven and avoid per-operation branches.
- Tool inputs are resource references, so file and folder paths should be
  ergonomic in the editor while remaining serializable graph payloads.
- The widget can improve artist workflow without changing the core/MCP
  operation contract.

Added:

- `PathParameterWidget`, a compact line edit plus browse button for file and
  folder parameter selection.
- Descriptor inference for `type: path`, `format: directory`, and
  path-like parameter names.
- Focused tests proving generated file/folder picker modes and dialog-driven
  browse behavior without launching a modal dialog.

Verification so far:

- Focused path parameter tests: 2 passed.
- Operation graph panel tests: 11 passed.
- Qt suite: 66 passed.
- Full project verification: 597 passed, 3 skipped.

## 2026-06-01 Operation Parameter Preset Slice

Promoted graph operation presets into the shared authoring descriptor contract
and taught the Qt parameter form to apply them without per-operation branches.

Book/roadmap principles applied:

- Qt controls should be generated from descriptor metadata rather than custom
  operation widgets.
- MCP operation discovery should expose the same parameter profiles as the
  desktop editor so agents can compose graph nodes with known starting values.
- A preset is authoring intent ergonomics; evaluated graphs still store
  concrete node parameters.

Added:

- `OperationDescriptor.parameter_presets` and `OperationRow.parameter_presets`.
- Default and selectable presets for smoothing, decimation, materials, lightmap
  UV bake, convex collision bake, text/image source generation, worker refine,
  and worker texture operations.
- A Qt preset combo that applies descriptor presets through existing generated
  widgets and preserves normal graph parameter serialization.
- Focused Qt, bridge, and MCP tests proving preset application and descriptor
  exposure.

Verification so far:

- Focused descriptor preset tests: 3 passed.
- Focused core/Qt/MCP descriptor preset tests: 43 passed, 1 skipped.
- Qt suite: 67 passed.
- Full project verification: 598 passed, 3 skipped.

## 2026-06-01 Scene Graph History Resource Link Slice

Made saved Qt scene graph history addressable by MCP resources.

Book/roadmap principles applied:

- Saved scenes should preserve graph intent and history as resources, not
  transient UI labels.
- MCP resources should expose inspectable state that agents can resume from.
- Resource identity must stay deterministic across save/open so automation can
  refer to the same graph-history row later.

Added:

- `ghostforge_core.scene_links` helpers for scene ids, graph URIs, evaluation
  URIs, deterministic graph-history ids, and scene object history resource URIs.
- Qt scene document save/open annotation for graph-history rows with
  `history_id`, `resource_uri`, and `mcp_links`.
- MCP resources for `ghostforge://scenes`, scene documents, scene object graph
  history lists, and individual history rows.
- Focused Qt and MCP tests proving scene save/open history links and MCP
  scene/history resource inspection.

Verification so far:

- Focused scene graph-history resource tests: 4 passed.
- Focused scene/MCP persistence tests: 47 passed.
- Qt suite: 67 passed.
- Full project verification: 599 passed, 3 skipped.

## 2026-06-01 MCP Graph Workflow Prompt Slice

Added first-class MCP prompts for repeated graph and engine-handoff workflows.

Book/roadmap principles applied:

- MCP prompts should encode repeatable workflows while tools perform actions
  and resources expose inspectable state.
- Agent workflows must route through worker probes, graph resources, manifests,
  audits, and bridge packages rather than direct side channels.
- Prompt guidance should preserve Ghost Forge as the source of truth for asset
  generation, repair, validation, provenance, and engine handoff.

Added:

- `generate_engine_ready_prop` prompt for text-to-3D graph generation,
  evaluation, audit, repair, and bridge packaging.
- `repair_generated_mesh_for_unity` prompt for scene/history-driven Unity
  repair loops using audits and retarget graphs.
- `prepare_unreal_static_mesh_package` prompt for Unreal audit, retarget, and
  `ghostforge_bridge_unreal.json` packaging.
- Focused MCP test coverage for prompt registration and rendered workflow
  content.

Verification so far:

- Focused MCP workflow prompt test: 1 passed.
- MCP authoring surface tests: 13 passed.
- Qt suite: 67 passed.
- Full project verification: 600 passed, 3 skipped.

## 2026-06-01 Scene Graph History Comparison Slice

Added structured comparison for saved scene object graph-history rows.

Book/roadmap principles applied:

- Saved graph results are pipeline evidence and should be comparable without
  hand-parsing scene JSON.
- MCP actions/resources should preserve deterministic resource identity and
  return structured deltas agents can reason over.
- Comparison should focus on manifest and handoff-relevant fields: output,
  artifacts, bridge packages, audit status/issues, and retarget diagnostics.

Added:

- `compare_graph_history_payloads()` in `ghostforge_core.scene_links`.
- `compare_scene_graph_history` MCP tool.
- `ghostforge://scenes/{scene_id}/objects/{object_id}/graph-history/{left_history_id}/compare/{right_history_id}` resource.
- Focused MCP tests proving comparison registration and output/audit/resource
  deltas across two saved graph-history rows.

Verification so far:

- Focused MCP graph-history comparison tests: 2 passed.
- MCP authoring surface tests: 13 passed.
- Qt suite: 67 passed.
- Full project verification: 600 passed, 3 skipped.

## 2026-06-01 Qt Graph History Comparison Slice

Added graph-history delta comparison to the Qt result inspector so artists can
see the same output, artifact, bridge, audit, and retarget changes that MCP
agents receive from scene graph-history comparison resources.

Book/roadmap principles applied:

- Qt model/view panels should display shared core state rather than inventing
  local-only comparison logic.
- Saved graph-history rows are pipeline evidence and must preserve stable
  `history_id`, `resource_uri`, and `mcp_links` fields across UI round-trips.
- Artist-facing debugging and MCP automation should converge on the same
  manifest-backed diff contract.

Added:

- `GraphEvaluationHistoryRow` preservation for saved graph-history resource
  identity fields.
- A selectable `History Delta` result-inspector label that compares the
  selected row against the previous row via `compare_graph_history_payloads()`.
- Focused Qt test coverage for resource-id preservation, output/audit/resource
  deltas, retarget list deltas, and the oldest-row no-comparison state.

Verification so far:

- Py compile for edited Qt graph files: passed.
- Focused Qt graph-history comparison test: 1 passed.
- Operation graph panel tests: 13 passed.
- Qt suite: 68 passed.
- Full project verification: 601 passed, 3 skipped.

## 2026-06-01 Qt Graph History Pair Link Slice

Extended the Qt graph-history comparison surface from adjacent selected-row
diffs to explicit From/To pair selection with a copyable MCP comparison URI.

Book/roadmap principles applied:

- Qt widgets should present model-backed state while shared helpers preserve
  resource identity and URI rules.
- Saved graph-history rows are pipeline resources, so non-adjacent comparisons
  should address the same MCP resource an agent can read later.
- Human debugging and agent automation should share a stable handoff link
  rather than relying on screenshots or copied prose.

Added:

- `graph_history_comparison_resource_uri_from_payloads()` in
  `ghostforge_core.scene_links`.
- Qt From/To combo boxes for graph-history comparison pairs.
- A selectable MCP comparison URI label plus `Copy Compare URI` button/signal.
- Focused Qt coverage for non-adjacent comparison, URI derivation, clipboard
  copy, and disabled copy state when only one row is selected as both sides.

Verification so far:

- Py compile for edited scene-link and Qt graph files: passed.
- Focused Qt graph-history pair/link test: 1 passed.
- Operation graph panel tests: 13 passed.
- Qt suite: 68 passed.
- Full project verification: 601 passed, 3 skipped.

## 2026-06-01 Qt Graph History Delta Table Slice

Added a model-backed delta table to the Qt graph-history comparison surface so
artists can scan comparison evidence without reading the full prose summary.

Book/roadmap principles applied:

- Qt model/view is the right shape for data-heavy diagnostic surfaces.
- Pipeline/debug evidence should be structured rows that can later be filtered,
  sorted, and addressed by tests.
- The desktop editor should render the same field, resource, audit, and
  retarget deltas that MCP exposes, keeping human and agent inspection aligned.

Added:

- `GraphHistoryDeltaRow` and `GraphHistoryDeltaModel`.
- Delta-row conversion for changed top-level fields, resource path changes,
  audit count/issue changes, and retarget diagnostic list changes.
- A `Delta Table` in the graph result inspector that updates with the selected
  comparison pair.
- Focused model and panel tests for comparison row rendering.

Verification so far:

- Py compile for edited Qt graph/model files: passed.
- Focused delta model/panel tests: 2 passed.
- Operation graph panel tests: 13 passed.
- Qt suite: 69 passed.
- Full project verification: 602 passed, 3 skipped.

## 2026-06-01 Qt Graph History Comparison Persistence Slice

Promoted the active Qt graph-history comparison pair from transient widget
state into persisted `.gforge` scene state.

Book/roadmap principles applied:

- Qt model/view state should be restored from the document, not reconstructed
  from incidental combo-box defaults.
- Pipeline/debug evidence should survive editor restarts if it can influence
  artist or MCP agent decisions.
- MCP comparison URIs are more useful when the desktop scene reopens on the
  same left/right evidence target that produced the URI.

Added:

- `SceneObjectRecord.operation_graph_comparison_pair`.
- `.gforge` serialization/deserialization for validated left/right
  graph-history ids.
- Qt graph-panel APIs and signals for reading/restoring the selected comparison
  pair while keeping pair selection model-backed.
- Main-window save/open synchronization so reopened scenes restore the From/To
  comparison controls, delta table, and copyable MCP comparison URI.
- Focused tests for scene document round-trip, panel pair restore, and
  main-window save/reopen behavior.

Verification so far:

- Focused comparison persistence tests: 3 passed.
- Full project verification: 602 passed, 3 skipped.
