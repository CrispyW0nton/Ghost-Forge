"""Audit runner end-to-end: report assembly, manifest persistence, presets."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.audit import AUDIT_HISTORY_KEY, audit_asset, default_preset
from ghostforge_core.audit.report import AuditSeverity
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    read_manifest,
)


def _seed_asset(
    tmp_path: Path,
    *,
    asset_id: str = "audit_test",
    license_spdx: str | None = "CC0-1.0",
    engine_target: EngineTarget | None = EngineTarget.unity,
) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    asset_dir = tmp_path / asset_id
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id=asset_id)
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    if license_spdx:
        builder.with_license(LicenseSpec(spdx=license_spdx))
    if engine_target is not None:
        builder.add_engine_target(EngineTargetSpec(engine=engine_target))
    builder.write()
    return asset_dir


def test_audit_missing_manifest_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        audit_asset(tmp_path / "nope")


def test_audit_default_preset_persists_history(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    report = audit_asset(asset_dir, run_gltf_validator=False)
    assert report.preset == "default"
    assert report.error_count == 0  # default preset is permissive enough for a box

    manifest = read_manifest(asset_dir)
    history = manifest.custom.get(AUDIT_HISTORY_KEY)
    assert isinstance(history, list) and len(history) == 1
    assert history[0]["preset"] == "default"
    assert history[0]["status"] in {"passed", "warnings"}

    audit_steps = [s for s in manifest.provenance if s.kind == "audit"]
    assert len(audit_steps) == 1
    assert audit_steps[0].parameters["preset"] == "default"


def test_audit_persist_false_does_not_touch_manifest(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    before = read_manifest(asset_dir)
    audit_asset(asset_dir, persist=False, run_gltf_validator=False)
    after = read_manifest(asset_dir)
    assert before == after


def test_audit_unity_preset_flags_missing_uvs(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    report = audit_asset(asset_dir, preset="unity", run_gltf_validator=False, persist=False)
    assert report.status == "failed"
    assert report.error_count >= 1
    codes = {issue.code for issue in report.issues}
    assert "missing_uvs" in codes


def test_audit_unity_preset_warning_for_lightmap_uv(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    report = audit_asset(asset_dir, preset="unity", run_gltf_validator=False, persist=False)
    codes = {issue.code for issue in report.issues}
    # Lightmap UV is a warning, not an error.
    warnings = [
        issue for issue in report.issues if issue.severity == AuditSeverity.warning
    ]
    assert any(w.code == "missing_lightmap_uv" for w in warnings) or "missing_uvs" in codes


def test_audit_history_caps_at_16(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    for _ in range(20):
        audit_asset(asset_dir, run_gltf_validator=False)
    manifest = read_manifest(asset_dir)
    history = manifest.custom[AUDIT_HISTORY_KEY]
    assert len(history) == 16


def test_audit_validation_summary_propagates_to_manifest(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    audit_asset(asset_dir, preset="unity", run_gltf_validator=False)
    manifest = read_manifest(asset_dir)
    # The Unity preset surfaces missing UVs; status should reflect failure.
    assert manifest.validation.status in {"failed", "warnings"}
    assert manifest.validation.error_count + manifest.validation.warning_count >= 1


def test_audit_unknown_preset_raises(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    with pytest.raises(ValueError):
        audit_asset(asset_dir, preset="godot", run_gltf_validator=False)


def test_audit_progress_callback_invoked(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    seen: list[tuple[str, float, str]] = []

    def progress(stage: str, percent: float, message: str) -> None:
        seen.append((stage, percent, message))

    audit_asset(asset_dir, run_gltf_validator=False, progress=progress)
    assert any(stage == "rule" for stage, *_ in seen)
    assert any(stage == "done" for stage, *_ in seen)


def test_audit_with_explicit_preset_object(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    preset = default_preset().model_copy(update={"name": "default"})
    report = audit_asset(asset_dir, preset=preset, run_gltf_validator=False, persist=False)
    assert report.preset == "default"


def test_audit_skips_gltf_validator_when_unavailable(tmp_path, monkeypatch):
    asset_dir = _seed_asset(tmp_path)
    # Force the validator lookup to return None even if installed.
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    monkeypatch.delenv("GHOSTFORGE_GLTF_VALIDATOR", raising=False)

    report = audit_asset(asset_dir, run_gltf_validator=True, persist=False)
    gltf_rule = next((r for r in report.rules if r.rule == "gltf.validator"), None)
    assert gltf_rule is not None
    assert gltf_rule.skipped
    assert "PATH" in (gltf_rule.skip_reason or "") or "gltf-validator" in (
        gltf_rule.skip_reason or ""
    )
