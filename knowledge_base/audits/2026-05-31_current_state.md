# Ghost Forge Current State Audit

Date: 2026-05-31

## Executive Summary

Ghost Forge is currently strongest as a backend/MCP asset pipeline foundation. It has a surprisingly solid Python core with tests around jobs, workers, manifests, audits, knowledge base, engine handoff, authoring graphs, retargeting, and vertical slices.

As a 3D development tool, it is not yet comparable to Blender or Maya. The current editor surface is an Electron/React/Three prototype with import, orbit view, transform gizmo, panels, and job integration, but it lacks the deep interactive systems expected from a production DCC: robust scene persistence, undo/redo, mesh edit modes, material/node editing, sculpting, animation timeline, rigging, constraints, production render/export workflows, and plugin ecosystem.

## Verification Run

| Check | Result |
| --- | --- |
| `python -m pytest` | 515 passed, 3 skipped |
| initial `npm run build` | failed: `electron-vite` missing because dependencies were not installed |
| `npm install` | succeeded, 677 packages installed; npm reported 15 vulnerabilities |
| second `npm run build` | succeeded |
| `npm audit --omit=dev` | failed with production advisories for `axios`, `follow-redirects`, `electron` |
| `npm run lint` | failed: ESLint 9 requires `eslint.config.js` |

## Repository State

Branch: `genspark_ai_developer`

The worktree was already dirty before this audit. Existing modified/untracked files included `README.md`, `api/app.py`, renderer components, `ghostforge_core`, `ghostforge_app`, `ghostforge_mcp`, `pyproject.toml`, tests, and `GhostForge-Dual-Mode-Asset-Foundry-Audit.md`.

## Backend/Core State

Strong areas:

- Shared `ghostforge_core` bootstrap with storage, jobs, registry, KB, workers, engines, slices, scheduler, models, benchmarks, authoring graphs.
- Durable job runner and job store.
- Worker registry with capability probes.
- Manifest contract and audit system.
- Engine export bridge and Unity/Unreal adapter stubs.
- MCP tool surface covering health, jobs, workers, KB, manifests, audits, engines, GPU/model status, sessions, benchmarks, vertical slices.
- Flask v2 bridge over the same domains.
- Broad test coverage.

Weak areas:

- Many advanced workers are interface-complete but not runnable without heavyweight dependencies/models.
- Default KB is empty and uses hash embeddings unless optional KB extras are installed.
- Unity/Unreal adapters are unconfigured by default.
- Real production sample assets and end-to-end golden tests are still needed.

## Runtime Probe

Runnable workers on this machine:

- `silhouette_image_to_3d`
- `stub_image_to_3d`
- `stub_texture_mesh`
- `stub_refine_mesh`

Unavailable workers:

- `trellis`: `torch not installed`
- `hunyuan3d`: `torch not installed`
- `triposg`: `torch not installed`
- `instantmesh`: `torch not installed`
- `diffusers_texture`: missing `torch`, `diffusers`
- `paint3d`: `torch not installed`
- `syncmvd`: `torch not installed`

Knowledge base:

- backend: `json`
- embedder: `hash:256`
- count: `0`

Engine adapters:

- `unity`: not configured
- `unreal`: not configured

## Editor/UI State

Current Electron/React surface includes:

- custom shell layout,
- scene hierarchy,
- mesh import for GLB/GLTF/OBJ/STL/PLY in the viewport,
- Three.js orbit controls,
- transform controls for translate/rotate/scale,
- camera presets,
- right-panel tabs for properties/UV/texture/modifiers/audit/engine,
- worker/model/slice/API v2 stores,
- AI chat settings and panel.

Important limitations:

- Scene state is mostly runtime state, not a mature document model.
- No full undo/redo command stack.
- Mesh editing tools are mostly labels or backend concepts, not complete interactive workflows.
- UV/texture workflows exist but are not a full UV editor or painter.
- Viewport selection is object-level, with no robust face/edge/vertex editing.
- No mature animation timeline, rigging, constraints, deformers, sculpting, material node graph, physics, render pipeline, or plugin system.
- Frontend lint is currently not operational.

## Comparison: Blender And Maya

Blender and Maya are mature DCC applications with decades of tooling around modeling, sculpting, UVs, animation, rigging, simulation, rendering, scripting, import/export, extensibility, and production pipelines. Their official documentation and product pages emphasize broad modeling, animation/rigging, rendering, scripting/API, and pipeline workflows.

Ghost Forge today is closer to an AI asset pipeline prototype plus a promising editor shell:

| Area | Ghost Forge Today | Blender/Maya Class |
| --- | --- | --- |
| Viewport | Basic inspect/orbit/transform | Mature selection, modes, overlays, snapping, viewport rendering |
| Mesh modeling | Minimal interactive editing | Extensive polygon/subdivision/sculpt/modeling tools |
| UVs | xatlas pipeline, atlas output | Full manual/automatic UV editing workflows |
| Materials/textures | Procedural/AI pipeline concepts | Material graphs, painting, baking, lookdev |
| Animation | Retarget/core concepts present, no mature editor timeline | Full keyframe, graph editors, rigging, constraints |
| Rigging | Retarget modules exist; no general rig UI | Full skeleton/deformer/constraint workflows |
| AI generation | Central product differentiator, but real workers unavailable here | Not the main native focus |
| Asset validation | Strong manifest/audit direction | Available through tools/addons/pipelines, not always central |
| Extensibility | MCP/core worker registry | Mature plugin/scripting ecosystems |

Conclusion: Ghost Forge should not try to beat Blender/Maya immediately at general DCC depth. Its credible wedge is AI-native generation, validation, provenance, and engine handoff with enough editor functionality to inspect and correct assets.

## Qt Migration Recommendation

Switching the desktop architecture to Qt is reasonable. Ghost Forge's long-term UI needs dockable panels, action routing, model/view data, native dialogs, settings persistence, background job controls, and a high-density professional tool layout. Ghost Rigger demonstrates that this pattern can scale in this codebase family.

Recommended approach:

1. Keep `ghostforge_core` unchanged as the domain layer.
2. Add `ghostforge_qt` with PySide6 app shell.
3. Build Qt models/controllers over core APIs before porting every visual panel.
4. Implement a renderer abstraction early. Start with import/inspect/transform parity, then add picking, mesh edit modes, UV viewer, and material preview.
5. Keep Electron available until Qt reaches parity for the current workflows.

## Highest Priority Risks

- Capability overstatement: UI and README can imply production AI generation even when only stubs/CPU fallback are runnable.
- Frontend dependency risk: production advisories in `axios`, `follow-redirects`, and `electron`.
- Lint/config drift: ESLint command is currently broken.
- GUI maturity gap: the tested backend is much stronger than the editor.
- Model dependency fragmentation: real AI workers need isolated install/probe/caching strategy.
- Missing product file format: a universal 3D suite needs a durable scene/document format, not only runtime React state and asset folders.

## Recommended Next Slice

Build the Qt foundation without deleting the current app:

- `ghostforge_qt/main.py`
- `MainWindow`
- action registry
- scene/document model
- worker registry panel
- job monitor panel
- asset/manifest inspector
- basic viewport host placeholder
- tests for construction, command registration, worker table state, and job-controller events

This creates the spine for the future editor while preserving the working core and MCP tests.
