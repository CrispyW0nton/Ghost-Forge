# Ghost Forge DCC Competitor Roadmap

Date: 2026-05-31

## Purpose

This roadmap maps Ghost Forge's current Qt/PySide6 state against the capability envelopes of Blender, Maya, ZBrush, and RizomUV. It is not a promise to clone those tools feature-for-feature. Ghost Forge's credible route is to become an AI-native universal 3D asset foundry with enough DCC depth for artists to inspect, repair, edit, automate, and ship assets.

## Inputs Reviewed

Project state:

- `knowledge_base/audits/2026-05-31_current_state.md`
- `knowledge_base/crosswalks/ghostforge_development_bible.md`
- `knowledge_base/roadmap/qt_migration_plan.md`
- Current `ghostforge_qt` modules for the Qt shell, action registry, viewport, theme system, project content browser, scene model, worker/job panels, mesh diagnostics, mesh operation service, selection state, and operation history.

Book-derived inputs:

- Qt books: QAction command routing, signals/slots, model/view, settings, dialogs, resources, and non-blocking worker processes.
- Game engine architecture: explicit asset resources, pipelines, debug/profiling surfaces, concurrency boundaries, repeatable build/export contracts.
- Graphics/math books: coordinate systems, matrices, transforms, quaternions, rays, picking, intersections, UV/texture space, and numeric tolerance.
- Lightweight PDF term scan confirmed repeated emphasis on these areas: signals/threads/resources in the Qt books; resources/threads/transforms/quaternions in engine architecture; coordinates/matrices/transforms/quaternions/rays/UVs in the math books.

External capability research:

- Blender: official manual and API documentation for modeling, sculpting/painting, UV editing, Geometry Nodes, animation/rigging, rendering, asset browser, Python API, and add-ons.
- Maya: official Autodesk documentation/product pages for modeling, animation, rigging, Bifrost, Arnold, USD, scripting, and plug-in development.
- ZBrush: official Maxon documentation/product pages for sculpting, brushes, SubTools, DynaMesh, ZRemesher, ZModeler, PolyPaint, UV Master, Decimation Master, GoZ, ZScript, and Python hooks.
- RizomUV: official Rizom-Lab material for unwrap, seams, packing, texel density, UDIMs, distortion visualization, automation/scripting, command-line use, and SDK/library integration.

Current-source deltas checked on 2026-05-31:

- Blender 4.5 manual reinforces that viewport operators, undo/redo, selection, UV editor, geometry nodes, sculpt/paint, animation/rigging, physics, rendering, assets, add-ons, and Python scripting are all part of the expected "suite" surface.
- Maya 2026 materials reinforce the production-pipeline axis: OpenUSD, Bifrost, Arnold, LookdevX, Flow Retopology, Substance updates, OpenColorIO, scripting, rigging, animation, and AI-assisted deformation.
- ZBrush 2026 materials reinforce sculpt-first workflow depth: more than 200 brushes, DynaMesh, PolyPaint, Live Boolean, Redshift, ZModeler, Python scripting, GoZ/Substance bridge updates, ZRemesher controls, and UV Master constraints.
- RizomUV 2025 materials reinforce UV specialization: GPU packing, packing strategies, orientation tools, group-to-tile workflows, scene outliner, saved defaults, primitive selection conversion, invalid topology selection, pixel grid display, and SDK/library automation.
- Detailed notes from this pass live in `knowledge_base/research/dcc_capability_research_2026-05-31.md`.

Primary source links:

- Blender manual/API: `https://docs.blender.org/manual/en/4.5/`, `https://docs.blender.org/manual/en/4.5/modeling/index.html`, `https://docs.blender.org/manual/en/4.5/editors/uv/index.html`, `https://docs.blender.org/api/current/bpy.ops.html`
- Maya docs/product: `https://www.autodesk.com/products/maya/overview`, `https://www.autodesk.com/products/maya/features`, `https://help.autodesk.com/view/MAYAUL/2026/ENU/`, `https://help.autodesk.com/view/MAYADEV/2026/ENU/`
- ZBrush docs: `https://www.maxon.net/en/zbrush`, `https://help.maxon.net/zbr/en-us/Content/html/user-guide/zbrush-plugins/uv-master/uv-master.html`, `https://help.maxon.net/zbr/en-us/Content/html/reference-guide/tool/polymesh/geometry/zremesher/zremesher.html`, `https://help.maxon.net/zbr/en-us/Content/html/features/main-features/texturing/texturing.html`
- RizomUV docs/product: `https://www.rizomuv.com/`, `https://www.rizomuv.com/c-library/`, `https://www.rizomuv.com/feature/rizomuv-2025-whats-new/`

## Current Ghost Forge Baseline

Strong foundations:

