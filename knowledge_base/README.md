# Ghost Forge Knowledge Base

This folder is the development bible for Ghost Forge. It is not a copy of the reference books. It is a maintained, searchable layer of chapter maps, principles, project-specific decisions, audits, and roadmap notes derived from the provided books, Ghost Forge, and Ghost Rigger.

## Start Here

| Goal | Read |
| --- | --- |
| Understand current state | `audits/2026-05-31_current_state.md` |
| Compare DCC competitors | `research/dcc_capability_research_2026-05-31.md` |
| Make architecture decisions | `crosswalks/ghostforge_development_bible.md` |
| Plan Qt migration | `roadmap/qt_migration_plan.md` |
| Plan DCC feature growth | `roadmap/dcc_competitor_roadmap.md` |
| Work on PySide6/Qt UI | `book_notes/qt_gui_architecture.md` |
| Work on transforms, cameras, mesh math, rigging | `book_notes/graphics_math_foundations.md` |
| Work on jobs, asset pipeline, resources, profiling | `book_notes/game_engine_architecture.md` |
| Work on MCP, AI tool orchestration, engine handoff | `book_notes/mcp_integration.md` and `roadmap/tripo_mcp_engine_workflow.md` |
| Maintain the bible | `protocols/pre_work_book_review.md` and `iteration_log.md` |

## Source Books Scanned

- Martin Fitzpatrick, *Create GUI Applications with Python & Qt6*
- Lee Zhi Eng, *Qt 6 C++ GUI Programming Cookbook*, 3rd ed.
- Mark Summerfield, *Rapid GUI Programming with Python and Qt*
- Jason Gregory, *Game Engine Architecture*, 4th ed.
- Dunn and Parberry, *3D Math Primer for Graphics and Game Development*, 2nd ed.
- Ronald T. Kneusel, *Math for Programming*
- John Vince, *Mathematics for Computer Graphics*, 7th ed.
- Kevin Lowe, *Mastering Model Context Protocol: Advanced Techniques for AI Integration*
- Naveen Krishnan, *Model Context Protocol for LLMs*

Future reference scans should use the full local library root:

- `C:\Users\NewAdmin\Documents\Academy of Art University\Books`

The binary PDFs remain outside this repository. Notes here should stay copyright-safe: summarize, cross-reference, apply, and test.

## Maintenance Rule

Every meaningful implementation pass should improve this folder in one of three ways:

- Add a book-derived principle or correction.
- Add a subsystem decision and the reason it follows from the books or Ghost Rigger.
- Add a test, audit, or acceptance checklist that makes the principle enforceable.
