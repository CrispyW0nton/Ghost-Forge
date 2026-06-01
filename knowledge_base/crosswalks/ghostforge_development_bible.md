# Ghost Forge Development Bible

Ghost Forge's strongest path is not to clone Blender or Maya feature-for-feature. It should become an AI-native asset foundry and 3D editor: a universal suite that can import, generate, inspect, edit, validate, package, and hand assets to engines.

## Product North Star

Ghost Forge should be:

- universal, not KOTOR-specific,
- Qt-native for the desktop editor,
- AI-assisted but not AI-dependent,
- manifest-driven and auditable,
- honest about model availability and output quality,
- extensible through workers and MCP,
- capable of human editing workflows over time.

## Layering

| Layer | Responsibility |
| --- | --- |
| `ghostforge_core` | domain models, storage, jobs, workers, manifests, audits, KB, authoring graphs, engine bridges |
| `ghostforge_qt` | PySide6 desktop shell, dock panels, viewport, controllers, action registry |
| `ghostforge_mcp` | agent-callable tool surface over the core |
| `ghostforge_app` | current Flask/HTTP bridge, retained for compatibility during migration |
| legacy Electron/React | useful prototype and visual reference, but not the long-term primary shell |

## Book-Derived Rules

### From Qt Books

- Use signals/slots and actions for command routing.
- Use model/view for scene trees, asset browsers, worker tables, audits, and manifests.
- Keep widgets thin; put behavior in controllers/services.
- Use background workers/processes for long-running generation and validation.
- Persist layouts, settings, recent files, and window state.

### From Game Engine Architecture

- Treat tools and asset pipelines as first-class systems.
- Make resources explicit: identity, dependencies, cache state, provenance, validation.
- Build debug/profiling surfaces as product features, not afterthoughts.
- Keep concurrency boundaries visible and testable.
- Make asset handoff deterministic and repeatable.

### From Graphics Math

- Document coordinate systems and units.
- Treat transforms, cameras, picking, and mesh operations as math contracts with tests.
- Use quaternions/interpolation where they prevent rotation bugs.
- Validate floating-point and geometry edge cases.

### From Ghost Rigger

- Qt shell can scale when it has service boundaries, typed panels, renderer abstraction, theme/layout systems, and headless controller tests.
- A knowledge base is most useful when it stores decisions, audits, ground truth, and acceptance checks, not just notes.
- Viewport systems need picking, gizmo state, camera controls, transform type-in, measurement, and validation from the start.

### From MCP Books

- Treat MCP as a structured product interface: tools perform actions, resources expose inspectable state, and prompts encode repeatable workflows.
- Keep tool calls schema-first, deterministic where possible, and explicit about mutation, risk, progress, and recovery.
- Keep authentication and provider credentials server-side. Never write API keys to job specs, manifests, bridge packages, or knowledge-base notes.
- Preserve context through resources, manifests, slice state, and job ids instead of relying on chat memory.

## Near-Term Decision Rules

- Prefer Qt/PySide6 for new desktop UI.
- Preserve existing Python tests and core APIs during migration.
- Do not remove Electron until Qt reaches parity for import, viewport, scene outliner, worker registry, UV/texture/audit, and settings.
- Put every generated asset behind a manifest and audit path.
- Do not claim production AI generation unless real workers are installed, probed, and passing sample generation tests.
- Hosted AI workers such as Tripo are production-capable only when their probes confirm server-side credentials and a sample job succeeds.
- MCP-driven game generation should route through Ghost Forge manifests and engine bridge packages before Unity-MCP-Ghost or Unreal-MCP-Ghost import the asset.
- Text/image generation, worker retopo/refinement, and worker texturing must be first-class authoring graph operations, not GUI/MCP side channels. Source nodes create the first mesh; process nodes require an input mesh; all worker nodes write manifests and provenance.
- Build universal asset abstractions. Do not import KOTOR-specific Ghost Rigger assumptions except as optional adapters or inspiration.

## Definition Of Done For New Features

- User-facing command exists in Qt action registry or MCP tool surface.
- Core behavior is tested without GUI.
- GUI controller/model is tested headlessly where possible.
- Job/progress/error states are visible.
- Manifest/audit impact is documented.
- Knowledge base updated when a book or Ghost Rigger principle guided the design.
