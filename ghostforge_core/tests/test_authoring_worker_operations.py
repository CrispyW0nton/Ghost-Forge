"""Worker-backed authoring graph operations."""

from __future__ import annotations

from pathlib import Path

import pytest
import trimesh

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.authoring import (
    EditGraph,
    OperationNode,
    default_operation_registry,
    evaluate_graph,
    evaluate_graph_streaming,
)
from ghostforge_core.manifest import manifest_exists, read_manifest
from ghostforge_core.workers.stub import StubTextTo3DWorker


pytest.importorskip("trimesh")


@pytest.fixture
def ctx(tmp_path: Path):
    context = bootstrap(
        CoreConfig(
            data_root=tmp_path / "data",
            dispatch_jobs=False,
            enable_scheduler=False,
        )
    )
    context.workers.register(StubTextTo3DWorker())
    return context


def _box(path: Path) -> Path:
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(str(path))
    return path


def test_text_to_3d_source_node_uses_worker_and_records_artifacts(ctx, tmp_path):
    out = tmp_path / "out" / "generated.glb"
    graph = EditGraph(
        graph_id="source-graph",
        output_path=str(out),
        nodes=(
            OperationNode(
                id="source",
                kind="generate_text_to_3d",
                params={
                    "prompt": "small brass observatory",
                    "worker": "stub_text_to_3d",
                    "seed": 17,
                },
            ),
        ),
    )

    result, mesh = evaluate_graph(graph, registry=ctx.operations)

    assert result.status == "succeeded"
    assert mesh is not None
    assert out.exists()
    assert result.metadata["source_mode"] == "operation"
    assert result.metadata["vertices"] > 0
    effects = result.metadata["side_effects"]
    assert len(effects) == 1
    effect = effects[0]
    assert effect["operation"] == "generate_text_to_3d"
    assert effect["node_id"] == "source"
    assert effect["worker"] == "stub_text_to_3d"
    assert Path(effect["output_mesh"]).exists()
    assert manifest_exists(effect["asset_dir"])
    manifest = read_manifest(effect["asset_dir"])
    assert manifest.source_prompt == "small brass observatory"
    assert any(step.kind == "text_to_3d" for step in manifest.provenance)


def test_refine_and_texture_worker_nodes_process_current_mesh(ctx, tmp_path):
    base = _box(tmp_path / "base.glb")
    out = tmp_path / "out" / "processed.glb"
    graph = EditGraph(
        graph_id="process-graph",
        base_asset_path=str(base),
        output_path=str(out),
        nodes=(
            OperationNode(
                id="retopo",
                kind="worker_refine_mesh",
                params={
                    "worker": "stub_refine_mesh",
                    "target_face_count": 128,
                    "preserve_uvs": True,
                },
            ),
            OperationNode(
                id="paint",
                kind="worker_texture_mesh",
                params={
                    "prompt": "oxidized teal painted metal",
                    "worker": "stub_texture_mesh",
                    "texture_size": 256,
                },
            ),
        ),
    )

    result, mesh = evaluate_graph(graph, registry=ctx.operations)

    assert result.status == "succeeded"
    assert mesh is not None
    assert out.exists()
    effects = result.metadata["side_effects"]
    operations = [effect["operation"] for effect in effects]
    assert operations == ["worker_refine_mesh", "worker_texture_mesh"]
    for effect in effects:
        assert Path(effect["output_mesh"]).exists()
        assert manifest_exists(effect["asset_dir"])
    texture_effect = effects[-1]
    assert Path(texture_effect["texture_map"]).exists()
    texture_manifest = read_manifest(texture_effect["asset_dir"])
    roles = {artifact.role for artifact in texture_manifest.artifacts}
    assert "texture.base_color" in roles


def test_streaming_text_to_3d_source_node_emits_completed_result(ctx, tmp_path):
    out = tmp_path / "out" / "streamed.glb"
    graph = EditGraph(
        graph_id="stream-source",
        output_path=str(out),
        nodes=(
            OperationNode(
                id="source",
                kind="generate_text_to_3d",
                params={
                    "prompt": "weathered wooden crate",
                    "worker": "stub_text_to_3d",
                    "seed": 3,
                },
            ),
        ),
    )

    events = list(evaluate_graph_streaming(graph, registry=ctx.operations))

    assert [event["event"] for event in events] == [
        "started",
        "step",
        "exported",
        "completed",
    ]
    step = events[1]
    assert step["status"] == "succeeded"
    assert step["vertex_count"] > 0
    completed = events[-1]["result"]
    assert completed["status"] == "succeeded"
    assert completed["metadata"]["source_mode"] == "operation"
    assert completed["metadata"]["side_effects"][0]["operation"] == "generate_text_to_3d"
    assert out.exists()


def test_default_registry_lists_worker_backed_operations():
    kinds = {descriptor.kind for descriptor in default_operation_registry().descriptors()}
    assert {
        "generate_text_to_3d",
        "generate_image_to_3d",
        "worker_refine_mesh",
        "worker_texture_mesh",
    } <= kinds
