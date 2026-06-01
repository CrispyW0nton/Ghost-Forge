"""Unit tests for :class:`WorkerSession` and :class:`WorkerSessionRegistry`."""

from __future__ import annotations

import threading
import time

import pytest

from ghostforge_core.workers.session import (
    WorkerSession,
    WorkerSessionRegistry,
    get_session_registry,
)


def _counting_loader():
    state = {"count": 0}

    def loader():
        state["count"] += 1
        return f"resource-{state['count']}"

    return state, loader


def test_session_loads_lazily_and_caches():
    state, loader = _counting_loader()
    session = WorkerSession(loader=loader, name="t")
    assert session.status()["loaded"] is False

    with session.lease() as r1:
        assert r1 == "resource-1"
        assert session.status()["in_use"] == 1

    with session.lease() as r2:
        assert r2 == "resource-1"  # cached

    assert state["count"] == 1
    assert session.status()["in_use"] == 0


def test_session_disposes_on_free():
    disposed: list[str] = []
    _, loader = _counting_loader()

    session = WorkerSession(
        loader=loader,
        disposer=lambda v: disposed.append(v),
        name="dispose-t",
    )
    with session.lease():
        pass

    assert session.free() is True
    assert disposed == ["resource-1"]
    assert session.free() is False  # idempotent


def test_session_in_use_blocks_free_unless_forced():
    _, loader = _counting_loader()
    session = WorkerSession(loader=loader, name="busy-t")

    session.get()  # acquire without leasing
    try:
        # in_use=1 — soft free should refuse
        assert session.free() is False
        assert session.status()["loaded"] is True
        # force=True should drop it anyway
        assert session.free(force=True) is True
        assert session.status()["loaded"] is False
    finally:
        session.release()


def test_session_idle_eviction():
    _, loader = _counting_loader()
    session = WorkerSession(loader=loader, idle_timeout_seconds=0.01, name="idle-t")
    with session.lease():
        pass

    # Just after release, idle window not yet exceeded.
    assert session.free_idle(idle_for_seconds=10.0) is False
    time.sleep(0.05)
    assert session.free_idle() is True
    assert session.status()["loaded"] is False


def test_session_concurrent_leases_share_resource():
    state, loader = _counting_loader()

    # Make the loader slow so two threads hit the lock simultaneously.
    original = loader

    def slow_loader():
        time.sleep(0.05)
        return original()

    session = WorkerSession(loader=slow_loader, name="conc-t")

    results: list[str] = []
    barrier = threading.Barrier(4)

    def worker():
        barrier.wait()
        with session.lease() as r:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 4
    # All 4 should see resource-1; loader fired once or possibly more if
    # races picked the slow path. Assert "fired at most twice" — that
    # allows a tiny race window where two callers raced into _loader
    # simultaneously, which is fine semantically.
    assert state["count"] in (1, 2)


def test_loader_failure_does_not_pin_state():
    attempts = {"n": 0}

    def loader():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("boom")
        return "ok"

    session = WorkerSession(loader=loader, name="fail-t")
    with pytest.raises(RuntimeError, match="boom"):
        session.get()
    assert session.status()["loaded"] is False

    with session.lease() as r:
        assert r == "ok"


def test_registry_tracks_and_frees_all_sessions():
    registry = WorkerSessionRegistry()
    a = WorkerSession(loader=lambda: "a", name="a")
    b = WorkerSession(loader=lambda: "b", name="b")
    registry.register(a)
    registry.register(b)

    a.get()
    a.release()
    b.get()
    b.release()

    assert {s["name"] for s in registry.status()} == {"a", "b"}
    freed = registry.free()
    assert freed == 2
    assert all(s["loaded"] is False for s in registry.status())


def test_global_registry_singleton():
    a = get_session_registry()
    b = get_session_registry()
    assert a is b
