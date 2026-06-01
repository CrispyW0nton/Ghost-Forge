# GhostForge Dual-Mode Asset Foundry

Architecture audit and open source research for building GhostForge as both a standalone AI-native creator app and an MCP server that generates game-ready meshes, UVs, textures, and engine handoff packages.

Date: May 7, 2026

## Summary

GhostForge should have two first-class interfaces over one shared asset core.

1. **Standalone Creator App**: a Blender-like desktop workspace for humans: viewport, scene hierarchy, modeling helpers, UV editing, texture generation, concept board, asset browser, AI co-creator, export/import.
2. **MCP Asset Service**: a deterministic tool-call surface for AI agents: concept research, asset planning, mesh generation, UVs, textures, validation, optimization, and handoff to Unity-MCP-Ghost or Unreal-MCP-Ghost.

Unity-MCP-Ghost and Unreal-MCP-Ghost should build gameplay, levels, Blueprints, prefabs, input, UI, tests, screenshots, and validation. GhostForge should supply the missing art pipeline: researched concepts, generated meshes, UVs, textures, validation, optimization, and manifests.

## Current System Read

### Frontend

Electron/Vite/React with Three.js viewport, Zustand scene state, AI chat, UV tab, texture tab, and image-to-3D placeholder UI.

### Backend

Flask API with job state, uploads, outputs, mesh-info, xatlas unwrap, procedural/Stable Diffusion texture, UV atlas bake, GLB/OBJ export.

### Immediate Gap

GhostForge currently behaves like an app API, not yet an MCP server. It lacks durable jobs, a knowledge base, model worker registry, asset manifests, and engine handoff adapters.

## Target Architecture

### Desktop Creator Surface

The Electron/React app remains a full creative workspace, not just a wrapper around MCP. It should call the same internal asset APIs as the MCP server and display job state, previews, concepts, generated variants, and validation results.

### MCP Agent Surface

Expose GhostForge through MCP transports:

- `stdio` for local agents.
- `streamable-http` or SSE for remote/cloud agents.

Agents call asset tools directly and receive structured JSON.

### Asset Brain

The knowledge base stores:

- Style guides.
- Concept images.
- Image and text embeddings.
- Prompt recipes.
- Source licenses.
- Prior generated assets.
- Engine import recipes.

Use OpenCLIP plus an embedded vector DB first, then scale to LanceDB or Qdrant if asset volume grows. Both the app and MCP tools should query this same knowledge base.

### Asset Factory

Workers generate mesh, UVs, textures, cleanup, validation, and manifests. Unity/Unreal adapters pass validated packages to the engine MCP servers. The desktop app can also export the same packages manually.

### Shared Core

Keep generation, jobs, storage, model registry, validation, manifests, and knowledge retrieval outside the UI layer. The desktop app and MCP server should be peers, not separate implementations.

## Data Contract

Every generated asset should end as a folder plus `asset_manifest.json` containing:

- Stable asset ID.
- Source prompt.
- Reference images.
- License records.
- Mesh paths.
- Texture paths.
- Bounds and unit scale.
- Triangle count.
- UV count.
- Material slots.
- LODs.
- Collision intent.
- Engine target.
- Validation results.

## Repo Shortlist