- Tested Python core for jobs, workers, manifests, audits, engine handoff, authoring graphs, knowledge base, and MCP.
- Qt shell exists with main window, actions, docks, theme manager, project content browser, scene outliner, worker/job panels, and modeling dock.
- Viewport can draw a grid, axes, camera presets, display modes, CPU-projected mesh previews, object transforms, and basic overlays.
- Modeling services support artifact-producing operations: recalculate normals, flip normals, remove isolated vertices, decimate when a backend is available, normalize scale, recenter, weld, smooth Laplacian, subdivide, and apply material.
- Selection state, topology diagnostics, and scene-level undo/redo path swapping exist.

Current gap:

Ghost Forge is a real Qt editor foundation, not yet a real DCC. It now has early scene persistence, viewport picking, selection-aware operations, an editable mesh-core foundation, and graph-native worker operations for generation/refine/texture. It still needs GPU viewport rendering, deeper sub-object edit mode, a full document-owned mesh data model, UV editor, material system, modifier graph UI, sculpt/retopo workflows, animation/rigging editors, and mature interchange before it can compete with mature tools.

Recent progress as of 2026-06-01:

- Worker-backed authoring graph nodes landed for `generate_text_to_3d`, `generate_image_to_3d`, `worker_refine_mesh`, and `worker_texture_mesh`.
- Authoring graphs can now start from a source operation without a base mesh, while preserving manifests and side-effect metadata for worker outputs.
- Streaming and buffered evaluation paths share the same source-node semantics, which keeps Qt live preview, MCP progress, and headless automation aligned.
- Qt now has an operation-graph dock with a model/view palette, node stack, worker capability status, and evaluation path for selected mesh graphs or source-generated meshes.
- `.gforge` scene documents now round-trip per-object `EditGraph` resources, and Qt mirrors changed/evaluated graphs into the core graph store.
- MCP now exposes enriched operation descriptors, graph resources, graph evaluation resources, and source-worker graph evaluation with manifest side-effect provenance.
- Core and MCP now support durable `evaluate_edit_graph` jobs, with progress/result persistence and last-evaluation resources for long-running graph execution.
- Qt graph evaluation now submits durable jobs, watches terminal job state, and applies successful payloads back into scene objects or new source-generated objects with manifests, topology refresh, operation history, and node status updates.

## Competitor Capability Map

### Blender Capability Envelope

What matters:

- Dense modeling workflows: object/edit/sculpt modes, mesh editing, modifiers, curves, geometry nodes, snapping, proportional editing, overlays, and add-ons.
- Full pipeline breadth: UVs, materials, texture painting, rendering, animation, rigging, simulation, compositing, asset browser, scripting, and batch automation.
- Extensibility: Python API, operators, add-ons, custom panels, and data-block architecture.

Ghost Forge lesson:

Blender's power comes from a shared document/data model and operator stack. Ghost Forge should build a typed scene/document plus command/operation graph before chasing hundreds of individual tools.

### Maya Capability Envelope

What matters:

- Production animation and rigging: timeline, graph editor, constraints, skeletons, skin weights, deformers, references, USD, and pipeline APIs.
- Professional modeling and retopology workflows: mesh modeling, symmetry, retopology, UV tools, history stack, and procedural graph systems.
- Studio integration: scripting, plug-ins, scene references, USD workflows, Arnold/lookdev, batch/headless operation, and custom pipeline hooks.

Ghost Forge lesson:

Maya's moat is pipeline seriousness. Ghost Forge should make manifests, provenance, automation, audit gates, and engine handoff first-class instead of treating them as export afterthoughts.

### ZBrush Capability Envelope

What matters:

- High-density sculpting: brush engine, pressure-sensitive strokes, masking, polygroups, SubTools, layers, subdivision, DynaMesh-style remeshing, decimation, and retopology assistance.
- Artist-first mesh creation: primitives, ZSpheres-style blocking, ZModeler-style polygon editing, booleans, PolyPaint, material preview, and quick presentation/render modes.
- Interop: GoZ-style handoff and export tools.

Ghost Forge lesson:

Do not start by chasing high-poly sculpting. Build retopo/remesh/decimation, brush infrastructure, masking, and vertex-color painting after the viewport and editable topology layer are reliable.

### RizomUV Capability Envelope

What matters:

- Specialist UV quality: fast seam marking, unwrap, island editing, texel density controls, distortion views, packing, UDIM workflows, selection tools, and automation.
- Pipeline integration: command-line/scriptable processing and embeddable/library-style use cases.

Ghost Forge lesson:

UVs deserve their own editor, diagnostics, and automation path. Ghost Forge should support xatlas/core unwrap early, but the product-grade target is a UV workspace with seam editing, island packing, texel density, UDIMs, distortion heatmaps, and batch automation.

## Product Positioning

Near term:

Ghost Forge should compete as an AI-native asset pipeline and correction tool. It should import or generate assets, show exactly what is runnable, repair common geometry issues, unwrap/texture/audit assets, preserve provenance, and package outputs for engines.

