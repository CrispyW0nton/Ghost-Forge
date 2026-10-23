from __future__ import annotations

from ghostforge_core.cad import (
    CadGraphEntity,
    CadGraphReference,
    CadOperationEdge,
    CadOperationGraph,
    CadSelectionItem,
    CadSelectionSet,
    build_default_cad_registry,
    cad_operation_node_from_descriptor,
    validate_cad_operation_graph,
)


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


def test_cad_operation_graph_validates_descriptor_backed_replay_plan() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("transform")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_transform",
        parameters={"translate": [1.0, 0.0, 0.0], "scale": 1.0},
        selection=_mesh_selection(),
        inputs=(CadGraphReference(ref_id="mesh_in", entity_id="mesh_cube", role="input"),),
        outputs=(CadGraphReference(ref_id="mesh_out", entity_id="mesh_cube", role="output"),),
    )
    graph = CadOperationGraph(
        graph_id="cad_graph_transform",
        nodes=(node,),
        entity_table={"mesh_cube": CadGraphEntity(entity_id="mesh_cube", kind="mesh")},
    )

    report = validate_cad_operation_graph(graph, registry)

    assert report.ok is True
    assert report.status == "valid"
    assert [step.node_id for step in report.replay_plan] == ["n_transform"]
    assert report.replay_plan[0].parameter_snapshot["translate"] == [1.0, 0.0, 0.0]
    assert node.selection_contract["requires_active_object"] is True
    assert node.undo_token.startswith("n_transform:")


def test_cad_operation_graph_validates_source_primitive_without_input_entity() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("create_box")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_box",
        parameters={"extents": [2.0, 1.0, 0.5], "center": [0.0, 0.5, 0.0]},
        outputs=(CadGraphReference(ref_id="box_out", entity_id="box_mesh", role="output"),),
    )
    graph = CadOperationGraph(graph_id="cad_graph_box_source", nodes=(node,))

    report = validate_cad_operation_graph(graph, registry)

    assert report.ok is True
    assert report.status == "valid"
    assert [step.node_id for step in report.replay_plan] == ["n_box"]
    assert report.replay_plan[0].output_refs == ("box_out",)
    assert node.selection_contract["requires_active_object"] is False


def test_cad_operation_graph_rejects_unknown_ai_parameters() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("transform")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_bad_param",
        parameters={"translate": [0.0, 0.0, 0.0], "imaginary_slider": 7},
        selection=_mesh_selection(),
    )
    graph = CadOperationGraph(graph_id="cad_graph_bad_param", nodes=(node,))

    report = validate_cad_operation_graph(graph, registry)

    assert report.ok is False
    assert "parameter.unknown" in {diagnostic.code for diagnostic in report.diagnostics}
    assert report.replay_plan == ()


def test_cad_operation_graph_surfaces_planned_handler_diagnostics_for_ai_repair() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("extrude")
    selection = CadSelectionSet(
        items=(
            CadSelectionItem(
                object_id="solid_cube",
                object_kind="mesh",
                selection_kind="face",
                topology_id="F_top",
            ),
        ),
        active_object_id="solid_cube",
    )
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_extrude",
        parameters={"distance": 1.25, "operation": "new_body"},
        selection=selection,
    )
    graph = CadOperationGraph(graph_id="cad_graph_extrude_planned", nodes=(node,))

    report = validate_cad_operation_graph(graph, registry)

    diagnostics = {diagnostic.code: diagnostic for diagnostic in report.diagnostics}
    assert report.ok is False
    assert "handler.planned" in diagnostics
    assert diagnostics["handler.planned"].node_id == "n_extrude"
    assert diagnostics["handler.planned"].repair_suggestions


def test_cad_operation_graph_requires_referenced_topology_lineage() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("transform")
    node = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_missing_lineage",
        selection=_mesh_selection(),
        inputs=(
            CadGraphReference(
                ref_id="face_input",
                entity_id="mesh_cube",
                topology_id="missing_lineage",
                role="selected_face",
            ),
        ),
    )
    graph = CadOperationGraph(
        graph_id="cad_graph_missing_lineage",
        nodes=(node,),
        entity_table={"mesh_cube": CadGraphEntity(entity_id="mesh_cube", kind="mesh")},
    )

    report = validate_cad_operation_graph(graph, registry)

    assert report.ok is False
    assert "graph.topology_ref_missing" in {diagnostic.code for diagnostic in report.diagnostics}


def test_cad_operation_graph_rejects_default_construction_cycles() -> None:
    registry = build_default_cad_registry()
    descriptor = registry.get("transform")
    first = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_first",
        selection=_mesh_selection("mesh_a"),
    )
    second = cad_operation_node_from_descriptor(
        descriptor,
        node_id="n_second",
        selection=_mesh_selection("mesh_b"),
    )
    graph = CadOperationGraph(
        graph_id="cad_graph_cycle",
        nodes=(first, second),
        edges=(
            CadOperationEdge(edge_id="e_first_second", from_node_id="n_first", to_node_id="n_second"),
            CadOperationEdge(edge_id="e_second_first", from_node_id="n_second", to_node_id="n_first"),
        ),
    )

    report = validate_cad_operation_graph(graph, registry)

    assert report.ok is False
    assert "graph.cycle_detected" in {diagnostic.code for diagnostic in report.diagnostics}
    assert report.replay_plan == ()
