"""
UV Unwrapping Module
Uses xatlas (same algorithm used by many AAA game studios) to automatically
generate UV coordinates for any 3D mesh.

xatlas implements:
  - Angle-based flattening (ABF)
  - Least squares conformal maps (LSCM)
  - Packing into atlases using the RBPF algorithm
"""

import numpy as np
import trimesh
import xatlas
import os
import logging

logger = logging.getLogger(__name__)


def load_mesh(filepath: str) -> trimesh.Trimesh:
    """
    Load a 3D mesh from file. Supports OBJ, GLB, GLTF, STL, PLY, FBX, DAE.
    Merges scene into single mesh if needed.
    """
    logger.info(f"Loading mesh from {filepath}")
    loaded = trimesh.load(filepath, force="mesh", process=False)

    if isinstance(loaded, trimesh.Scene):
        logger.info("Scene detected — merging all geometries into one mesh")
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No geometry found in scene file")
        loaded = trimesh.util.concatenate(meshes)

    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Could not load mesh from {filepath}")

    logger.info(f"Loaded mesh: {len(loaded.vertices)} vertices, {len(loaded.faces)} faces")
    return loaded


def unwrap_mesh(mesh: trimesh.Trimesh, atlas_size: int = 1024, padding: int = 2) -> dict:
    """
    Automatically generate UV coordinates for the mesh using xatlas.

    xatlas uses ABF++ (Angle-Based Flattening) to minimize angular distortion,
    then packs all UV islands into a single atlas with RBPF bin packing.

    Parameters:
        mesh       : trimesh.Trimesh object
        atlas_size : target texture resolution (xatlas uses this as hint)
        padding    : pixel padding between UV islands (prevents bleeding)

    Returns:
        dict with keys:
            vertices    - new vertex positions (may be expanded due to UV seams)
            faces       - face indices into new vertices
            uvs         - UV coordinates per new vertex
            original_mesh - original trimesh for reference
    """
    logger.info(f"Starting UV unwrap (atlas_size={atlas_size}, padding={padding})")

    vertices = np.array(mesh.vertices, dtype=np.float32)
    faces = np.array(mesh.faces, dtype=np.uint32)

    # Compute normals for better ABF seam placement
    mesh.fix_normals()
    normals = np.array(mesh.vertex_normals, dtype=np.float32)

    # Run xatlas parametrization
    # ChartOptions controls how the mesh is segmented into UV islands
    # PackOptions controls how islands are arranged in the atlas
    vmapping, new_faces, new_uvs = xatlas.parametrize(vertices, faces, normals)

    # vmapping maps new vertex indices → original vertex indices
    new_vertices = vertices[vmapping]

    logger.info(
        f"UV unwrap complete: "
        f"{len(new_vertices)} vertices (was {len(vertices)}), "
        f"{len(new_faces)} faces, "
        f"{len(new_uvs)} UV coords"
    )

    return {
        "vertices": new_vertices,
        "faces": new_faces,
        "uvs": new_uvs,
        "vmapping": vmapping,
        "original_mesh": mesh,
    }


def build_unwrapped_mesh(unwrap_result: dict) -> trimesh.Trimesh:
    """
    Construct a new trimesh.Trimesh from the xatlas unwrap result,
    with UVs stored as a TextureVisuals object.
    """
    vertices = unwrap_result["vertices"]
    faces = unwrap_result["faces"]
    uvs = unwrap_result["uvs"]

    # Clamp UVs to [0, 1] (xatlas should produce valid UVs but be safe)
    uvs = np.clip(uvs, 0.0, 1.0)

    material = trimesh.visual.material.SimpleMaterial()
    visuals = trimesh.visual.TextureVisuals(uv=uvs, material=material)
    new_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, visual=visuals, process=False)

    return new_mesh


def save_mesh_obj(mesh: trimesh.Trimesh, output_path: str) -> str:
    """
    Export mesh as OBJ with MTL sidecar. Returns the path to the .obj file.
    """
    mesh.export(output_path)
    logger.info(f"Saved unwrapped mesh to {output_path}")
    return output_path


def save_mesh_glb(mesh: trimesh.Trimesh, output_path: str) -> str:
    """
    Export mesh as GLB (binary glTF). Preferred for web viewers.
    """
    mesh.export(output_path)
    logger.info(f"Saved unwrapped mesh (GLB) to {output_path}")
    return output_path


def unwrap_file(
    input_path: str,
    output_dir: str,
    atlas_size: int = 1024,
    padding: int = 2,
    output_format: str = "obj",
) -> dict:
    """
    Full pipeline: load → unwrap → save.

    Returns paths to saved files and mesh statistics.
    """
    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(input_path))[0]

    # 1. Load
    mesh = load_mesh(input_path)

    # 2. Unwrap
    result = unwrap_mesh(mesh, atlas_size=atlas_size, padding=padding)

    # 3. Build new mesh with UVs
    unwrapped = build_unwrapped_mesh(result)

    # 4. Save
    if output_format == "glb":
        out_path = os.path.join(output_dir, f"{basename}_unwrapped.glb")
        save_mesh_glb(unwrapped, out_path)
    else:
        out_path = os.path.join(output_dir, f"{basename}_unwrapped.obj")
        save_mesh_obj(unwrapped, out_path)

    return {
        "output_path": out_path,
        "original_vertices": len(result["original_mesh"].vertices),
        "original_faces": len(result["original_mesh"].faces),
        "unwrapped_vertices": len(result["vertices"]),
        "uv_coords": len(result["uvs"]),
        "mesh": unwrapped,
        "unwrap_result": result,
    }
