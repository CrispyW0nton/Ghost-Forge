from __future__ import annotations

from ghostforge_core import CoreConfig
from ghostforge_core.authoring import EditGraph, OperationNode
from ghostforge_core.manifest import ManifestBuilder, read_manifest
from ghostforge_qt.services.core_bridge import CoreBridge
import trimesh


def test_core_bridge_reports_worker_capability_honestly(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    rows = bridge.list_workers()
    names = {row.name for row in rows}

    assert "stub_image_to_3d" in names
    assert "stub_texture_mesh" in names
    assert any(row.runnable for row in rows)
    assert any(row.is_stub and row.runnable for row in rows)


def test_core_bridge_runtime_snapshot_includes_core_domains(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    snapshot = bridge.runtime_snapshot()

    assert snapshot.data_root == tmp_path.resolve()
    assert snapshot.kb_backend
    assert snapshot.kb_embedder
    assert len(snapshot.workers) >= 1
    assert {engine.name for engine in snapshot.engines} == {"unity", "unreal"}


def test_core_bridge_lists_authoring_operations_with_worker_status(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    rows = {row.kind: row for row in bridge.list_operations()}

    assert rows["recenter"].status == "available"
    assert rows["generate_image_to_3d"].operation_type == "source"
    assert rows["generate_image_to_3d"].capability == "image_to_3d"
    assert rows["worker_texture_mesh"].operation_type == "worker"
    assert rows["worker_texture_mesh"].capability == "texture_mesh"
    assert rows["worker_texture_mesh"].status in {"runnable", "stub", "missing"}
    assert rows["worker_texture_mesh"].parameter_presets
    assert rows["worker_texture_mesh"].parameter_presets[0]["label"] == "Realtime 1K"


def test_core_bridge_submits_authoring_graph_evaluation_job(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))
    graph = EditGraph(
        graph_id="qt_job_graph",
        base_asset_path=str(tmp_path / "missing.glb"),
        nodes=(OperationNode(id="n1", kind="recenter"),),
    )

    handle = bridge.submit_authoring_graph_evaluation(graph)

    assert handle.kind == "evaluate_edit_graph"
    assert handle.status.value == "pending"
    assert bridge.context.graphs.load("qt_job_graph").nodes[0].kind == "recenter"


def test_core_bridge_submits_audit_asset_job(tmp_path):
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path, dispatch_jobs=False))

    handle = bridge.submit_audit_asset(tmp_path / "asset", run_gltf_validator=False)

    assert handle.kind == "audit_asset"
    assert handle.status.value == "pending"


def test_core_bridge_creates_offline_engine_export_bridge(tmp_path):
    mesh_path = tmp_path / "cube.glb"
    trimesh.creation.box(extents=(1, 1, 1)).export(mesh_path)
    asset_dir = tmp_path / "asset"
    (
        ManifestBuilder.for_dir(asset_dir, asset_id="cube_asset")
        .with_name("Cube")
        .with_geometry_from_mesh(mesh_path)
        .with_validation_from_mesh(mesh_path)
        .add_artifact_from_path(mesh_path, role="mesh.primary")
        .write()
    )
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    _package, package_path = bridge.create_engine_export_bridge(
        asset_dir,
        target_engine="unity",
        bridge_dir=tmp_path / "bridges",
    )

    assert package_path.exists()
    assert package_path.name == "ghostforge_bridge_unity.json"
    manifest = read_manifest(asset_dir)
    assert any(target.engine.value == "unity" for target in manifest.engine_targets)
    assert manifest.custom["engine_export_bridges"][-1]["target_engine"] == "unity"


def test_core_bridge_plans_engine_retarget_graph(tmp_path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(mesh_path)
    (
        ManifestBuilder.for_dir(asset_dir, asset_id="hero_box")
        .with_name("Hero Box")
        .with_geometry_from_mesh(mesh_path)
        .with_validation_from_mesh(mesh_path)
        .add_artifact_from_path(mesh_path, role="mesh.primary")
        .write()
    )
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    graph, report = bridge.plan_engine_retarget_graph(
        asset_dir,
        target_engine="unreal",
        base_name="HeroBox",
        graph_id="qt_unreal_retarget",
        output_path=tmp_path / "retargeted.glb",
    )

    assert graph.graph_id == "qt_unreal_retarget"
    assert graph.output_path.endswith("retargeted.glb")
    assert graph.nodes
    assert any(node.kind.startswith("retarget_") for node in graph.nodes)
    assert report.issues
    assert bridge.context.graphs.load("qt_unreal_retarget").nodes == graph.nodes


def test_core_bridge_lints_engine_retarget(tmp_path):
    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1, 2, 3)).export(mesh_path)
    (
        ManifestBuilder.for_dir(asset_dir, asset_id="hero_box")
        .with_name("Hero Box")
        .with_geometry_from_mesh(mesh_path)
        .with_validation_from_mesh(mesh_path)
        .add_artifact_from_path(mesh_path, role="mesh.primary")
        .write()
    )
    bridge = CoreBridge(config=CoreConfig(data_root=tmp_path / "data", dispatch_jobs=False))

    report = bridge.lint_engine_retarget(asset_dir, target_engine="unreal")

    assert report.preset == "unreal"
    assert any(issue.rule.startswith("retarget.") for issue in report.issues)