| Repo / Family | Capability | Fit for GhostForge | Constraints |
| --- | --- | --- | --- |
| AUV-Net | Aligned UV maps for related shape classes | High value for texture transfer/synthesis across similar assets. Not a general unwrap replacement. | NVIDIA source license; research integration first |
| TRELLIS | Text/image to 3D assets with meshes, Gaussians, radiance fields | Strong candidate for high-quality concept-to-mesh backend; needs GPU worker isolation. | MIT; Linux + 16GB+ NVIDIA GPU expected |
| Hunyuan3D | Text/image to 3D with geometry and texture stages | Best fit for production asset generator slot because it already thinks in geometry + texture phases. | Open source; confirm exact model license per release |
| TripoSG | Image-to-3D shape generation | Good fast backend candidate for props and silhouettes; pair with GhostForge UV/texture stage. | MIT |
| InstantMesh | Single-image mesh generation in about 10 seconds | Useful low-latency backend for quick vertical-slice props. | Apache-2.0 |
| Paint3D | Lighting-less 2K UV texture generation | Very relevant to game engines because lighting-less textures relight cleanly in Unity/Unreal. | Apache-2.0 |
| SyncMVD | Synchronized multi-view diffusion texturing | Good upgrade path over single flat texture bake; supports xatlas auto unwrap. | MIT |
| TEXTure | Text-guided texture generation/edit/transfer | Strong interactive texturing/editing research base; useful for agent-driven texture revisions. | MIT |
| OpenCLIP | Image-text embeddings | Core for concept image search, mood-board retrieval, and generated asset indexing. | MIT |
| LanceDB / Chroma / Qdrant | Vector retrieval storage | Knowledge base should store text, concept images, generated previews, licenses, and asset manifests. | Open source; choose embedded first |
| Openverse MCP | Openly licensed image search via MCP | Useful reference/concept source with attribution metadata built in. | MIT; track attribution |
| Blender MCP / blender-kiln | Asset cleanup, texturing, optimization, export pipeline | Best complement for post-generation cleanup, dimension checks, material audits, and GLB/FBX export. | Mixed; tool-by-tool license review |
| glTF-Transform + glTF Validator | Optimize and validate glTF/GLB assets | Required before assets are handed to Unity/Unreal MCP tools. | MIT / Apache-style ecosystem |
| glTFast | Unity glTF/GLB import | Unity delivery adapter should emit GLB plus import instructions or call Unity MCP asset import tools. | Open source Unity package |
| Unreal Interchange | Unreal glTF import and material pipelines | Unreal delivery adapter should use Interchange/Python through Unreal-MCP-Ghost. | Epic official framework |

## Proposed MCP Tool Surface

| Tool | Responsibility |
| --- | --- |
| `research_concept_brief` | Input: genre, references, constraints. Output: visual brief, palette, asset list, source citations. |
| `search_reference_images` | Search Openverse/local KB, filter licenses, return ranked references with attribution. |
| `ingest_concept_images` | Embed user images with OpenCLIP, caption them, attach license/project metadata. |
| `plan_vertical_slice_assets` | Turn gameplay brief into required meshes, textures, collision, scale, LOD, engine targets. |
| `generate_mesh_asset` | Dispatch TRELLIS/Hunyuan/TripoSG/InstantMesh worker, store raw mesh and preview. |
| `unwrap_uvs` | Run existing xatlas path or future AUV-Net aligned category unwrap. |
| `generate_texture_set` | Run procedural, Paint3D/SyncMVD/TEXTure, or Stable Diffusion texture stage. |
| `audit_asset_game_readiness` | Check poly count, non-manifold geometry, UVs, texture resolution, bounds, naming, license. |
| `optimize_asset` | Run Blender/gltf-transform steps: scale, normals, materials, compression, LODs. |
| `publish_asset_manifest` | Emit manifest JSON with file paths, stats, prompts, licenses, engine import hints. |
| `send_to_unity` | Call Unity-MCP-Ghost to import/create prefab/place asset. |
| `send_to_unreal` | Call Unreal-MCP-Ghost to import/create material/Blueprint/place asset. |

## Build Plan

| Phase | Goal | Deliverable |
| --- | --- | --- |
| Phase 1 | Wrap current Flask pipeline as MCP tools | Expose health, mesh-info, jobs, unwrap, texture, previews, downloads through `stdio` + HTTP transports. |
| Phase 2 | Create asset manifest contract | Every output should include mesh, textures, dimensions, units, poly count, UV status, prompts, source licenses, engine import hints. |
| Phase 3 | Add knowledge base and concept research | OpenCLIP embeddings, vector DB, Openverse/reference ingestion, project style guides, prompt recipes, generated asset memory. |
| Phase 4 | Add model worker registry | TRELLIS, Hunyuan3D, TripoSG, InstantMesh, Paint3D/SyncMVD workers behind capability probes and job queues. |
| Phase 5 | Engine handoff adapters | Unity-MCP-Ghost and Unreal-MCP-Ghost calls for import, material creation, prefabs/Blueprints, placement, screenshots, validation. |
| Phase 6 | Vertical slice planner | Given a game concept, plan assets, generate them, import them, build scene composition, then ask engine MCP tools to validate playability. |

