"""
Flask API Server
Provides REST endpoints for the UV + Texture pipeline.
"""

import os
import sys
import uuid
import json
import logging
import threading
from pathlib import Path
from flask import (
    Flask, request, jsonify, send_file,
    send_from_directory, abort
)
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Make sure our modules are importable
sys.path.insert(0, os.path.dirname(__file__))
from pipeline import run_pipeline

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_DIR   = Path(__file__).parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "outputs"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

ALLOWED_MESH_EXTENSIONS = {".obj", ".glb", ".gltf", ".stl", ".ply", ".dae", ".fbx"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 200 MB

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

# In-memory job store  {job_id: {status, progress, stage, result, error}}
jobs: dict = {}
jobs_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename: str, allowed: set) -> bool:
    return Path(filename).suffix.lower() in allowed


def update_job(job_id: str, **kwargs):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(kwargs)


def make_progress_callback(job_id: str):
    def cb(stage: str, pct: int):
        update_job(job_id, stage=stage, progress=pct)
    return cb


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

def run_job(
    job_id: str,
    mesh_path: str,
    ref_image_path: str | None,
    prompt: str,
    texture_size: int,
    use_ai: bool,
    ai_steps: int,
    output_format: str,
):
    job_output_dir = str(OUTPUT_DIR / job_id)
    try:
        update_job(job_id, status="running", progress=0, stage="Starting")
        result = run_pipeline(
            input_mesh_path=mesh_path,
            output_dir=job_output_dir,
            texture_prompt=prompt,
            reference_image_path=ref_image_path,
            texture_size=texture_size,
            use_ai=use_ai,
            ai_steps=ai_steps,
            output_format=output_format,
            job_id=job_id,
            progress_callback=make_progress_callback(job_id),
        )
        update_job(
            job_id,
            status="done",
            progress=100,
            stage="Complete",
            result=result,
        )
        logger.info(f"Job {job_id} completed successfully")
    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        update_job(job_id, status="error", stage="Failed", error=str(e))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory(str(BASE_DIR / "templates"), "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0"})


@app.route("/api/jobs", methods=["POST"])
def create_job():
    """
    Start a new UV+texture job.

    Form fields:
        mesh        (file, required)  — 3D model file
        prompt      (str, required)   — texture description
        reference   (file, optional)  — reference image
        texture_size (int)            — 512 / 1024 / 2048 (default 1024)
        use_ai      (bool)            — use Stable Diffusion (default false)
        ai_steps    (int)             — SD steps (default 20)
        output_format (str)           — "glb" or "obj" (default "glb")
    """
    if "mesh" not in request.files:
        return jsonify({"error": "No mesh file provided"}), 400

    mesh_file = request.files["mesh"]
    if not mesh_file.filename:
        return jsonify({"error": "Empty filename"}), 400
    if not allowed_file(mesh_file.filename, ALLOWED_MESH_EXTENSIONS):
        return jsonify({
            "error": f"Unsupported mesh format. Allowed: {ALLOWED_MESH_EXTENSIONS}"
        }), 400

    prompt = request.form.get("prompt", "worn metal surface, detailed, high quality")
    texture_size = int(request.form.get("texture_size", 1024))
    use_ai = request.form.get("use_ai", "false").lower() in ("1", "true", "yes")
    ai_steps = int(request.form.get("ai_steps", 20))
    output_format = request.form.get("output_format", "glb").lower()

    # Clamp texture size to valid options
    texture_size = min(max(texture_size, 256), 2048)

    job_id = str(uuid.uuid4())
    job_upload_dir = UPLOAD_DIR / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)

    # Save mesh
    mesh_filename = secure_filename(mesh_file.filename)
    mesh_path = str(job_upload_dir / mesh_filename)
    mesh_file.save(mesh_path)

    # Save reference image if provided
    ref_image_path = None
    if "reference" in request.files:
        ref_file = request.files["reference"]
        if ref_file.filename and allowed_file(ref_file.filename, ALLOWED_IMAGE_EXTENSIONS):
            ref_filename = secure_filename(ref_file.filename)
            ref_image_path = str(job_upload_dir / ref_filename)
            ref_file.save(ref_image_path)

    # Register job
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "progress": 0,
            "stage": "Queued",
            "prompt": prompt,
            "mesh_filename": mesh_filename,
            "result": None,
            "error": None,
        }

    # Launch background thread
    t = threading.Thread(
        target=run_job,
        args=(job_id, mesh_path, ref_image_path, prompt,
              texture_size, use_ai, ai_steps, output_format),
        daemon=True,
    )
    t.start()

    logger.info(f"Job {job_id} started: '{prompt}' | AI={use_ai} | size={texture_size}")
    return jsonify({"job_id": job_id, "status": "queued"}), 202


@app.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@app.route("/api/jobs/<job_id>/download/<file_type>", methods=["GET"])
def download_file(job_id: str, file_type: str):
    """
    Download output files for a completed job.
    file_type: "mesh" | "texture" | "uv_layout"
    """
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Job not ready"}), 404

    result = job.get("result", {})
    path_map = {
        "mesh":      result.get("output_mesh"),
        "texture":   result.get("texture_map"),
        "uv_layout": result.get("uv_layout"),
    }

    file_path = path_map.get(file_type)
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": f"File '{file_type}' not found"}), 404

    return send_file(
        file_path,
        as_attachment=True,
        download_name=os.path.basename(file_path),
    )


@app.route("/api/jobs/<job_id>/preview/<file_type>", methods=["GET"])
def preview_file(job_id: str, file_type: str):
    """Serve files inline (for display in the browser)."""
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job["status"] != "done":
        return jsonify({"error": "Job not ready"}), 404

    result = job.get("result", {})
    path_map = {
        "texture":   result.get("texture_map"),
        "uv_layout": result.get("uv_layout"),
    }

    file_path = path_map.get(file_type)
    if not file_path or not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, mimetype="image/png")


@app.route("/api/jobs", methods=["GET"])
def list_jobs():
    with jobs_lock:
        all_jobs = [
            {k: v for k, v in j.items() if k != "result"}
            for j in jobs.values()
        ]
    return jsonify(all_jobs)


if __name__ == "__main__":
    logger.info("Starting UV & Texture Generator API on port 5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
