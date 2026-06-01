# Pre-Work Book Review Protocol

This protocol exists so Ghost Forge does not drift into random feature accretion. Before implementation, use the books as a design filter.

## Required Loop

1. Identify the subsystem being changed.
2. Open the matching knowledge note in `knowledge_base/book_notes/`.
3. Check whether the current work touches a cross-cutting rule in `knowledge_base/crosswalks/ghostforge_development_bible.md`.
4. If the book notes do not answer the question, rescan the relevant book chapter or outline from the local PDF and add a concise note.
5. Implement the change.
6. Update `knowledge_base/iteration_log.md` with what changed, what book/Ghost Rigger principle guided it, and what verification was run.

## Copyright Boundary

Allowed:

- Chapter maps and section names.
- Short paraphrased principles.
- Ghost Forge-specific applications.
- Test ideas and acceptance criteria.
- Links or local paths to source books.

Avoid:

- Long quotations.
- Reproducing tables, examples, or exercises.
- Copying prose into docs or comments.

## Local Book Paths

The current source PDFs are stored in:

`C:/Users/NewAdmin/Documents/Academy of Art University/Books/`

If these paths move, update this file and `knowledge_base/README.md`.
