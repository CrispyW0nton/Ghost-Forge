# Ghost Forge Book Notes

These notes convert the provided books into Ghost Forge engineering guidance. They are intentionally not exhaustive summaries. Each note answers: what should we build, how should we structure it, and what tests or acceptance checks prove we did it correctly?

## Notes

| Note | Main Sources | Use For |
| --- | --- | --- |
| `qt_gui_architecture.md` | Fitzpatrick, Lee, Summerfield, Ghost Rigger | PySide6 app shell, dock panels, model/view, actions, settings, worker threads, dialogs, themes |
| `game_engine_architecture.md` | Gregory, Ghost Rigger | asset pipeline, tools architecture, jobs, resources, profiling, debug surfaces, production gates |
| `graphics_math_foundations.md` | Dunn/Parberry, Vince, Kneusel, Ghost Rigger | transforms, coordinate spaces, cameras, selection, matrices, quaternions, mesh operations, validation |
| `mcp_integration.md` | Lowe, Krishnan, Unity-MCP-Ghost, Unreal-MCP-Ghost | MCP tools/resources/prompts, secure credentials, progress, schemas, engine bridge orchestration |

## Rule

Before adding a feature, update or consult the matching note. If the note does not yet cover the feature, add a concise project-specific entry before or alongside the code change.
