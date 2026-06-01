# Ghost Forge Qt Migration Plan

## Goal

Move Ghost Forge from an Electron/React prototype shell to a Qt/PySide6 desktop editor while preserving the tested Python core, MCP server, and HTTP compatibility surface.

## Principles From Ghost Rigger

- Qt should own the desktop process, settings, menus, docks, theme, and window layout.
- The renderer should be an abstraction behind a Qt widget, not scattered through panels.
- Panels should talk to controllers/services, not to raw file formats or model workers.
- Headless tests should cover controllers, models, file contracts, and command routing.
- The knowledge base should be updated when architecture choices change.

## Proposed Package Layout

```
ghostforge_qt/
  __init__.py
  main.py
  app.py
  actions.py
  services/
    core_bridge.py
    job_controller.py
    settings_service.py
  models/
    scene_model.py
    worker_model.py
    manifest_model.py
    audit_model.py
  panels/
    scene_outliner.py
    asset_browser.py
    worker_panel.py
    job_panel.py
    properties_panel.py
    manifest_panel.py
    audit_panel.py
    engine_panel.py
    chat_panel.py
  viewports/
    viewport_host.py
    renderer_interface.py
    null_renderer.py
    opengl_renderer.py
  tests/
```

## Migration Phases

### Phase 0: Safety And Docs

- Keep Electron app building.
- Fix ESLint 9 config or pin ESLint 8.
- Address production npm audit advisories.
- Keep `python -m pytest` green.
- Maintain `knowledge_base/iteration_log.md`.

### Phase 1: Qt Shell

- Add PySide6 optional dependency.
- Add `ghostforge_qt.main`.
- Create `QMainWindow` with menus, toolbar, dock areas, status bar, and persistent layout.
- Create action registry for core commands.
- Add smoke tests for app construction and action registration.

### Phase 2: Core Bridge

- Add `CoreBridge` that bootstraps `ghostforge_core`.
- Expose workers, models, jobs, KB status, audits, and engines through Qt-friendly services.
- Add worker registry panel and job monitor panel.
- Display probe state honestly.

### Phase 3: Document And Viewport

- Create a durable scene/document model.
- Add import mesh command and object tree.
- Add viewport host with null renderer first, then OpenGL/wgpu renderer.
- Add camera orbit, frame selected, transform gizmo, and transform type-in.

### Phase 4: Asset Workflows

- Port UV unwrap, texture generation, audit, manifest edit, and export bridge workflows.
- Every command creates or updates manifests.
- Add progress/cancel/log UI.

### Phase 5: Editing Tools

- Add object/mesh selection modes.
- Add operation history and undo/redo.
- Add mesh cleanup operations.
- Add UV viewer/editor foundations.
- Add material preview and texture-set management.

### Phase 6: AI-Native Suite

- Add model installation/cache UI.
- Add prompt/reference/KB workflow.
- Add variant browser and provenance graph.
- Add engine handoff dashboards.
- Add vertical-slice planner UI.

## Acceptance Gate For Retiring Electron

Do not retire the Electron shell until Qt can:

- launch reliably,
- import and display GLB/OBJ/STL/PLY,
- select and transform objects,
- persist a scene/document,
- run and monitor core jobs,
- inspect worker/model availability,
- unwrap and texture through core,
- show manifests and audits,
- create engine export bridge packages,
- pass backend and Qt smoke tests.
