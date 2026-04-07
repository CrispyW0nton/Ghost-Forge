"""
Creates a simple test OBJ mesh (a subdivided icosphere)
to verify the pipeline works correctly.
"""
import trimesh
import numpy as np

# Create an icosphere — a decent test because it has curved surfaces
# that stress-test UV unwrapping
mesh = trimesh.creation.icosphere(subdivisions=3)

# Add some vertex color noise so it's interesting
print(f"Test mesh: {len(mesh.vertices)} vertices, {len(mesh.faces)} faces")
mesh.export("/home/user/webapp/uploads/test_sphere.obj")
print("Saved: /home/user/webapp/uploads/test_sphere.obj")

# Also create a torus (more interesting for UV test)
torus = trimesh.creation.torus(major_radius=1.0, minor_radius=0.35, major_sections=40, minor_sections=20)
print(f"Test torus: {len(torus.vertices)} vertices, {len(torus.faces)} faces")
torus.export("/home/user/webapp/uploads/test_torus.obj")
print("Saved: /home/user/webapp/uploads/test_torus.obj")
