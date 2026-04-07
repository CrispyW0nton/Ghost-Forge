"""
UV Unwrapping Module — GhostForge v1.3
Uses xatlas (same algorithm used by many AAA game studios) to automatically
generate UV coordinates for any 3D mesh.

xatlas implements:
  - Angle-based flattening (ABF)
  - Least squares conformal maps (LSCM)
  - Packing into atlases using the RBPF algorithm

v1.3 fixes:
  - xatlas crash isolation: runs in a subprocess; segfault cannot kill Flask
  - Mesh decimation guard: auto-decimates meshes > FACE_LIMIT before xatlas
  - Duplicate vertex deduplication: prevents 'axis 0 index exceeds dim' crash
  - Multi-material support: load_mesh_scene() returns per-material sub-meshes
  - UV preservation: detect_existing_uvs() lets caller skip re-unwrapping
"""

import json
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile

import numpy as np
import trimesh

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Safety limits
# ---------------------------------------------------------------------------
FACE_LIMIT_SAFE    = 20_000   # xatlas is fast and stable below this
FACE_LIMIT_SLOW    = 50_000   # warn user; will still try
FACE_LIMIT_HARD    = 100_000  # hard cap — decimate before unwrapping
DECIMATE_TARGET    = 18_000   # target face count after decimation


# ===========================================================================
# 1. Mesh loading
# ===========================================================================

def load_mesh(filepath: str) -> trimesh.Trimesh:
    """
    Load a 3D mesh, merging all sub-meshes into one.
    Fixes:
      - process=False → no silent vertex welding that breaks vmapping
      - deduplication done explicitly after load (see _preprocess)
    """
    logger.info(f"Loading mesh from {filepath}")
    loaded = trimesh.load(filepath, force="mesh", process=False)

    if isinstance(loaded, trimesh.Scene):
        logger.info("Scene detected — merging all geometries")
        meshes = [g for g in loaded.geometry.values()
                  if isinstance(g, trimesh.Trimesh)]
        if not meshes:
            raise ValueError("No geometry found in scene file")
        loaded = trimesh.util.concatenate(meshes)

    if not isinstance(loaded, trimesh.Trimesh):
        raise ValueError(f"Could not load mesh from {filepath}")

    logger.info(f"Loaded mesh: {len(loaded.vertices)} verts, {len(loaded.faces)} faces")
    return loaded


def load_mesh_scene(filepath: str) -> dict:
    """
    Load a file and return BOTH a merged mesh AND per-material sub-meshes.

    Returns:
        {
          "merged":     trimesh.Trimesh   — all geometry merged
          "submeshes":  list of (name, trimesh.Trimesh) tuples
          "has_scene":  bool
        }
    """
    logger.info(f"Loading scene from {filepath}")
    loaded = trimesh.load(filepath, process=False)

    submeshes = []
    has_scene = False

    if isinstance(loaded, trimesh.Scene):
        has_scene = True
        for name, geom in loaded.geometry.items():
            if isinstance(geom, trimesh.Trimesh):
                submeshes.append((name, geom))
        if not submeshes:
            raise ValueError("No geometry in scene file")
        merged = trimesh.util.concatenate([m for _, m in submeshes])
    elif isinstance(loaded, trimesh.Trimesh):
        submeshes = [("mesh", loaded)]
        merged = loaded
    else:
        raise ValueError(f"Unexpected type from trimesh.load: {type(loaded)}")

    logger.info(
        f"Scene: {len(submeshes)} sub-mesh(es), "
        f"merged={len(merged.vertices)}v/{len(merged.faces)}f"
    )
    return {"merged": merged, "submeshes": submeshes, "has_scene": has_scene}


