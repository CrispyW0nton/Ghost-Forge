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

The Qt graph surface now creates offline engine bridge packages through the
same core export-bridge contract used by MCP. The UI reads manifest validation
state, engine targets, and existing bridge history before enabling Unity/Unreal
bridge actions, so engine handoff remains a pipeline event attached to the
asset manifest instead of a direct editor call.

Qt retarget planning now also goes through the same core planner exposed by MCP.
The editor asks the core to audit the selected manifest for Unity/Unreal
conventions, receives a retarget `EditGraph`, and attaches it to the scene
object for normal graph evaluation. This preserves engine handoff as an
inspectable sequence of operations instead of a hidden one-shot export fix-up.

Retarget diagnostics now remain visible at the graph boundary. The Qt panel
records the planned retarget graph in result history and shows the filtered
`retarget.*` audit issues that caused the planner to emit each fix-up family,
so a user or MCP peer can reason about axis, units, pivot, naming, collision,
and texture readiness before bridge packaging.

Retarget diagnostic reports are now persisted inside graph history details.
This keeps the planner's audit evidence attached to the scene document, which
is closer to the manifest-driven pipeline goal than storing only a human-readable
status string.

Retarget verification is now a second pipeline event. Once a planned retarget
graph evaluates, Qt re-runs the target-engine retarget audit through the core,
records the post-evaluation report, and compares planned issue keys against the
new report. Resolved, remaining, and newly introduced diagnostics become
history data that future MCP resources and bridge gates can inspect.

Graph result artifacts must be reachable resources. The Qt result history now
records side-effect output meshes, texture maps, asset directories, and
manifest paths as structured details, then the editor exposes open/reveal
actions for those paths. This makes graph evaluation output inspectable in the
same way a tools pipeline expects build products, logs, and packages to be
inspectable.

The next refinement treats those paths as a resource table, not button-local
state. Output meshes, artifacts, manifests, and asset directories now have
kind/source/path rows, which is closer to a tools pipeline browser and makes it
possible to expand into audit-history and package drill-downs without changing
the graph evaluation contract.

Bridge packages and audit history now participate in that same resource table.
Manifest `engine.bridge.*` artifacts, `custom.engine_export_bridges` package
paths, and latest `custom.audit_history` summaries become inspectable rows,
making engine handoff and validation evidence visible beside the graph result
that produced the asset.

The table now has lightweight drill-down metadata as well as paths. Selected
bridge resources expose the target engine and recommended MCP handoff contract;
selected audit resources expose preset/status/counts/timing. This makes the
resource table a real debugging surface for engine handoff readiness instead of
a file launcher alone.

Manifest resource rows now include validation issue summaries and latest
provenance steps. That turns manifest-driven asset state into inspectable
pipeline evidence inside the graph editor: users can see why a result is ready
or blocked, which operation trail produced it, and where to open the underlying
manifest if deeper investigation is needed.

The validation/provenance drill-down now includes lists, not only headline
counts. Issue rows show severity, code, location, and message; provenance rows
show ordered operation steps with job/timing hints. This is closer to a build
pipeline report and gives Qt users the same evidence MCP callers inspect in
structured manifest resources.

Audit and bridge resources now complete the same loop. Persisted audit reports
contribute issue lines, while bridge history contributes a compact package
preview of the external handoff contract. This makes the Qt graph inspector a
single place to inspect generated products, validation evidence, provenance,
and Unity/Unreal handoff metadata.

Filtering the resource table by kind turns that inspector into a more practical
pipeline browser. Outputs, side-effect artifacts, manifests, asset directories,
audit-history rows, and bridge packages can be isolated for focused debugging,
but the full resource set remains the source for deterministic file and package
actions.

Bridge package JSON preview closes the first engine-handoff inspection loop.
The editor now reads selected `ghostforge_bridge_<engine>.json` packages and
surfaces the external contract fields that matter to Unity-MCP-Ghost or
Unreal-MCP-Ghost: target engine, asset id, paths, target path, recommended MCP
server/tool, embedded manifest validation, artifact count, and notes.

Retarget verification now behaves more like a pipeline diff report. Planned
diagnostics are compared against the post-evaluation audit and rendered as
remaining, new, and resolved rows. Remaining and new rows are ordered first
because they are the next blocking facts for bridge readiness.

Per-node graph bypass is now exposed in Qt. Disabling a node preserves the
operation and its parameters as authored intent while removing it from the next
evaluation, which matches the non-destructive pipeline rule that graph resources
should remain inspectable and repeatable rather than deleted for quick tests.

Graph node reordering is now exposed through the same pipeline contract. Moving
a node changes the persisted operation order, preserves node ids/parameters,
clears stale evaluation state, and leaves the graph ready for a deterministic
re-evaluation. This moves the Qt graph closer to a real modifier stack.

The graph table now supports drag/drop reordering through the same contract.
Qt's internal move operation is constrained to Ghost Forge node rows and still
updates the underlying graph resource, which keeps desktop actions and future
MCP inspection on the same authored order.

