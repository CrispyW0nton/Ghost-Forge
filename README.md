# Ghost Forge

Ghost Forge is an open-source, AI-native 3D creation suite for generating, editing, validating, and handing game-ready assets to modern engines.

The long-term goal is a universal 3D modeling and content-generation environment that can grow toward Blender, Maya, ZBrush, and RizomUV-class workflows while keeping an advantage those tools were not built around: AI automation, provenance, validation, and engine handoff through MCP.

## Product Goal

Ghost Forge should become:

- a universal 3D modeling suite, not a KOTOR-specific tool,
- a Qt/PySide6 desktop editor with a robust viewport and dockable production UI,
- an AI-assisted asset foundry for text/image-to-3D, texturing, repair, retopo, UVs, and variants,
- a manifest-driven pipeline where every generated or edited asset keeps provenance and audit history,
- an MCP-capable tool server for vibe-coding games and automated asset workflows,
- an engine bridge producer for Unity-MCP-Ghost and Unreal-MCP-Ghost.

Ghost Forge is not trying to clone Blender or Maya overnight. Its credible wedge is an AI-native asset pipeline that can generate rough assets, expose honest capability gates, help artists inspect and correct outputs, and ship audited engine-ready packages.

## Current Architecture

| Layer | Purpose |
| --- | --- |
| `ghostforge_core` | Shared Python domain layer: jobs, workers, manifests, audits, authoring graphs, slices, engine handoff, knowledge base |
| `ghostforge_qt` | PySide6 desktop editor: project browser, scene model, viewport foundation, modeling tools, themes |
| `ghostforge_mcp` | MCP server for agent-callable generation, audit, slice, and engine-handoff workflows |
| `ghostforge_app` | Flask HTTP bridge retained during the Qt migration |
| legacy Electron/React | Earlier prototype UI retained as reference until Qt reaches parity |
| `knowledge_base` | Project memory, roadmap, audits, and book-derived development rules |

## What Works Now

- PySide6 desktop shell with project/content browser, theme system, scene outliner, viewport foundation, and modeling dock.
- CPU-projected 3D viewport with mesh preview, camera presets, display modes, transform type-in, object/sub-object picking, and selection highlighting.
- Universal mesh tooling for cleanup, normals, weld, smooth, subdivide, decimate, recenter, material assignment, selected delete/weld/flip normals, and operation history.
- Editable mesh core foundation with stable vertex/edge/face IDs, adjacency, validation, connected components, and delta undo/redo.
- Worker registry with honest probes for TRELLIS, Hunyuan3D, TripoSG, InstantMesh, Paint3D, SyncMVD, silhouette image-to-3D, and stubs.
- Hosted Tripo AI text-to-3D worker exposed as `tripo_api`, gated by server-side credentials.
- Core-owned authoring graphs with text/image generation source nodes, worker refine/texture nodes, persisted graph resources, and durable `evaluate_edit_graph` jobs.
- Qt operation-graph dock with descriptor-driven node parameter editing, shared operation presets, file/folder path pickers, button and drag/drop node reordering, per-node enable/disable bypass controls, visible background job progress/cancel/retry states, graph-linked audit jobs, per-node artifact/manifest/audit badges, persistent result history with stable scene/resource IDs, persisted active graph-history comparison pairs, a filterable model-backed resource list and metadata drill-down for outputs, artifacts, manifests, validation issue lists, provenance step lists, audit issue lists, bridge package history, bridge package JSON previews, graph-history delta comparison with non-adjacent pair selection, a summary table, and copyable MCP comparison URIs, shared-core Unity/Unreal retarget planning with model-backed remaining/new/resolved diagnostic diffs, manifest-gated Unity/Unreal bridge creation, failed-node focus, and scene/manifest/node-status updates on completion.
- MCP tools and prompts for worker probing, text/image generation, texture/refine jobs, audits, vertical slices, edit graphs, graph-history comparison, graph repair workflows, retarget planning, and Unity/Unreal handoff.
- Asset manifests with geometry summaries, provenance, license, concept citations, validation summaries, engine targets, and bridge package history.
- Offline export bridge packages for Unity-MCP-Ghost and Unreal-MCP-Ghost.
- Knowledge base and roadmap grounded in Qt, graphics math, game-engine architecture, MCP, and DCC competitor research.

## AI Content Generation

Ghost Forge supports both local/optional model workers and hosted providers behind the same worker contract.