def detect_existing_uvs(mesh: trimesh.Trimesh) -> bool:
    """
    Return True if the mesh already has UV coordinates.
    Allows the pipeline to skip re-unwrapping when UVs are already baked in.
    """
    try:
        vis = mesh.visual
        if hasattr(vis, "uv") and vis.uv is not None and len(vis.uv) > 0:
            logger.info(f"Mesh already has {len(vis.uv)} UV coords — skip re-unwrap available")
            return True
        # TextureVisuals wraps uv inside .uv attribute
        if hasattr(vis, "kind") and vis.kind == "texture":
            if hasattr(vis, "uv") and vis.uv is not None and len(vis.uv) > 0:
                return True
    except Exception:
        pass
    return False


def get_existing_uvs(mesh: trimesh.Trimesh):
    """
    Extract existing UV array from a mesh that has them.
    Returns (uvs: np.ndarray, faces: np.ndarray) or (None, None).
    """
    try:
        vis = mesh.visual
        if hasattr(vis, "uv") and vis.uv is not None and len(vis.uv) > 0:
            uvs = np.array(vis.uv, dtype=np.float32)
            faces = np.array(mesh.faces, dtype=np.uint32)
            return uvs, faces
    except Exception:
        pass
    return None, None


# ===========================================================================
# 2. Mesh preprocessing (dedup + decimate)
# ===========================================================================

