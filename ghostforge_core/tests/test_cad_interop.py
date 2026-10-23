from __future__ import annotations

from ghostforge_core.cad import build_default_interop_registry


def test_default_interop_registry_tracks_plasticity_format_families_without_runtime_dependency() -> None:
    registry = build_default_interop_registry()
    summary = registry.summary()

    assert summary["format_count"] == 6
    assert summary["runtime_dependency"] == "none"
    assert summary["plasticity_role"] == "development_evidence_only"
    assert summary["family_counts"] == {"brep": 4, "drawing": 1, "mesh": 1}
    assert summary["direction_counts"] == {"import": 5, "export": 6}
    assert {descriptor.format_id for descriptor in registry.all()} == {
        "dwg_dxf",
        "iges_igs",
        "mesh_export",
        "parasolid_x_t_x_b",
        "sat_sab",
        "step_stp",
    }


def test_step_descriptor_has_brep_translation_options_and_fixture_gates() -> None:
    step = build_default_interop_registry().get("step_stp")

    assert step.can_import is True
    assert step.can_export is True
    assert step.extensions == (".step", ".stp")
    assert {"dwgstep30.dll", "stepstep30.dll", "xtstep30.dll"}.issubset(
        set(step.plasticity_evidence)
    )
    option_names = {option.name for option in step.option_schema}
    assert {"units", "heal_geometry", "preserve_names", "step_schema"}.issubset(option_names)
    assert "fixture_cube_solid" in step.fixture_tests
    assert "diagnostics_serialized" in step.verification_gates


def test_mesh_export_descriptor_preserves_static_option_uncertainty_as_explicit_schema() -> None:
    mesh_export = build_default_interop_registry().get("mesh_export")

    assert mesh_export.can_import is False
    assert mesh_export.can_export is True
    assert mesh_export.family == "mesh"
    assert {option.name for option in mesh_export.options_for_direction("export")} >= {
        "format",
        "target_path",
        "scope",
        "axis_preset",
        "angle_tolerance",
        "max_width",
        "inflect",
        "overwrite_policy",
    }
    assert {option.name for option in mesh_export.format_options_from_recon} == {
        "angle_tolerance",
        "inflect",
        "max_width",
    }
    assert any(option.safety_note for option in mesh_export.option_schema if option.name == "target_path")
    assert "source_topology_unchanged" in mesh_export.verification_gates


def test_dwg_dxf_descriptor_models_drawing_specific_options() -> None:
    dwg = build_default_interop_registry().get("dwg_dxf")

    assert dwg.family == "drawing"
    assert dwg.extensions == (".dwg", ".dxf")
    option_names = {option.name for option in dwg.option_schema}
    assert {"drawing_version", "preserve_layers", "lineweight_policy", "include_hidden_lines"}.issubset(
        option_names
    )
    assert "unsupported_entities_diagnostic" in dwg.verification_gates


def test_future_kernel_formats_are_explicitly_backend_gated() -> None:
    registry = build_default_interop_registry()

    parasolid = registry.get("parasolid_x_t_x_b")
    sat = registry.get("sat_sab")
    assert any(failure.code == "parasolid.backend_unavailable" for failure in parasolid.failure_modes)
    assert any(failure.code == "acis.backend_unavailable" for failure in sat.failure_modes)
    assert "backend_capability_check" in parasolid.automation_requirements
    assert "backend_capability_check" in sat.automation_requirements
