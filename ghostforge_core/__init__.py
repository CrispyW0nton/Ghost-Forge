from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .audit import (
    AUDIT_HISTORY_KEY,
    AuditContext,
    AuditIssue,
    AuditPreset,
    AuditReport,
    AuditRule,
    AuditRuleResult,
    AuditSeverity,
    AuditStatus,
    DEFAULT_RULES,
    audit_asset,
    default_preset,
    get_preset,
    list_presets,
    unity_preset,
    unreal_preset,
)
from .engines import (
    BaseEngineAdapter,
    EngineAdapter,
    EngineAssetInvalid,
    EngineCallError,
    EngineConfig,
    EngineHandoffError,
    EngineHandoffResult,
    EngineNotConfigured,
    EngineProbeResult,
    EngineRegistry,
    EngineTransport,
    HttpMcpTransport,
    RecordingTransport,
    StdioMcpTransport,
    UnityEngineAdapter,
    UnrealEngineAdapter,
    config_from_env,
    default_engine_adapters,
)
from .export_bridge import (
    BRIDGE_VERSION,
    ExportBridgeError,
    ExportBridgePackage,
    create_export_bridge_package,
)
from .jobs import CancelToken, JobRunner, JobStore, ProgressReporter
from .kb import (
    ConceptCitation,
    ConceptEntry,
    ConceptSearchResult,
    ConceptSource,
    Embedder,
    HashEmbedder,
    JsonVectorStore,
    KnowledgeBase,
    StyleGuideEntry,
    VectorStore,
    build_knowledge_base,
)
from .manifest import (
    MANIFEST_FILENAME,
    MANIFEST_VERSION,
    AssetManifest,
    CollisionIntent,
    CollisionSpec,
    EngineTarget,
    EngineTargetSpec,
    GeometrySummary,
    LODEntry,
    LicenseSpec,
    ManifestBuilder,
    MaterialSpec,
    ProvenanceStep,
    TextureRole,
    TextureSlot,
    Units,
    ValidationSummary,
    build_geometry_summary,
    manifest_exists,
    manifest_path,
    read_manifest,
    summarize_validation,
    write_manifest,
)
from .benchmarks import (
    BenchmarkRequest,
    BenchmarkResult,
    BenchmarkStore,
    RunSample,
    make_benchmark_id,
    run_benchmark,
)
from .authoring import (
    DEFAULT_OPERATIONS,
    EditGraph,
    EditGraphStore,
    EvaluationResult,
    EvaluationStep,
    GraphNotFound,
    Operation,
    OperationContext,
    OperationDescriptor,
    OperationError,
    OperationNode,
    OperationRegistry,
    default_operation_registry,
    evaluate_graph,
    make_operation,
)
from .gpu import GpuInfo, GpuStatus, detect_gpus
from .models import (
    DEFAULT_ARTIFACTS,
    ModelArtifact,
    ModelDownloadError,
    ModelFile,
    ModelNotFound,
    ModelRegistry,
    ModelStatus,
)
from .registry import Registry
from .scheduler import ResourceScheduler, ResourceUnavailable, SchedulerSlot
from .slice import (
    AssetKind,
    AssetRunState,
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    PlanValidationError,
    SliceExecutionError,
    SliceNotFound,
    SliceStore,
    SliceSummary,
    StageRecord,
    StageStatus,
    VerticalSlicePlan,
    VerticalSliceRun,
    execute_vertical_slice,
    plan_vertical_slice,
    update_plan_assets,
)
from .storage import Storage, compute_artifact
from .workers import (
    CPU_ONLY_RESOURCES,
    Capability,
    DEFAULT_GPU_RESOURCES,
    ImageTo3DRequest,
    ProbeResult,
    RefineMeshRequest,
    TextTo3DRequest,
    TextureMeshRequest,
    Worker,
    WorkerDescriptor,
    WorkerRegistry,
    WorkerResources,
    WorkerSelectionError,
    WorkerUnavailable,
    default_workers,
)
from .types import (
    Artifact,
    AuditAssetRequest,
    Error,
    ExecuteVerticalSliceRequest,
    FrozenModel,
    JobHandle,
    JobProgress,
    JobSpec,
    JobStatus,
    MeshInfo,
    SendToEngineRequest,
    TextureRequest,
    TextureResult,
    UnwrapRequest,
    UnwrapResult,
    utc_now,
)
from .validation import Issue, ValidationReport, validate_glb, validate_mesh


@dataclass(frozen=True)
class CoreConfig:
    data_root: Path = Path("./data")
    max_workers: int = 2
    dispatch_jobs: bool = True
    kb_backend: str | None = None
    kb_embedder: str | None = None
    cpu_concurrency: int = 4
    enable_scheduler: bool = True
    register_default_models: bool = True


