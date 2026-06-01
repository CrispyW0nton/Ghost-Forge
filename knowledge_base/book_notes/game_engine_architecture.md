# Game Engine Architecture Notes For Ghost Forge

Sources scanned: Jason Gregory's *Game Engine Architecture*, Ghost Rigger's renderer/tool architecture, and the existing Ghost Forge core.

## Chapter Map Anchors

The scanned outline emphasizes:

- What a game engine is and how tools differ from runtime.
- Tools and asset pipeline.
- Profiling, debugging, memory, and concurrency.
- Parallelism and synchronization.
- Engine systems, timing, and runtime loop concerns.
- Human interface devices and editor-facing workflows.

## Ghost Forge Applications

### Tool, Not Runtime

Ghost Forge should behave like an editor/tool pipeline, not a game runtime. Its job is to author, validate, package, and hand off assets. Unity/Unreal remain the runtime targets.

### Shared Asset Pipeline

The existing `ghostforge_core` is correctly aimed at a shared pipeline:

- storage,
- jobs,
- worker registry,
- manifests,
- validation/audit,
- knowledge base,
- engine export bridges,
- vertical slices.

The Qt shell should call this core directly and should not duplicate pipeline code.

### Asset Contract

Every generated or imported asset should move toward:

- stable asset directory,
- `asset_manifest.json`,
- source prompt/reference/citations,
- geometry summary,
- UV and material state,
- texture slots,
- units and bounds,
- target engines,
- audit summary,
- export bridge package when applicable.

### Debuggability

A serious 3D tool needs first-class diagnostics:

- worker probe panel,
- GPU/session panel,
- per-job logs,
- manifest diff viewer,
- validation history,
- viewport screenshot capture,
- reproducible audit reports.

### Concurrency Boundary

AI model workers should remain isolated from the editor loop. Heavy CUDA dependencies should be process-isolated where practical. The UI should degrade gracefully when only CPU/stub workers are available.

## Capability Honesty

Do not present TRELLIS, Hunyuan3D, TripoSG, InstantMesh, Paint3D, or SyncMVD as available just because classes exist. The UI should show probe results and model-cache state.

## First Tests To Add

- Manifest creation after every user-visible export/generation path.
- Audit gates block engine handoff unless forced.
- Worker probe state is rendered accurately in the Qt model.
- A failed model worker leaves a durable failed job with logs and no partial success badge.
- Export bridge package validates without Unity/Unreal installed.
