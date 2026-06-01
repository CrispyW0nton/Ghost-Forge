# Tripo MCP Engine Workflow Roadmap

Date: 2026-06-01

Purpose: route Ghost Forge content generation through a secure, manifest-backed MCP workflow that can generate smart meshes with textures and hand them to Unity-MCP-Ghost or Unreal-MCP-Ghost.

## Current Integration Target

Tripo's current OpenAPI docs define an async task workflow:

- authenticate with a server-side Bearer token,
- submit generation with `POST /v2/openapi/task`,
- poll `GET /v2/openapi/task/{task_id}`,
- read downloadable URLs from `data.output` such as `model`, `base_model`, or `pbr_model`.

The H3 text-to-model line exposes the smart mesh controls Ghost Forge needs first:

- `texture` and `pbr`,
- `texture_quality`,
- `smart_low_poly`,
- `quad`,
- `face_limit`,
- `auto_size`,
- `export_uv`,
- `geometry_quality`,
- `generate_parts`.

## Architectural Decision

Tripo is a hosted worker, not a GUI special case. It should live behind `ghostforge_core.workers` and be selected through the same capability registry as local models.

Credentials:

- Read keys from `GHOSTFORGE_TRIPO_API_KEY` or `TRIPO_API_KEY`.
- Allow future secure settings/keyring integration.
- Do not store raw keys in request extras, manifests, logs, bridge packages, or docs.

## MCP Route For Vibe-Coding Games

The intended agent route is:

1. Probe `list_worker_capabilities` and confirm `tripo_api` is runnable.
2. Call `submit_text_to_3d` for a single asset, or create a vertical slice asset with `strategy="text_to_3d"`.
3. Pass smart mesh options through `extras`/`generation_extras`.
4. Let Ghost Forge write the asset directory, output mesh, manifest, provenance, and audit state.
5. Annotate the manifest with the target engine.
6. Either create `ghostforge_bridge_unity.json` / `ghostforge_bridge_unreal.json`, or call `send_to_unity` / `send_to_unreal` when adapters are configured.
7. Let Unity-MCP-Ghost or Unreal-MCP-Ghost perform editor-specific import, placement, validation, and repair.

## Unity And Unreal Bridge Notes

Unity-MCP-Ghost currently has a strong project bridge and `asset_refresh`/asset-management surface. The near-term Ghost Forge route should create an offline bridge package and target an `Assets/GhostForge/...` path. Unity should then copy/import the GLB/FBX into the project and refresh the AssetDatabase.

Unreal-MCP-Ghost has explicit `import_static_mesh` and `import_skeletal_mesh` tools. Ghost Forge should recommend `import_static_mesh` for generated GLB/FBX props unless a rigging/character stage produces a skeletal FBX.

## Implementation Phases

### Phase A: Secure Hosted Worker

- Register `tripo_api` as a real `text_to_3d` worker.
- Probe credentials without making a network request.
- Submit/poll/download through a testable HTTP client.
- Redact secret-shaped keys from manifest parameters.
- Expose smart mesh options through MCP.

### Phase B: Slice-Level Game Asset Generation

- Allow vertical-slice assets to use `strategy="text_to_3d"`.
- Add `generation_extras` for provider-specific but manifest-visible options.
- Preserve prompt, worker, smart mesh settings, audit, target engine, and handoff state.

### Phase C: Engine Import Automation

- Add a bridge package importer convention for Unity-MCP-Ghost.
- Map Unreal bridge packages to `import_static_mesh` / `import_skeletal_mesh` arguments.
- Add optional direct adapter presets for local Unity and Unreal MCP servers.

### Phase D: Qt Provider And Generation UI

- Add a Content Generation panel with provider status, credential state, prompt controls, smart mesh presets, and cost warnings.
- Add generated-variant browser with topology, texture, audit, and engine-readiness comparison.
- Store provider keys through OS keyring or a secure settings abstraction, not project files.

## Acceptance Gate

A game agent can ask Ghost Forge to create a low-poly textured prop for Unity or Unreal, receive a job id, wait for completion, inspect a manifest, run an audit, and produce either an offline bridge JSON or a direct engine handoff without any API key appearing in persisted project files.
