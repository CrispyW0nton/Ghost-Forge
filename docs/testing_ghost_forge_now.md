# Testing Ghost Forge Now

Ghost Forge is not Blender yet, but these paths test the functioning Qt editor slices that exist today.

## Launch

```powershell
python -m ghostforge_qt.main
```

Use `--data-root C:\path\to\data` if you want a disposable project/runtime folder.

## Fastest Smoke Test

1. Open `Help > Create Test Cube`.
2. Confirm the cube appears in the Scene panel and viewport.
3. Press `F` for Frame All and `.` for Frame Selected.
4. Use the viewport toolbar to switch display, selection, transform, camera, projection, and navigation profile.
5. In Modeling, edit transform values or use the viewport gizmo, then test Undo/Redo.
6. Select a scene row and press `Delete`, then Undo. This removes the object from the scene without deleting source files.
7. For generated outputs, select the generated scene row and use `Asset > Delete Generated Files...` to permanently remove project-local graph/output folders.
8. Open Graph, add a deterministic mesh operation, adjust `Params / Job`, and Evaluate.
9. Save the scene, restart, and reopen the `.gforge` file.

## What To Expect

- The viewport is currently CPU-projected and functional for import, framing, selection state, camera controls, and transform gizmo tests.
- Content is project-based. `Open Project` points Ghost Forge at a project root; the Content browser reflects that folder.
- Graph evaluation uses durable jobs and should update scene/result history when an operation succeeds.
- AI generation only works when a worker or hosted provider is configured and probed as runnable.
- Image-to-3D source nodes are best treated as blockout/reference reconstruction. For production-quality attempts, chain `Generate Image To 3D` with `Worker Refine Mesh` using a hero cleanup preset and `Worker Texture Mesh` using a high-resolution texture preset when runnable workers exist.
- `Delete Generated Files...` only targets project-local generated outputs. Imported source meshes outside the project are left alone.

## Useful Verification Commands

```powershell
python -m pytest ghostforge_qt\tests --tb=short
python -m pytest ghostforge_core\tests\test_authoring_graph_job.py ghostforge_qt\tests\test_main_window.py -q
```
