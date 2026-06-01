from __future__ import annotations

from PySide6 import QtCore

from ghostforge_core.types import JobHandle

from .core_bridge import CoreBridge


class JobController(QtCore.QObject):
    """Polls the core job store and exposes Qt signals for panels."""

    jobsChanged = QtCore.Signal(list)
    error = QtCore.Signal(str)

    def __init__(self, bridge: CoreBridge, *, interval_ms: int = 1000) -> None:
        super().__init__()
        self.bridge = bridge
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.refresh)

    def start(self) -> None:
        self._timer.start()
        self.refresh()

    def stop(self) -> None:
        self._timer.stop()

    @QtCore.Slot()
    def refresh(self) -> None:
        try:
            jobs = self.bridge.list_jobs(limit=100)
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            self.error.emit(str(exc))
            return
        self.jobsChanged.emit(jobs)

    @QtCore.Slot(str)
    def cancel(self, job_id: str) -> None:
        try:
            self.bridge.cancel_job(job_id)
        except Exception as exc:
            self.error.emit(str(exc))
        self.refresh()
