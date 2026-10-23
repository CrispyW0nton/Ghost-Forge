from __future__ import annotations

from ghostforge_core.cad import (
    CadSelectionItem,
    CadSelectionSet,
    CadTopologyDelta,
    CadTopologyLineage,
    CadTopologySnapshot,
    build_committed_result,
    build_default_cad_registry,
    build_preview_result,
    preflight_cad_command,
    resolve_cad_command_context,
)


def _mesh_object_selection() -> CadSelectionSet:
    return CadSelectionSet(
        items=(
            CadSelectionItem(
                object_id="mesh_cube",
                object_kind="mesh",
                selection_kind="object",
                topology_id="mesh_cube",
            ),
        ),
        active_object_id="mesh_cube",
    )


def test_implemented_mesh_command_preflight_accepts_valid_selection_and_defaults() -> None:
    descriptor = build_default_cad_registry().get("transform")
    context = resolve_cad_command_context(descriptor, selection=_mesh_object_selection())

    report = preflight_cad_command(descriptor, context)
    preview = build_preview_result(descriptor, context, report)

    assert report.ok is True
    assert report.failures == ()
    assert report.selection_summary["count"] == 1
    assert report.parameter_summary["scale"] == 1.0
    assert preview.status == "preview_ready"
    assert preview.preview_payload["parameter_snapshot"]["translate"] == [0.0, 0.0, 0.0]


def test_preflight_reports_missing_required_parameter_and_planned_handler_gate() -> None:
    descriptor = build_default_cad_registry().get("extrude")
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
    context = resolve_cad_command_context(descriptor, selection=selection)

    report = preflight_cad_command(descriptor, context)

    assert report.ok is False
    failure_codes = {failure.code for failure in report.failures}
    assert "parameter.distance.required" in failure_codes
    assert "handler.planned" in failure_codes


def test_preflight_enforces_selection_kind_count_and_active_plane_contracts() -> None:
    descriptor = build_default_cad_registry().get("project").model_copy(
        update={
            "selection_contract": build_default_cad_registry()
            .get("project")
            .selection_contract.model_copy(update={"active_plane_required": True})
        }
    )
    selection = CadSelectionSet(
        items=(
            CadSelectionItem(
                object_id="profile",
                object_kind="mesh",
                selection_kind="vertex",
                topology_id="V_0",
            ),
        ),
        active_object_id="profile",
    )
    context = resolve_cad_command_context(descriptor, selection=selection)

    report = preflight_cad_command(descriptor, context)

    failure_codes = {failure.code for failure in report.failures}
    assert "selection.count_below_minimum" in failure_codes
    assert "selection.active_plane_missing" in failure_codes
    assert "selection.subobject_kind_unsupported" in failure_codes


def test_preflight_validates_enum_and_numeric_ranges() -> None:
    descriptor = build_default_cad_registry().get("fillet")
    selection = CadSelectionSet(
        items=(
            CadSelectionItem(
                object_id="solid_cube",
                object_kind="mesh",
                selection_kind="edge",
                topology_id="E_vertical",
            ),
        ),
        active_object_id="solid_cube",
    )
    context = resolve_cad_command_context(
        descriptor,
        selection=selection,
        parameters={"radius": -1.0, "continuity": "g3"},
    )

    report = preflight_cad_command(descriptor, context)

    failure_codes = {failure.code for failure in report.failures}
    assert "parameter.radius.below_minimum" in failure_codes
    assert "parameter.continuity.invalid_enum" in failure_codes


def test_committed_result_records_topology_delta_undo_and_manifest_event() -> None:
    descriptor = build_default_cad_registry().get("normalize_scale")
    context = resolve_cad_command_context(
        descriptor,
        selection=_mesh_object_selection(),
        parameters={"target_extent": 2.0},
    )
    report = preflight_cad_command(descriptor, context)
    delta = CadTopologyDelta(
        before=CadTopologySnapshot(object_ids=("mesh_cube",), vertex_count=8, edge_count=12, face_count=6),
        after=CadTopologySnapshot(object_ids=("mesh_cube",), vertex_count=8, edge_count=12, face_count=6),
        modifies=("vertices", "bounds"),
        preserves=("faces", "materials"),
        lineage=(
            CadTopologyLineage(
                source_id="mesh_cube",
                result_ids=("mesh_cube",),
                relation="modified",
            ),
        ),
        result_summary={"vertex_count": 8, "face_count": 6, "bounds_changed": True},
    )

    result = build_committed_result(descriptor, context, report, delta)

    assert result.status == "committed"
    assert result.undo_record is not None
    assert result.undo_record.parameter_snapshot["target_extent"] == 2.0
    assert result.manifest_event is not None
    assert "provenance.operation" in result.manifest_event.effects
    assert result.model_dump(mode="json")["topology_delta"]["lineage"][0]["relation"] == "modified"


def test_controlled_probe_command_can_preflight_but_keeps_evidence_warning() -> None:
    descriptor = build_default_cad_registry().get("export_mesh")
    context = resolve_cad_command_context(
        descriptor,
        selection=CadSelectionSet(
            items=(
                CadSelectionItem(
                    object_id="scene",
                    object_kind="scene",
                    selection_kind="object",
                ),
            )
        ),
        parameters={"target_path": "C:/tmp/export.glb", "format": "glb"},
    )

    report = preflight_cad_command(descriptor, context)

    assert report.ok is True
    assert {warning.code for warning in report.warnings} == {"evidence.controlled_probe_needed"}