Path-like operation parameters are now explicit editor resources too. The Qt
form infers file or folder pickers from the same descriptor fields consumed by
core graph evaluation and MCP discovery, but the saved graph payload remains a
plain string. That keeps asset inputs, reference images, output folders, and
future bridge directories ergonomic in the desktop tool without creating a
GUI-only contract.

Operation presets are now part of the shared authoring descriptor. Presets for
cleanup, decimation, materials, bake operations, and worker generation/refine/
texture operations give artists and agents repeatable starting values while the
evaluated graph still stores only concrete node parameters. This supports a
tools-pipeline rule: defaults and profiles should be discoverable, testable,
and shared across UI and automation.

Scene graph history now behaves like an addressable pipeline resource. Saved
`.gforge` documents include a scene id, and each operation-graph history row
gets a deterministic history id plus MCP links to the graph, graph evaluation,
scene, and object-specific history row. This makes persisted Qt work inspectable
by automation without collapsing it into a mesh path alone.

MCP workflow prompts now encode repeatable pipeline playbooks. The generate,
Unity repair, and Unreal package prompts direct agents through capability
probes, operation descriptors/presets, edit graph evaluation, saved graph
resources, audits, and offline bridge packages. That keeps automation aligned
with the manifest-first tools pipeline rather than encouraging one-off side
effects.

Saved graph-history rows can now be compared as pipeline evidence. The shared
scene-link helper computes structured deltas for output/status fields, artifact
paths, bridge packages, audit issue lists, and retarget diagnostic lists, while
MCP exposes the same comparison as a tool and resource. This gives agents a
repeatable way to explain what changed between two graph evaluations.

The Qt result inspector now consumes that same comparison contract. Selecting a
history row compares it with the next older row and shows output, artifact,
bridge, audit, and retarget changes beside the other result resources. This
keeps artist-facing debugging and MCP agent inspection aligned on one
manifest-backed pipeline diff.

The comparison surface now supports explicit pair selection and URI handoff.
Artists can compare non-adjacent saved rows, then copy the same
`ghostforge://.../graph-history/{left}/compare/{right}` resource URI that an
MCP agent would read. This strengthens the pipeline rule that debug evidence is
addressable resource state, not editor-only text.

The inspector now renders those comparison results as rows too. Field changes,
resource additions/removals, audit issue changes, and retarget list deltas are
represented by `GraphHistoryDeltaRow` records, which makes graph-history
comparison closer to a build/pipeline report than a paragraph of log text.

The active comparison target is now part of the scene document contract. A
saved `.gforge` object records the left/right graph-history ids for the current
diff, and reopening the scene restores both the table evidence and the MCP
comparison URI. This follows the pipeline principle that useful debug state
should survive editor restarts and remain addressable for automation.

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
- Qt graph result bridge actions that write manifest-recorded Unity/Unreal bridge packages.
- Qt graph result retarget actions that attach core-planned Unity/Unreal retarget graphs before bridge packaging.
- Qt graph result retarget diagnostics that keep planner audit issues visible beside the generated graph.
- Persisted planned-retarget report payloads that restore across `.gforge` save/open.
- Post-evaluation retarget audit comparisons that persist resolved, remaining, and new diagnostic keys.
- Graph result file actions that open/reveal output meshes, manifests, asset directories, and side-effect artifacts from persisted history.
- Model-backed graph result resource rows for output/artifact/manifest/asset-directory paths.
- Manifest-derived graph result resource rows for bridge packages and latest audit-history evidence.
- Selected-resource drill-down metadata for bridge package contracts and audit-history summaries.
- Manifest resource drill-down details for validation issue codes and latest provenance step chains.
- Full selected-resource validation issue and provenance step lists for manifest rows.
- Selected-resource audit issue lists and bridge package preview fields.
- Filtered graph result resource views for outputs, artifacts, manifests, asset directories, audit evidence, and bridge packages.
- Selected bridge package JSON previews for external engine handoff fields.
- Model-backed retarget diagnostic diff rows for planned, remaining, new, and resolved target-engine audit issues.
- Per-node enable/disable controls for non-destructive graph bypass.
- Per-node reorder controls for non-destructive modifier-stack ordering.
- Drag/drop graph reorder routed through the shared graph model, not UI-only row shuffling.
- Descriptor-driven path controls for graph operation inputs and output folders.
- Shared operation parameter presets exposed through core descriptors and applied by Qt.
- Stable scene graph-history resource IDs and MCP links for saved Qt scenes.
- MCP prompts for engine-ready prop generation, Unity repair, and Unreal package workflows.
- MCP graph-history comparison tool/resource for saved scene graph rows.
- Qt graph-history comparison display backed by the shared scene-link helper and saved history resource IDs.
- Qt pair-selected graph-history comparisons with copyable MCP comparison URIs.
- Model-backed Qt graph-history delta rows for scan-friendly comparison reports.
- Persisted graph-history comparison pair state in `.gforge` scene documents.
- Audit gates block engine handoff unless forced.
- Worker probe state is rendered accurately in the Qt model.
- A failed model worker leaves a durable failed job with logs and no partial success badge.
- Export bridge package validates without Unity/Unreal installed.
