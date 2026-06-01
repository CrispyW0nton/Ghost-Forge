from __future__ import annotations

from ghostforge_core import CoreConfig
from ghostforge_qt.services.core_bridge import CoreBridge


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
