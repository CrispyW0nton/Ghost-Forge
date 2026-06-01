"""Audit operation handler.

Wraps :func:`ghostforge_core.audit.audit_asset` for the JobRunner. The
handler emits coarse progress events as each rule starts so MCP clients
streaming via ``wait_for_job`` see the audit advance through its rule
set, not just freeze on "running" until everything completes.
"""

from __future__ import annotations

from typing import Any

from ..audit import audit_asset
from ..jobs import CancelToken, ProgressReporter
from ..types import AuditAssetRequest


def run_audit(
    spec: AuditAssetRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> dict[str, Any]:
    def _progress(stage: str, percent: float, message: str) -> None:
        if reporter is not None:
            reporter(stage, percent, message)
        if cancel is not None:
            cancel.throw_if_cancelled()

    report = audit_asset(
        spec.asset_dir,
        preset=spec.preset,
        run_gltf_validator=spec.run_gltf_validator,
        persist=spec.persist,
        job_id=spec.job_id,
        progress=_progress,
    )
    return report.model_dump(mode="json")


__all__ = ["run_audit"]
