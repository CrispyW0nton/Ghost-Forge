from __future__ import annotations

import pytest

from ghostforge_core.workers import (
    Capability,
    ProbeResult,
    Worker,
    WorkerRegistry,
    WorkerSelectionError,
    default_workers,
)


class _FakeWorker:
    def __init__(
        self,
        name: str,
        capabilities,
        priority: int,
        runnable: bool = True,
        is_stub: bool = False,
        reason: str | None = None,
    ) -> None:
        self.name = name
        self.capabilities = list(capabilities)
        self.priority = priority
        self.license = "MIT"
        self.description = name
        self.homepage = None
        self.paper_url = None
        self.weights_url = None
        self.is_stub = is_stub
        self._runnable = runnable
        self._reason = reason

    def probe(self) -> ProbeResult:
        return ProbeResult(
            name=self.name,
            runnable=self._runnable,
            reason=self._reason,
            metadata={"is_stub": self.is_stub},
        )

    def run(self, spec, reporter, cancel):  # pragma: no cover - selection-only test
        return {"worker": self.name, "output_mesh": "/tmp/x.glb"}


def test_registry_round_trip():
    reg = WorkerRegistry()
    a = _FakeWorker("a", [Capability.image_to_3d], priority=10)
    reg.register(a)
    assert reg.get("a") is a
    assert [w.name for w in reg.all()] == ["a"]
    assert reg.for_capability(Capability.image_to_3d) == [a]
    assert reg.for_capability(Capability.text_to_3d) == []


def test_registry_picks_highest_priority_runnable():
    reg = WorkerRegistry()
    high = _FakeWorker("high", [Capability.image_to_3d], priority=50)
    mid = _FakeWorker("mid", [Capability.image_to_3d], priority=30)
    low_unrunnable = _FakeWorker(
        "low_unrunnable",
        [Capability.image_to_3d],
        priority=80,
        runnable=False,
        reason="GPU missing",
    )
    reg.register(high)
    reg.register(mid)
    reg.register(low_unrunnable)

    selected = reg.select(Capability.image_to_3d)
    assert selected.name == "high"


def test_registry_explicit_name_must_be_runnable():
    reg = WorkerRegistry()
    reg.register(
        _FakeWorker(
            "no_gpu",
            [Capability.image_to_3d],
            priority=80,
            runnable=False,
            reason="GPU missing",
        )
    )
    with pytest.raises(WorkerSelectionError) as exc_info:
        reg.select(Capability.image_to_3d, name="no_gpu")
    assert "GPU missing" in str(exc_info.value)


def test_registry_explicit_name_capability_mismatch():
    reg = WorkerRegistry()
    reg.register(_FakeWorker("text_only", [Capability.text_to_3d], priority=20))
    with pytest.raises(WorkerSelectionError):
        reg.select(Capability.image_to_3d, name="text_only")


def test_registry_allow_stub_false_skips_stub():
    reg = WorkerRegistry()
    real = _FakeWorker(
        "real",
        [Capability.image_to_3d],
        priority=50,
        runnable=False,
        reason="GPU missing",
    )
    stub = _FakeWorker("stub", [Capability.image_to_3d], priority=0, is_stub=True)
    reg.register(real)
    reg.register(stub)

    assert reg.select(Capability.image_to_3d).name == "stub"
    with pytest.raises(WorkerSelectionError):
        reg.select(Capability.image_to_3d, allow_stub=False)


def test_registry_no_runnable_raises_helpful():
    reg = WorkerRegistry()
    reg.register(
        _FakeWorker(
            "x",
            [Capability.image_to_3d],
            priority=40,
            runnable=False,
            reason="boom",
        )
    )
    with pytest.raises(WorkerSelectionError) as exc_info:
        reg.select(Capability.image_to_3d)
    assert "image_to_3d" in str(exc_info.value)


def test_default_workers_includes_all_named_models():
    registry = default_workers()
    names = {w.name for w in registry.all()}
    expected_real = {
        "trellis",
        "hunyuan3d",
        "tripo_api",
        "triposg",
        "instantmesh",
        "paint3d",
        "syncmvd",
    }
    expected_stubs = {
        "stub_image_to_3d",
        "stub_texture_mesh",
        "stub_refine_mesh",
    }
    assert expected_real.issubset(names)
    assert expected_stubs.issubset(names)
    assert "primitive_text_to_3d" not in names
    assert "stub_text_to_3d" not in names


def test_default_workers_satisfy_protocol():
    registry = default_workers()
    for worker in registry.all():
        assert isinstance(worker, Worker)
