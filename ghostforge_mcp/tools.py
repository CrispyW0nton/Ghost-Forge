"""MCP tool surface for GhostForge.

Each tool is a thin wrapper over a `ghostforge_core` operation. Argument
schemas are derived from the function signatures by FastMCP, but the actual
field defaults, ranges, and types come from the Pydantic models in
:mod:`ghostforge_core.types`. Building each request through the matching
Pydantic model keeps that file the single source of truth for validation,
JSON Schema export, and runtime coercion.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

# Importing tools.py implies the MCP server is being built, so the optional
# `mcp` dependency must already be installed. Importing `Context` at module
# scope keeps it visible to FastMCP's runtime `get_type_hints` resolution.
from mcp.server.fastmcp import Context, FastMCP

from ghostforge_core.audit import (
    audit_asset as audit_asset_op,
    list_presets as list_audit_presets_op,
)
from ghostforge_core.benchmarks import (
    BenchmarkRequest,
    make_benchmark_id,
    run_benchmark as run_benchmark_op,
)
from ghostforge_core.engines import EngineConfig, EngineHandoffError
from ghostforge_core.models import ModelDownloadError, ModelNotFound
from ghostforge_core.kb.ingest import (
    ingest_local_image,
    ingest_openverse,
    ingest_url,
)
from ghostforge_core.kb.schema import ConceptSource
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    manifest_exists,
    read_manifest,
)
from ghostforge_core.operations import mesh_info as mesh_info_op
from ghostforge_core.slice import (
    AssetKind,
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    SliceNotFound,
    plan_vertical_slice,
    update_plan_assets,
)
from ghostforge_core.slice import execute_vertical_slice as execute_slice_op
from ghostforge_core.types import (
    AuditAssetRequest,
    ExecuteVerticalSliceRequest,
    JobHandle,
    JobStatus,
    SendToEngineRequest,
    TextureRequest,
    UnwrapRequest,
)
from ghostforge_core.validation import validate_mesh
from ghostforge_core.workers import (
    Capability,
    ImageTo3DRequest,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
)
from ghostforge_core.workers.session import get_session_registry

from .server import get_context


_TERMINAL_STATUSES = {JobStatus.succeeded, JobStatus.failed, JobStatus.cancelled}


def _handle_to_dict(handle: JobHandle) -> dict[str, Any]:
    return handle.model_dump(mode="json")


def _resolve_output_dir(output_dir: str | None) -> Path:
    if output_dir:
        path = Path(output_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path
    return get_context().storage.new_asset_dir()


def register_tools(server: FastMCP) -> None:
    """Attach all GhostForge tools to a FastMCP server instance."""

    @server.tool(description="Return MCP server health, data root, and registered job kinds.")
    def health() -> dict[str, Any]:
        ctx = get_context()
        return {
            "status": "ok",
            "name": "ghostforge",
            "version": "0.1.0",
            "data_root": str(ctx.storage.root),
            "dispatch_jobs": ctx.config.dispatch_jobs,
            "max_workers": ctx.config.max_workers,
            "kinds": [
                descriptor.model_dump(mode="json")
                for descriptor in ctx.registry.list()
            ],
        }

    @server.tool(description="List job kinds the server can dispatch and their capabilities.")
    def list_capabilities() -> list[dict[str, Any]]:
        return [d.model_dump(mode="json") for d in get_context().registry.list()]

    @server.tool(
        description=(
            "Inspect a mesh file (OBJ, GLB, GLTF, STL, PLY, FBX where supported). "
            "Returns vertex/face counts, watertightness, bounds, and size."
        )
    )
    def mesh_info(mesh_path: str) -> dict[str, Any]:
        request = mesh_info_op.MeshInfoRequest(mesh_path=Path(mesh_path))
        info = mesh_info_op.run(request)
        return info.model_dump(mode="json")

    @server.tool(
        description=(
            "Run lightweight validation on a mesh file. Returns errors, warnings, "
            "and info issues without producing artifacts."
        )
    )
    def validate_mesh_tool(mesh_path: str) -> dict[str, Any]:
        return validate_mesh(Path(mesh_path)).model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a UV unwrap job (xatlas). Returns a job handle whose status "
            "transitions through pending -> running -> succeeded|failed. Poll "
            "with `get_job` or stream progress via `wait_for_job`."
        )
    )
    def submit_unwrap(
        input_mesh_path: str,
        output_dir: str | None = None,
        atlas_size: int = 1024,
        padding: int = 2,
        output_format: str = "glb",
        force_unwrap: bool = False,
        uv_only: bool = True,
    ) -> dict[str, Any]:
        spec = UnwrapRequest(
            input_mesh_path=Path(input_mesh_path),
            output_dir=_resolve_output_dir(output_dir),
            atlas_size=atlas_size,
            padding=padding,
            output_format=output_format,
            force_unwrap=force_unwrap,
            uv_only=uv_only,
        )
        handle = get_context().runner.submit("unwrap_uvs", spec)
        return _handle_to_dict(handle)

    @server.tool(
        description=(
            "Submit a texture generation job (procedural or AI-driven). Returns "
            "a job handle. Set `use_ai=True` to drive Stable Diffusion when the "
            "AI extras are installed."
        )
    )
    def submit_texture(
        input_mesh_path: str,
        prompt: str = "worn metal surface, detailed, high quality PBR",
        output_dir: str | None = None,
        reference_image_path: str | None = None,
        texture_size: int = 1024,
        use_ai: bool = False,
        ai_steps: int = 20,
        output_format: str = "glb",
        force_unwrap: bool = False,
    ) -> dict[str, Any]:
        spec = TextureRequest(
            input_mesh_path=Path(input_mesh_path),
            output_dir=_resolve_output_dir(output_dir),
            prompt=prompt,
            reference_image_path=Path(reference_image_path) if reference_image_path else None,
            texture_size=texture_size,
            use_ai=use_ai,
            ai_steps=ai_steps,
            output_format=output_format,
            force_unwrap=force_unwrap,
        )
        handle = get_context().runner.submit("generate_texture_set", spec)
        return _handle_to_dict(handle)

    @server.tool(description="Fetch the current state of a job by id.")
    def get_job(job_id: str) -> dict[str, Any]:
        return _handle_to_dict(get_context().jobs.get(job_id))

    @server.tool(description="List jobs filtered by status and/or kind.")
    def list_jobs(
        status: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        handles = get_context().jobs.list(
            status=status,
            kind=kind,
            limit=limit,
            offset=offset,
        )
        return [_handle_to_dict(h) for h in handles]

    @server.tool(
        description=(
            "Request cancellation of a running job. Returns the latest handle. "
            "Cancellation is cooperative; the job transitions to `cancelled` "
            "once the worker observes the request."
        )
    )
    def cancel_job(job_id: str) -> dict[str, Any]:
        ctx = get_context()
        ctx.jobs.request_cancel(job_id)
        return _handle_to_dict(ctx.jobs.get(job_id))

    # ------------------------------------------------------------------
    # Worker registry
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List all registered model workers. Each entry includes the "
            "static descriptor (capabilities, license, links) and the latest "
            "probe result (runnable, missing dependencies, device, VRAM)."
        )
    )
    def list_workers() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for worker in ctx.workers.all():
            descriptor = ctx.workers.describe(worker)
            probe = worker.probe()
            out.append(
                {
                    "descriptor": descriptor.model_dump(mode="json"),
                    "probe": probe.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "List capabilities and the workers that advertise them, with each "
            "worker's probe runnable flag. Useful for selecting an explicit "
            "worker before submitting a job."
        )
    )
    def list_worker_capabilities() -> dict[str, list[dict[str, Any]]]:
        ctx = get_context()
        capabilities_map: dict[str, list[dict[str, Any]]] = {}
        for capability in Capability:
            entries: list[dict[str, Any]] = []
            for worker in ctx.workers.for_capability(capability):
                probe = worker.probe()
                entries.append(
                    {
                        "name": worker.name,
                        "priority": worker.priority,
                        "is_stub": getattr(worker, "is_stub", False),
                        "license": getattr(worker, "license", None),
                        "runnable": probe.runnable,
                        "reason": probe.reason,
                    }
                )
            entries.sort(key=lambda e: e["priority"], reverse=True)
            if entries:
                capabilities_map[capability.value] = entries
        return capabilities_map

    @server.tool(description="Re-probe a specific worker and return the result.")
    def probe_worker(name: str) -> dict[str, Any]:
        return get_context().workers.probe(name).model_dump(mode="json")

    def _resolve_output_dir_for_workers(output_dir: str | None) -> Path:
        if output_dir:
            path = Path(output_dir).resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path
        return get_context().storage.new_asset_dir()

    @server.tool(
        description=(
            "Submit an image-to-3D job. Auto-selects the highest-priority "
            "runnable worker that advertises image_to_3d unless `worker` is "
            "specified. Returns a job handle; poll with get_job or "
            "wait_for_job."
        )
    )
    def submit_image_to_3d(
        input_image_path: str,
        prompt: str | None = None,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = ImageTo3DRequest(
            input_image_path=Path(input_image_path),
            prompt=prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
        )
        handle = ctx.runner.submit("image_to_3d", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a hosted text-to-3D job. The default worker is tripo_api "
            "when GHOSTFORGE_TRIPO_API_KEY or TRIPO_API_KEY is set in the "
            "server environment. Smart mesh options map to Tripo H3 controls "
            "for texture/PBR, smart low-poly, quad remesh, face limits, UVs, "
            "auto-size, and geometry quality."
        )
    )
    def submit_text_to_3d(
        prompt: str,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        negative_prompt: str | None = None,
        output_format: str = "glb",
        model_version: str = "v3.1-20260211",
        texture: bool = True,
        pbr: bool = True,
        texture_quality: str = "standard",
        smart_low_poly: bool = False,
        quad: bool = False,
        face_limit: int | None = None,
        auto_size: bool = False,
        export_uv: bool = True,
        geometry_quality: str = "standard",
        generate_parts: bool = False,
        compress: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        extras: dict[str, Any] = {
            "model_version": model_version,
            "texture": texture,
            "pbr": pbr,
            "texture_quality": texture_quality,
            "smart_low_poly": smart_low_poly,
            "quad": quad,
            "auto_size": auto_size,
            "export_uv": export_uv,
            "geometry_quality": geometry_quality,
            "generate_parts": generate_parts,
        }
        if face_limit is not None:
            extras["face_limit"] = face_limit
        if compress:
            extras["compress"] = compress
        spec = TextTo3DRequest(
            prompt=prompt,
            negative_prompt=negative_prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
            extras=extras,
        )
        handle = ctx.runner.submit("text_to_3d", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a mesh-texturing job (Paint3D / SyncMVD style). Reads an "
            "existing mesh and a text prompt; produces a textured mesh + "
            "base-color map."
        )
    )
    def submit_texture_mesh(
        input_mesh_path: str,
        prompt: str,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        reference_image_path: str | None = None,
        texture_size: int = 1024,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = TextureMeshRequest(
            input_mesh_path=Path(input_mesh_path),
            prompt=prompt,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            reference_image_path=Path(reference_image_path) if reference_image_path else None,
            texture_size=texture_size,
            output_format=output_format,
        )
        handle = ctx.runner.submit("texture_mesh", spec)
        return handle.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a mesh-refinement job (retopology, decimation). Currently "
            "only the stub worker is registered; real workers will be wired "
            "as they're added."
        )
    )
    def submit_refine_mesh(
        input_mesh_path: str,
        target_face_count: int | None = None,
        preserve_uvs: bool = True,
        output_dir: str | None = None,
        worker: str | None = None,
        seed: int | None = None,
        output_format: str = "glb",
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = RefineMeshRequest(
            input_mesh_path=Path(input_mesh_path),
            target_face_count=target_face_count,
            preserve_uvs=preserve_uvs,
            output_dir=_resolve_output_dir_for_workers(output_dir),
            worker=worker,
            seed=seed,
            output_format=output_format,
        )
        handle = ctx.runner.submit("refine_mesh", spec)
        return handle.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Knowledge base
    # ------------------------------------------------------------------

    def _parse_sources(sources: list[str] | None) -> list[ConceptSource] | None:
        if not sources:
            return None
        try:
            return [ConceptSource(s) for s in sources]
        except ValueError as exc:
            raise ValueError(
                f"Unknown concept source. Valid: {[s.value for s in ConceptSource]}"
            ) from exc

    @server.tool(
        description=(
            "Return knowledge base status: backend, embedder, total concept count, "
            "and embedding dimension. Useful for diagnosing whether OpenCLIP / "
            "LanceDB are active."
        )
    )
    def kb_status() -> dict[str, Any]:
        kb = get_context().kb
        return {
            "backend": kb.backend,
            "embedder": kb.embedding_model,
            "embedding_dim": kb.embedding_dim,
            "count": kb.count(),
            "image_dir": str(kb.image_dir),
        }

    @server.tool(
        description=(
            "Ingest a local image as a knowledge base concept. License is "
            "mandatory (use 'CC0-1.0' for public domain, an SPDX id, or "
            "'project-internal' for in-house references)."
        )
    )
    def kb_ingest_local_image(
        image_path: str,
        title: str,
        license: str,
        description: str = "",
        attribution: str | None = None,
        creator: str | None = None,
        tags: list[str] | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = ingest_local_image(
            kb,
            Path(image_path),
            title=title,
            license=license,
            description=description,
            attribution=attribution,
            creator=creator,
            tags=tags,
            source_url=source_url,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Download an image URL and ingest it as a knowledge base concept. "
            "License is mandatory and must accurately describe the source's "
            "terms; refusing with 'unknown' is intentional, not a bug."
        )
    )
    def kb_ingest_url(
        url: str,
        title: str,
        license: str,
        description: str = "",
        attribution: str | None = None,
        creator: str | None = None,
        tags: list[str] | None = None,
        license_url: str | None = None,
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = ingest_url(
            kb,
            url,
            title=title,
            license=license,
            description=description,
            attribution=attribution,
            creator=creator,
            tags=tags,
            license_url=license_url,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Search Openverse and ingest the top results as concepts. "
            "license_filter defaults to permissive licenses (cc0, pdm, by, "
            "by-sa). Returns the list of ingested entries."
        )
    )
    def kb_ingest_openverse(
        query: str,
        count: int = 5,
        license_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        entries = ingest_openverse(
            kb,
            query,
            license_filter=license_filter,
            count=count,
        )
        return [e.model_dump(mode="json") for e in entries]

    @server.tool(
        description=(
            "Add a project style guide. License defaults to 'project-internal' "
            "to indicate the text is owned by the project. Style guides are "
            "embedded alongside image concepts and bias retrieval toward "
            "in-house art direction."
        )
    )
    def kb_ingest_style_guide(
        title: str,
        text: str,
        tags: list[str] | None = None,
        license: str = "project-internal",
    ) -> dict[str, Any]:
        kb = get_context().kb
        entry = kb.add_text(
            title=title,
            text=text,
            license=license,
            source=ConceptSource.style_guide,
            tags=tags,
        )
        return entry.model_dump(mode="json")

    @server.tool(
        description=(
            "Run a similarity search over knowledge base concepts using a text "
            "query. Cross-modal text→image retrieval is meaningful only when "
            "the OpenCLIP embedder is active; with the default hash embedder, "
            "text queries match best against style-guide entries."
        )
    )
    def kb_search_text(
        query: str,
        k: int = 5,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        results = kb.search_text(
            query,
            k=k,
            sources=_parse_sources(sources),
            tags=tags,
        )
        return [r.model_dump(mode="json") for r in results]

    @server.tool(
        description=(
            "Run a similarity search over knowledge base concepts using a "
            "reference image."
        )
    )
    def kb_search_image(
        image_path: str,
        k: int = 5,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        results = kb.search_image_path(
            Path(image_path),
            k=k,
            sources=_parse_sources(sources),
            tags=tags,
        )
        return [r.model_dump(mode="json") for r in results]

    @server.tool(description="Fetch a single knowledge base concept by id.")
    def kb_get(concept_id: str) -> dict[str, Any]:
        return get_context().kb.get(concept_id).model_dump(mode="json")

    @server.tool(description="List concepts, optionally filtered by source.")
    def kb_list(
        sources: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        kb = get_context().kb
        entries = kb.list(
            limit=limit,
            offset=offset,
            sources=_parse_sources(sources),
        )
        return [e.model_dump(mode="json") for e in entries]

    @server.tool(
        description=(
            "Attach knowledge base concept citations to an asset manifest. "
            "Creates the manifest if absent. Each citation captures the "
            "source URL, license, attribution, and an optional usage note "
            "so downstream engines and audits can trace provenance."
        )
    )
    def kb_cite_in_manifest(
        asset_dir: str,
        concept_ids: list[str],
        note: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)
        builder = ManifestBuilder.for_dir(path)
        for concept_id in concept_ids:
            citation = ctx.kb.make_citation(concept_id, note=note)
            builder.add_concept_citation(citation)
        manifest, _ = builder.write()
        return manifest.model_dump(mode="json")

    @server.tool(
        description=(
            "Read the AssetManifest at an asset directory. Returns the full v1 "
            "manifest JSON document, including geometry, materials, LODs, "
            "validation summary, license, and engine targets."
        )
    )
    def read_asset_manifest(asset_dir: str) -> dict[str, Any]:
        path = Path(asset_dir)
        if not manifest_exists(path):
            raise FileNotFoundError(f"No asset manifest at {path}")
        return read_manifest(path).model_dump(mode="json")

    @server.tool(
        description=(
            "Annotate an existing AssetManifest with license info, engine "
            "targets, tags, and free-form description. Creates the manifest "
            "if it does not yet exist. Useful for agents preparing assets for "
            "Unity or Unreal handoff."
        )
    )
    def update_asset_manifest(
        asset_dir: str,
        name: str | None = None,
        description: str | None = None,
        license_spdx: str | None = None,
        license_holder: str | None = None,
        license_attribution: str | None = None,
        license_source_url: str | None = None,
        engine_targets: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        path = Path(asset_dir)
        path.mkdir(parents=True, exist_ok=True)

        builder = ManifestBuilder.for_dir(path)
        builder.with_name(name).with_description(description)

        if any(
            v is not None
            for v in (license_spdx, license_holder, license_attribution, license_source_url)
        ):
            builder.with_license(
                LicenseSpec(
                    spdx=license_spdx,
                    holder=license_holder,
                    attribution=license_attribution,
                    source_url=license_source_url,
                )
            )

        for engine_name in engine_targets or []:
            try:
                builder.add_engine_target(EngineTargetSpec(engine=EngineTarget(engine_name)))
            except ValueError as exc:
                raise ValueError(
                    f"Unknown engine target '{engine_name}'. "
                    f"Valid options: {[e.value for e in EngineTarget]}"
                ) from exc

        for tag in tags or []:
            builder.add_tag(tag)

        manifest, _ = builder.write()
        return manifest.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Game-readiness audit
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List available audit presets. Each preset bundles thresholds "
            "for an engine: 'default' is engine-agnostic, 'unity' adds "
            "lightmap-UV / 65k-vert / power-of-two texture rules, 'unreal' "
            "raises poly ceilings for Nanite-friendly assets and uses "
            "/Game-style content paths."
        )
    )
    def list_audit_presets() -> list[dict[str, Any]]:
        return [preset.model_dump(mode="json") for preset in list_audit_presets_op()]

    @server.tool(
        description=(
            "Run the game-readiness audit on an asset directory. Returns the "
            "structured AuditReport including per-rule status and any "
            "issues. By default the report is also written back into "
            "manifest.validation and appended to "
            "manifest.custom['audit_history'] so engine adapters and other "
            "consumers see the verdict. Set persist=False for a dry-run "
            "audit. The optional Khronos glTF Validator runs when "
            "gltf-validator is on PATH or pointed to by "
            "GHOSTFORGE_GLTF_VALIDATOR."
        )
    )
    def audit_asset(
        asset_dir: str,
        preset: str = "default",
        run_gltf_validator: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        report = audit_asset_op(
            Path(asset_dir),
            preset=preset,
            run_gltf_validator=run_gltf_validator,
            persist=persist,
        )
        return report.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a game-readiness audit as a background job. Useful when "
            "the glTF Validator is enabled and assets are large; otherwise "
            "audit_asset blocks on the same logic and returns immediately."
        )
    )
    def submit_audit(
        asset_dir: str,
        preset: str = "default",
        run_gltf_validator: bool = True,
        persist: bool = True,
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = AuditAssetRequest(
            asset_dir=Path(asset_dir),
            preset=preset,
            run_gltf_validator=run_gltf_validator,
            persist=persist,
        )
        handle = ctx.runner.submit("audit_asset", spec)
        return _handle_to_dict(handle)

    # ------------------------------------------------------------------
    # Engine handoff
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List configured engine adapters (Unity-MCP-Ghost, Unreal-MCP-"
            "Ghost). Each entry shows the adapter name, the engine target it "
            "fulfils, the active transport, the configured import tool, and "
            "the latest probe result. Prefer create_engine_export_bridge for "
            "offline handoff packages; direct send tools require an explicitly "
            "configured transport."
        )
    )
    def list_engine_adapters() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for adapter in ctx.engines.all():
            cfg = adapter.get_config()
            probe = adapter.probe()
            out.append(
                {
                    "name": adapter.name,
                    "engine_target": adapter.engine_target.value,
                    "config": cfg.model_dump(mode="json"),
                    "probe": probe.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "Configure or re-configure an engine adapter at runtime. "
            "Choose transport='stdio' (with command list) for spawning a "
            "Unity/Unreal MCP server locally, or transport='http' (with url) "
            "to attach to an already-running engine MCP. Setting "
            "transport='none' resets the adapter to its unconfigured state. "
            "Returns the updated config + probe."
        )
    )
    def configure_engine_adapter(
        name: str,
        transport: str,
        command: list[str] | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        import_tool: str = "import_asset",
        import_args_extra: dict[str, Any] | None = None,
        timeout_seconds: float = 120.0,
        project_path: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(name)
        if transport not in {"stdio", "http", "none"}:
            raise ValueError(
                f"transport must be one of 'stdio', 'http', 'none' (got {transport!r})"
            )
        cfg = EngineConfig(
            name=name,
            transport=transport,  # type: ignore[arg-type]
            command=list(command or []),
            cwd=cwd,
            env=dict(env or {}),
            url=url,
            headers=dict(headers or {}),
            import_tool=import_tool,
            import_args_extra=dict(import_args_extra or {}),
            timeout_seconds=timeout_seconds,
            project_path=project_path,
        )
        adapter.configure(cfg)
        return {
            "name": adapter.name,
            "config": adapter.get_config().model_dump(mode="json"),
            "probe": adapter.probe().model_dump(mode="json"),
        }

    @server.tool(
        description=(
            "Hand a finished asset to Unity-MCP-Ghost. Validates the asset "
            "manifest, runs the game-readiness audit (Unity preset by "
            "default), checks engine_targets includes 'unity' (use force=True "
            "to override both engine_target and audit error gating), and "
            "either calls the configured import tool over MCP or, with "
            "dry_run=True, records a planned handoff in the manifest without "
            "contacting Unity. Returns the handoff result including the "
            "audit summary and engine response."
        )
    )
    def send_to_unity(
        asset_dir: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        return _run_send(
            engine="unity",
            asset_dir=asset_dir,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=extra_args,
            audit=audit,
            audit_preset=audit_preset,
        )

    @server.tool(
        description=(
            "Optional direct handoff to a configured Unreal-MCP-Ghost "
            "transport. For the default product workflow, use "
            "create_engine_export_bridge and import that JSON from the Unreal "
            "side. Default target paths follow Unreal's /Game/ convention."
        )
    )
    def send_to_unreal(
        asset_dir: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        return _run_send(
            engine="unreal",
            asset_dir=asset_dir,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=extra_args,
            audit=audit,
            audit_preset=audit_preset,
        )

    @server.tool(
        description=(
            "Create an offline export bridge package for Unity-MCP-Ghost or "
            "Unreal-MCP-Ghost. This validates the Ghost-Forge asset manifest "
            "and writes ghostforge_bridge_<engine>.json, but it does not call "
            "or control the game editor directly."
        )
    )
    def create_engine_export_bridge(
        asset_dir: str,
        target_engine: str,
        target_path: str | None = None,
        bridge_dir: str | None = None,
        recommended_tool: str = "import_asset",
        notes: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.export_bridge import create_export_bridge_package

        package, path = create_export_bridge_package(
            asset_dir,
            target_engine=target_engine,
            target_path=target_path,
            bridge_dir=bridge_dir,
            recommended_tool=recommended_tool,
            notes=notes,
        )
        return {
            "package": package.model_dump(mode="json"),
            "package_path": str(path),
            "direct_engine_call": False,
        }

    @server.tool(
        description=(
            "Submit an engine handoff as a background job. Useful when the "
            "engine MCP may take a while (large meshes, project-wide reimport "
            "passes). Poll the returned handle with get_job or wait_for_job."
        )
    )
    def submit_send_to_engine(
        asset_dir: str,
        engine: str,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        spec = SendToEngineRequest(
            asset_dir=Path(asset_dir),
            engine=engine,
            target_path=target_path,
            dry_run=dry_run,
            force=force,
            extra_args=dict(extra_args or {}),
            audit=audit,
            audit_preset=audit_preset,
        )
        handle = ctx.runner.submit("send_to_engine", spec)
        return _handle_to_dict(handle)

    def _run_send(
        *,
        engine: str,
        asset_dir: str,
        target_path: str | None,
        dry_run: bool,
        force: bool,
        extra_args: dict[str, Any] | None,
        audit: bool,
        audit_preset: str | None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(engine)
        try:
            result = adapter.send_asset(
                Path(asset_dir),
                target_path=target_path,
                dry_run=dry_run,
                force=force,
                extra_args=dict(extra_args or {}) or None,
                audit=audit,
                audit_preset=audit_preset,
            )
        except EngineHandoffError:
            raise
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # GPU + scheduler tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "Report current GPU detection state and scheduler lane status. "
            "Returns the detection backend (torch/pynvml/none), per-GPU "
            "VRAM and in-flight job counts, and the configured CPU "
            "concurrency budget."
        )
    )
    def list_gpus() -> dict[str, Any]:
        ctx = get_context()
        if ctx.scheduler is None:
            from ghostforge_core.gpu import detect_gpus

            status = detect_gpus(force=True)
            return {
                "scheduler_enabled": False,
                "backend": status.backend,
                "cpu_only": status.cpu_only,
                "gpus": [g.model_dump(mode="json") for g in status.gpus],
                "notes": list(status.notes),
            }
        snapshot = ctx.scheduler.status()
        snapshot["scheduler_enabled"] = True
        return snapshot

    @server.tool(
        description=(
            "Force a fresh GPU re-detection (bypasses the short cache). "
            "Useful after driver reinstalls, container restarts, or eGPU "
            "hot-plug. Returns the new status."
        )
    )
    def refresh_gpus() -> dict[str, Any]:
        ctx = get_context()
        if ctx.scheduler is None:
            from ghostforge_core.gpu import detect_gpus, reset_cache_for_tests

            reset_cache_for_tests()
            status = detect_gpus(force=True)
            return {
                "scheduler_enabled": False,
                "backend": status.backend,
                "cpu_only": status.cpu_only,
                "gpus": [g.model_dump(mode="json") for g in status.gpus],
            }
        ctx.scheduler.refresh(force=True)
        return ctx.scheduler.status()

    @server.tool(
        description=(
            "Return per-worker resource declarations: CUDA requirement, "
            "min/recommended VRAM, max concurrent runs per GPU, CPU "
            "fallback availability, and the model artifacts each worker "
            "depends on. Drives `download_model` decisions."
        )
    )
    def get_worker_resources() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for worker in ctx.workers.all():
            descriptor = ctx.workers.describe(worker)
            out.append(
                {
                    "name": descriptor.name,
                    "is_stub": descriptor.is_stub,
                    "capabilities": [c.value for c in descriptor.capabilities],
                    "resources": descriptor.resources.model_dump(mode="json"),
                    "required_models": list(descriptor.required_models),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Model registry tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List every registered model artifact and its current cache "
            "status (cached/missing files, integrity)."
        )
    )
    def list_models() -> list[dict[str, Any]]:
        ctx = get_context()
        out: list[dict[str, Any]] = []
        for artifact in ctx.models.list():
            status = ctx.models.status(artifact.model_id)
            out.append(
                {
                    "artifact": artifact.model_dump(mode="json"),
                    "status": status.model_dump(mode="json"),
                }
            )
        return out

    @server.tool(
        description=(
            "Cache state for a single model. `model_id` matches the id "
            "exposed by `get_worker_resources` and `list_models`."
        )
    )
    def model_status(model_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            return ctx.models.status(model_id).model_dump(mode="json")
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")

    @server.tool(
        description=(
            "List the model artifacts a worker depends on, with cache "
            "status for each. Use to decide whether `download_model` is "
            "needed before scheduling."
        )
    )
    def list_required_models(worker_name: str) -> list[dict[str, Any]]:
        ctx = get_context()
        worker = ctx.workers.get(worker_name)
        descriptor = ctx.workers.describe(worker)
        out: list[dict[str, Any]] = []
        for model_id in descriptor.required_models:
            try:
                status = ctx.models.status(model_id)
                out.append(status.model_dump(mode="json"))
            except ModelNotFound:
                out.append({"model_id": model_id, "registered": False})
        return out

    @server.tool(
        description=(
            "Download a registered model into the cache. Idempotent — "
            "skipped when fully cached and verified, unless `force=True`. "
            "Pass `token` for HuggingFace gated repos. Returns the new "
            "cache status."
        )
    )
    def download_model(
        model_id: str,
        force: bool = False,
        token: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        try:
            status = ctx.models.download(model_id, force=force, token=token)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        except ModelDownloadError as exc:
            raise RuntimeError(str(exc))
        return status.model_dump(mode="json")

    @server.tool(
        description=(
            "Recompute sha256 for every file of a cached model and update "
            "its integrity timestamp. Use after a suspect download or "
            "when surfacing a 'verified' badge in the UI."
        )
    )
    def verify_model(model_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            status = ctx.models.verify(model_id)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        except ModelDownloadError as exc:
            raise RuntimeError(str(exc))
        return status.model_dump(mode="json")

    @server.tool(
        description=(
            "Delete cached files for a single model (or all models when "
            "`model_id=None`). Returns the count of cleared model dirs."
        )
    )
    def clear_model_cache(model_id: str | None = None) -> dict[str, Any]:
        ctx = get_context()
        try:
            removed = ctx.models.clear(model_id)
        except ModelNotFound:
            raise ValueError(f"unknown model_id: {model_id}")
        return {"cleared": removed, "model_id": model_id}

    # ------------------------------------------------------------------
    # Benchmark tools (Prompt 8)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "Run a worker through repeated invocations and return wall-time "
            "stats. `spec` is the worker request payload (e.g. a "
            "TextTo3DRequest dict). Persists a JSON report under "
            "data/benchmarks/."
        )
    )
    def run_benchmark(
        worker_name: str,
        capability: str,
        spec: dict[str, Any],
        runs: int = 1,
        warmup_runs: int = 0,
        note: str | None = None,
        benchmark_id: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        request = BenchmarkRequest(
            benchmark_id=benchmark_id or make_benchmark_id(prefix=worker_name),
            worker_name=worker_name,
            capability=Capability(capability),
            spec=spec,
            runs=runs,
            warmup_runs=warmup_runs,
            note=note,
        )
        result = run_benchmark_op(
            request,
            registry=ctx.workers,
            store=ctx.benchmarks,
            storage=ctx.storage,
        )
        return result.model_dump(mode="json")

    @server.tool(
        description=(
            "List recent benchmark reports (newest first). `limit` caps "
            "the number returned."
        )
    )
    def list_benchmarks(limit: int = 50) -> list[dict[str, Any]]:
        ctx = get_context()
        return [r.model_dump(mode="json") for r in ctx.benchmarks.list(limit=limit)]

    @server.tool(
        description="Fetch a single benchmark report by id."
    )
    def get_benchmark(benchmark_id: str) -> dict[str, Any]:
        ctx = get_context()
        result = ctx.benchmarks.load(benchmark_id)
        if result is None:
            raise ValueError(f"benchmark not found: {benchmark_id}")
        return result.model_dump(mode="json")

    # ------------------------------------------------------------------
    # Worker session tools (Prompt 9)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List loaded worker sessions (cached model checkpoints / pipelines) "
            "with their idle times. Use to decide whether to free GPU memory."
        )
    )
    def list_worker_sessions() -> list[dict[str, Any]]:
        return get_session_registry().status()

    @server.tool(
        description=(
            "Free a loaded worker session by name (e.g. "
            "'diffusers_texture.txt2img'), or all of them when `name` is "
            "null. Set `force=True` to evict even when the session is in "
            "use. Returns the number of sessions actually freed."
        )
    )
    def free_worker_session(
        name: str | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        freed = get_session_registry().free(name, force=force)
        return {"freed": freed, "name": name, "force": force}

    @server.tool(
        description=(
            "Free worker sessions that have been idle longer than "
            "`idle_for_seconds`. When omitted, each session uses its own "
            "configured idle timeout. Returns the number of sessions "
            "evicted."
        )
    )
    def free_idle_worker_sessions(
        idle_for_seconds: float | None = None,
    ) -> dict[str, Any]:
        freed = get_session_registry().free_idle(idle_for_seconds=idle_for_seconds)
        return {"freed": freed, "idle_for_seconds": idle_for_seconds}

    # ------------------------------------------------------------------
    # Vertical slice tools (Prompt 7)
    # ------------------------------------------------------------------

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

    @server.tool(
        description=(
            "Create and persist a vertical slice plan. `brief` describes the "
            "game and target engine; `assets` is a list of asset specs (each "
            "with at least `asset_id` and `description`). Returns the saved "
            "plan including its slice_id."
        )
    )
    def create_vertical_slice(
        brief: dict[str, Any],
        assets: list[dict[str, Any]],
        slice_id: str | None = None,
        fail_fast: bool = False,
        skip_audit: bool = False,
        skip_handoff: bool = False,
    ) -> dict[str, Any]:
        ctx = get_context()
        plan = plan_vertical_slice(
            store=ctx.slices,
            brief=_coerce_brief(brief),
            assets=_coerce_assets(assets),
            slice_id=slice_id,
            fail_fast=fail_fast,
            skip_audit=skip_audit,
            skip_handoff=skip_handoff,
        )
        return plan.model_dump(mode="json")

    @server.tool(
        description=(
            "Replace the asset list on an existing slice plan. Useful for "
            "agent-driven plan refinement (LLM proposes assets, operator "
            "tweaks before executing)."
        )
    )
    def update_vertical_slice_assets(
        slice_id: str,
        assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        ctx = get_context()
        plan = update_plan_assets(ctx.slices, slice_id, _coerce_assets(assets))
        return plan.model_dump(mode="json")

    @server.tool(
        description=(
            "Return a slice's plan and latest run state. Use this to inspect "
            "per-asset stage progress and outputs."
        )
    )
    def get_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        run = ctx.slices.load_run(slice_id)
        return {
            "plan": plan.model_dump(mode="json"),
            "run": run.model_dump(mode="json") if run is not None else None,
        }

    @server.tool(
        description=(
            "List all known slices with their current status, asset count, "
            "and target engine."
        )
    )
    def list_vertical_slices() -> list[dict[str, Any]]:
        ctx = get_context()
        return [s.model_dump(mode="json") for s in ctx.slices.list_summaries()]

    @server.tool(
        description=(
            "Delete a slice's plan and run history (does not delete generated "
            "asset directories outside data/slices/)."
        )
    )
    def delete_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            ctx.slices.delete(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        return {"deleted": True, "slice_id": slice_id}

    @server.tool(
        description=(
            "Run a planned slice synchronously. For each asset, walks the "
            "pipeline (kb_search -> generate -> unwrap -> texture -> cite -> "
            "annotate -> audit -> handoff) and persists per-stage state. "
            "Suitable for short slices; use `submit_vertical_slice` for "
            "long-running ones so the client doesn't block."
        )
    )
    def execute_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        try:
            plan = ctx.slices.load_plan(slice_id)
        except SliceNotFound:
            raise ValueError(f"slice not found: {slice_id}")
        run = execute_slice_op(
            plan,
            store=ctx.slices,
            kb=ctx.kb,
            engines=ctx.engines,
        )
        return run.model_dump(mode="json")

    @server.tool(
        description=(
            "Submit a slice run as a background job. Returns a job handle; "
            "poll with `get_job` or stream progress via `wait_for_job`."
        )
    )
    def submit_vertical_slice(slice_id: str) -> dict[str, Any]:
        ctx = get_context()
        spec = ExecuteVerticalSliceRequest(slice_id=slice_id)
        handle = ctx.runner.submit("execute_vertical_slice", spec)
        return _handle_to_dict(handle)

    @server.tool(
        description=(
            "Invoke an arbitrary tool on a configured engine MCP server. Use "
            "for engine actions outside the GhostForge surface — placement, "
            "screenshots, scene control. Requires the engine adapter to be "
            "configured (see `configure_engine_adapter`)."
        )
    )
    def call_engine_tool(
        engine: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        adapter = ctx.engines.get(engine)
        return adapter.call_tool(tool_name, dict(arguments or {}))

    # ------------------------------------------------------------------
    # Retarget: cross-engine linting + planner (P12)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List the engine profiles GhostForge can retarget assets for. "
            "Each profile describes axis convention, units, naming, and "
            "lightmap requirements."
        )
    )
    def list_engine_profiles() -> list[dict[str, Any]]:
        from ghostforge_core.retarget import list_profiles

        return [p.model_dump(mode="json") for p in list_profiles()]

    @server.tool(
        description=(
            "Run the cross-engine audit against an asset for the given target. "
            "Returns the full AuditReport with retarget rule output included. "
            "Use the report's `issues` to drive a manual fix or call "
            "`generate_retarget_graph` to auto-plan one."
        )
    )
    def lint_for_engine(
        asset_dir: str,
        target_engine: str,
        run_gltf_validator: bool = False,
    ) -> dict[str, Any]:
        from ghostforge_core.audit import audit_asset
        from ghostforge_core.retarget.presets import (
            retarget_rules_for_preset,
            unity_retarget_preset,
            unreal_retarget_preset,
        )

        if target_engine not in {"unity", "unreal"}:
            raise ValueError("target_engine must be 'unity' or 'unreal'")
        factory = unity_retarget_preset if target_engine == "unity" else unreal_retarget_preset
        report = audit_asset(
            Path(asset_dir),
            preset=factory(),
            rules=retarget_rules_for_preset(target_engine),
            run_gltf_validator=run_gltf_validator,
            persist=False,
        )
        return report.model_dump(mode="json")

    @server.tool(
        description=(
            "Auto-plan a retarget edit graph for the given asset and engine. "
            "Reads the manifest, runs the cross-engine audit, and emits an "
            "EditGraph populated with `retarget_axis` / `retarget_units` / "
            "`retarget_pivot_for_engine` / `retarget_apply_naming` nodes "
            "addressing each diagnostic in stable order. Set `persist_graph=True` "
            "to save the graph for later evaluation via `evaluate_edit_graph`."
        )
    )
    def generate_retarget_graph(
        asset_dir: str,
        target_engine: str,
        base_name: str | None = None,
        graph_id: str | None = None,
        graph_name: str | None = None,
        output_path: str | None = None,
        persist_graph: bool = False,
    ) -> dict[str, Any]:
        from ghostforge_core.retarget import plan_retarget_graph_for_asset

        if target_engine not in {"unity", "unreal"}:
            raise ValueError("target_engine must be 'unity' or 'unreal'")
        graph, report = plan_retarget_graph_for_asset(
            asset_dir,
            target_engine=target_engine,
            base_name=base_name,
            graph_id=graph_id,
            graph_name=graph_name,
            output_path=output_path,
        )
        if persist_graph:
            ctx = get_context()
            ctx.graphs.save(graph)
        return {
            "graph": graph.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------
    # Authoring: operations + edit graphs (P11)
    # ------------------------------------------------------------------

    @server.tool(
        description=(
            "List every authoring operation the core can apply to a mesh "
            "(transform, decimate, smooth, etc). Returns descriptors with the "
            "kind, label, parameter schema, and any optional dependencies."
        )
    )
    def list_operations() -> list[dict[str, Any]]:
        ctx = get_context()
        return [d.model_dump(mode="json") for d in ctx.operations.descriptors()]

    @server.tool(
        description=(
            "Create a new edit graph. The graph captures a non-destructive "
            "stack of operations layered onto a base asset. Returns the "
            "graph_id you can use with the other graph tools."
        )
    )
    def create_edit_graph(
        name: str = "",
        description: str = "",
        asset_id: str | None = None,
        base_asset_path: str | None = None,
        output_path: str | None = None,
        graph_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import EditGraph

        ctx = get_context()
        gid = graph_id or ctx.graphs.make_id()
        graph = EditGraph(
            graph_id=gid,
            name=name,
            description=description,
            asset_id=asset_id,
            base_asset_path=base_asset_path,
            output_path=output_path,
        )
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(description="List every persisted edit graph (graph metadata only).")
    def list_edit_graphs() -> list[dict[str, Any]]:
        ctx = get_context()
        return [g.model_dump(mode="json") for g in ctx.graphs.list()]

    @server.tool(description="Fetch one edit graph plus its last evaluation report (if any).")
    def get_edit_graph(graph_id: str) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        evaluation = ctx.graphs.load_evaluation(graph_id)
        out: dict[str, Any] = {"graph": graph.model_dump(mode="json")}
        if evaluation is not None:
            out["evaluation"] = evaluation.model_dump(mode="json")
        return out

    @server.tool(description="Delete an edit graph and its evaluation report.")
    def delete_edit_graph(graph_id: str) -> dict[str, Any]:
        ctx = get_context()
        ctx.graphs.delete(graph_id)
        return {"deleted": graph_id}

    @server.tool(
        description=(
            "Append an operation node to the end of an edit graph. Use "
            "`list_operations` to discover valid `kind` values and their "
            "parameter schema."
        )
    )
    def append_graph_node(
        graph_id: str,
        kind: str,
        params: dict[str, Any] | None = None,
        label: str = "",
        enabled: bool = True,
        notes: str | None = None,
        node_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import OperationNode

        ctx = get_context()
        if not ctx.operations.has(kind):
            raise ValueError(f"unknown operation kind {kind!r}")
        graph = ctx.graphs.load(graph_id)
        nid = node_id or f"node-{len(graph.nodes) + 1:03d}"
        node = OperationNode(
            id=nid,
            kind=kind,
            label=label,
            enabled=enabled,
            params=dict(params or {}),
            notes=notes,
        )
        graph = graph.with_nodes(list(graph.nodes) + [node])
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Update an existing node's params, label, enabled flag, notes, or "
            "kind. Only the keys you supply are changed."
        )
    )
    def update_graph_node(
        graph_id: str,
        node_id: str,
        kind: str | None = None,
        params: dict[str, Any] | None = None,
        label: str | None = None,
        enabled: bool | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        nodes = list(graph.nodes)
        idx = next((i for i, n in enumerate(nodes) if n.id == node_id), None)
        if idx is None:
            raise KeyError(f"node {node_id!r} not in graph {graph_id!r}")
        update: dict[str, Any] = {}
        if kind is not None:
            if not ctx.operations.has(kind):
                raise ValueError(f"unknown operation kind {kind!r}")
            update["kind"] = kind
        if params is not None:
            update["params"] = dict(params)
        if label is not None:
            update["label"] = label
        if enabled is not None:
            update["enabled"] = enabled
        if notes is not None:
            update["notes"] = notes
        nodes[idx] = nodes[idx].model_copy(update=update)
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(description="Remove a node from an edit graph.")
    def remove_graph_node(graph_id: str, node_id: str) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        nodes = [n for n in graph.nodes if n.id != node_id]
        if len(nodes) == len(graph.nodes):
            raise KeyError(f"node {node_id!r} not in graph {graph_id!r}")
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Reorder graph nodes. `order` must contain every existing node id "
            "exactly once, in the new desired order."
        )
    )
    def reorder_graph_nodes(graph_id: str, order: list[str]) -> dict[str, Any]:
        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        by_id = {n.id: n for n in graph.nodes}
        if set(order) != set(by_id) or len(order) != len(by_id):
            raise ValueError("order must contain every existing node id exactly once")
        nodes = [by_id[i] for i in order]
        graph = graph.with_nodes(nodes)
        ctx.graphs.save(graph)
        return graph.model_dump(mode="json")

    @server.tool(
        description=(
            "Evaluate an edit graph end-to-end: load the base asset, apply "
            "every enabled node in order, write the result to `output_path` "
            "(defaults to the graph's stored output_path), and persist the "
            "per-step evaluation report. Use `fail_fast=True` to abort on "
            "the first failed node."
        )
    )
    def evaluate_edit_graph(
        graph_id: str,
        input_path: str | None = None,
        output_path: str | None = None,
        output_format: str = "glb",
        fail_fast: bool = False,
        manifest_dir: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import evaluate_graph as evaluate_op
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        ctx = get_context()
        graph = ctx.graphs.load(graph_id)
        result, _ = evaluate_op(
            graph,
            registry=ctx.operations,
            input_path=input_path,
            output_path=output_path,
            output_format=output_format,
            fail_fast=fail_fast,
        )
        ctx.graphs.save_evaluation(result)
        payload = result.model_dump(mode="json")
        side_effects = (result.metadata or {}).get("side_effects") or []
        if manifest_dir and side_effects:
            try:
                manifest = apply_side_effects_to_manifest(
                    manifest_dir, side_effects, asset_id=asset_id
                )
                if manifest is not None:
                    payload["manifest"] = manifest.model_dump(mode="json")
            except Exception as exc:
                payload["manifest_error"] = str(exc)
        return payload

    @server.tool(
        description=(
            "Evaluate an EditGraph and emit per-step progress notifications. "
            "The MCP client must include a `progressToken` in the request "
            "`_meta` to receive notifications; without one the tool still "
            "returns the final EvaluationResult but emits no progress events. "
            "Pass `manifest_dir` to apply collision/lightmap side-effects to "
            "an asset manifest after evaluation."
        )
    )
    async def evaluate_edit_graph_streaming(
        graph_id: str,
        ctx: Context,
        input_path: str | None = None,
        output_path: str | None = None,
        output_format: str = "glb",
        fail_fast: bool = False,
        manifest_dir: str | None = None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        from ghostforge_core.authoring import evaluate_graph_streaming
        from ghostforge_core.authoring.schema import EvaluationResult
        from ghostforge_core.manifest import apply_side_effects_to_manifest

        core = get_context()
        graph = core.graphs.load(graph_id)

        loop = asyncio.get_event_loop()
        last_event: dict[str, Any] | None = None

        # The streaming evaluator is a synchronous generator. Run it on a
        # worker thread and pump events back to the MCP client via
        # report_progress so we never block the asyncio loop.
        def _drain(queue: asyncio.Queue) -> None:
            try:
                for event in evaluate_graph_streaming(
                    graph,
                    registry=core.operations,
                    input_path=input_path,
                    output_path=output_path,
                    output_format=output_format,
                    fail_fast=fail_fast,
                ):
                    asyncio.run_coroutine_threadsafe(queue.put(event), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(None), loop)

        queue: asyncio.Queue = asyncio.Queue()
        runner = loop.run_in_executor(None, _drain, queue)

        while True:
            event = await queue.get()
            if event is None:
                break
            last_event = event
            if event.get("event") == "step":
                progress = float(event.get("progress") or 0.0)
                msg_parts = [event.get("kind", ""), event.get("status", "")]
                if event.get("message"):
                    msg_parts.append(str(event["message"]))
                if event.get("error"):
                    msg_parts.append(f"error: {event['error']}")
                try:
                    await ctx.report_progress(
                        progress=progress,
                        total=100.0,
                        message=" ".join(p for p in msg_parts if p).strip() or None,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass

        await runner

        result_payload: dict[str, Any] | None = None
        if last_event is not None and last_event.get("event") == "completed":
            result_payload = last_event.get("result")
            try:
                final = EvaluationResult.model_validate(result_payload)
                core.graphs.save_evaluation(final)
            except Exception:
                pass

            side_effects = (
                (result_payload or {}).get("metadata", {}).get("side_effects") or []
            )
            if manifest_dir and side_effects:
                try:
                    manifest = apply_side_effects_to_manifest(
                        manifest_dir, side_effects, asset_id=asset_id
                    )
                    if manifest is not None:
                        result_payload["manifest"] = manifest.model_dump(mode="json")
                except Exception as exc:
                    result_payload["manifest_error"] = str(exc)

        return {"result": result_payload, "events_seen": last_event is not None}

    @server.tool(
        description=(
            "Block until a job reaches a terminal state, streaming progress "
            "notifications. The MCP client must include a `progressToken` in "
            "the request `_meta` to receive progress events; without one this "
            "still returns the final handle but emits no progress."
        )
    )
    async def wait_for_job(
        job_id: str,
        ctx: Context,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 0.25,
    ) -> dict[str, Any]:
        core = get_context()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + max(timeout_seconds, 0.0)
        last_percent: float | None = None
        last_stage: str | None = None

        while True:
            handle = core.jobs.get(job_id)
            progress = handle.progress
            if progress is not None:
                if progress.percent != last_percent or progress.stage != last_stage:
                    try:
                        await ctx.report_progress(
                            progress=progress.percent,
                            total=100.0,
                            message=f"{progress.stage}: {progress.message}".strip(": "),
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Progress notifications are best-effort. The client may
                        # not have requested progress (no progressToken), or may
                        # have disconnected; never fail the tool because of it.
                        pass
                    last_percent = progress.percent
                    last_stage = progress.stage

            if handle.status in _TERMINAL_STATUSES:
                return _handle_to_dict(handle)

            if loop.time() >= deadline:
                raise TimeoutError(
                    f"Job {job_id} did not reach a terminal state within "
                    f"{timeout_seconds:.1f}s (last status={handle.status.value})"
                )
            await asyncio.sleep(max(poll_interval_seconds, 0.05))


__all__ = ["register_tools"]
