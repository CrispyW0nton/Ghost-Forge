"""Worker protocol, registry, and selection errors."""

from __future__ import annotations

import threading
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

from ..types import FrozenModel
from .capabilities import Capability
from .resources import CPU_ONLY_RESOURCES, WorkerResources


class WorkerUnavailable(RuntimeError):
    """Raised by a worker's :meth:`Worker.run` when it cannot execute today.

    Workers should perform the same checks they did in :meth:`Worker.probe`
    so failures surface with a consistent reason regardless of whether the
    caller probed first.
    """


class WorkerSelectionError(RuntimeError):
    """Raised when no worker can be selected for a capability.

    This is the explicit signal to agents and UI: "you asked for X, no
    runnable worker advertises X". Always include enough context for the
    user to fix it (install extras, switch worker, fall back to stub).
    """


class ProbeResult(FrozenModel):
    """Result of asking a worker whether it can run on this host.

    Probes must be cheap — import checks, GPU detection, weight-file
    presence. Any operation that can fail in seconds (downloading weights,
    loading a checkpoint into VRAM) belongs in :meth:`Worker.run`, not
    here, so a UI can probe a hundred workers in well under a second.
    """

    name: str
    runnable: bool
    reason: str | None = None
    missing: list[str] = Field(default_factory=list)
    device: str | None = None
    gpu_index: int | None = None
    available_vram_mb: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerDescriptor(FrozenModel):
    """Static description of a worker; safe to send across MCP."""

    name: str
    capabilities: list[Capability]
    priority: int
    license: str | None = None
    description: str = ""
    homepage: str | None = None
    paper_url: str | None = None
    weights_url: str | None = None
    is_stub: bool = False
    resources: WorkerResources = Field(default_factory=lambda: CPU_ONLY_RESOURCES)
    required_models: list[str] = Field(default_factory=list)


@runtime_checkable
class Worker(Protocol):
    """Common surface for a model worker.

    The protocol intentionally avoids subclassing to keep the contract loose
    — a worker only needs the listed attributes and methods. Use
    :func:`WorkerRegistry.register_class` for the common case where the
    worker is a no-state class, or instantiate directly when state matters
    (e.g. preloading weights for the duration of a session).
    """

    name: str
    capabilities: list[Capability]
    priority: int
    license: str | None
    description: str
    homepage: str | None
    paper_url: str | None
    weights_url: str | None
    is_stub: bool
    resources: WorkerResources
    required_models: list[str]

    def probe(self) -> ProbeResult: ...
    def run(self, spec: BaseModel, reporter: Any, cancel: Any) -> dict[str, Any]: ...


class WorkerRegistry:
    """Directory of available workers indexed by name and capability.

    Probes are not cached automatically. Callers that hammer ``select`` in
    a tight loop should snapshot probe results themselves — the registry
    re-probes each call so a freshly-installed extra (e.g. CUDA driver
    update) takes effect on the next request.
    """

    def __init__(self) -> None:
        self._workers: dict[str, Worker] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, worker: Worker) -> None:
        with self._lock:
            self._workers[worker.name] = worker

    def unregister(self, name: str) -> None:
        with self._lock:
            self._workers.pop(name, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Worker:
        with self._lock:
            if name not in self._workers:
                raise WorkerSelectionError(f"Unknown worker: {name!r}")
            return self._workers[name]

    def all(self) -> list[Worker]:
        with self._lock:
            return list(self._workers.values())

    def for_capability(self, capability: Capability) -> list[Worker]:
        with self._lock:
            return [w for w in self._workers.values() if capability in w.capabilities]

    def describe(self, worker: Worker) -> WorkerDescriptor:
        return WorkerDescriptor(
            name=worker.name,
            capabilities=list(worker.capabilities),
            priority=worker.priority,
            license=getattr(worker, "license", None),
            description=getattr(worker, "description", ""),
            homepage=getattr(worker, "homepage", None),
            paper_url=getattr(worker, "paper_url", None),
            weights_url=getattr(worker, "weights_url", None),
            is_stub=getattr(worker, "is_stub", False),
            resources=getattr(worker, "resources", CPU_ONLY_RESOURCES),
            required_models=list(getattr(worker, "required_models", [])),
        )

    # ------------------------------------------------------------------
    # Probing
    # ------------------------------------------------------------------

    def probe_all(self) -> list[ProbeResult]:
        return [w.probe() for w in self.all()]

    def probe(self, name: str) -> ProbeResult:
        return self.get(name).probe()

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(
        self,
        capability: Capability,
        *,
        name: str | None = None,
        allow_stub: bool = True,
    ) -> Worker:
        """Pick a runnable worker for ``capability``.

        Selection rules:

        * If ``name`` is given, that exact worker must exist, advertise the
          capability, and probe ``runnable=True``. Otherwise raise.
        * Otherwise rank all workers advertising ``capability`` by
          ``priority`` (descending), keep only those that probe runnable,
          and return the highest. Stubs are included unless
          ``allow_stub=False``.
        """
        if name is not None:
            worker = self.get(name)
            if capability not in worker.capabilities:
                raise WorkerSelectionError(
                    f"Worker {name!r} does not advertise capability {capability.value!r}"
                )
            probe = worker.probe()
            if not probe.runnable:
                raise WorkerSelectionError(
                    f"Worker {name!r} not runnable: {probe.reason or 'unknown reason'}"
                )
            return worker

        candidates = self.for_capability(capability)
        if not allow_stub:
            candidates = [w for w in candidates if not getattr(w, "is_stub", False)]

        ranked: list[tuple[Worker, ProbeResult]] = []
        for worker in candidates:
            probe = worker.probe()
            if probe.runnable:
                ranked.append((worker, probe))

        if not ranked:
            raise WorkerSelectionError(
                f"No runnable worker advertises capability {capability.value!r}. "
                f"Probe a worker individually for installation guidance."
            )

        ranked.sort(key=lambda item: item[0].priority, reverse=True)
        return ranked[0][0]


__all__ = [
    "CPU_ONLY_RESOURCES",
    "ProbeResult",
    "Worker",
    "WorkerDescriptor",
    "WorkerRegistry",
    "WorkerResources",
    "WorkerSelectionError",
    "WorkerUnavailable",
]
