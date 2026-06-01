# MCP Integration Notes For Ghost Forge

Sources scanned: Kevin Lowe's *Mastering Model Context Protocol: Advanced Techniques for AI Integration*, Naveen Krishnan's *Model Context Protocol for LLMs*, Unity-MCP-Ghost, Unreal-MCP-Ghost, and the current Ghost Forge MCP surface.

## Scan Anchors

Lightweight PDF scan:

- Lowe: 194 pages; high-frequency anchors included context, tool, server, client, security, integration, transport, and resource.
- Krishnan: 524 pages; high-frequency anchors included server, tool, context, resource, client, security, integration, and authentication.

These notes intentionally capture project rules and do not reproduce book text.

## Ghost Forge Applications

### MCP Is A Product Surface

Ghost Forge's MCP server is not a debug wrapper around the GUI. It is a first-class product surface for game agents that need to generate, validate, package, and hand off assets without opening the desktop editor.

Tool design should be:

- explicit about mutation and risk,
- narrow enough for agents to compose,
- backed by durable jobs for long-running work,
- schema-first so failures are clear,
- resumable through job ids, manifests, and slice run state.

### Secrets Stay Out Of Project Artifacts

Hosted AI providers such as Tripo must read credentials from server-side environment variables, OS credential storage, or a future secure settings provider. Secrets must not appear in:

- worker request extras,
- job handles,
- manifests,
- provenance,
- bridge packages,
- screenshots,
- knowledge-base notes.

Ghost Forge should redact secret-shaped keys before writing manifest parameters.

### Tools, Resources, And Prompts

Use tools for actions, resources for inspectable state, and prompts/templates for repeated agent workflows.

Immediate Ghost Forge mapping:

- Tools: `submit_text_to_3d`, `submit_image_to_3d`, `create_engine_export_bridge`, `send_to_unity`, `send_to_unreal`, `create_vertical_slice`, `submit_vertical_slice`.
- Resources: operation descriptor resource, edit graph list/resource/evaluation resources, worker capability resources, engine bridge readiness resources, project asset manifest resources, Tripo provider status resource.
- Prompts: `generate_engine_ready_prop`, `repair_generated_mesh_for_unity`, and `prepare_unreal_static_mesh_package`.

### Graph MCP Parity

The MCP surface should expose the same authoring graph contract used by Qt:

- `list_operations` must include operation type, source/worker capability, matching workers, and runnable/stub/missing state.
- Edit graphs are inspectable resources, not just transient tool arguments.
- Evaluation tools must persist both the graph and the last evaluation report in `EditGraphStore`.
- Long-running evaluation should be submitted as `evaluate_edit_graph` jobs so agents can poll, wait with progress, and resume through graph/evaluation resources.
- Source graphs with no base mesh are valid when the first enabled node is a generation source.
- Worker graph side effects should be written into the final manifest as traceable worker-operation history without leaking provider secrets.
- Operation descriptors should expose shared parameter presets so agents can
  choose the same realtime, hero, mobile, bake, and cleanup profiles available
  in the Qt editor instead of guessing parameter bundles.
- Saved Qt scenes should be inspectable MCP resources. Scene objects with
  operation graphs expose stable graph-history row ids and links back to
  `ghostforge://graphs/{graph_id}` and its evaluation resource.
- Repeated graph workflows should be encoded as prompts, not tribal knowledge:
  generate engine-ready props, repair generated meshes for Unity, and prepare
  Unreal static mesh packages all route through capability probes, graph
  evaluation, manifests, audits, and bridge packages.
- Scene graph-history comparison should be an MCP action/resource pair. Agents
  can compare two saved rows by id and receive changed output/audit fields,
  artifact and bridge path deltas, audit issue additions/removals, and retarget
  diagnostic list changes.
- The Qt result inspector should use the same comparison helper for artist
  visibility, while preserving saved `history_id`, `resource_uri`, and
  `mcp_links` so an MCP agent can address the same evidence later.
- Qt should expose copyable comparison resource URIs for selected graph-history
  pairs so human review and agent automation can resume from the same saved
  scene evidence.
- Qt should render the shared comparison payload as structured rows as well as
  prose, so MCP-style field/resource/audit/retarget deltas stay inspectable in
  the desktop editor.
- Qt scene documents should persist the active graph-history comparison pair,
  because a copied MCP comparison URI is only truly reusable if reopening the
  scene restores the same left/right evidence target.

### Engine MCP Handoff

Ghost Forge should generate assets into its own manifest-backed project structure first. Unity-MCP-Ghost and Unreal-MCP-Ghost should receive either:

- an offline `ghostforge_bridge_<engine>.json` package, or
- a direct `send_to_engine` call through a configured adapter.

This keeps provenance, audit, target-engine intent, and failures in Ghost Forge even when the final import happens in another MCP server.

## Acceptance Checks

- `list_worker_capabilities` shows hosted text-to-3D as unavailable until a Tripo key is configured.
- `submit_text_to_3d` returns a job handle and never echoes the key.
- Generated assets emit `asset_manifest.json` with source prompt, selected worker, smart mesh options, and no secrets.
- MCP edit graph evaluation can start from an image/text generation source node and still emit graph, worker, and manifest provenance.
- `list_operations` includes operation `parameter_presets` where available, and those presets match the Qt parameter form choices.
- `ghostforge://scenes` lists saved Qt `.gforge` scenes, and scene/object graph-history resources return stable `history_id` and `mcp_links` fields.
- MCP prompt listing includes `generate_engine_ready_prop`, `repair_generated_mesh_for_unity`, and `prepare_unreal_static_mesh_package`, and each prompt instructs agents to use graph/audit/bridge resources instead of direct side channels.
- `compare_scene_graph_history` and the matching comparison resource return structured deltas between two saved scene object graph-history rows.
- The Qt result inspector can show the same structured graph-history deltas for the selected row versus the previous row without dropping MCP link fields.
- The Qt result inspector can compare non-adjacent graph-history rows and copy the matching MCP comparison resource URI.
- The Qt result inspector renders graph-history comparison payloads as model-backed delta rows for field, resource, audit, and retarget changes.
- `.gforge` scene save/open restores the active graph-history comparison pair used to derive the MCP comparison URI.
- `submit_evaluate_edit_graph` returns a durable job handle and the final result can be inspected through the graph evaluation resource.
- Vertical-slice assets can use `strategy="text_to_3d"` with Tripo smart options and still flow through audit and engine handoff stages.
- Unity/Unreal handoff stays bridge-based unless an adapter transport is explicitly configured.

## Open Questions

- Should secure runtime credentials live in Qt settings via OS keyring, project-local encrypted settings, or process environment only?
- Should Unity-MCP-Ghost add a dedicated `import_generated_asset` tool to match Unreal's explicit `import_static_mesh` surface?
- Should Tripo conversion, smart low-poly, rig/pre-rig, and retarget tasks be modeled as separate Ghost Forge workers or as post-process operations?