Mid term:

Ghost Forge should become a practical universal modeling suite for asset finishing: object/sub-object selection, mesh editing, modifiers, UVs, materials, basic rigging, batch automation, and engine export.

Long term:

Ghost Forge can become a Blender/Maya-class alternative in targeted production flows by making AI automation, validation, provenance, and engine handoff stronger than legacy DCCs, while growing the core editing surface steadily.

## Roadmap Phases

### Phase 1: DCC Spine

Goal: make the current Qt foundation behave like a durable editor.

- Add a real project/scene file format, for example `.gforge`, containing scene objects, transforms, source asset paths, operation history, material slots, unit scale, coordinate convention, and manifest links.
- Promote current mesh operations from Qt-only outputs into a core authoring/operation graph.
- Add document save/load, autosave, recent projects, and layout persistence.
- Add manifest creation/update for every import, generated output, cleanup operation, texture operation, and export.
- Add an asset inspector that shows mesh stats, topology warnings, UV status, material slots, provenance, and export readiness.
- Keep `python -m pytest` and Qt headless tests green after every slice.

Acceptance gate:

- Open/import/save/reopen a project with meshes, transforms, generated operation outputs, topology summaries, and manifests intact.

### Phase 2: Professional Viewport Interaction

Goal: move from preview rendering to editor interaction.

- Add ray-based object, vertex, edge, face, border, and element picking.
- Add hover and selection highlighting in the viewport.
- Add box select, lasso select, grow/shrink selection, select linked, select boundary, and invert.
- Add camera orbit/pan/zoom with stable framing, clipping, view presets, bookmarks, and frame selected.
- Add transform gizmo handles for move/rotate/scale with snapping, axis constraints, pivot modes, local/world orientation, and numeric type-in.
- Add measurement tools, grid scale controls, safe area/axis overlays, normal display, face orientation display, and x-ray/wire/solid/material display modes.
- Replace or hide the CPU painter behind a renderer abstraction when an OpenGL/wgpu viewport is ready.

Acceptance gate:

- Deterministic tests for ray picking, transform persistence, snapping, and coordinate conversion.

### Phase 3: Editable Mesh Core

Goal: establish the topology layer that all serious modeling features need.

- Add an editable mesh representation with stable vertex/edge/face IDs, adjacency, normals, UV references, material indices, and validation.
- Add true undo/redo commands over mesh deltas, not only path swaps.
- Implement first real sub-object tools: delete, dissolve, extrude, inset, bevel, bridge, connect, fill/cap, split, merge, weld selected, flip selected normals, separate, duplicate, and detach.
- Add symmetry/mirror editing and proportional editing.
- Add a non-destructive modifier stack: mirror, bevel, solidify, subdivision, triangulate, decimate, boolean, array, remesh, weighted normals.
- Keep artifact-producing mode for AI-generated/cleanup steps, but allow interactive edits inside the document.

Acceptance gate:

- A user can model and save a simple hard-surface prop from primitives using only Ghost Forge.

### Phase 4: UV And Texture Workspace

Goal: build the RizomUV-inspired workflow without becoming UV-only software.

- Add a 2D UV viewport with island selection, seam marking, pinning, unwrap, relax, straighten, align, stitch, split, pack, rotate, scale, and mirror.
- Add texel density controls, checker preview, distortion heatmap, overlapped island detection, flipped UV detection, and UDIM tile management.
- Add xatlas/built-in unwrap jobs and optional external bridge points for specialist tools.
- Add material slots, texture-set management, PBR channel slots, image previews, bake targets, and generated texture provenance.
- Add batch UV/texture automation for project folders.

Acceptance gate:

- Import a mesh, mark seams, unwrap, inspect distortion, pack islands, assign PBR textures, and export glTF/USD with UVs/materials intact.

### Phase 5: AI-Native Asset Foundry

Goal: make Ghost Forge meaningfully different from Blender/Maya.

- Add model/dependency install and cache manager for TRELLIS, Hunyuan3D, TripoSG, InstantMesh, texture workers, and local/remote AI providers.
- Add hosted-provider integrations beginning with Tripo H3 text-to-model: secure API key handling, smart mesh options, polling/download, sample generation tests, and MCP-ready engine handoff.
- Add prompt/reference boards with citations, image refs, silhouette refs, style refs, constraints, negative prompts, and target engine profiles.
- Add variant browser with side-by-side topology, UV, material, audit, and engine-readiness comparisons.
- Add AI repair commands: fix scale, make watertight, reduce polycount, retopologize, unwrap, texture, generate LODs, generate collision, name/material cleanup, and export package.
- Add provenance graph connecting prompts, references, workers, intermediate meshes, operations, audits, and final exports.
- Add an AI command palette that proposes operations but routes through explicit, undoable commands.

