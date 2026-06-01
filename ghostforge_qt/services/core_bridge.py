from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ghostforge_core import CoreConfig, CoreContext, EvaluateGraphRequest, bootstrap
from ghostforge_core.authoring import EditGraph, EvaluationResult, SOURCE_OPERATION_KINDS, evaluate_graph
from ghostforge_core.operations import mesh_info as mesh_info_op
from ghostforge_core.types import JobHandle, MeshInfo


@dataclass(frozen=True)
class WorkerRow:
    name: str
    capabilities: tuple[str, ...]
    priority: int
    runnable: bool
    reason: str
    is_stub: bool
    license: str
    device: str
    required_models: tuple[str, ...]


@dataclass(frozen=True)
class EngineRow:
    name: str
    configured: bool
    transport: str
    reason: str


@dataclass(frozen=True)
class OperationRow:
    kind: str
    label: str
    category: str
    summary: str
    operation_type: str
    capability: str | None
    status: str
    workers: tuple[str, ...]
    params_schema: dict[str, Any]


@dataclass(frozen=True)
class RuntimeSnapshot:
    data_root: Path
    kb_backend: str
    kb_embedder: str
    kb_count: int
    workers: tuple[WorkerRow, ...]
    engines: tuple[EngineRow, ...]
    jobs: tuple[JobHandle, ...]


class CoreBridge:
    """Qt-facing adapter around :mod:`ghostforge_core`.

    Widgets and panels consume small immutable rows instead of reaching into the
    core registries directly. This keeps GUI code testable and lets the bridge
    add caching, signals, or process boundaries later.
    """

    WORKER_OPERATION_CAPABILITIES = {
        "generate_text_to_3d": "text_to_3d",
        "generate_image_to_3d": "image_to_3d",
        "worker_refine_mesh": "refine_mesh",
        "worker_texture_mesh": "texture_mesh",
    }

    def __init__(self, *, config: CoreConfig | None = None, context: CoreContext | None = None) -> None:
        self.context = context or bootstrap(config)

    @property
    def data_root(self) -> Path:
        return self.context.storage.root

    def runtime_snapshot(self) -> RuntimeSnapshot:
        return RuntimeSnapshot(
            data_root=self.data_root,
            kb_backend=self.context.kb.backend,
            kb_embedder=self.context.kb.embedding_model,
            kb_count=self.context.kb.count(),
            workers=tuple(self.list_workers()),
            engines=tuple(self.list_engines()),
            jobs=tuple(self.list_jobs(limit=25)),
        )

    def list_workers(self) -> list[WorkerRow]:
        rows: list[WorkerRow] = []
        for worker in self.context.workers.all():
            descriptor = self.context.workers.describe(worker)
            try:
                probe = worker.probe()
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                runnable = False
                reason = str(exc)
                device = ""
            else:
                runnable = probe.runnable
                reason = probe.reason or ""
                device = probe.device or ""
            rows.append(
                WorkerRow(
                    name=descriptor.name,
                    capabilities=tuple(cap.value for cap in descriptor.capabilities),
                    priority=descriptor.priority,
                    runnable=runnable,
                    reason=reason,
                    is_stub=descriptor.is_stub,
                    license=descriptor.license or "",
                    device=device,
                    required_models=tuple(descriptor.required_models),
                )
            )
        rows.sort(key=lambda row: (not row.runnable, -row.priority, row.name))
        return rows

    def list_engines(self) -> list[EngineRow]:
        rows: list[EngineRow] = []
        for adapter in self.context.engines.all():
            probe = adapter.probe()
            rows.append(
                EngineRow(
                    name=probe.name,
                    configured=probe.configured,
                    transport=probe.transport,
                    reason=probe.reason or "",
                )
            )
        return rows

    def list_operations(self) -> list[OperationRow]:
        workers = self.list_workers()
        rows: list[OperationRow] = []
        for descriptor in self.context.operations.descriptors():
            capability = self.WORKER_OPERATION_CAPABILITIES.get(descriptor.kind)
            op_type = "source" if descriptor.kind in SOURCE_OPERATION_KINDS else "operation"
            if capability is not None and op_type != "source":
                op_type = "worker"
            worker_matches = (
                [row for row in workers if capability in row.capabilities]
                if capability is not None
                else []
            )
            rows.append(
                OperationRow(
                    kind=descriptor.kind,
                    label=descriptor.label,
                    category=descriptor.category,
                    summary=descriptor.summary,
                    operation_type=op_type,
                    capability=capability,
                    status=self._operation_status(worker_matches, capability=capability),
                    workers=tuple(row.name for row in worker_matches),
                    params_schema=dict(descriptor.params_schema),
                )
            )
        return rows

    def _operation_status(self, workers: list[WorkerRow], *, capability: str | None) -> str:
        if capability is None:
            return "available"
        if any(row.runnable and not row.is_stub for row in workers):
            return "runnable"
        if any(row.runnable and row.is_stub for row in workers):
            return "stub"
        if workers:
            return "missing"
        return "unavailable"

    def list_jobs(self, *, limit: int = 50) -> list[JobHandle]:
        return self.context.jobs.list(limit=limit)

    def cancel_job(self, job_id: str) -> JobHandle:
        self.context.jobs.request_cancel(job_id)
        return self.context.jobs.get(job_id)

    def mesh_info(self, mesh_path: Path) -> MeshInfo:
        return mesh_info_op.run(mesh_info_op.MeshInfoRequest(mesh_path=mesh_path))

    def new_asset_dir(self) -> Path:
        return self.context.storage.new_asset_dir()

    def submit(self, kind: str, spec: Any) -> JobHandle:
        return self.context.runner.submit(kind, spec)

    def evaluate_authoring_graph(
        self,
        graph: EditGraph,
        *,
        input_path: Path | None = None,
        output_path: Path | None = None,
    ) -> tuple[EvaluationResult, Any]:
        self.context.graphs.save(graph)
        result, mesh = evaluate_graph(
            graph,
            registry=self.context.operations,
            input_path=input_path,
            output_path=output_path,
        )
        self.context.graphs.save_evaluation(result)
        return result, mesh

    def save_authoring_graph(self, graph: EditGraph) -> EditGraph:
        return self.context.graphs.save(graph)

    def submit_authoring_graph_evaluation(
        self,
        graph: EditGraph,
        *,
        input_path: Path | None = None,
        output_path: Path | None = None,
        manifest_dir: Path | None = None,
        asset_id: str | None = None,
    ) -> JobHandle:
        self.context.graphs.save(graph)
        spec = EvaluateGraphRequest(
            graph_id=graph.graph_id,
            input_path=input_path,
            output_path=output_path,
            manifest_dir=manifest_dir,
            asset_id=asset_id,
        )
        return self.context.runner.submit("evaluate_edit_graph", spec)
