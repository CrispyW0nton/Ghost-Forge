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

### Graph-Native Worker Operations

AI generation, retopology/refinement, and texture generation should be schedulable
inside the same authoring graph as deterministic mesh cleanup and modeling
operations. Game-engine tooling principles argue against a hidden side channel:
every worker step needs stable resource identity, an output directory, manifest
provenance, validation/audit hooks, and debuggable failure state. Source nodes
may create the first mesh in a graph, while process nodes must require either a
base mesh or an earlier source node.

Graphs themselves are resources. A saved scene should not collapse an operation
graph into a mesh path alone; it should preserve the graph resource and mirror it
through the core `EditGraphStore` so UI, MCP, audits, and engine packages can all
refer back to the same authored intent.

Graph evaluation is pipeline work, not a UI callback. Long-running graph
evaluations, especially those invoking hosted or local AI workers, should run as
durable jobs with progress, cancellation hooks, persisted graph state, and a
last evaluation report.

The Qt editor should treat completed graph jobs like asset-pipeline events:
terminal job payloads update or create scene records, write the scene object's
final manifest, refresh topology diagnostics, and preserve the graph resource
for later MCP inspection or engine package creation.

Graph jobs should be debuggable while they run. The editor now mirrors durable
job progress into the graph panel, including active job id, stage/message,
cancel-request state, failure/cancel terminal states, and retry affordance. That
keeps long-running worker and hosted-provider operations visible at the same
resource boundary used by MCP.

Completed graph jobs should also expose their resource effects at the node
level. The Qt graph model now derives artifact and manifest badges from
evaluation metadata side effects, including output meshes, texture maps,
asset directories, and node-local manifest paths. Failed evaluations select the
first failed node so the artist or agent can jump straight to the broken step.
The graph panel also keeps a model-backed result history summarizing the same
payloads, including manifest validation/audit status when a manifest payload is
available.

Graph-linked audit actions now keep the asset pipeline authoritative: Qt submits
an `audit_asset` job for the selected graph result's manifest-backed asset
directory, waits for the durable job to settle, then re-reads the manifest so
the graph badges/history reflect the persisted validation and audit trail.

Graph result history is now persisted with scene objects. This treats evaluation
and audit context as resource state that survives editor restarts, rather than
as UI-only memory. Future MCP resources and engine handoff packages should be
able to inspect the same history when deciding whether a generated asset is
ready to ship.

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
- Graph evaluations that start from worker source nodes and still emit manifests.
- Scene persistence that keeps operation graph resources attached to scene objects.
- Durable graph-evaluation jobs that persist progress, result payloads, and last evaluation reports.
- Qt completion handling for graph-evaluation jobs that updates the scene and manifest from the durable job payload.
- Graph-panel progress/cancel/failure UI backed by durable job handles.
- Per-node graph result badges for worker artifacts/manifests and failed-node focus from evaluation reports.
- Graph result history rows with artifact counts and manifest validation/audit badges.
- Graph-linked audit jobs that persist audit history and refresh the graph panel from the manifest.
- Scene documents that restore graph result/audit history alongside graph resources.
- Audit gates block engine handoff unless forced.
- Worker probe state is rendered accurately in the Qt model.
- A failed model worker leaves a durable failed job with logs and no partial success badge.
- Export bridge package validates without Unity/Unreal installed.
