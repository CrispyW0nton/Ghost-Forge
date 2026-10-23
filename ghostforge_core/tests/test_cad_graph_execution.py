from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.cad import (
    CadGraphEntity,
    CadGraphReference,
    CadOperationGraph,
    CadSelectionItem,
    CadSelectionSet,
    build_default_cad_registry,
    cad_operation_node_from_descriptor,
    execute_cad_operation_graph,
)
from ghostforge_core.manifest import read_manifest


def _cube_mesh(path: Path) -> Path:
    trimesh = pytest.importorskip("trimesh")
    mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    mesh.export(str(path))
    return path


def _mesh_selection(object_id: str = "mesh_cube") -> CadSelectionSet:
    return CadSelectionSet(
        items=(
            CadSelectionItem(
                object_id=object_id,
                object_kind="mesh",
                selection_kind="object",
                topology_id=object_id,
            ),
        ),
        active_object_id=object_id,
    )


def test_execute_cad_operation_graph_emits_mesh_manifest_quality_and_lineage(tmp_path):
    registry = build_default_cad_registry()
    descriptor = registry.get("transform")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_transform",
        parameters={"translate": [2.0, 0.0, 0.0], "scale": 1.0},
        selection=_mesh_selection(),
        inputs=(CadGraphReference(ref_id="mesh_in", entity_id="mesh_cube", role="input"),),
        outputs=(CadGraphReference(ref_id="mesh_out", entity_id="mesh_cube", role="output"),),
    )
    graph = CadOperationGraph(
        graph_id="cad_graph_transform_exec",
        nodes=(node,),
        entity_table={"mesh_cube": CadGraphEntity(entity_id="mesh_cube", kind="mesh")},
    )
    input_mesh = _cube_mesh(tmp_path / "cube.glb")
    output_dir = tmp_path / "asset"

    result = execute_cad_operation_graph(
        graph,
        input_mesh_path=input_mesh,
        output_dir=output_dir,
        output_format="glb",
        asset_id="cad_exec_asset",
    )

    assert result.status == "succeeded"
    assert result.validation.ok is True
    assert result.output_mesh_path is not None and result.output_mesh_path.exists()
    assert result.manifest_path is not None and result.manifest_path.exists()
    assert result.mesh_quality_report is not None
    assert result.mesh_quality_report.vertex_count == 8
    assert result.mesh_quality_report.face_count == 12
    assert result.mesh_quality_report.topology_lineage_record_count == 1
    assert "lineage:n_transform" in result.graph.topology_table
    assert result.steps[0].lineage_record_id == "lineage:n_transform"
    assert result.steps[0].topology_delta.result_summary["bounds_changed"] is True

    manifest = read_manifest(output_dir)
    assert manifest.asset_id == "cad_exec_asset"
    assert manifest.geometry is not None
    assert manifest.geometry.vertex_count == 8
    assert manifest.provenance[-1].kind == "cad_operation_graph"
    assert manifest.custom["cad_operation_graph"]["graph_id"] == graph.graph_id
    assert manifest.custom["cad_execution"]["step_count"] == 1
    assert manifest.custom["cad_mesh_quality_report"]["source_lineage_coverage"] == 1.0

    trimesh = pytest.importorskip("trimesh")
    output_mesh = trimesh.load(str(result.output_mesh_path), force="mesh", process=False)
    assert output_mesh.bounds[0][0] > 1.0


def test_execute_cad_operation_graph_creates_source_box_without_input_mesh(tmp_path):
    registry = build_default_cad_registry()
    descriptor = registry.get("create_box")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_box",
        parameters={"extents": [2.0, 3.0, 4.0], "center": [1.0, 2.0, 3.0]},
        outputs=(CadGraphReference(ref_id="box_out", entity_id="box_mesh", role="output"),),
    )
    graph = CadOperationGraph(graph_id="cad_graph_box_exec", nodes=(node,))
    output_dir = tmp_path / "box_asset"

    result = execute_cad_operation_graph(
        graph,
        output_dir=output_dir,
        output_format="glb",
        asset_id="cad_box_asset",
    )

    assert result.status == "succeeded"
    assert result.validation.ok is True
    assert result.output_mesh_path is not None and result.output_mesh_path.exists()
    assert result.manifest_path is not None and result.manifest_path.exists()
    assert result.mesh_quality_report is not None
    assert result.mesh_quality_report.vertex_count == 8
    assert result.mesh_quality_report.face_count == 12
    assert result.steps[0].topology_delta.before.vertex_count == 0
    assert result.steps[0].topology_delta.after.vertex_count == 8
    assert result.steps[0].topology_delta.lineage[0].relation == "created"
    assert result.steps[0].topology_delta.lineage[0].source_id == "source:n_box"
    assert result.graph.entity_table["box_mesh"].producing_node_id == "n_box"
    assert result.graph.topology_table["lineage:n_box"].created_refs == ("box_mesh",)

    manifest = read_manifest(output_dir)
    assert manifest.asset_id == "cad_box_asset"
    assert manifest.custom["cad_operation_graph"]["entity_table"]["box_mesh"]["producing_node_id"] == "n_box"
    assert manifest.custom["cad_execution"]["steps"][0]["topology_delta"]["lineage"][0]["relation"] == "created"

    trimesh = pytest.importorskip("trimesh")
    output_mesh = trimesh.load(str(result.output_mesh_path), force="mesh", process=False)
    assert output_mesh.vertices.shape[0] == 8
    assert output_mesh.faces.shape[0] == 12
    assert pytest.approx(float(output_mesh.extents.max())) == 4.0


def test_execute_cad_operation_graph_blocks_planned_kernel_nodes_without_output(tmp_path):
    registry = build_default_cad_registry()
    descriptor = registry.get("extrude")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_extrude",
        parameters={"distance": 1.0, "operation": "new_body"},
        selection=CadSelectionSet(
            items=(
                CadSelectionItem(
                    object_id="solid_cube",
                    object_kind="mesh",
                    selection_kind="face",
                    topology_id="F_top",
                ),
            ),
            active_object_id="solid_cube",
        ),
    )
    graph = CadOperationGraph(graph_id="cad_graph_planned", nodes=(node,))
    input_mesh = _cube_mesh(tmp_path / "cube.glb")

    result = execute_cad_operation_graph(
        graph,
        input_mesh_path=input_mesh,
        output_dir=tmp_path / "blocked",
    )

    assert result.status == "blocked"
    assert result.output_mesh_path is None
    assert result.manifest_path is None
    assert "handler.planned" in {diagnostic.code for diagnostic in result.diagnostics}
    assert not (tmp_path / "blocked" / "asset_manifest.json").exists()
