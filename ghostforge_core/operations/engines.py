"""Engine handoff operations.

Bridges the engine adapter layer (transport-aware) to the GhostForge
operations layer (job-runner-aware). The dispatch handler:

* Resolves the configured adapter for the requested engine.
* Streams a small set of progress milestones so MCP clients see the
  handoff move from "selected" through "calling" to "done".
* Honours cancellation tokens before invoking the transport. Once the
  engine MCP is mid-call the handoff completes; cancellation can only
  cut in at well-defined seams.
* Returns a JSON-serialisable dict suitable for storage in the job
  store and for direct return through MCP tools.
"""

from __future__ import annotations

from typing import Any

from ..engines import EngineHandoffError, EngineRegistry, EngineHandoffResult
from ..jobs import CancelToken, ProgressReporter
from ..types import SendToEngineRequest


_REGISTRY: EngineRegistry | None = None


def set_registry(registry: EngineRegistry) -> None:
    global _REGISTRY
    _REGISTRY = registry


def _registry() -> EngineRegistry:
    if _REGISTRY is None:
        raise RuntimeError(
            "Engine registry not initialised. Call ghostforge_core.bootstrap() "
            "before submitting send_to_engine jobs."
        )
    return _REGISTRY


def _adapter_for(engine: str):
    registry = _registry()
    try:
        return registry.get(engine)
    except KeyError as exc:
        raise EngineHandoffError(
            f"No engine adapter named '{engine}'. Configured: {registry.names()}"
        ) from exc


def run_send_to_engine(
    spec: SendToEngineRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    adapter = _adapter_for(spec.engine)
    reporter and reporter("select", 5.0, f"selected engine='{spec.engine}'")
    cancel and cancel.throw_if_cancelled()

    probe = adapter.probe()
    reporter and reporter(
        "probe",
        15.0,
        f"transport={probe.transport} configured={probe.configured}",
    )
    if not probe.configured and not spec.dry_run:
        raise EngineHandoffError(
            f"Adapter '{spec.engine}' is not configured "
            f"(transport={probe.transport}); reason: {probe.reason}. "
            "Either configure it (env vars or configure_engine_adapter) "
            "or pass dry_run=True to record a planned handoff."
        )

    cancel and cancel.throw_if_cancelled()
    reporter and reporter(
        "call",
        45.0,
        "dry_run=True (no engine call)" if spec.dry_run else f"calling tool '{adapter.get_config().import_tool}'",
    )

    result: EngineHandoffResult = adapter.send_asset(
        spec.asset_dir,
        target_path=spec.target_path,
        dry_run=spec.dry_run,
        force=spec.force,
        extra_args=spec.extra_args or None,
        audit=spec.audit,
        audit_preset=spec.audit_preset,
    )
    reporter and reporter("done", 100.0, f"delivered to {result.engine}")
    return result.model_dump(mode="json")


__all__ = ["run_send_to_engine", "set_registry"]
