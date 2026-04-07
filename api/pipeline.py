"""
Main Pipeline
Combines UV unwrapping and texture generation into a single workflow.

Pipeline stages:
  1. Load mesh (OBJ, GLB, GLTF, STL, PLY)
  2. Auto UV unwrap with xatlas (ABF++ + atlas packing)
  3. Generate texture (procedural or Stable Diffusion)
  4. Apply texture to unwrapped mesh
  5. Export textured mesh (OBJ+MTL or GLB)
"""

import os
import logging
import json
import time
import numpy as np
from PIL import Image
import trimesh

from uv_unwrap import unwrap_file, load_mesh, unwrap_mesh, build_unwrapped_mesh
from texture_gen import generate_texture, render_uv_checkerboard

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def run_pipeline(
    input_mesh_path: str,
    output_dir: str,
    texture_prompt: str = "worn metal surface, aged, detailed",
    reference_image_path: str = None,
    texture_size: int = 1024,
    atlas_size: int = 1024,
    padding: int = 2,
    use_ai: bool = False,
    ai_steps: int = 20,
    output_format: str = "glb",
    uv_only: bool = False,
    job_id: str = None,
    progress_callback=None,
) -> dict:
    """
    Full UV + Texture pipeline.

    Args:
        input_mesh_path      : path to input 3D model
        output_dir           : directory for all outputs
        texture_prompt       : text description of desired texture
        reference_image_path : optional reference image for texture style
        texture_size         : output texture resolution (512, 1024, 2048)
        atlas_size           : UV atlas resolution hint for xatlas
        padding              : pixel padding between UV islands
        use_ai               : use Stable Diffusion instead of procedural
        ai_steps             : SD inference steps (quality vs speed)
        output_format        : "glb" or "obj"
        job_id               : unique job identifier for tracking
        progress_callback    : optional fn(stage: str, pct: int) for UI updates

    Returns:
        dict with paths to all output files and statistics
    """
    t_start = time.time()
    os.makedirs(output_dir, exist_ok=True)

    def progress(stage, pct):
        logger.info(f"[{pct}%] {stage}")
        if progress_callback:
            progress_callback(stage, pct)

    basename = os.path.splitext(os.path.basename(input_mesh_path))[0]

    # -------------------------------------------------------------------------
    # Stage 1: Load mesh
    # -------------------------------------------------------------------------
    progress("Loading mesh", 5)
    mesh = load_mesh(input_mesh_path)
    original_stats = {
        "vertices": len(mesh.vertices),
        "faces": len(mesh.faces),
        "bounds": mesh.bounds.tolist(),
        "watertight": mesh.is_watertight,
    }
    logger.info(f"Original mesh: {original_stats}")

    # -------------------------------------------------------------------------
    # Stage 2: UV unwrap with xatlas
    # -------------------------------------------------------------------------
    progress("Unwrapping UVs with xatlas (ABF++ algorithm)", 15)
    unwrap_result = unwrap_mesh(mesh, atlas_size=atlas_size, padding=padding)
    uvs = unwrap_result["uvs"]
    faces = unwrap_result["faces"]
    vertices = unwrap_result["vertices"]

    uv_stats = {
        "unwrapped_vertices": len(vertices),
        "uv_coords": len(uvs),
        "uv_expansion": round(len(vertices) / max(len(mesh.vertices), 1), 3),
    }
    logger.info(f"UV stats: {uv_stats}")

    # -------------------------------------------------------------------------
    # Stage 3: Save UV layout visualization (checkerboard debug map)
    # -------------------------------------------------------------------------
    progress("Rendering UV layout preview", 30)
    uv_preview_path = os.path.join(output_dir, f"{basename}_uv_layout.png")
    checker = render_uv_checkerboard(uvs, faces, size=texture_size)
    checker.save(uv_preview_path)
    logger.info(f"UV layout saved to {uv_preview_path}")

    # -------------------------------------------------------------------------
    # Stage 4: UV-only mode — export unwrapped mesh without texture
    # -------------------------------------------------------------------------
    if uv_only:
        progress("Exporting UV-unwrapped mesh (UV-only mode)", 80)
        if output_format == "glb":
            output_mesh_path = os.path.join(output_dir, f"{basename}_uv_unwrapped.glb")
        else:
            output_mesh_path = os.path.join(output_dir, f"{basename}_uv_unwrapped.obj")

        uv_mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        uv_mesh.export(output_mesh_path)

        t_end = time.time()
        meta = {
            "job_id": job_id, "input": input_mesh_path,
            "prompt": texture_prompt, "texture_size": texture_size,
            "uv_only": True,
            "output_mesh": output_mesh_path, "texture_map": None,
            "uv_layout": uv_preview_path,
            "original_stats": original_stats, "uv_stats": uv_stats,
            "processing_time_seconds": round(time.time() - t_start, 2),
        }
        meta_path = os.path.join(output_dir, f"{basename}_meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        progress("Done!", 100)
        return meta

    # -------------------------------------------------------------------------
    # Stage 4b: Generate texture
    # -------------------------------------------------------------------------
    progress(
        f"Generating texture ({'Stable Diffusion AI' if use_ai else 'procedural'} mode)",
        40
    )
    texture_path = os.path.join(output_dir, f"{basename}_texture.png")
    generate_texture(
        prompt=texture_prompt,
        output_path=texture_path,
        uvs=uvs,
        faces=faces,
        reference_image_path=reference_image_path,
        texture_size=texture_size,
        use_ai=use_ai,
        ai_steps=ai_steps,
    )

    # -------------------------------------------------------------------------
    # Stage 5: Apply texture to mesh and export
    # -------------------------------------------------------------------------
    progress("Applying texture to mesh", 80)
    texture_img = Image.open(texture_path).convert("RGB")
    texture_img_trimesh = trimesh.visual.texture.TextureVisuals(
        uv=np.clip(uvs, 0, 1),
        image=texture_img,
    )

    textured_mesh = trimesh.Trimesh(
        vertices=vertices,
        faces=faces,
        visual=texture_img_trimesh,
        process=False,
    )

    # -------------------------------------------------------------------------
    # Stage 6: Export
    # -------------------------------------------------------------------------
    progress("Exporting textured mesh", 90)
    if output_format == "glb":
        output_mesh_path = os.path.join(output_dir, f"{basename}_textured.glb")
    else:
        output_mesh_path = os.path.join(output_dir, f"{basename}_textured.obj")

    textured_mesh.export(output_mesh_path)
    logger.info(f"Exported textured mesh to {output_mesh_path}")

    # -------------------------------------------------------------------------
    # Stage 7: Write metadata JSON
    # -------------------------------------------------------------------------
    t_end = time.time()
    meta = {
        "job_id": job_id,
        "input": input_mesh_path,
        "prompt": texture_prompt,
        "texture_size": texture_size,
        "use_ai": use_ai,
        "output_mesh": output_mesh_path,
        "texture_map": texture_path,
        "uv_layout": uv_preview_path,
        "original_stats": original_stats,
        "uv_stats": uv_stats,
        "processing_time_seconds": round(t_end - t_start, 2),
    }
    meta_path = os.path.join(output_dir, f"{basename}_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    progress("Done!", 100)
    logger.info(f"Pipeline complete in {meta['processing_time_seconds']}s")

    return meta