Tripo AI text-to-3D uses the official Tripo OpenAPI task flow:

- submit a task,
- poll for completion,
- download `model`, `base_model`, or `pbr_model`,
- write the result into a manifest-backed asset directory.

Set one of these environment variables before running the app or MCP server:

```powershell
$env:GHOSTFORGE_TRIPO_API_KEY = "your-key"
# or
$env:TRIPO_API_KEY = "your-key"
```

Do not put API keys in project files or request extras. Ghost Forge rejects inline key fields and redacts secret-shaped values before manifest writes.

## MCP And Engine Handoff

Ghost Forge can run as an MCP server for game-development agents. A typical game asset workflow is:

1. Probe workers with `list_worker_capabilities`.
2. Generate a smart mesh with `submit_text_to_3d` or a vertical slice asset using `strategy="text_to_3d"`.
3. Pass smart mesh settings such as texture/PBR, smart low-poly, quad, face limit, UV export, and geometry quality.
4. Wait for the job and inspect the generated manifest.
5. Audit or retarget for Unity or Unreal.
6. Create `ghostforge_bridge_unity.json` or `ghostforge_bridge_unreal.json`, or call `send_to_unity` / `send_to_unreal` when an engine adapter is configured.

Unity-MCP-Ghost and Unreal-MCP-Ghost remain responsible for editor-specific import, placement, validation, and repair inside the game project. Ghost Forge owns asset generation, provenance, audit state, and bridge package creation.

## Knowledge Base

The `knowledge_base/` folder is part of the source of truth for development. Before major work, review:

- `knowledge_base/README.md`
- `knowledge_base/crosswalks/ghostforge_development_bible.md`
- `knowledge_base/roadmap/dcc_competitor_roadmap.md`
- `knowledge_base/roadmap/tripo_mcp_engine_workflow.md`
- the matching subsystem note under `knowledge_base/book_notes/`

The local book library used for future scans lives outside the repo at:

```text
C:\Users\NewAdmin\Documents\Academy of Art University\Books
```

Book notes in this repo are summaries and project-specific applications, not copied book content.

## Roadmap

Near-term slices:

1. Renderer upgrade: OpenGL/wgpu-backed viewport behind the current renderer interface.
2. Transform gizmo: move/rotate/scale handles, snapping, pivot/orientation modes.
3. UV workspace MVP: 2D UV viewport, seam marking, unwrap, pack, checker, distortion overlay.
4. Material/texture inspector: PBR slots, texture previews, provenance, material assignment.
5. Operation/modifier graph polish: descriptor-driven parameter editors, artifact links/actions, manifest/audit badges, persisted result history and active comparison pairs, graph-result inspectors, persisted retarget diagnostics/comparisons, graph-history deltas with MCP links, and engine-readiness actions.
6. AI worker manager: dependency probes, install/cache UI, hosted provider credentials, sample generation tests.
7. Hosted Tripo generation: smart mesh presets, vertical-slice generation extras, Unity/Unreal bridge routing.
8. Sculpt/retopo foundation: brushes, masking, remesh/decimate/retopo, projection, baking.
9. Animation and rigging: skeletons, skinning, constraints, timeline, retargeting.
10. Pipeline extensibility: USD/FBX where possible, Python scripting, plugin manifests, batch/headless jobs.

## Quick Start

Install the Python package in editable mode:

```powershell
python -m pip install -e .
```

Run the core tests:

```powershell
python -m pytest
```

Run the MCP server:

```powershell
python -m ghostforge_mcp
```

Run the Qt desktop editor:

```powershell
python -m ghostforge_qt.main
```

Optional extras:

```powershell
python -m pip install -e ".[qt]"
python -m pip install -e ".[mcp]"
python -m pip install -e ".[mesh]"
python -m pip install -e ".[ai]"
```

## Verification Status

Latest full Python verification:

```text
602 passed, 3 skipped
```

Frontend/Electron work still requires the older Node pipeline. The Qt editor is the forward architecture.

## Credits

- Based in part on Modly by Lightning Pixel, MIT License: https://github.com/lightningpixel/modly
- xatlas: https://github.com/jpcy/xatlas
- trimesh: https://github.com/mikedh/trimesh
- diffusers: https://github.com/huggingface/diffusers
- React Three Fiber: https://github.com/pmndrs/react-three-fiber
- Three.js: https://threejs.org
- Zustand: https://github.com/pmndrs/zustand
