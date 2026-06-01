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