@dataclass
class CoreContext:
    config: CoreConfig
    storage: Storage
    jobs: JobStore
    runner: JobRunner
    registry: Registry
    kb: KnowledgeBase
    workers: WorkerRegistry
    engines: EngineRegistry
    slices: SliceStore
    scheduler: ResourceScheduler | None
    models: ModelRegistry
    benchmarks: BenchmarkStore
    operations: OperationRegistry
    graphs: EditGraphStore


def bootstrap(config: CoreConfig | None = None) -> CoreContext:
    from .operations import audit as audit_ops
    from .operations import engines as engine_ops
    from .operations import mesh_info, texture, unwrap
    from .operations import slice as slice_ops
    from .operations import workers as worker_ops

    resolved = config or CoreConfig()
    storage = Storage(resolved.data_root)
    jobs = JobStore(storage.jobs_db_path)
    runner = JobRunner(
        jobs,
        max_workers=resolved.max_workers,
        dispatch=resolved.dispatch_jobs,
    )
    registry = Registry()
    kb = build_knowledge_base(
        resolved.data_root,
        backend=resolved.kb_backend,
        embedder_name=resolved.kb_embedder,
    )
    model_cache = storage.cache_dir / "models"
    model_registry = ModelRegistry(model_cache)
    if resolved.register_default_models:
        model_registry.register_many(DEFAULT_ARTIFACTS)

    workers = default_workers()
    # Wire the model registry into any worker that wants checkpoint
    # resolution (InstantMesh, future TRELLIS / Hunyuan, etc.). Workers
    # without ``set_model_registry`` simply ignore the injection.
    for worker in workers.all():
        injector = getattr(worker, "set_model_registry", None)
        if callable(injector):
            injector(model_registry)
    worker_ops.set_registry(workers)

    scheduler: ResourceScheduler | None = None
    if resolved.enable_scheduler:
        scheduler = ResourceScheduler(cpu_concurrency=resolved.cpu_concurrency)
        worker_ops.set_scheduler(scheduler)
    else:
        worker_ops.set_scheduler(None)

    engine_registry = default_engine_adapters()
    engine_ops.set_registry(engine_registry)
    slice_store = SliceStore(storage)
    slice_ops.set_runtime(kb=kb, engines=engine_registry, store=slice_store)

    benchmarks = BenchmarkStore(storage)
    operations = default_operation_registry()
    # Cross-engine retarget operations register into the same op
    # registry so they appear in the modifier-stack UI alongside
    # transform / decimate / etc.
    from .retarget import RETARGET_OPERATIONS

    operations.register_all(RETARGET_OPERATIONS)
    graphs = EditGraphStore(storage)

    registry.register("mesh_info", mesh_info.run, capabilities=["mesh-info"], version="0.1.0")
    registry.register("unwrap_uvs", unwrap.run, capabilities=["uv", "xatlas"], version="0.1.0")
    registry.register("generate_texture_set", texture.run, capabilities=["texture", "uv-bake"], version="0.1.0")
    registry.register(
        "image_to_3d", worker_ops.run_image_to_3d, capabilities=["image-to-3d"], version="0.1.0"
    )
    registry.register(
        "text_to_3d", worker_ops.run_text_to_3d, capabilities=["text-to-3d"], version="0.1.0"
    )
    registry.register(
        "texture_mesh", worker_ops.run_texture_mesh, capabilities=["texture-mesh"], version="0.1.0"
    )
    registry.register(
        "refine_mesh", worker_ops.run_refine_mesh, capabilities=["refine-mesh"], version="0.1.0"
    )
    registry.register(
        "send_to_engine",
        engine_ops.run_send_to_engine,
        capabilities=["engine-handoff"],
        version="0.1.0",
    )
    registry.register(
        "audit_asset",
        audit_ops.run_audit,
        capabilities=["audit", "game-readiness"],
        version="0.1.0",
    )
    registry.register(
        "execute_vertical_slice",
        slice_ops.run_execute_slice,
        capabilities=["vertical-slice", "orchestration"],
        version="0.1.0",
    )

    runner.register("mesh_info", mesh_info.MeshInfoRequest, mesh_info.run)
    runner.register("unwrap_uvs", UnwrapRequest, unwrap.run)
    runner.register("generate_texture_set", TextureRequest, texture.run)
    runner.register("image_to_3d", ImageTo3DRequest, worker_ops.run_image_to_3d)
    runner.register("text_to_3d", TextTo3DRequest, worker_ops.run_text_to_3d)
    runner.register("texture_mesh", TextureMeshRequest, worker_ops.run_texture_mesh)
    runner.register("refine_mesh", RefineMeshRequest, worker_ops.run_refine_mesh)
    runner.register("send_to_engine", SendToEngineRequest, engine_ops.run_send_to_engine)
    runner.register("audit_asset", AuditAssetRequest, audit_ops.run_audit)
    runner.register(
        "execute_vertical_slice",
        ExecuteVerticalSliceRequest,
        slice_ops.run_execute_slice,
    )
    runner.dispatch_pending()

    return CoreContext(
        config=resolved,
        storage=storage,
        jobs=jobs,
        runner=runner,
        registry=registry,
        kb=kb,
        workers=workers,
        engines=engine_registry,
        slices=slice_store,
        scheduler=scheduler,
        models=model_registry,
        benchmarks=benchmarks,
        operations=operations,
        graphs=graphs,
    )


