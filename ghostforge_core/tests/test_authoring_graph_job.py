from __future__ import annotations

import time
from pathlib import Path

import pytest

from ghostforge_core import CoreConfig, EvaluateGraphRequest, bootstrap
from ghostforge_core.authoring import EditGraph, OperationNode


def test_evaluate_edit_graph_job_persists_result(tmp_path: Path):
    trimesh = pytest.importorskip("trimesh")

    ctx = bootstrap(CoreConfig(data_root=tmp_path / "data", dispatch_jobs=True))
    base = tmp_path / "cube.glb"
    out = tmp_path / "out.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(base))
    ctx.graphs.save(
        EditGraph(
            graph_id="job_graph",
            base_asset_path=str(base),
            output_path=str(out),
            nodes=(OperationNode(id="n1", kind="recenter"),),
        )
    )

    try:
        handle = ctx.runner.submit(
            "evaluate_edit_graph",
            EvaluateGraphRequest(graph_id="job_graph"),
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            handle = ctx.jobs.get(handle.id)
            if handle.status.value in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.05)
    finally:
        ctx.runner.shutdown(wait=True)

    assert handle.status.value == "succeeded", handle
    assert out.exists()
    assert handle.result is not None
    assert handle.result["status"] == "succeeded"
    assert handle.result["graph"]["graph_id"] == "job_graph"
    stored = ctx.graphs.load_evaluation("job_graph")
    assert stored is not None
    assert stored.status == "succeeded"