Acceptance gate:

- A user can generate or import a rough asset, let Ghost Forge propose corrections, accept/reject each operation, and ship an audited engine-ready package.

### Phase 6: Sculpt And Retopology

Goal: bring in ZBrush-inspired asset creation after the viewport/topology/operation layers are stable.

- Add brush infrastructure: radius, strength, falloff, symmetry, masking, smoothing, inflate, clay/build-up, pinch, flatten, scrape, move, grab, crease, and polish.
- Add multiresolution or dynamic remesh strategy after profiling.
- Add vertex color/PolyPaint-style painting and mask/paint layers.
- Add decimation, remesh, quad-retopo integration, shrinkwrap, projection, and high-to-low baking.
- Add stylus/tablet pressure support through Qt input events.

Acceptance gate:

- Sculpt a blocked-out organic asset, retopologize/decimate it, bake detail to a lower-poly mesh, and export.

### Phase 7: Animation, Rigging, And Deformation

Goal: grow toward Maya/Blender character and motion workflows.

- Add timeline, keyframes, dope sheet, graph editor, playback controls, and animation curves.
- Add skeleton/joint tools, constraints, IK/FK basics, skin binding, weight painting, blendshapes, and retargeting UI over the existing core concepts.
- Add deformers: lattice, bend, twist, taper, curve, smooth, shrinkwrap, and corrective shapes.
- Add animation import/export for glTF and FBX/USD where available.

Acceptance gate:

- Rig a simple character or prop, animate it, preview motion in the viewport, and export with validated skeleton/animation data.

### Phase 8: Pipeline, Interchange, And Extensibility

Goal: match the production seriousness of Maya while keeping Ghost Forge's AI/core advantage.

- Add robust import/export: glTF/GLB, OBJ, STL, PLY, USD/USDZ, Alembic, and FBX where licensing/dependencies permit.
- Add USD layers/variants/material bindings as a first-class pipeline path.
- Add Python scripting API, command registry, plug-in manifest format, and MCP bridge parity.
- Add batch/headless processing for import, generate, audit, repair, UV, texture, LOD, and engine package workflows.
- Add engine target profiles for Unity, Unreal, Godot, web/glTF, and custom studio profiles.
- Add profiler/debug panels for jobs, memory, mesh size, texture size, worker status, and export validation.

Acceptance gate:

- A studio-style batch run can process a project folder into audited engine packages with logs, manifests, and reproducible command history.

## Next Implementation Slices

1. Scene persistence: `.gforge` save/load, autosave, recent projects, resource IDs, stable object IDs, operation history records, and manifest links.
2. Viewport picking: object/sub-object ray hit tests, selection highlighting, and multi-select.
3. Selection-aware operations: delete, flip selected normals, weld selected vertices, detach/separate selected faces.
4. Mesh edit data model: stable topology IDs, adjacency, validation, and delta-based undo.
5. Renderer upgrade: OpenGL/wgpu-backed viewport behind the existing renderer interface.
6. Transform gizmo: move/rotate/scale handles, snapping, pivot/orientation modes, and tests.
7. UV workspace MVP: 2D UV viewport, seam marking, unwrap, pack, checker, distortion overlay.
8. Material/texture inspector: PBR slots, texture previews, generated texture provenance, material assignment.
9. Operation/modifier graph: core-owned graph nodes for cleanup/modeling/modifier operations.
10. Graph operation UI polish: descriptor-driven node parameter forms, per-node artifact links, manifest/audit badges, progress/cancel states, and result history.
11. AI worker manager: dependency probes, install/cache UI, sample generation tests, and honest capability gates.
12. Hosted Tripo generation: secure credential surface, smart mesh presets, text-to-3D jobs, vertical-slice generation extras, and Unity/Unreal bridge routing.

## Design Rules Going Forward

- Every user-visible operation should be command-routed, undoable where practical, and reflected in the scene document.
- Every generated or transformed asset should have manifest/provenance/audit impact.
- Viewport math must be testable: coordinate policy, transforms, ray picking, snapping, and selection must have fixtures.
- Widgets stay thin. Controllers/services call `ghostforge_core`; panels display state and collect user intent.
- Do not imply parity with Blender, Maya, ZBrush, or RizomUV until a workflow passes its acceptance gate.
- The fastest way to feel professional is not more buttons. It is correct selection, transforms, undo, save/load, diagnostics, and predictable output.

## Immediate Next Slice

Deepen graph editing UX and background completion handling:

- Add parameter editors generated from operation descriptors rather than the current minimal prompt/reference fields.
- Add in-flight graph progress, failure, cancellation, and retry states to the graph panel, backed by durable job ids.
- Surface node artifact links and manifest/audit badges directly in the graph panel.
- Keep graph ids stable across Qt save/open and MCP inspection.
