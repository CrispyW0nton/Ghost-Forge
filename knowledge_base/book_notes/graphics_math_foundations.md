# Graphics Math Foundations For Ghost Forge

Sources scanned: Dunn/Parberry's *3D Math Primer*, John Vince's *Mathematics for Computer Graphics*, Ronald Kneusel's *Math for Programming*, and Ghost Rigger's viewport/gizmo/math subsystems.

## Chapter Map Anchors

The scanned books emphasize:

- Cartesian coordinate systems and handedness.
- Vectors, points, dot products, cross products, distances.
- Multiple coordinate spaces: object, world, camera, view/upright.
- Matrices, transformations, basis vectors, row/column conventions.
- Rotations, Euler angles, quaternions, interpolation.
- Geometric primitives, curves, barycentric coordinates, collision/intersection.
- Floating-point error and robust numeric reasoning.

## Ghost Forge Applications

### Coordinate Policy

Ghost Forge needs a documented coordinate policy before the Qt viewport grows:

- internal asset coordinate convention,
- displayed axes,
- import/export conversion rules,
- Unity and Unreal target conversions,
- row/column matrix convention,
- units and scale.

This should live in code and in the manifest.

### Viewport Transform Contract

Every visible transform should have one source of truth:

- object transform in scene/document model,
- viewport gizmo edits update that model,
- modifier/authoring graph observes or records the edit,
- export reads the model, not transient widget state.

Ghost Forge currently has transform gizmo state in React and an authoring graph write path. The Qt rewrite should formalize this as a controller with tests.

### Picking And Selection

A modeling suite needs robust picking before deep mesh editing:

- object selection,
- face/edge/vertex modes,
- ray construction from camera and mouse,
- acceleration structures for large meshes,
- predictable multi-select behavior.

Ghost Rigger already has useful patterns: picking providers, transform controller, gizmo renderer, mesh selection state, and mesh operation history.

### Mesh Operations

Operations must be explicit and reversible where possible:

- transform,
- weld,
- delete/detach,
- bridge/cap/connect,
- normals recalculation,
- decimate/remesh,
- UV unwrap,
- texture bake.

The immediate Ghost Forge goal is not to out-model Blender. It is to create a clean operation graph that can later grow into real modeling tools.

### Numeric Safety

Add tolerance-aware validation for:

- zero-area faces,
- NaN/Inf coordinates,
- non-finite transforms,
- inverted or non-uniform scale where unsupported,
- tangent/normal consistency,
- unit-scale mismatch.

## First Tests To Add

- Coordinate conversion round trip for Unity and Unreal targets.
- Transform compose/decompose invariants.
- Ray picking hits deterministic fixtures.
- Mesh stats reject NaN, Inf, empty geometry, and non-manifold cases.
- Gizmo edits persist into the scene model and authoring graph.
