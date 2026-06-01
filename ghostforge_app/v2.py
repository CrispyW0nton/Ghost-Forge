"""HTTP API v2 — desktop UI bridge to the new core.

Wraps the same domains the MCP server exposes, but as REST endpoints
that the React renderer can call directly. Each section of this module
mirrors a concern in ``ghostforge_core``:

* ``/api/v2/runtime/*``      — GPU detection, scheduler status, sessions
* ``/api/v2/workers/*``      — worker registry list + probe + run-stub
* ``/api/v2/models/*``       — model registry + cache management
* ``/api/v2/kb/*``           — knowledge base search / list / cite
* ``/api/v2/audit/*``        — audit presets + audit run
* ``/api/v2/engines/*``      — engine adapters list / probe / configure / send
* ``/api/v2/slices/*``       — vertical slice plan / execute / list / delete

Every endpoint returns JSON with ``Content-Type: application/json``.
Errors are returned as ``{"error": <code>, "message": <human>}`` with
4xx/5xx status codes.

The blueprint deliberately avoids any UI-specific massaging: payloads
are the canonical Pydantic models from the core, ``model_dump(mode=
"json")``-ed. The renderer's apiV2 client maps them into UI shapes.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from werkzeug.utils import secure_filename

from ghostforge_core.audit import audit_asset
from ghostforge_core.audit.presets import (
    default_preset,
    unity_preset,
    unreal_preset,
)
from ghostforge_core.engines.base import EngineConfig
from ghostforge_core.kb.schema import ConceptSource
from ghostforge_core.manifest import (
    LicenseSpec,
    ManifestBuilder,
    manifest_exists,
    read_manifest,
)
from ghostforge_core.slice import (
    AssetSpec,
    GameBrief,
    plan_vertical_slice,
    update_plan_assets,
)
from ghostforge_core.slice.executor import execute_vertical_slice
from ghostforge_core.slice.schema import (
    AssetKind,
    EngineTarget,
    GenerationStrategy,
)
from ghostforge_core.workers import (
    Capability,
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from ghostforge_core.workers.session import get_session_registry

from .legacy import ALLOWED_IMAGE, ALLOWED_MESH, allowed


def _ctx() -> Any:
    """Resolve the per-request CoreContext.

    Behaviour:

    * If the app has a ``GHOSTFORGE_TENANTS`` registry configured, the
      tenant id is pulled from the ``X-Ghostforge-Tenant`` request
      header (falling back to env / default), and the corresponding
      :class:`CoreContext` is returned. Tenants are auto-created on
      first request to keep the surface tiny.
    * Otherwise we fall back to the legacy ``GHOSTFORGE_CTX``
      singleton — exactly what tests and the existing desktop app
      have always seen.
    """

    tenants = current_app.config.get("GHOSTFORGE_TENANTS")
    if tenants is not None:
        from ghostforge_core.tenancy import (
            TenantNotAllowed,
            tenant_id_from_request,
        )
        import os

        try:
            tenant_id = tenant_id_from_request(
                headers=request.headers,
                env=os.environ,
            )
        except TenantNotAllowed as exc:
            from werkzeug.exceptions import BadRequest

            raise BadRequest(str(exc))
        return tenants.resolve(tenant_id)
    return current_app.config["GHOSTFORGE_CTX"]


def _err(code: str, message: str, status: int = 400):
    return jsonify({"error": code, "message": message}), status


def _save_upload(file_storage, *, allowed_set: set[str], dest_dir: Path) -> Path | None:
    if not file_storage or not file_storage.filename:
        return None
    if not allowed(file_storage.filename, allowed_set):
        raise ValueError(f"unsupported extension; allowed: {sorted(allowed_set)}")
    name = secure_filename(file_storage.filename)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / name
    file_storage.save(path)
    return path


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------


def create_blueprint() -> Blueprint:
    bp = Blueprint("ghostforge_v2", __name__, url_prefix="/api/v2")

    # ------------------------------------------------------------------
    # Runtime: GPU + scheduler + sessions
    # ------------------------------------------------------------------

    @bp.route("/runtime/gpus")
    def runtime_gpus():
        from ghostforge_core.gpu import detect_gpus

        ctx = _ctx()
        force = request.args.get("refresh", "false").lower() in ("1", "true", "yes")
        status = detect_gpus(force=force)
        return jsonify(
            {
                "scheduler_enabled": ctx.scheduler is not None,
                "backend": status.backend,
                "cpu_only": status.cpu_only,
                "notes": list(status.notes),
                "gpus": [g.model_dump(mode="json") for g in status.gpus],
            }
        )

    @bp.route("/runtime/scheduler")
    def runtime_scheduler():
        ctx = _ctx()
        if ctx.scheduler is None:
            return jsonify({"enabled": False})
        return jsonify({"enabled": True, **ctx.scheduler.status()})

    @bp.route("/runtime/sessions")
    def runtime_sessions():
        return jsonify(get_session_registry().status())

    @bp.route("/runtime/sessions/free", methods=["POST"])
    def runtime_sessions_free():
        body = request.get_json(silent=True) or {}
        name = body.get("name")
        force = bool(body.get("force", False))
        idle = body.get("idle_for_seconds")
        if idle is not None:
            freed = get_session_registry().free_idle(idle_for_seconds=float(idle))
        else:
            freed = get_session_registry().free(name, force=force)
        return jsonify({"freed": freed, "name": name, "force": force})

    # ------------------------------------------------------------------
    # Workers
    # ------------------------------------------------------------------

    @bp.route("/workers")
    def workers_list():
        ctx = _ctx()
        out = []
        for worker in ctx.workers.all():
            descriptor = ctx.workers.describe(worker)
            try:
                probe = worker.probe()
            except Exception as exc:  # pragma: no cover — defensive
                probe = None
                probe_error = str(exc)
            else:
                probe_error = None
            out.append(
                {
                    "descriptor": descriptor.model_dump(mode="json"),
                    "probe": probe.model_dump(mode="json") if probe else None,
                    "probe_error": probe_error,
                }
            )
        return jsonify(out)

    @bp.route("/workers/<worker_name>/probe")
    def workers_probe(worker_name: str):
        ctx = _ctx()
        try:
            worker = ctx.workers.get(worker_name)
        except Exception:
            return _err("NOT_FOUND", f"worker {worker_name!r} not registered", 404)
        return jsonify(worker.probe().model_dump(mode="json"))

    @bp.route("/workers/run", methods=["POST"])
    def workers_run():
        """Submit a worker job synchronously through the operations layer.

        For long-running real workers the renderer should still go
        through the durable job system (``/api/jobs`` legacy or v2
        slice runs), but this endpoint gives the UI a fast path for
        stub-driven smoke tests and tiny CPU-friendly prompts.
        """

        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        capability = body.get("capability")
        spec_data = body.get("spec") or {}
        if not capability:
            return _err("BAD_REQUEST", "missing 'capability'")

        try:
            cap = Capability(capability)
        except ValueError:
            return _err(
                "BAD_REQUEST",
                f"unknown capability {capability!r}; expected one of "
                f"{[c.value for c in Capability]}",
            )
        request_classes = {
            Capability.image_to_3d: ImageTo3DRequest,
            Capability.text_to_3d: TextTo3DRequest,
            Capability.texture_mesh: TextureMeshRequest,
            Capability.refine_mesh: RefineMeshRequest,
        }
        op_kinds = {
            Capability.image_to_3d: "image_to_3d",
            Capability.text_to_3d: "text_to_3d",
            Capability.texture_mesh: "texture_mesh",
            Capability.refine_mesh: "refine_mesh",
        }
        spec_cls = request_classes[cap]
        try:
            spec = spec_cls(**spec_data)
        except Exception as exc:
            return _err("BAD_REQUEST", f"invalid spec: {exc}")

        # Submit via the durable runner so the UI can poll for status.
        handle = ctx.runner.submit(op_kinds[cap], spec)
        return jsonify({"job_id": handle.id, "status": "queued"}), 202

    # ------------------------------------------------------------------
    # Models
    # ------------------------------------------------------------------

    @bp.route("/models")
    def models_list():
        ctx = _ctx()
        out = []
        for artifact in ctx.models.list():
            status = ctx.models.status(artifact.model_id)
            out.append(
                {
                    "artifact": artifact.model_dump(mode="json"),
                    "status": status.model_dump(mode="json"),
                }
            )
        return jsonify(out)

    @bp.route("/models/<model_id>/status")
    def models_status(model_id: str):
        ctx = _ctx()
        try:
            return jsonify(ctx.models.status(model_id).model_dump(mode="json"))
        except Exception:
            return _err("NOT_FOUND", f"unknown model {model_id!r}", 404)

    @bp.route("/models/<model_id>/download", methods=["POST"])
    def models_download(model_id: str):
        ctx = _ctx()
        try:
            status = ctx.models.download(model_id)
        except Exception as exc:
            return _err("DOWNLOAD_FAILED", str(exc), 500)
        return jsonify(status.model_dump(mode="json"))

    @bp.route("/models/<model_id>/clear", methods=["POST"])
    def models_clear(model_id: str):
        ctx = _ctx()
        try:
            removed = ctx.models.clear(model_id)
        except Exception as exc:
            return _err("CLEAR_FAILED", str(exc), 500)
        return jsonify({"cleared": removed, "model_id": model_id})

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    @bp.route("/kb/concepts")
    def kb_list():
        ctx = _ctx()
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))
        sources = request.args.getlist("source")
        sources_arg = [ConceptSource(s) for s in sources] if sources else None
        entries = ctx.kb.list(limit=limit, offset=offset, sources=sources_arg)
        return jsonify([e.model_dump(mode="json") for e in entries])

    @bp.route("/kb/search", methods=["POST"])
    def kb_search():
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        query = body.get("query")
        k = int(body.get("k", 5))
        sources_raw = body.get("sources") or []
        tags = body.get("tags")
        sources = [ConceptSource(s) for s in sources_raw] if sources_raw else None
        if not query:
            return _err("BAD_REQUEST", "missing 'query'")
        results = ctx.kb.search_text(query, k=k, sources=sources, tags=tags)
        return jsonify([r.model_dump(mode="json") for r in results])

    @bp.route("/kb/ingest/local", methods=["POST"])
    def kb_ingest_local():
        from ghostforge_core.kb.ingest import ingest_local_image

        ctx = _ctx()
        if "image" not in request.files:
            return _err("BAD_REQUEST", "no image file uploaded")
        image_file = request.files["image"]
        license_str = request.form.get("license")
        if not license_str:
            return _err(
                "LICENSE_REQUIRED",
                "every ingested concept must declare a license",
            )

        upload_dir = ctx.storage.uploads_dir / f"kb_{uuid.uuid4().hex}"
        try:
            saved = _save_upload(image_file, allowed_set=ALLOWED_IMAGE, dest_dir=upload_dir)
        except ValueError as exc:
            return _err("BAD_REQUEST", str(exc))
        if saved is None:
            return _err("BAD_REQUEST", "no image saved")

        title = request.form.get("title") or saved.stem
        tags_raw = request.form.get("tags")
        tags = [t.strip() for t in tags_raw.split(",")] if tags_raw else []
        attribution = request.form.get("attribution")
        try:
            entry = ingest_local_image(
                kb=ctx.kb,
                image_path=saved,
                title=title,
                license=license_str,
                attribution=attribution,
                tags=tags,
            )
        except Exception as exc:
            return _err("INGEST_FAILED", str(exc), 500)
        return jsonify(entry.model_dump(mode="json"))

    @bp.route("/kb/cite", methods=["POST"])
    def kb_cite():
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        concept_ids = body.get("concept_ids") or []
        note = body.get("note")
        if not asset_dir or not concept_ids:
            return _err("BAD_REQUEST", "asset_dir and concept_ids required")

        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)
        builder = ManifestBuilder.for_dir(path)
        for cid in concept_ids:
            citation = ctx.kb.make_citation(cid, note=note)
            builder.add_concept_citation(citation)
        manifest, _ = builder.write()
        return jsonify(manifest.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    @bp.route("/audit/presets")
    def audit_presets():
        return jsonify(
            {
                name: factory().model_dump(mode="json")
                for name, factory in _PRESETS.items()
            }
        )

    @bp.route("/audit/run", methods=["POST"])
    def audit_run():
        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        preset_name = body.get("preset", "default")
        run_gltf = bool(body.get("run_gltf_validator", False))
        if not asset_dir:
            return _err("BAD_REQUEST", "asset_dir required")

        preset_factory = _PRESETS.get(preset_name)
        if preset_factory is None:
            return _err(
                "BAD_REQUEST",
                f"unknown preset {preset_name!r}; expected {sorted(_PRESETS)}",
            )

        try:
            report = audit_asset(
                Path(asset_dir),
                preset=preset_factory(),
                run_gltf_validator=run_gltf,
            )
        except FileNotFoundError as exc:
            return _err("NOT_FOUND", str(exc), 404)
        except Exception as exc:
            return _err("AUDIT_FAILED", str(exc), 500)
        return jsonify(report.model_dump(mode="json"))

    @bp.route("/audit/manifest")
    def audit_manifest():
        asset_dir = request.args.get("asset_dir")
        if not asset_dir:
            return _err("BAD_REQUEST", "asset_dir required")
        path = Path(asset_dir)
        if not manifest_exists(path):
            return _err("NOT_FOUND", "no manifest", 404)
        return jsonify(read_manifest(path).model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Engines
    # ------------------------------------------------------------------

    @bp.route("/engines")
    def engines_list():
        ctx = _ctx()
        out = []
        for adapter in ctx.engines.all():
            try:
                probe = adapter.probe().model_dump(mode="json")
            except Exception as exc:  # pragma: no cover — defensive
                probe = {"error": str(exc)}
            out.append(
                {
                    "name": adapter.name,
                    "default_audit_preset": getattr(
                        adapter, "default_audit_preset", "default"
                    ),
                    "probe": probe,
                }
            )
        return jsonify(out)

    @bp.route("/engines/<name>/configure", methods=["POST"])
    def engines_configure(name: str):
        ctx = _ctx()
        try:
            adapter = ctx.engines.get(name)
        except Exception:
            return _err("NOT_FOUND", f"unknown engine {name!r}", 404)
        body = request.get_json(silent=True) or {}
        # Force the config name to match the adapter so renderer doesn't
        # accidentally cross-wire Unity → Unreal.
        body["name"] = name
        # Default transport so older clients don't trip on missing field.
        body.setdefault("transport", "stdio")
        try:
            config = EngineConfig(**body)
        except Exception as exc:
            return _err("BAD_REQUEST", f"invalid EngineConfig: {exc}")
        try:
            adapter.configure(config)
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        return jsonify(adapter.probe().model_dump(mode="json"))

    @bp.route("/engines/<name>/send", methods=["POST"])
    def engines_send(name: str):
        ctx = _ctx()
        try:
            adapter = ctx.engines.get(name)
        except Exception:
            return _err("NOT_FOUND", f"unknown engine {name!r}", 404)
        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        if not asset_dir:
            return _err("BAD_REQUEST", "asset_dir required")

        kwargs: dict[str, Any] = {}
        if "target_path" in body and body["target_path"]:
            kwargs["target_path"] = body["target_path"]
        if "dry_run" in body:
            kwargs["dry_run"] = bool(body["dry_run"])
        if "audit" in body:
            kwargs["audit"] = bool(body["audit"])
        if "audit_preset" in body and body["audit_preset"]:
            kwargs["audit_preset"] = body["audit_preset"]
        if "force" in body:
            kwargs["force"] = bool(body["force"])

        try:
            result = adapter.send_asset(Path(asset_dir), **kwargs)
        except Exception as exc:
            from ghostforge_core.engines import (
                EngineAuditFailed,
                EngineHandoffError,
                EngineNotConfigured,
            )

            if isinstance(exc, EngineNotConfigured):
                return _err("NOT_CONFIGURED", str(exc), 409)
            if isinstance(exc, EngineAuditFailed):
                # Surface the audit report so the UI can show issues.
                report = getattr(exc, "report", None)
                payload = {
                    "error": "AUDIT_FAILED",
                    "message": str(exc),
                    "audit": report.model_dump(mode="json") if report else None,
                }
                return jsonify(payload), 422
            if isinstance(exc, EngineHandoffError):
                return _err("HANDOFF_FAILED", str(exc), 500)
            return _err("HANDOFF_FAILED", str(exc), 500)
        return jsonify(result.model_dump(mode="json"))

    @bp.route("/engines/<name>/export-bridge", methods=["POST"])
    def engines_export_bridge(name: str):
        """Create an offline bridge package for Unity/Unreal MCP importers."""

        if name not in {"unity", "unreal"}:
            return _err("NOT_FOUND", f"unknown bridge target {name!r}", 404)
        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        if not asset_dir:
            return _err("BAD_REQUEST", "asset_dir required")
        try:
            from ghostforge_core.export_bridge import create_export_bridge_package

            package, path = create_export_bridge_package(
                asset_dir,
                target_engine=name,
                target_path=body.get("target_path"),
                bridge_dir=body.get("bridge_dir"),
                recommended_tool=body.get("recommended_tool", "import_asset"),
                notes=body.get("notes"),
            )
        except Exception as exc:
            from ghostforge_core.export_bridge import ExportBridgeError

            if isinstance(exc, ExportBridgeError):
                return _err("BRIDGE_EXPORT_FAILED", str(exc), 400)
            return _err("BRIDGE_EXPORT_FAILED", str(exc), 500)

        return jsonify(
            {
                "package": package.model_dump(mode="json"),
                "package_path": str(path),
                "direct_engine_call": False,
            }
        )

    # ------------------------------------------------------------------
    # Vertical slices
    # ------------------------------------------------------------------

    @bp.route("/slices")
    def slices_list():
        ctx = _ctx()
        return jsonify([s.model_dump(mode="json") for s in ctx.slices.list_summaries()])

    @bp.route("/slices/<slice_id>")
    def slices_get(slice_id: str):
        ctx = _ctx()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except Exception:
            return _err("NOT_FOUND", f"slice {slice_id!r} not found", 404)
        run = ctx.slices.load_run(slice_id)
        return jsonify(
            {
                "plan": plan.model_dump(mode="json"),
                "run": run.model_dump(mode="json") if run else None,
            }
        )

    @bp.route("/slices", methods=["POST"])
    def slices_create():
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            brief = _coerce_brief(body.get("brief") or {})
            assets = _coerce_assets(body.get("assets") or [])
            plan = plan_vertical_slice(
                store=ctx.slices,
                brief=brief,
                assets=assets,
                slice_id=body.get("slice_id"),
                fail_fast=bool(body.get("fail_fast", False)),
                skip_audit=bool(body.get("skip_audit", False)),
                skip_handoff=bool(body.get("skip_handoff", False)),
            )
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        return jsonify(plan.model_dump(mode="json")), 201

    @bp.route("/slices/<slice_id>/assets", methods=["POST"])
    def slices_update_assets(slice_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            assets = _coerce_assets(body.get("assets") or [])
            plan = update_plan_assets(ctx.slices, slice_id, assets)
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        return jsonify(plan.model_dump(mode="json"))

    @bp.route("/slices/<slice_id>", methods=["DELETE"])
    def slices_delete(slice_id: str):
        ctx = _ctx()
        try:
            ctx.slices.delete(slice_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        return jsonify({"deleted": slice_id})

    @bp.route("/slices/<slice_id>/execute", methods=["POST"])
    def slices_execute(slice_id: str):
        ctx = _ctx()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except Exception:
            return _err("NOT_FOUND", f"slice {slice_id!r} not found", 404)
        try:
            run = execute_vertical_slice(
                plan,
                store=ctx.slices,
                kb=ctx.kb,
                engines=ctx.engines,
            )
        except Exception as exc:
            return _err("EXECUTION_FAILED", str(exc), 500)
        return jsonify(run.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Retarget: cross-engine linting + auto-retarget planner (P12)
    # ------------------------------------------------------------------

    @bp.route("/retarget/profiles")
    def retarget_profiles():
        from ghostforge_core.retarget import list_profiles

        return jsonify(
            {"profiles": [p.model_dump(mode="json") for p in list_profiles()]}
        )

    @bp.route("/retarget/lint", methods=["POST"])
    def retarget_lint():
        from ghostforge_core.audit import audit_asset
        from ghostforge_core.retarget.presets import (
            retarget_rules_for_preset,
            unity_retarget_preset,
            unreal_retarget_preset,
        )

        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        target = body.get("target_engine")
        if not asset_dir:
            return _err("BAD_REQUEST", "'asset_dir' is required")
        if target not in {"unity", "unreal"}:
            return _err(
                "BAD_REQUEST",
                "'target_engine' must be 'unity' or 'unreal'",
            )
        preset_factory = (
            unity_retarget_preset if target == "unity" else unreal_retarget_preset
        )
        try:
            report = audit_asset(
                Path(asset_dir),
                preset=preset_factory(),
                rules=retarget_rules_for_preset(target),
                run_gltf_validator=bool(body.get("run_gltf_validator", False)),
                persist=bool(body.get("persist", False)),
            )
        except FileNotFoundError as exc:
            return _err("NOT_FOUND", str(exc), 404)
        except Exception as exc:
            return _err("LINT_FAILED", str(exc), 500)
        return jsonify(report.model_dump(mode="json"))

    @bp.route("/retarget/plan", methods=["POST"])
    def retarget_plan():
        from ghostforge_core.retarget import plan_retarget_graph_for_asset

        body = request.get_json(silent=True) or {}
        asset_dir = body.get("asset_dir")
        target = body.get("target_engine")
        if not asset_dir:
            return _err("BAD_REQUEST", "'asset_dir' is required")
        if target not in {"unity", "unreal"}:
            return _err(
                "BAD_REQUEST",
                "'target_engine' must be 'unity' or 'unreal'",
            )
        try:
            graph, report = plan_retarget_graph_for_asset(
                asset_dir,
                target_engine=target,
                base_name=body.get("base_name"),
                graph_id=body.get("graph_id"),
                graph_name=body.get("graph_name"),
                output_path=body.get("output_path"),
                run_gltf_validator=bool(body.get("run_gltf_validator", False)),
            )
        except FileNotFoundError as exc:
            return _err("NOT_FOUND", str(exc), 404)
        except ValueError as exc:
            return _err("BAD_REQUEST", str(exc))
        except Exception as exc:
            return _err("PLAN_FAILED", str(exc), 500)

        if bool(body.get("persist_graph", False)):
            ctx = _ctx()
            ctx.graphs.save(graph)

        return jsonify(
            {
                "graph": graph.model_dump(mode="json"),
                "report": report.model_dump(mode="json"),
            }
        )

    # ------------------------------------------------------------------
    # Authoring: operations + edit graphs
    # ------------------------------------------------------------------

    @bp.route("/operations")
    def operations_list():
        ctx = _ctx()
        return jsonify(
            {
                "operations": [
                    d.model_dump(mode="json") for d in ctx.operations.descriptors()
                ]
            }
        )

    @bp.route("/graphs", methods=["GET"])
    def graphs_list():
        ctx = _ctx()
        return jsonify(
            {"graphs": [g.model_dump(mode="json") for g in ctx.graphs.list()]}
        )

    @bp.route("/graphs", methods=["POST"])
    def graphs_create():
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            graph = _build_graph(ctx, body, new_id=True)
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        ctx.graphs.save(graph)
        return jsonify(graph.model_dump(mode="json")), 201

    @bp.route("/graphs/<graph_id>", methods=["GET"])
    def graphs_get(graph_id: str):
        ctx = _ctx()
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        evaluation = ctx.graphs.load_evaluation(graph_id)
        payload = {"graph": graph.model_dump(mode="json")}
        if evaluation is not None:
            payload["evaluation"] = evaluation.model_dump(mode="json")
        return jsonify(payload)

    @bp.route("/graphs/<graph_id>", methods=["PUT"])
    def graphs_update(graph_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            existing = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        body.setdefault("graph_id", graph_id)
        try:
            updated = _merge_graph_update(existing, body)
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        ctx.graphs.save(updated)
        return jsonify(updated.model_dump(mode="json"))

    @bp.route("/graphs/<graph_id>", methods=["DELETE"])
    def graphs_delete(graph_id: str):
        ctx = _ctx()
        try:
            ctx.graphs.delete(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        return jsonify({"deleted": graph_id})

    @bp.route("/graphs/<graph_id>/nodes", methods=["POST"])
    def graphs_append_node(graph_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        try:
            node = _coerce_node(ctx, body, allow_generated_id=True)
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        nodes = list(graph.nodes) + [node]
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return jsonify(graph.model_dump(mode="json")), 201

    @bp.route("/graphs/<graph_id>/nodes/<node_id>", methods=["PUT"])
    def graphs_update_node(graph_id: str, node_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        nodes = list(graph.nodes)
        idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
        if idx is None:
            return _err("NOT_FOUND", f"node {node_id!r} not in graph", 404)
        try:
            update = nodes[idx].model_copy(update=_node_update_fields(body))
        except Exception as exc:
            return _err("BAD_REQUEST", str(exc))
        nodes[idx] = update
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return jsonify(graph.model_dump(mode="json"))

    @bp.route("/graphs/<graph_id>/nodes/<node_id>", methods=["DELETE"])
    def graphs_remove_node(graph_id: str, node_id: str):
        ctx = _ctx()
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        nodes = [n for n in graph.nodes if n.id != node_id]
        if len(nodes) == len(graph.nodes):
            return _err("NOT_FOUND", f"node {node_id!r} not in graph", 404)
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return jsonify(graph.model_dump(mode="json"))

    @bp.route("/graphs/<graph_id>/reorder", methods=["POST"])
    def graphs_reorder_nodes(graph_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        order = body.get("order")
        if not isinstance(order, list) or not all(isinstance(o, str) for o in order):
            return _err("BAD_REQUEST", "'order' must be a list of node ids")
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        by_id = {n.id: n for n in graph.nodes}
        if set(order) != set(by_id) or len(order) != len(by_id):
            return _err("BAD_REQUEST", "order must contain every existing node id exactly once")
        nodes = [by_id[i] for i in order]
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return jsonify(graph.model_dump(mode="json"))

    @bp.route("/graphs/<graph_id>/evaluate", methods=["POST"])
    def graphs_evaluate(graph_id: str):
        ctx = _ctx()
        body = request.get_json(silent=True) or {}
        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)
        from ghostforge_core.authoring import evaluate_graph
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        try:
            result, _ = evaluate_graph(
                graph,
                registry=ctx.operations,
                input_path=body.get("input_path"),
                output_path=body.get("output_path"),
                output_format=body.get("output_format", "glb"),
                fail_fast=bool(body.get("fail_fast", False)),
            )
        except Exception as exc:
            return _err("EVAL_FAILED", str(exc), 500)
        ctx.graphs.save_evaluation(result)

        # If the caller asked us to update a manifest with bake side-
        # effects (collision, lightmap), do it now and pin the resulting
        # path into the response so the UI can render it.
        manifest_dir = body.get("manifest_dir") or body.get("update_manifest_dir")
        side_effects = (result.metadata or {}).get("side_effects") or []
        manifest_payload: dict[str, Any] | None = None
        if manifest_dir and side_effects:
            try:
                manifest = apply_side_effects_to_manifest(
                    manifest_dir,
                    side_effects,
                    asset_id=body.get("asset_id"),
                )
                if manifest is not None:
                    manifest_payload = manifest.model_dump(mode="json")
            except Exception as exc:  # surface the failure but don't drop result
                manifest_payload = {"error": str(exc)}

        response = result.model_dump(mode="json")
        if manifest_payload is not None:
            response["manifest"] = manifest_payload
        return jsonify(response)

    @bp.route("/graphs/<graph_id>/evaluate/stream", methods=["GET", "POST"])
    def graphs_evaluate_stream(graph_id: str):
        """Server-Sent Events stream of per-step evaluation events.

        GET passes parameters via query string for use with EventSource;
        POST accepts the same JSON body as the buffered /evaluate route.
        Each event is emitted as ``data: {json}\\n\\n``.
        """

        ctx = _ctx()
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
        else:
            body = {
                key: request.args.get(key)
                for key in ("input_path", "output_path", "output_format", "manifest_dir", "asset_id")
                if request.args.get(key) is not None
            }
            body["fail_fast"] = request.args.get("fail_fast", "").lower() in {"1", "true", "yes"}

        try:
            graph = ctx.graphs.load(graph_id)
        except Exception as exc:
            return _err("NOT_FOUND", str(exc), 404)

        from ghostforge_core.authoring import evaluate_graph_streaming
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        manifest_dir = body.get("manifest_dir") or body.get("update_manifest_dir")
        asset_id = body.get("asset_id")

        @stream_with_context
        def generate():
            last_event: dict[str, Any] | None = None
            try:
                gen = evaluate_graph_streaming(
                    graph,
                    registry=ctx.operations,
                    input_path=body.get("input_path"),
                    output_path=body.get("output_path"),
                    output_format=body.get("output_format", "glb"),
                    fail_fast=bool(body.get("fail_fast", False)),
                )
                for event in gen:
                    last_event = event
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                # Best-effort manifest write after the stream ends.
                if (
                    manifest_dir
                    and last_event is not None
                    and last_event.get("event") == "completed"
                ):
                    side_effects = (
                        last_event.get("result", {}).get("metadata", {}).get("side_effects")
                        or []
                    )
                    if side_effects:
                        try:
                            manifest = apply_side_effects_to_manifest(
                                manifest_dir, side_effects, asset_id=asset_id
                            )
                            payload = {
                                "event": "manifest",
                                "manifest": manifest.model_dump(mode="json")
                                if manifest is not None
                                else None,
                            }
                            yield f"data: {json.dumps(payload, default=str)}\n\n"
                        except Exception as exc:
                            yield f"data: {json.dumps({'event': 'manifest_error', 'error': str(exc)})}\n\n"
                # Persist the final result so the buffered API stays consistent.
                if last_event is not None and last_event.get("event") == "completed":
                    from ghostforge_core.authoring.schema import EvaluationResult

                    try:
                        final = EvaluationResult.model_validate(last_event["result"])
                        ctx.graphs.save_evaluation(final)
                    except Exception:
                        pass
            except Exception as exc:
                yield f"data: {json.dumps({'event': 'error', 'error': str(exc)})}\n\n"

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return bp


# ---------------------------------------------------------------------------
# Coercion helpers (mirror the MCP tool helpers)
# ---------------------------------------------------------------------------


_PRESETS = {
    "default": default_preset,
    "unity": unity_preset,
    "unreal": unreal_preset,
}


def _coerce_brief(payload: dict[str, Any]) -> GameBrief:
    if "license" in payload and isinstance(payload["license"], dict):
        payload = {**payload, "license": LicenseSpec(**payload["license"])}
    return GameBrief(**payload)


def _coerce_assets(items: list[dict[str, Any]]) -> list[AssetSpec]:
    out: list[AssetSpec] = []
    for entry in items:
        data = dict(entry)
        if "license" in data and isinstance(data["license"], dict):
            data["license"] = LicenseSpec(**data["license"])
        if "kind" in data and isinstance(data["kind"], str):
            data["kind"] = AssetKind(data["kind"])
        if "strategy" in data and isinstance(data["strategy"], str):
            data["strategy"] = GenerationStrategy(data["strategy"])
        if "target_engine" in data and isinstance(data["target_engine"], str):
            data["target_engine"] = EngineTarget(data["target_engine"])
        if "reference_image_path" in data and isinstance(data["reference_image_path"], str):
            data["reference_image_path"] = Path(data["reference_image_path"])
        if "input_mesh_path" in data and isinstance(data["input_mesh_path"], str):
            data["input_mesh_path"] = Path(data["input_mesh_path"])
        out.append(AssetSpec(**data))
    return out


def _coerce_node(ctx: Any, payload: dict[str, Any], *, allow_generated_id: bool):
    from ghostforge_core.authoring import OperationNode

    data = dict(payload)
    kind = data.get("kind")
    if not kind or not isinstance(kind, str):
        raise ValueError("'kind' is required")
    if not ctx.operations.has(kind):
        raise ValueError(f"unknown operation kind {kind!r}")
    if "id" not in data or not data["id"]:
        if not allow_generated_id:
            raise ValueError("'id' is required")
        data["id"] = f"node-{uuid.uuid4().hex[:10]}"
    return OperationNode(**data)


def _node_update_fields(payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {"label", "enabled", "params", "notes", "kind"}
    return {k: v for k, v in payload.items() if k in allowed}


def _build_graph(ctx: Any, payload: dict[str, Any], *, new_id: bool):
    from ghostforge_core.authoring import EditGraph

    data = dict(payload)
    if new_id or not data.get("graph_id"):
        data["graph_id"] = ctx.graphs.make_id()
    nodes_payload = data.pop("nodes", []) or []
    nodes = [_coerce_node(ctx, n, allow_generated_id=True) for n in nodes_payload]
    graph = EditGraph(**data)
    if nodes:
        graph = graph.with_nodes(nodes)
    return graph


def _merge_graph_update(existing: Any, payload: dict[str, Any]):
    update_fields: dict[str, Any] = {}
    for key in (
        "name",
        "description",
        "asset_id",
        "base_asset_path",
        "output_path",
    ):
        if key in payload:
            update_fields[key] = payload[key]
    return existing.model_copy(update=update_fields)


__all__ = ["create_blueprint"]
