# Ghost Forge Development Protocol

Ghost Forge is being developed as a universal 3D creation suite with AI-assisted asset generation, validation, and engine handoff. Treat `knowledge_base/` as the project memory and check it before making code changes.

## Mandatory Pre-Work

Before starting implementation work:

1. Read `knowledge_base/README.md`.
2. Read `knowledge_base/crosswalks/ghostforge_development_bible.md`.
3. Read the current subsystem note under `knowledge_base/book_notes/`:
   - Qt/UI work: `qt_gui_architecture.md`
   - viewport, transforms, rigging, mesh math: `graphics_math_foundations.md`
   - pipeline, jobs, resources, tools architecture: `game_engine_architecture.md`
4. Add a short entry to `knowledge_base/iteration_log.md` when a book concept changes a design decision.

Do not copy long passages from the books into the repo. Record chapter maps, durable principles, project-specific applications, tests to add, and open questions.

## Architecture Direction

- Keep `ghostforge_core` as the shared domain layer for jobs, manifests, workers, knowledge base, audits, authoring graphs, slices, and engine handoff.
- Build the future desktop editor as a Qt/PySide6 shell over the shared core, taking structural lessons from Ghost Rigger.
- Keep MCP and HTTP surfaces as peers of the GUI, not as the only way the GUI can reach core functionality.
- Prefer honest capability gates: UI controls should show whether a worker is runnable, stubbed, CPU-only, or missing dependencies.

## Verification

For backend changes, run `python -m pytest`. For frontend/Electron work, run `npm run build` and, once lint configuration is repaired, `npm run lint`. For Qt work, add focused headless tests around controllers, models, command routing, and file contracts before relying on visual inspection.
