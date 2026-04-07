"""
GhostForge Flask API Server
Provides REST endpoints for the UV + Texture pipeline.
"""

import os
import sys
import uuid
import json
import logging
import threading
import mimetypes
from pathlib import Path
from flask import (
    Flask, request, jsonify, send_file,
    send_from_directory, abort
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(__file__))
from pipeline import run_pipeline

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_MESH  = {".obj", ".glb", ".gltf", ".stl", ".ply", ".dae", ".fbx"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_UPLOAD    = 300 * 1024 * 1024  # 300 MB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD
CORS(app, origins="*", allow_headers=["Content-Type", "Authorization"])

jobs: dict = {}
jobs_lock  = threading.Lock()

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed(filename, allowed_set):
    return Path(filename).suffix.lower() in allowed_set

def update_job(job_id, **kw):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kw)

def make_cb(job_id):
    def cb(stage, pct):
        update_job(job_id, stage=stage, progress=pct)
    return cb

# ── Background worker ─────────────────────────────────────────────────────────
def run_job(job_id, mesh_path, ref_path, prompt,
            tex_size, use_ai, ai_steps, out_fmt, uv_only, force_unwrap):
    try:
        update_job(job_id, status="running", progress=0, stage="Starting")
        result = run_pipeline(
            input_mesh_path=mesh_path,
            output_dir=str(OUTPUT_DIR / job_id),
            texture_prompt=prompt,
            reference_image_path=ref_path,
            texture_size=tex_size,
            use_ai=use_ai,
            ai_steps=ai_steps,
            output_format=out_fmt,
            uv_only=uv_only,
            force_unwrap=force_unwrap,
            job_id=job_id,
            progress_callback=make_cb(job_id),
        )
        update_job(job_id, status="done", progress=100, stage="Complete", result=result)
        logger.info(f"Job {job_id} done in {result.get('processing_time_seconds',0):.1f}s")
    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        update_job(job_id, status="error", stage="Failed", error=str(e))

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR / "templates"), "index.html")

@app.route("/api/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "1.4.0",
        "capabilities": [
            "uv", "texture", "mesh-info",
            "uv-bake",          # texture now UV-projected, not flat-tiled
            "crash-isolation",  # xatlas runs in subprocess
            "auto-decimate",    # meshes >100k faces auto-decimated
            "dedup-verts",      # duplicate vertices removed pre-xatlas
            "uv-preserve",      # existing UVs reused when force_unwrap=false
            "multi-material",   # sub-meshes listed in metadata
            "40-materials",     # 40+ procedural material presets
        ]
    })

