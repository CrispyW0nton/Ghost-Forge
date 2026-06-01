# DCC Capability Research: Blender, Maya, ZBrush, RizomUV

Date: 2026-05-31

Purpose: record current competitor capability research and the book-derived logic used to steer Ghost Forge's roadmap.

## Sources Checked

Project memory:

- `knowledge_base/README.md`
- `knowledge_base/crosswalks/ghostforge_development_bible.md`
- `knowledge_base/audits/2026-05-31_current_state.md`
- `knowledge_base/roadmap/qt_migration_plan.md`
- `knowledge_base/roadmap/dcc_competitor_roadmap.md`
- `knowledge_base/book_notes/graphics_math_foundations.md`
- `knowledge_base/book_notes/game_engine_architecture.md`
- `knowledge_base/book_notes/qt_gui_architecture.md`

Book anchors checked by PDF outline and current notes:

- Dunn and Parberry, `3D Math Primer`: coordinate systems, vectors, multiple coordinate spaces, matrices, linear transforms.
- Kneusel, `Math for Programming`: floating-point arithmetic, vectors, vector spaces, matrices, affine transforms, curves and areas.
- Vince, `Mathematics for Computer Graphics`: coordinate systems, homogeneous coordinates, vectors, normals, transforms, matrices, quaternions.
- Gregory, `Game Engine Architecture`: tools and asset pipeline, profiling, parallelism, resources and file system, resource manager.
- Fitzpatrick, `Create GUI Applications with Python & Qt6`: signals and slots, actions/menus/toolbars, model/view, threads, processes.
- Summerfield, `Rapid GUI Programming with Python and Qt`: signals/slots, user actions, item graphics, multithreading.
- Lee, `Qt 6 C++ GUI Programming Cookbook`: signals/slots, QPainter coordinate transforms, threading, QRunnable, model/view.

Current product docs checked:

- Blender 4.5 manual: https://docs.blender.org/manual/en/4.5/
- Autodesk Maya overview and 2026 help: https://www.autodesk.com/products/maya/overview and https://help.autodesk.com/view/MAYAUL/2026/ENU/
- Maxon ZBrush product/help: https://www.maxon.net/en/zbrush and https://help.maxon.net/zbr/en-us/
- RizomUV 2025 and C++ Library pages: https://www.rizomuv.com/feature/rizomuv-2025-whats-new/ and https://www.rizomuv.com/c-library/

## Current Ghost Forge Baseline

Ghost Forge is now an AI-native asset foundry foundation with a growing Qt editor, not a mature DCC replacement.

Strong:

- Shared `ghostforge_core` with jobs, workers, manifests, audits, KB, authoring graphs, retargeting, benchmarks, slices, and engine export bridges.
- MCP and Flask surfaces over the core.
- Qt package with `QMainWindow`, action registry, dock panels, project/content browser, worker/job panels, theme system, scene table model, CPU mesh preview viewport, transform type-in, topology diagnostics, mesh selection state, operation history, and artifact-producing mesh operations.

Weak:

- Scene/document persistence is still a placeholder.
- Viewport rendering is CPU-projected preview, not an interactive GPU renderer with true picking.
- Sub-object selection modes exist as state, but not as real viewport picking/editing workflows.
- UV unwrap, texture, audit, and export bridge commands are registered in Qt but not wired through real panels.
- High-end AI workers remain dependency/model gated on this machine.
- No sculpting, brush system, rigging UI, animation timeline, material graph, production render/lookdev system, physics/simulation, plugin marketplace, or USD-grade pipeline.

## Competitor Capability Contracts

### Blender

Blender is the broad open-source benchmark. Its manual surface spans workspaces, 3D viewport, object and mesh modes, modeling, UV editor, sculpting and painting, Grease Pencil, animation and rigging, physics, rendering, compositing, asset/data-block management, add-ons, and Python scripting.

Ghost Forge lesson:

- Build a shared document/data model and command/operation stack before chasing hundreds of individual tools.
- Treat viewport overlays, snapping, pivots, transform orientation, undo/redo, object/sub-object modes, and scriptable operators as foundation.

### Maya

Maya is the studio pipeline benchmark. Autodesk positions it around professional modeling, animation, rigging, simulation/effects, rendering, OpenUSD workflows, scripting, and pipeline integration. Maya 2026 docs highlight modeling updates, animation-in-context, rigging/character animation improvements, Bifrost, LookdevX, Arnold, USD, Flow Retopology, Substance updates, color management, and math-node changes.

Ghost Forge lesson:

- Pipeline seriousness is a product feature: manifests, references, USD/handoff, scripting, jobs, retopology workers, color/material contracts, and diagnostics need first-class UI.

### ZBrush

ZBrush is the sculpting and high-detail ideation benchmark. Current Maxon docs emphasize digital sculpting, painting, modeling, more than 200 brushes, DynaMesh, PolyPaint, Live Boolean, Redshift, ZModeler, desktop/iPad continuity, Python scripting, GoZ updates, Substance Bridge, manual retopo tools, ZRemesher, and UV Master.

Ghost Forge lesson:

- Do not chase a full sculpt engine first. Add guided remesh/retopo, target counts, density hints, border/crease preservation, projection/variant workflow, and provenance around current mesh operations.

### RizomUV

RizomUV is the specialized UV benchmark. The 2025 release highlights GPU packing, packing strategies, orientation tools, group-to-tile workflows, scene outliner, saved defaults, primitive selection conversion, border/invalid-topology selection, pixel grid display, and trimsheet export. Its C++ Library frames full automatic UV generation as auto segmentation/unfold plus GPU/CPU packing with no overlaps and respected padding.

Ghost Forge lesson:

- UVs deserve an inspectable editor and audit surface: islands, overlap, padding, texel density, distortion, packing coverage, group/tile settings, checker preview, and reproducible manifest settings.

## Design Decisions Changed

- Scene/document persistence should precede broad feature expansion.
- Viewport picking and sub-object selection should become tested contracts before more staged modeling tools.
- UV editor/audit should become a first-class workflow, not just a one-click unwrap.
- Retopo/remesh should become guided, provenance-bearing variant generation with quality metrics.
- AI generation should remain worker-probed and manifest/audit-gated rather than presented as always available.

## Tests To Add

- Scene document round-trip: import multiple meshes, transform one, run operation, save, reload, preserve IDs, paths, transforms, and history.
- Picking contract: viewport ray tests select deterministic object/face/edge/vertex fixtures.
- UV audit: detects missing UVs, overlaps, low coverage, excessive distortion, inconsistent texel density, and inadequate padding.
- Retopo/remesh contract: produces a new artifact with target-ratio metadata, preserved source path, topology summary, and audit deltas.
- Manifest provenance: every Qt command that produces an asset writes operation settings, source asset ID, worker/backend state, and output paths.
- Engine handoff gate: export package fails or warns when scale, non-finite transforms, missing UVs, missing texture slots, or topology errors violate a target preset.
