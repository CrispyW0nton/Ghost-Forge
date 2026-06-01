from __future__ import annotations

from pathlib import Path

from ghostforge_core.jobs import CancelToken, ProgressReporter
from ghostforge_core.types import FrozenModel


class ExportRequest(FrozenModel):
    source_path: Path
    destination_path: Path


class ExportResult(FrozenModel):
    path: Path


def run(
    spec: ExportRequest,
    reporter: ProgressReporter | None = None,
    cancel: CancelToken | None = None,
) -> ExportResult:
    reporter and reporter("Exporting asset", 10)
    cancel and cancel.throw_if_cancelled()
    spec.destination_path.parent.mkdir(parents=True, exist_ok=True)
    spec.destination_path.write_bytes(spec.source_path.read_bytes())
    reporter and reporter("Export complete", 100)
    return ExportResult(path=spec.destination_path)