def _preprocess_mesh(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """
    Prepare a mesh for xatlas:
      1. Merge duplicate / near-duplicate vertices (fixes index-out-of-bounds crash)
      2. Remove degenerate faces (zero-area triangles that confuse ABF)
      3. Remove NaN / Inf vertices
    """
    v = mesh.vertices.copy()
    f = mesh.faces.copy()
    n_orig = len(v)

    # --- Remove NaN/Inf ---
    bad_verts = np.any(~np.isfinite(v), axis=1)
    if bad_verts.any():
        logger.warning(f"Removing {bad_verts.sum()} NaN/Inf vertices")

    # --- Merge duplicate vertices (tolerance 1e-8) ---
    try:
        unique_verts, inv = np.unique(
            np.round(v, decimals=8), axis=0, return_inverse=True
        )
        remapped_faces = inv[f]
        # Validate all face indices are within bounds
        if remapped_faces.max() < len(unique_verts):
            v = unique_verts.astype(np.float32)
            f = remapped_faces.astype(np.uint32)
            if len(v) < n_orig:
                logger.info(f"Deduplication: {n_orig} → {len(v)} verts")
        else:
            logger.warning("Deduplication produced invalid indices — skipping")
    except Exception as e:
        logger.warning(f"Vertex deduplication failed (non-critical): {e}")

    # --- Remove degenerate faces ---
    e1 = v[f[:, 1]] - v[f[:, 0]]
    e2 = v[f[:, 2]] - v[f[:, 0]]
    cross = np.cross(e1, e2)
    areas = np.linalg.norm(cross, axis=1)
    valid = areas > 1e-12
    if not valid.all():
        logger.info(f"Removing {(~valid).sum()} degenerate faces")
        f = f[valid]

    # Rebuild trimesh
    cleaned = trimesh.Trimesh(vertices=v, faces=f, process=False)
    return cleaned


def _decimate_mesh(mesh: trimesh.Trimesh, target_faces: int) -> trimesh.Trimesh:
    """
    Reduce face count to target_faces using quadric decimation.
    Falls back to graceful error if simplification is unavailable.
    """
    n = len(mesh.faces)
    if n <= target_faces:
        return mesh

    ratio = target_faces / n
    logger.info(f"Decimating {n} → ~{target_faces} faces (ratio={ratio:.3f})")

    try:
        import open3d as o3d
        o3d_mesh = o3d.geometry.TriangleMesh()
        o3d_mesh.vertices = o3d.utility.Vector3dVector(mesh.vertices)
        o3d_mesh.triangles = o3d.utility.Vector3iVector(mesh.faces)
        simplified = o3d_mesh.simplify_quadric_decimation(target_faces)
        verts = np.asarray(simplified.vertices, dtype=np.float32)
        faces = np.asarray(simplified.triangles, dtype=np.uint32)
        result = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
        logger.info(f"open3d decimation → {len(result.faces)} faces")
        return result
    except ImportError:
        pass

    # Fallback: trimesh built-in simplification
    try:
        result = mesh.simplify_quadric_decimation(target_faces)
        logger.info(f"trimesh decimation → {len(result.faces)} faces")
        return result
    except Exception as e:
        logger.warning(f"Decimation failed ({e}); continuing with original mesh")
        return mesh


# ===========================================================================
# 3. xatlas subprocess runner (crash isolation)
# ===========================================================================

_XATLAS_WORKER_SCRIPT = """
import sys, json, numpy as np, xatlas

data   = json.loads(sys.stdin.read())
verts  = np.array(data["vertices"], dtype=np.float32)
faces  = np.array(data["faces"],    dtype=np.uint32)
norms  = np.array(data["normals"],  dtype=np.float32) if data.get("normals") else None

try:
    if norms is not None:
        vmapping, new_faces, new_uvs = xatlas.parametrize(verts, faces, norms)
    else:
        vmapping, new_faces, new_uvs = xatlas.parametrize(verts, faces)
    result = {
        "ok":       True,
        "vmapping": vmapping.tolist(),
        "faces":    new_faces.tolist(),
        "uvs":      new_uvs.tolist(),
    }
except Exception as e:
    result = {"ok": False, "error": str(e)}

print(json.dumps(result))
"""


def _run_xatlas_subprocess(vertices: np.ndarray,
                           faces: np.ndarray,
                           normals: np.ndarray = None,
                           timeout: int = 120) -> dict:
    """
    Run xatlas.parametrize() in a child process.
    If xatlas segfaults, the child dies but Flask stays alive.
    """
    payload = {
        "vertices": vertices.tolist(),
        "faces":    faces.tolist(),
        "normals":  normals.tolist() if normals is not None else None,
    }
    payload_str = json.dumps(payload)

    proc = subprocess.Popen(
        [sys.executable, "-c", _XATLAS_WORKER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = proc.communicate(
            input=payload_str.encode(), timeout=timeout
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError(
            f"xatlas timed out after {timeout}s "
            f"(mesh has {len(faces)} faces — try decimating first)"
        )

    if proc.returncode != 0:
        err_msg = stderr.decode(errors="replace").strip()
        raise RuntimeError(
            f"xatlas subprocess crashed (code {proc.returncode}). "
            f"stderr: {err_msg[:300]}"
        )

    try:
        result = json.loads(stdout.decode())
    except json.JSONDecodeError as e:
        raise RuntimeError(f"xatlas subprocess returned invalid JSON: {e}")

    if not result.get("ok"):
        raise RuntimeError(f"xatlas error: {result.get('error', 'unknown')}")

    return {
        "vmapping": np.array(result["vmapping"], dtype=np.uint32),
        "faces":    np.array(result["faces"],    dtype=np.uint32),
        "uvs":      np.array(result["uvs"],      dtype=np.float32),
    }


# ===========================================================================
# 4. Main unwrap entry point
# ===========================================================================

def unwrap_mesh(mesh: trimesh.Trimesh,
                atlas_size: int = 1024,
                padding: int = 2,
                force_unwrap: bool = False) -> dict:
    """
    Automatically generate UV coordinates for the mesh using xatlas.

    Parameters:
        mesh         : trimesh.Trimesh object
        atlas_size   : target texture resolution (xatlas uses this as hint)
        padding      : pixel padding between UV islands
        force_unwrap : if False, preserve existing UVs when present

    Returns dict with keys:
        vertices      — new vertex positions (expanded at UV seams)
        faces         — face indices into new vertices
        uvs           — UV coordinates per new vertex
        original_mesh — original trimesh for reference
        decimated     — True if mesh was auto-decimated
        skipped_unwrap— True if existing UVs were reused
    """
    logger.info(
        f"UV unwrap requested: {len(mesh.vertices)}v / {len(mesh.faces)}f "
        f"| atlas={atlas_size} pad={padding}"
    )

    # ── A. Check for existing UVs ───────────────────────────────────────────
    if not force_unwrap and detect_existing_uvs(mesh):
        existing_uvs, existing_faces = get_existing_uvs(mesh)
        if existing_uvs is not None:
            logger.info("Reusing existing UV coordinates (force_unwrap=False)")
            return {
                "vertices":       np.array(mesh.vertices, dtype=np.float32),
                "faces":          existing_faces,
                "uvs":            existing_uvs,
                "vmapping":       np.arange(len(mesh.vertices), dtype=np.uint32),
                "original_mesh":  mesh,
                "decimated":      False,
                "skipped_unwrap": True,
            }

    # ── B. Preprocess: dedup + remove degenerate faces ──────────────────────
    mesh = _preprocess_mesh(mesh)
    decimated = False

    # ── C. Decimate if above hard limit ─────────────────────────────────────
    face_count = len(mesh.faces)
    if face_count > FACE_LIMIT_HARD:
        logger.warning(
            f"Mesh has {face_count} faces (limit={FACE_LIMIT_HARD}). "
            f"Auto-decimating to ~{DECIMATE_TARGET} faces."
        )
        mesh = _decimate_mesh(mesh, DECIMATE_TARGET)
        mesh = _preprocess_mesh(mesh)  # re-clean after decimate
        decimated = True
    elif face_count > FACE_LIMIT_SLOW:
        logger.warning(
            f"Mesh has {face_count} faces — UV unwrap may take 10–60 s."
        )

    vertices = np.array(mesh.vertices, dtype=np.float32)
    faces    = np.array(mesh.faces,    dtype=np.uint32)

    # Validate indices are in range
    if faces.size > 0 and faces.max() >= len(vertices):
        raise ValueError(
            f"Face index {faces.max()} out of range for {len(vertices)} vertices "
            f"— mesh is corrupt after preprocessing"
        )

    # ── D. Compute normals ──────────────────────────────────────────────────
    try:
        mesh.fix_normals()
        normals = np.array(mesh.vertex_normals, dtype=np.float32)
        if normals.shape[0] != len(vertices):
            normals = None
    except Exception:
        normals = None

    # ── E. Run xatlas in subprocess (segfault-safe) ──────────────────────────
    logger.info(f"Running xatlas on {len(faces)} faces (subprocess mode)")
    timeout = max(60, len(faces) // 200)  # ~1s per 200 faces, min 60s
    xatlas_result = _run_xatlas_subprocess(vertices, faces, normals, timeout=timeout)

    vmapping   = xatlas_result["vmapping"]
    new_faces  = xatlas_result["faces"]
    new_uvs    = xatlas_result["uvs"]

    # Validate vmapping indices
    if vmapping.max() >= len(vertices):
        raise RuntimeError(
            f"xatlas vmapping references vertex {vmapping.max()} "
            f"but mesh only has {len(vertices)} — unexpected xatlas output"
        )

    new_vertices = vertices[vmapping]

    logger.info(
        f"UV unwrap complete: {len(new_vertices)}v (was {len(vertices)}), "
        f"{len(new_faces)} faces, {len(new_uvs)} UVs"
    )

    return {
        "vertices":       new_vertices,
        "faces":          new_faces,
        "uvs":            new_uvs,
        "vmapping":       vmapping,
        "original_mesh":  mesh,
        "decimated":      decimated,
        "skipped_unwrap": False,
    }


# ===========================================================================
# 5. Multi-material unwrap (one UV set per sub-mesh)
# ===========================================================================

def unwrap_submeshes(submeshes: list,
                     atlas_size: int = 1024,
                     padding: int = 2,
                     force_unwrap: bool = False) -> list:
    """
    Unwrap each sub-mesh independently, returning a list of unwrap result dicts.
    Each dict also includes 'name' and 'index'.
    Useful for multi-material characters where each material needs its own atlas.
    """
    results = []
    for idx, (name, mesh) in enumerate(submeshes):
        logger.info(f"Unwrapping sub-mesh {idx}: '{name}' "
                    f"({len(mesh.vertices)}v / {len(mesh.faces)}f)")
        try:
            res = unwrap_mesh(mesh, atlas_size=atlas_size,
                              padding=padding, force_unwrap=force_unwrap)
            res["name"]  = name
            res["index"] = idx
            results.append(res)
        except Exception as e:
            logger.error(f"Sub-mesh '{name}' unwrap failed: {e}")
            results.append({
                "name": name, "index": idx,
                "error": str(e),
                "vertices": np.array(mesh.vertices, dtype=np.float32),
                "faces":    np.array(mesh.faces,    dtype=np.uint32),
                "uvs":      None,
            })
    return results


# ===========================================================================
# 6. Build textured trimesh from unwrap result
# ===========================================================================

def build_unwrapped_mesh(unwrap_result: dict,
                         texture_image=None) -> trimesh.Trimesh:
    """
    Construct a new trimesh.Trimesh from the xatlas unwrap result.
    If texture_image (PIL.Image) is provided, attach it as TextureVisuals.
    """
    vertices = unwrap_result["vertices"]
    faces    = unwrap_result["faces"]
    uvs      = np.clip(unwrap_result["uvs"], 0.0, 1.0)

    if texture_image is not None:
        visuals = trimesh.visual.TextureVisuals(
            uv=uvs,
            image=texture_image,
        )
    else:
        material = trimesh.visual.material.SimpleMaterial()
        visuals  = trimesh.visual.TextureVisuals(uv=uvs, material=material)

    return trimesh.Trimesh(
        vertices=vertices, faces=faces, visual=visuals, process=False
    )


# ===========================================================================
# 7. Export helpers
# ===========================================================================

def save_mesh_obj(mesh: trimesh.Trimesh, output_path: str) -> str:
    mesh.export(output_path)
    logger.info(f"Saved OBJ → {output_path}")
    return output_path


def save_mesh_glb(mesh: trimesh.Trimesh, output_path: str) -> str:
    mesh.export(output_path)
    logger.info(f"Saved GLB → {output_path}")
    return output_path


# ===========================================================================
# 8. Convenience: full file pipeline (load → preprocess → unwrap → save)
# ===========================================================================

def unwrap_file(
    input_path:    str,
    output_dir:    str,
    atlas_size:    int  = 1024,
    padding:       int  = 2,
    output_format: str  = "glb",
    force_unwrap:  bool = False,
) -> dict:
    """Load → unwrap → save. Returns paths and mesh statistics."""
    os.makedirs(output_dir, exist_ok=True)
    basename = os.path.splitext(os.path.basename(input_path))[0]

    mesh   = load_mesh(input_path)
    result = unwrap_mesh(mesh, atlas_size=atlas_size,
                         padding=padding, force_unwrap=force_unwrap)
    unwrapped = build_unwrapped_mesh(result)

    if output_format == "glb":
        out_path = os.path.join(output_dir, f"{basename}_unwrapped.glb")
        save_mesh_glb(unwrapped, out_path)
    else:
        out_path = os.path.join(output_dir, f"{basename}_unwrapped.obj")
        save_mesh_obj(unwrapped, out_path)

    return {
        "output_path":        out_path,
        "original_vertices":  len(result["original_mesh"].vertices),
        "original_faces":     len(result["original_mesh"].faces),
        "unwrapped_vertices": len(result["vertices"]),
        "uv_coords":          len(result["uvs"]),
        "decimated":          result.get("decimated", False),
        "skipped_unwrap":     result.get("skipped_unwrap", False),
        "mesh":               unwrapped,
        "unwrap_result":      result,
    }
