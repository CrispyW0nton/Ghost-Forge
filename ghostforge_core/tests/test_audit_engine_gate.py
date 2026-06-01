"""Engine adapter audit gate.

Verifies that the audit fires before handoff, that errors block unless
``force=True``, and that the audit report ends up in both the handoff
result and the manifest.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.audit import AUDIT_HISTORY_KEY
from ghostforge_core.engines import (
    EngineAuditFailed,
    RecordingTransport,
    UnityEngineAdapter,
)
from ghostforge_core.manifest import (
    EngineTarget,
    EngineTargetSpec,
    LicenseSpec,
    ManifestBuilder,
    read_manifest,
)


def _seed_asset(tmp_path: Path) -> Path:
    pytest.importorskip("trimesh")
    import trimesh

    asset_dir = tmp_path / "asset_pkg"
    asset_dir.mkdir()
    mesh_path = asset_dir / "mesh.glb"
    trimesh.creation.box(extents=(1.0, 1.0, 1.0)).export(mesh_path)

    builder = ManifestBuilder.for_dir(asset_dir, asset_id="asset_pkg")
    builder.with_geometry_from_mesh(mesh_path)
    builder.add_artifact_from_path(mesh_path, role="mesh.primary")
    builder.with_license(LicenseSpec(spdx="CC0-1.0"))
    builder.add_engine_target(EngineTargetSpec(engine=EngineTarget.unity))
    builder.write()
    return asset_dir


def test_audit_blocks_handoff_when_unity_preset_fails(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport()
    adapter.set_transport(transport)

    with pytest.raises(EngineAuditFailed) as exc:
        adapter.send_asset(asset_dir)
    assert exc.value.report.status == "failed"
    # Engine MCP must NOT have been called.
    assert transport.calls == []


def test_audit_force_overrides_failures(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport()
    adapter.set_transport(transport)

    result = adapter.send_asset(asset_dir, force=True)
    assert result.audit is not None
    assert result.audit["status"] == "failed"
    assert transport.calls and transport.calls[0][0] == "import_asset"

    # Manifest now records the audit history AND the engine handoff.
    manifest = read_manifest(asset_dir)
    assert AUDIT_HISTORY_KEY in manifest.custom
    assert "engine_handoffs" in manifest.custom


def test_audit_disabled_skips_check_entirely(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport()
    adapter.set_transport(transport)

    result = adapter.send_asset(asset_dir, audit=False)
    assert result.audit is None
    manifest = read_manifest(asset_dir)
    assert AUDIT_HISTORY_KEY not in manifest.custom


def test_audit_dry_run_still_records_audit(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    adapter = UnityEngineAdapter()

    # dry_run + force lets us record audit + plan without actually shipping.
    result = adapter.send_asset(asset_dir, dry_run=True, force=True)
    assert result.dry_run is True
    assert result.audit is not None
    manifest = read_manifest(asset_dir)
    history = manifest.custom[AUDIT_HISTORY_KEY]
    assert len(history) == 1


def test_explicit_preset_overrides_engine_default(tmp_path):
    asset_dir = _seed_asset(tmp_path)
    adapter = UnityEngineAdapter()
    transport = RecordingTransport()
    adapter.set_transport(transport)

    # Default preset is permissive enough that a UV-less trimesh box passes.
    result = adapter.send_asset(asset_dir, audit_preset="default")
    assert result.audit is not None
    assert result.audit["preset"] == "default"
    assert result.audit["status"] in {"passed", "warnings"}
    assert transport.calls
