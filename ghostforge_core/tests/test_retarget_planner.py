"""Auto-retarget planner tests.

Two complementary surfaces:

* :func:`plan_retarget_graph_from_diagnostics` — pure function, no I/O.
* :func:`plan_retarget_graph_for_asset` — reads a manifest from disk.

The first set of tests drives the pure function with hand-built issues
so the planner's mapping from diagnostic codes → operation nodes is
fully covered. The second set seeds an actual asset directory and runs
the full audit→plan flow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.audit.report import AuditIssue, AuditSeverity
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
)
from ghostforge_core.retarget.planner import (
    plan_retarget_graph_for_asset,
    plan_retarget_graph_from_diagnostics,
)


def _issue(code: str, *, rule: str = "retarget.axis", severity: AuditSeverity = AuditSeverity.info):
    return AuditIssue(rule=rule, severity=severity, code=code, message=f"diag:{code}")


# ---------------------------------------------------------------------------
# from_diagnostics
# ---------------------------------------------------------------------------


def test_planner_no_issues_returns_empty_graph():
    graph = plan_retarget_graph_from_diagnostics([], target_engine="unreal")
    assert graph.nodes == ()
    assert graph.graph_id == "retarget-unreal"


def test_planner_axis_only():
    graph = plan_retarget_graph_from_diagnostics(
        [_issue("axis_mismatch_assumed", rule="retarget.axis")],
        target_engine="unreal",
    )
    kinds = [n.kind for n in graph.nodes]
    assert kinds == ["retarget_axis"]
    assert graph.nodes[0].params["to"] == "unreal"
    assert graph.nodes[0].params["from"] == "gltf_canonical"


def test_planner_units_emits_correct_factor_for_unreal():
    graph = plan_retarget_graph_from_diagnostics(
        [_issue("units_scale_required", rule="retarget.units", severity=AuditSeverity.warning)],
        target_engine="unreal",
    )
    assert [n.kind for n in graph.nodes] == ["retarget_units"]
    assert graph.nodes[0].params["factor"] == pytest.approx(100.0)


def test_planner_units_factor_one_for_unity():
    graph = plan_retarget_graph_from_diagnostics(
        [_issue("units_scale_required", rule="retarget.units", severity=AuditSeverity.warning)],
        target_engine="unity",
    )
    assert graph.nodes[0].params["factor"] == pytest.approx(1.0)


def test_planner_naming_only_emits_for_unreal_with_base_name():
    graph = plan_retarget_graph_from_diagnostics(
        [_issue("static_mesh_prefix_missing", rule="retarget.naming")],
        target_engine="unreal",
        base_name="HeroProp",
    )
    assert [n.kind for n in graph.nodes] == ["retarget_apply_naming"]
    assert graph.nodes[0].params["base_name"] == "HeroProp"


def test_planner_naming_skipped_when_unity_has_no_prefix():
    """Unity has empty naming prefixes, so the planner skips the naming op."""

    graph = plan_retarget_graph_from_diagnostics(
        [_issue("static_mesh_prefix_missing", rule="retarget.naming")],
        target_engine="unity",
    )
    assert graph.nodes == ()


def test_planner_full_chain_for_unreal_orders_stable():
    issues = [
        _issue("axis_mismatch_assumed"),
        _issue("units_scale_required", rule="retarget.units", severity=AuditSeverity.warning),
        _issue("pivot_not_at_base", rule="retarget.pivot", severity=AuditSeverity.warning),
        _issue("static_mesh_prefix_missing", rule="retarget.naming"),
    ]
    graph = plan_retarget_graph_from_diagnostics(
        issues, target_engine="unreal", base_name="Hero"
    )
    kinds = [n.kind for n in graph.nodes]
    # Stable order: axis -> units -> pivot -> naming.
    assert kinds == [
        "retarget_axis",
        "retarget_units",
        "retarget_pivot_for_engine",
        "retarget_apply_naming",
    ]


def test_planner_idempotent_node_ids_unique():
    """Repeated calls with the same issue mix yield uniquely-id'd nodes."""

    issues = [
        _issue("axis_mismatch_assumed"),
        _issue("static_mesh_prefix_missing", rule="retarget.naming"),
    ]
    graph = plan_retarget_graph_from_diagnostics(
        issues, target_engine="unreal", base_name="Hero"
    )
    ids = [n.id for n in graph.nodes]
    assert len(set(ids)) == len(ids)


# ---------------------------------------------------------------------------
# from a real asset
# ---------------------------------------------------------------------------


def _seed_asset(tmp_path: Path) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    asset_dir = tmp_path / "asset"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 2.0, 3.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="hero_box")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unreal))
    builder.write()
    return asset_dir


def test_plan_retarget_for_asset_unreal_emits_axis_units_naming(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    graph, report = plan_retarget_graph_for_asset(
        asset_dir,
        target_engine="unreal",
        base_name="HeroBox",
    )
    kinds = [n.kind for n in graph.nodes]
    # The seeded box: axis swap (Y↔Z + handedness), unit scale, naming.
    assert "retarget_axis" in kinds
    assert "retarget_units" in kinds
    assert "retarget_apply_naming" in kinds
    # Report carries the underlying diagnostics.
    issue_codes = {i.code for i in report.issues}
    assert "axis_mismatch_assumed" in issue_codes
    assert "units_scale_required" in issue_codes


def test_plan_retarget_for_asset_unity_skips_units_naming(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    graph, _report = plan_retarget_graph_for_asset(
        asset_dir,
        target_engine="unity",
    )
    kinds = [n.kind for n in graph.nodes]
    # Unity preserves units and has no naming prefix, but handedness still flips.
    assert "retarget_axis" in kinds
    assert "retarget_units" not in kinds
    assert "retarget_apply_naming" not in kinds


def test_plan_retarget_unknown_engine_raises(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    with pytest.raises(ValueError):
        plan_retarget_graph_for_asset(asset_dir, target_engine="godot")


def test_plan_retarget_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        plan_retarget_graph_for_asset(tmp_path / "missing", target_engine="unity")


def test_plan_retarget_for_asset_links_base_asset_path(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    graph, _ = plan_retarget_graph_for_asset(
        asset_dir, target_engine="unreal", base_name="HeroBox"
    )
    assert graph.base_asset_path is not None
    assert graph.base_asset_path.endswith("mesh.glb")