__all__ = [
    "AUDIT_HISTORY_KEY",
    "MANIFEST_FILENAME",
    "MANIFEST_VERSION",
    "AssetManifest",
    "Artifact",
    "AuditAssetRequest",
    "AuditContext",
    "AuditIssue",
    "AuditPreset",
    "AuditReport",
    "AuditRule",
    "AuditRuleResult",
    "AuditSeverity",
    "AuditStatus",
    "BaseEngineAdapter",
    "CancelToken",
    "Capability",
    "CollisionIntent",
    "CollisionSpec",
    "ConceptCitation",
    "ConceptEntry",
    "ConceptSearchResult",
    "ConceptSource",
    "CoreConfig",
    "CoreContext",
    "DEFAULT_OPERATIONS",
    "EditGraph",
    "EditGraphStore",
    "EvaluationResult",
    "EvaluationStep",
    "GraphNotFound",
    "Operation",
    "OperationContext",
    "OperationDescriptor",
    "OperationError",
    "OperationNode",
    "OperationRegistry",
    "default_operation_registry",
    "evaluate_graph",
    "make_operation",
    "AssetKind",
    "AssetRunState",
    "AssetSpec",
    "BenchmarkRequest",
    "BenchmarkResult",
    "BenchmarkStore",
    "BRIDGE_VERSION",
    "CPU_ONLY_RESOURCES",
    "DEFAULT_ARTIFACTS",
    "DEFAULT_GPU_RESOURCES",
    "Embedder",
    "EngineAdapter",
    "EngineAssetInvalid",
    "EngineCallError",
    "EngineConfig",
    "EngineHandoffError",
    "EngineHandoffResult",
    "EngineNotConfigured",
    "EngineProbeResult",
    "EngineRegistry",
    "EngineTarget",
    "EngineTargetSpec",
    "EngineTransport",
    "Error",
    "ExecuteVerticalSliceRequest",
    "ExportBridgeError",
    "ExportBridgePackage",
    "FrozenModel",
    "GameBrief",
    "GenerationStrategy",
    "GpuInfo",
    "GpuStatus",
    "GeometrySummary",
    "HashEmbedder",
    "HttpMcpTransport",
    "ImageTo3DRequest",
    "JobHandle",
    "JobProgress",
    "JobRunner",
    "JobSpec",
    "JobStatus",
    "JobStore",
    "JsonVectorStore",
    "KnowledgeBase",
    "LODEntry",
    "LicenseSpec",
    "ManifestBuilder",
    "MaterialSpec",
    "MeshInfo",
    "ModelArtifact",
    "ModelDownloadError",
    "ModelFile",
    "ModelNotFound",
    "ModelRegistry",
    "ModelStatus",
    "ProbeResult",
    "ProgressReporter",
    "ProvenanceStep",
    "RecordingTransport",
    "RefineMeshRequest",
    "Registry",
    "ResourceScheduler",
    "ResourceUnavailable",
    "RunSample",
    "SchedulerSlot",
    "SendToEngineRequest",
    "PlanValidationError",
    "SliceExecutionError",
    "SliceNotFound",
    "SliceStore",
    "SliceSummary",
    "StageRecord",
    "StageStatus",
    "StdioMcpTransport",
    "Storage",
    "StyleGuideEntry",
    "TextTo3DRequest",
    "TextureMeshRequest",
    "TextureRequest",
    "TextureResult",
    "TextureRole",
    "TextureSlot",
    "Units",
    "UnityEngineAdapter",
    "UnrealEngineAdapter",
    "UnwrapRequest",
    "UnwrapResult",
    "VerticalSlicePlan",
    "VerticalSliceRun",
    "Issue",
    "ValidationReport",
    "ValidationSummary",
    "VectorStore",
    "Worker",
    "WorkerDescriptor",
    "WorkerRegistry",
    "WorkerResources",
    "WorkerSelectionError",
    "WorkerUnavailable",
    "DEFAULT_RULES",
    "audit_asset",
    "bootstrap",
    "create_export_bridge_package",
    "detect_gpus",
    "execute_vertical_slice",
    "make_benchmark_id",
    "plan_vertical_slice",
    "run_benchmark",
    "update_plan_assets",
    "build_geometry_summary",
    "build_knowledge_base",
    "compute_artifact",
    "config_from_env",
    "default_engine_adapters",
    "default_preset",
    "default_workers",
    "get_preset",
    "list_presets",
    "unity_preset",
    "unreal_preset",
    "manifest_exists",
    "manifest_path",
    "read_manifest",
    "summarize_validation",
    "validate_glb",
    "validate_mesh",
    "write_manifest",
    "utc_now",
]
