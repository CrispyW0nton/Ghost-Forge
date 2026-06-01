"""Legacy v1 HTTP API.

Preserves the original ``/api/*`` surface that the existing Electron
renderer (`src/renderer/src/modules/api.js`) was built against. Mesh
upload + job submission + GLB preview is unchanged so the existing UI
keeps working unmodified during the P10 transition.

New functionality (worker registry, KB, audit, engines, slices, GPU
runtime) is exposed under ``/api/v2/*`` from :mod:`ghostforge_app.v2`.
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from ghostforge_core.operations.mesh_info import MeshInfoRequest
from ghostforge_core.types import JobStatus, TextureRequest, UnwrapRequest

ALLOWED_MESH = {".obj", ".glb", ".gltf", ".stl", ".ply", ".dae", ".fbx"}
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def allowed(filename: str, allowed_set: set[str]) -> bool:
    return Path(filename).suffix.lower() in allowed_set


def _ctx() -> Any:
    return current_app.config["GHOSTFORGE_CTX"]


def create_blueprint() -> Blueprint:
    bp = Blueprint("ghostforge_legacy", __name__)

    @bp.route("/api/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "version": "1.10.0",
                "architecture": "ghostforge_core",
                "capabilities": [
                    "uv",
                    "texture",
                    "mesh-info",
                    "durable-jobs",
                    "asset-manifest-v1",
                    "mcp-ready-core",
                    "uv-bake",
                    "knowledge-base",
                    "worker-registry",
                    "engine-handoff",
                    "game-readiness-audit",
                    "vertical-slice",
                    "gpu-runtime",
                    "real-workers",
                ],
            }
        )

    @bp.route("/api/mesh-info", methods=["POST"])
    def mesh_info():
        ctx = _ctx()
        if "mesh" not in request.files:
            return jsonify({"error": "No mesh file"}), 400

        mesh_file = request.files["mesh"]
        if not mesh_file.filename or not allowed(mesh_file.filename, ALLOWED_MESH):
            return jsonify({"error": "Unsupported format"}), 400

        tmp_name = f"tmp_{uuid.uuid4().hex}_{secure_filename(mesh_file.filename)}"
        tmp_path = ctx.storage.upload_path(tmp_name)
        mesh_file.save(tmp_path)
        try:
            result = ctx.registry.get("mesh_info")(MeshInfoRequest(mesh_path=tmp_path), None, None)
            return jsonify(result.model_dump(mode="json"))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    @bp.route("/api/jobs", methods=["POST"])
    def create_job():
        ctx = _ctx()
        if "mesh" not in request.files:
            return jsonify({"error": "No mesh file"}), 400

        mesh_file = request.files["mesh"]
        if not mesh_file.filename or not allowed(mesh_file.filename, ALLOWED_MESH):
            return jsonify({"error": f"Unsupported format. Allowed: {sorted(ALLOWED_MESH)}"}), 400

        asset_id = uuid.uuid4().hex
        upload_dir = ctx.storage.uploads_dir / asset_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        output_dir = ctx.storage.asset_dir(asset_id)
        output_dir.mkdir(parents=True, exist_ok=True)

        mesh_name = secure_filename(mesh_file.filename)
        mesh_path = upload_dir / mesh_name
        mesh_file.save(mesh_path)

        ref_path = None
        if "reference" in request.files:
            ref_file = request.files["reference"]
            if ref_file.filename and allowed(ref_file.filename, ALLOWED_IMAGE):
                ref_name = secure_filename(ref_file.filename)
                ref_path = upload_dir / ref_name
                ref_file.save(ref_path)

        prompt = request.form.get("prompt", "worn metal surface, detailed, high quality PBR")
        texture_size = min(max(int(request.form.get("texture_size", 1024)), 256), 4096)
        use_ai = request.form.get("use_ai", "false").lower() in ("1", "true", "yes")
        ai_steps = int(request.form.get("ai_steps", 20))
        output_format = request.form.get("output_format", "glb").lower()
        uv_only = request.form.get("uv_only", "false").lower() in ("1", "true", "yes")
        force_unwrap = request.form.get("force_unwrap", "false").lower() in ("1", "true", "yes")

        if uv_only:
            spec = UnwrapRequest(
                input_mesh_path=mesh_path,
                output_dir=output_dir,
                atlas_size=texture_size,
                output_format=output_format,
                force_unwrap=force_unwrap,
                uv_only=True,
            )
            handle = ctx.runner.submit("unwrap_uvs", spec)
        else:
            spec = TextureRequest(
                input_mesh_path=mesh_path,
                output_dir=output_dir,
                prompt=prompt,
                reference_image_path=ref_path,
                texture_size=texture_size,
                use_ai=use_ai,
                ai_steps=ai_steps,
                output_format=output_format,
                force_unwrap=force_unwrap,
            )
            handle = ctx.runner.submit("generate_texture_set", spec)

        return jsonify({"job_id": handle.id, "status": "queued"}), 202

    @bp.route("/api/jobs/<job_id>")
    def get_job(job_id: str):
        ctx = _ctx()
        try:
            return jsonify(_legacy_job_json(ctx.jobs.get(job_id)))
        except KeyError:
            return jsonify({"error": "Not found"}), 404

    @bp.route("/api/jobs")
    def list_jobs():
        ctx = _ctx()
        return jsonify([_legacy_job_json(job, include_result=False) for job in ctx.jobs.list()])

    @bp.route("/api/jobs/<job_id>/download/<file_type>")
    def download_file(job_id: str, file_type: str):
        ctx = _ctx()
        try:
            job = ctx.jobs.get(job_id)
            fp = _result_path(job.result, file_type)
        except KeyError:
            return jsonify({"error": "Job not ready"}), 404

        if job.status != JobStatus.succeeded or fp is None or not fp.exists():
            return jsonify({"error": f"'{file_type}' not found"}), 404
        return send_file(fp, as_attachment=True, download_name=fp.name)

    @bp.route("/api/jobs/<job_id>/preview/<file_type>")
    def preview_file(job_id: str, file_type: str):
        ctx = _ctx()
        try:
            job = ctx.jobs.get(job_id)
            fp = _result_path(job.result, file_type)
        except KeyError:
            return jsonify({"error": "Job not ready"}), 404

        if job.status != JobStatus.succeeded or fp is None or not fp.exists():
            return jsonify({"error": "File not found"}), 404

        if file_type in ("texture", "uv_layout"):
            return send_file(fp, mimetype="image/png")
        if file_type == "mesh_glb":
            return send_file(fp, mimetype="model/gltf-binary", as_attachment=False, download_name=fp.name)
        return send_file(fp)

    @bp.route("/api/outputs/<job_id>/<filename>")
    def serve_output(job_id: str, filename: str):
        ctx = _ctx()
        safe_name = secure_filename(filename)
        try:
            job = ctx.jobs.get(job_id)
        except KeyError:
            return jsonify({"error": "File not found"}), 404

        candidates = []
        if job.result:
            candidates.extend(Path(v) for v in job.result.values() if isinstance(v, str))
        output_path = next((p for p in candidates if p.name == safe_name), None)
        if output_path is None or not output_path.exists():
            return jsonify({"error": "File not found"}), 404

        mime, _ = mimetypes.guess_type(str(output_path))
        if output_path.suffix.lower() == ".glb":
            mime = "model/gltf-binary"
        return send_file(str(output_path), mimetype=mime or "application/octet-stream")

    # Legacy /api/models is now backed by the real ModelRegistry. We
    # serialise to the previous shape (id / name / installed / size_gb)
    # so the legacy UI keeps rendering, with `installed` reflecting
    # actual cache state. New UI calls /api/v2/models for the full
    # ModelStatus surface.
    @bp.route("/api/models")
    def list_models():
        ctx = _ctx()
        out = []
        for artifact in ctx.models.list():
            status = ctx.models.status(artifact.model_id)
            size_gb = (
                round((artifact.total_size_bytes or 0) / 1024**3, 1)
                if artifact.total_size_bytes
                else None
            )
            out.append(
                {
                    "id": artifact.model_id,
                    "name": artifact.model_id.replace("-", "_").upper(),
                    "installed": status.cached,
                    "size_gb": size_gb,
                    "license": artifact.license,
                    "homepage": artifact.homepage,
                }
            )
        return jsonify(out)

    @bp.route("/api/extensions")
    def list_extensions():
        return jsonify([])

    @bp.route("/api/generate", methods=["POST"])
    def generate_mesh_legacy():
        # Legacy mock endpoint kept alive for the existing Generate tab
        # before its rewrite. Returns a 503 with a hint so the UI shows
        # "MODEL_NOT_INSTALLED" instead of a generic error.
        return (
            jsonify(
                {
                    "error": "USE_V2",
                    "message": "Image-to-3D generation now lives under /api/v2/workers/run.",
                }
            ),
            503,
        )

    return bp


def _legacy_job_json(job, include_result: bool = True) -> dict:
    result = job.result or {}
    progress = job.progress.percent if job.progress else 0
    stage = job.progress.stage if job.progress else job.status.value
    status = {
        JobStatus.pending: "queued",
        JobStatus.running: "running",
        JobStatus.succeeded: "done",
        JobStatus.failed: "error",
        JobStatus.cancelled: "error",
    }[job.status]
    payload = {
        "id": job.id,
        "status": status,
        "progress": progress,
        "stage": stage,
        "result": result if include_result else None,
        "error": job.error.message if job.error else None,
    }
    if not include_result:
        payload.pop("result", None)
    return payload


def _result_path(result: dict | None, file_type: str) -> Path | None:
    if not result:
        return None
    key = {
        "mesh": "output_mesh",
        "mesh_glb": "output_mesh",
        "texture": "texture_map",
        "uv_layout": "uv_layout",
    }.get(file_type)
    value = result.get(key) if key else None
    return Path(value) if value else None


__all__ = ["create_blueprint", "ALLOWED_MESH", "ALLOWED_IMAGE", "allowed"]