# ── Mesh info (fast preview of stats without full pipeline) ───────────────────
@app.route("/api/mesh-info", methods=["POST"])
def mesh_info():
    """
    Quick mesh statistics without running the pipeline.
    Returns vertex/face counts, bounding box, format.
    """
    if "mesh" not in request.files:
        return jsonify({"error": "No mesh file"}), 400

    mesh_file = request.files["mesh"]
    if not mesh_file.filename or not allowed(mesh_file.filename, ALLOWED_MESH):
        return jsonify({"error": "Unsupported format"}), 400

    tmp_dir  = UPLOAD_DIR / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    tmp_path = str(tmp_dir / secure_filename(mesh_file.filename))
    mesh_file.save(tmp_path)

    try:
        import trimesh
        loaded = trimesh.load(tmp_path, force="mesh", process=False)
        if isinstance(loaded, trimesh.Scene):
            meshes = list(loaded.geometry.values())
            if not meshes:
                return jsonify({"error": "No geometry in file"}), 400
            loaded = trimesh.util.concatenate(meshes)

        bounds = loaded.bounds.tolist() if loaded.bounds is not None else None
        size   = None
        if bounds:
            size = [bounds[1][i] - bounds[0][i] for i in range(3)]

        return jsonify({
            "vertices":   len(loaded.vertices),
            "faces":      len(loaded.faces),
            "edges":      len(loaded.edges) if hasattr(loaded, 'edges') else None,
            "watertight": bool(loaded.is_watertight),
            "bounds":     bounds,
            "size":       size,
            "format":     Path(tmp_path).suffix.lower(),
        })
    except Exception as e:
        logger.exception(f"mesh-info error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        try: os.remove(tmp_path)
        except: pass

# ── Create job ────────────────────────────────────────────────────────────────
@app.route("/api/jobs", methods=["POST"])
def create_job():
    """
    Start a UV + texture job.

    Form fields:
        mesh          (file)    — 3D model
        prompt        (str)     — texture description
        reference     (file)    — optional reference image
        texture_size  (int)     — 512/1024/2048
        use_ai        (bool)    — Stable Diffusion mode
        ai_steps      (int)     — SD inference steps
        output_format (str)     — glb | obj
        uv_only       (bool)    — skip texture, just unwrap UVs
    """
    if "mesh" not in request.files:
        return jsonify({"error": "No mesh file"}), 400

    mf = request.files["mesh"]
    if not mf.filename or not allowed(mf.filename, ALLOWED_MESH):
        return jsonify({"error": f"Unsupported format. Allowed: {sorted(ALLOWED_MESH)}"}), 400

    prompt      = request.form.get("prompt", "worn metal surface, detailed, high quality PBR")
    tex_size    = min(max(int(request.form.get("texture_size", 1024)), 256), 4096)
    use_ai      = request.form.get("use_ai",  "false").lower() in ("1", "true", "yes")
    ai_steps    = int(request.form.get("ai_steps", 20))
    out_fmt     = request.form.get("output_format", "glb").lower()
    uv_only      = request.form.get("uv_only",      "false").lower() in ("1", "true", "yes")
    force_unwrap = request.form.get("force_unwrap", "false").lower() in ("1", "true", "yes")

    job_id      = str(uuid.uuid4())
    upload_dir  = UPLOAD_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    mesh_name   = secure_filename(mf.filename)
    mesh_path   = str(upload_dir / mesh_name)
    mf.save(mesh_path)

    ref_path = None
    if "reference" in request.files:
        rf = request.files["reference"]
        if rf.filename and allowed(rf.filename, ALLOWED_IMAGE):
            rname    = secure_filename(rf.filename)
            ref_path = str(upload_dir / rname)
            rf.save(ref_path)

    with jobs_lock:
        jobs[job_id] = {
            "id":            job_id,
            "status":        "queued",
            "progress":      0,
            "stage":         "Queued",
            "prompt":        prompt,
            "mesh_filename": mesh_name,
            "uv_only":       uv_only,
            "force_unwrap":  force_unwrap,
            "result":        None,
            "error":         None,
        }

    threading.Thread(
        target=run_job,
        args=(job_id, mesh_path, ref_path, prompt,
              tex_size, use_ai, ai_steps, out_fmt, uv_only, force_unwrap),
        daemon=True,
    ).start()

    logger.info(f"Job {job_id}: '{prompt}' | AI={use_ai} | UV_ONLY={uv_only} | FORCE_UNWRAP={force_unwrap} | size={tex_size}")
    return jsonify({"job_id": job_id, "status": "queued"}), 202

# ── Get / list jobs ───────────────────────────────────────────────────────────
@app.route("/api/jobs/<job_id>")
def get_job(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    return jsonify(job)

@app.route("/api/jobs")
def list_jobs():
    with jobs_lock:
        out = [{k: v for k, v in j.items() if k != "result"} for j in jobs.values()]
    return jsonify(out)

# ── Download outputs ──────────────────────────────────────────────────────────
@app.route("/api/jobs/<job_id>/download/<file_type>")
def download_file(job_id, file_type):
    """
    file_type: mesh | texture | uv_layout
    """
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Job not ready"}), 404

    result = job.get("result", {})
    paths  = {
        "mesh":      result.get("output_mesh"),
        "texture":   result.get("texture_map"),
        "uv_layout": result.get("uv_layout"),
    }
    fp = paths.get(file_type)
    if not fp or not os.path.exists(fp):
        return jsonify({"error": f"'{file_type}' not found"}), 404

    return send_file(fp, as_attachment=True, download_name=os.path.basename(fp))

# ── Preview files (inline, for browser display) ────────────────────────────────
@app.route("/api/jobs/<job_id>/preview/<file_type>")
def preview_file(job_id, file_type):
    """
    file_type: texture | uv_layout | mesh_glb
    mesh_glb serves the textured GLB directly — used by Three.js in the viewport
    """
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Job not ready"}), 404

    result = job.get("result", {})
    paths  = {
        "texture":   result.get("texture_map"),
        "uv_layout": result.get("uv_layout"),
        "mesh_glb":  result.get("output_mesh"),
    }
    fp = paths.get(file_type)
    if not fp or not os.path.exists(fp):
        return jsonify({"error": "File not found"}), 404

    # Determine MIME type
    if file_type in ("texture", "uv_layout"):
        return send_file(fp, mimetype="image/png")
    elif file_type == "mesh_glb":
        return send_file(fp, mimetype="model/gltf-binary",
                         as_attachment=False,
                         download_name=os.path.basename(fp))

    return send_file(fp)

# ── Serve output files by job_id and filename (for Three.js GLB loading) ──────
@app.route("/api/outputs/<job_id>/<filename>")
def serve_output(job_id, filename):
    """Direct file serving for GLB/texture/UV preview in Three.js."""
    output_path = OUTPUT_DIR / job_id / secure_filename(filename)
    if not output_path.exists():
        return jsonify({"error": "File not found"}), 404
    mime, _ = mimetypes.guess_type(str(output_path))
    if filename.endswith('.glb'):
        mime = "model/gltf-binary"
    return send_file(str(output_path), mimetype=mime or "application/octet-stream")

# ── Models / extensions (stub for Modly compatibility) ────────────────────────
@app.route("/api/models")
def list_models():
    return jsonify([
        {"id": "hunyuan3d-mini",  "name": "Hunyuan3D Mini",  "installed": False, "size_gb": 4.2},
        {"id": "triposg",         "name": "TripoSG",          "installed": False, "size_gb": 7.1},
        {"id": "trellis2",        "name": "TRELLIS 2",        "installed": False, "size_gb": 12.0},
    ])

@app.route("/api/extensions")
def list_extensions():
    return jsonify([])

# ── Image-to-3D generation ────────────────────────────────────────────────────
@app.route("/api/generate", methods=["POST"])
def generate_mesh():
    """
    Image-to-3D mesh generation.
    Requires a large AI model to be installed (Hunyuan3D, TripoSG, TRELLIS 2).
    Returns a job ID that can be polled via /api/jobs/<id>.
    """
    model_id = request.form.get("model_id", "hunyuan3d-mini")

    # Check if an image was provided
    if "image" not in request.files:
        return jsonify({"error": "No image file provided. Field name must be 'image'."}), 400

    img_file = request.files["image"]
    if not img_file.filename or not allowed(img_file.filename, ALLOWED_IMAGE):
        return jsonify({
            "error": f"Unsupported image format. Allowed: {sorted(ALLOWED_IMAGE)}"
        }), 400

    # Check if the requested model is installed
    MODELS = {
        "hunyuan3d-mini": {"name": "Hunyuan3D Mini",  "size_gb": 4.2},
        "triposg":         {"name": "TripoSG",          "size_gb": 7.1},
        "trellis2":        {"name": "TRELLIS 2",        "size_gb": 12.0},
    }

    if model_id not in MODELS:
        return jsonify({"error": f"Unknown model '{model_id}'. Valid: {list(MODELS.keys())}"}), 400

    model_info = MODELS[model_id]

    # Try to import the model runner — will fail if not installed
    try:
        # These imports will raise ImportError if models are not downloaded
        if model_id == "hunyuan3d-mini":
            import hunyuan3d  # noqa
        elif model_id == "triposg":
            import triposg    # noqa
        elif model_id == "trellis2":
            import trellis    # noqa
    except ImportError:
        return jsonify({
            "error": "MODEL_NOT_INSTALLED",
            "model":  model_id,
            "name":   model_info["name"],
            "size_gb": model_info["size_gb"],
            "message": (
                f"{model_info['name']} ({model_info['size_gb']} GB) is not installed. "
                f"This model requires a GPU and a large download. "
                f"Install instructions: https://github.com/CrispyW0nton/Ghost-Tripo-API#models"
            ),
            "install_hint": f"pip install ghostforge-{model_id}"
        }), 503

    # If we get here the model is installed — save image and create job
    job_id     = str(uuid.uuid4())
    upload_dir = UPLOAD_DIR / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    img_name  = secure_filename(img_file.filename)
    img_path  = str(upload_dir / img_name)
    img_file.save(img_path)

    with jobs_lock:
        jobs[job_id] = {
            "id":       job_id,
            "status":   "queued",
            "progress": 0,
            "stage":    "Queued",
            "type":     "generate",
            "model":    model_id,
            "result":   None,
            "error":    None,
        }

    # (Real generation thread would go here once a model is installed)
    logger.info(f"Generate job {job_id}: model={model_id} image={img_name}")
    return jsonify({"job_id": job_id, "status": "queued"}), 202


if __name__ == "__main__":
    logger.info("GhostForge API — starting on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
