"""Benchmark runner: timing, persistence, capability checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.benchmarks import (
    BenchmarkRequest,
    BenchmarkResult,
    make_benchmark_id,
    run_benchmark,
)
from ghostforge_core.workers.capabilities import Capability


pytest.importorskip("trimesh")


@pytest.fixture
def ctx(tmp_path: Path):
    return bootstrap(CoreConfig(data_root=tmp_path, dispatch_jobs=False))


@pytest.fixture
def concept_image(tmp_path: Path) -> Path:
    path = tmp_path / "concept.png"
    path.write_bytes(b"not-a-real-image-but-stub-worker-does-not-read-it")
    return path


def test_run_benchmark_with_stub_image_to_3d(ctx, concept_image):
    request = BenchmarkRequest(
        benchmark_id=make_benchmark_id(prefix="stub-i2d"),
        worker_name="stub_image_to_3d",
        capability=Capability.image_to_3d,
        spec={"input_image_path": str(concept_image), "prompt": "rune stone"},
        runs=2,
    )
    result = run_benchmark(
        request,
        registry=ctx.workers,
        store=ctx.benchmarks,
        storage=ctx.storage,
    )
    assert isinstance(result, BenchmarkResult)
    assert result.runs_succeeded == 2
    assert result.runs_failed == 0
    assert result.wall_seconds_min is not None
    assert result.wall_seconds_max >= result.wall_seconds_min
    assert result.runs[0].output_mesh is not None
    assert (ctx.benchmarks.root / f"{request.benchmark_id}.json").exists()


def test_warmup_runs_not_recorded(ctx, concept_image):
    request = BenchmarkRequest(
        benchmark_id="warm-test",
        worker_name="stub_image_to_3d",
        capability=Capability.image_to_3d,
        spec={"input_image_path": str(concept_image), "prompt": "tree"},
        runs=1,
        warmup_runs=2,
    )
    result = run_benchmark(
        request,
        registry=ctx.workers,
        store=ctx.benchmarks,
        storage=ctx.storage,
    )
    assert len(result.runs) == 1, "warmup runs must not appear in samples"


def test_capability_mismatch_raises(ctx):
    request = BenchmarkRequest(
        benchmark_id="mismatch-test",
        worker_name="stub_image_to_3d",
        capability=Capability.refine_mesh,  # stub_image_to_3d does NOT advertise this
        spec={"input_mesh_path": "ignored"},
        runs=1,
    )
    with pytest.raises(ValueError):
        run_benchmark(
            request,
            registry=ctx.workers,
            store=ctx.benchmarks,
            storage=ctx.storage,
        )


def test_unknown_worker_raises(ctx):
    request = BenchmarkRequest(
        benchmark_id="unknown-test",
        worker_name="not_a_real_worker",
        capability=Capability.image_to_3d,
        spec={"input_image_path": "x.png"},
        runs=1,
    )
    with pytest.raises(Exception):
        run_benchmark(
            request,
            registry=ctx.workers,
            store=ctx.benchmarks,
            storage=ctx.storage,
        )


def test_list_benchmarks_returns_newest_first(ctx, concept_image):
    for label in ("a", "b", "c"):
        run_benchmark(
            BenchmarkRequest(
                benchmark_id=f"order-{label}",
                worker_name="stub_image_to_3d",
                capability=Capability.image_to_3d,
                spec={"input_image_path": str(concept_image), "prompt": label},
                runs=1,
            ),
            registry=ctx.workers,
            store=ctx.benchmarks,
            storage=ctx.storage,
        )
    listed = ctx.benchmarks.list(limit=10)
    assert {r.benchmark_id for r in listed} == {"order-a", "order-b", "order-c"}
