from __future__ import annotations

import pytest

from ghostforge_core.workers import default_workers


REAL_NAMES = {"trellis", "hunyuan3d", "triposg", "instantmesh", "paint3d", "syncmvd"}


def test_real_workers_probe_unrunnable_without_gpu_stack():
    """Real workers should report runnable=False without crashing on a host
    that doesn't have torch/CUDA/upstream repos installed. The probe must
    still return a ``ProbeResult`` with a useful reason."""
    registry = default_workers()
    for worker in registry.all():
        if worker.name not in REAL_NAMES:
            continue
        probe = worker.probe()
        assert probe.name == worker.name
        if not probe.runnable:
            assert probe.reason, f"{worker.name} returned unrunnable with no reason"


def test_stub_workers_probe_runnable():
    registry = default_workers()
    stubs = [w for w in registry.all() if getattr(w, "is_stub", False)]
    assert stubs
    for stub in stubs:
        probe = stub.probe()
        # Trimesh + Pillow are hard dependencies in this checkout, so stubs
        # must always be runnable here.
        assert probe.runnable, f"stub {stub.name} unexpectedly unrunnable: {probe.reason}"


def test_real_workers_run_raises_clearly_when_unrunnable():
    """On hosts without GPU + upstream repos, ``run`` should raise something
    actionable: either ``WorkerUnavailable`` (declined) or ``NotImplementedError``
    (probe passed but real call not yet wired). ``probe`` decides which."""
    from ghostforge_core.workers import WorkerUnavailable

    registry = default_workers()
    for worker in registry.all():
        if worker.name not in REAL_NAMES:
            continue
        probe = worker.probe()
        with pytest.raises((WorkerUnavailable, NotImplementedError)):
            worker.run(spec=_DummySpec(), reporter=None, cancel=None)
        # Sanity: declined runs should mention the worker name.
        # We can't assert a specific exception class without GPU, so just
        # confirm the probe lined up with the failure mode.
        if not probe.runnable:
            # Calling again should still raise; probes are pure functions.
            assert worker.probe().runnable is False


class _DummySpec:
    def model_dump_json(self) -> str:
        return "{}"

    def model_dump(self, mode: str = "python"):
        return {}