## Important Risks

| Risk | Recommendation |
| --- | --- |
| Licensing | Generated models, reference images, and research repos have mixed licenses. Track license per input, model, and output. Avoid non-commercial models for commercial workflows. |
| GPU fragmentation | TRELLIS, Hunyuan3D, Paint3D, SyncMVD have heavy, conflicting CUDA dependencies. Run each as an isolated worker environment. |
| Game readiness | AI meshes often need scale, normals, UVs, materials, LODs, collision, lightmap UVs, and naming cleanup before engine import. |
| Agent safety | MCP tools need deterministic schemas, job state, dry-run modes, and explicit file output boundaries. |
| Quality loop | Without screenshots and validators, agents cannot judge whether assets are usable in the target engine. |

## AUV-Net Positioning

Do not treat AUV-Net as a general xatlas replacement.

AUV-Net learns aligned UV spaces across a shape category, so matching semantic parts land in the same atlas regions. That is powerful for cars, bodies, heads, chairs, and repeated enemy/prop families where texture transfer matters. Keep xatlas as the general-purpose unwrap path, then add AUV-Net as a category-trained aligned-UV mode.

### Best First AUV-Net Experiment

Pick one bounded category, likely crates, vehicles, weapons, or modular props. Train/evaluate aligned UV maps and texture swapping on that category only.

### MCP Exposure

Add a tool such as `generate_aligned_uv_asset(category, mesh, source_texture_asset_id)` that falls back to xatlas when category support is unavailable.

## Knowledge Base Shape

### Collections

- `concepts`: reference images, captions, license, style tags.
- `assets`: generated meshes/textures, previews, manifests, validation.
- `engine_recipes`: Unity and Unreal import/playability patterns.
- `model_cards`: backend capability, license, hardware, failure modes.

### Retrieval Policy

Agents query the knowledge base before generating assets, like Unreal-MCP-Ghost requires for gameplay systems.

Ranking should combine:

- Text embeddings.
- Image embeddings.
- Metadata filters.
- Project-specific style constraints.

Every external reference must carry license and attribution fields through the manifest.

## Engine Handoff

### Unity-MCP-Ghost

Prefer GLB import through glTFast-compatible workflows, then ask Unity MCP tools to create prefabs, assign materials, generate colliders, place assets, bake NavMesh, and capture screenshots.

### Unreal-MCP-Ghost

Prefer Unreal Interchange/Python import through Unreal-MCP-Ghost, then create materials, static mesh assets, Blueprints, collision, placement, validation screenshots, and compile checks.

## Referenced Sources

- [AUV-Net](https://github.com/nv-tlabs/AUV-NET) and [paper summary](https://arxiv.org/abs/2204.03105)
- [TRELLIS](https://github.com/microsoft/TRELLIS), [InstantMesh](https://github.com/TencentARC/InstantMesh), [TripoSG](https://github.com/VAST-AI-Research/TripoSG), [Hunyuan3D](https://github.com/hunyuan3d/hunyuan3d)
- [Paint3D](https://github.com/OpenTexture/Paint3D), [SyncMVD](https://github.com/LIU-Yuxin/SyncMVD), [TEXTure](https://github.com/TEXTurePaper/TEXTurePaper)
- [OpenCLIP](https://github.com/mlfoundations/open_clip), [LanceDB](https://github.com/lancedb/lancedb), [Openverse MCP](https://github.com/neno-is-ooo/mcp-openverse)
- [glTF-Transform](https://github.com/donmccurdy/glTF-Transform), [glTF Validator](https://github.com/KhronosGroup/glTF-Validator), [glTFast](https://github.com/atteneder/glTFast), [Unreal Interchange](https://dev.epicgames.com/documentation/unreal-engine/importing-assets-using-interchange-in-unreal-engine)
