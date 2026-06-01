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
