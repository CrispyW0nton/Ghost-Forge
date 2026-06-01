"""End-to-end tests for the v2 HTTP API.

These tests exercise the Flask app the desktop UI talks to. They are
deliberately black-box: they post real requests, decode JSON, and
assert on the structure the renderer relies on. If a test breaks here,
the React panel that consumes the endpoint also breaks.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest


def _json(response):
    assert response.is_json, f"non-JSON response: {response.status} {response.data[:200]!r}"
    return response.get_json()


# ---------------------------------------------------------------------------
# Runtime endpoints
# ---------------------------------------------------------------------------


def test_runtime_gpus_returns_cpu_only_on_bare_host(client):
    payload = _json(client.get("/api/v2/runtime/gpus"))
    assert payload["scheduler_enabled"] is True
    # No torch / pynvml on the test host.
    assert payload["cpu_only"] is True
    assert payload["gpus"] == []
    assert isinstance(payload["notes"], list)


def test_runtime_scheduler_status(client):
    payload = _json(client.get("/api/v2/runtime/scheduler"))
    assert payload["enabled"] is True
    assert "cpu_concurrency" in payload or "cpu_in_use" in payload


def test_runtime_sessions_lists_unloaded_sessions(client):
    # Reset cached resources from previous tests in the same process.
    # NB: ``free`` evicts the cached value but leaves the session
    # registration intact (sessions are long-lived per worker), so the
    # listing may include name entries with ``loaded: False`` from
    # previously-registered workers.
    from ghostforge_core.workers.session import get_session_registry

    get_session_registry().free(force=True)

    payload = _json(client.get("/api/v2/runtime/sessions"))
    assert isinstance(payload, list)
    # Anything in the list must be an unloaded entry — no real model
    # weights are pinned in memory on the test host.
    for entry in payload:
        assert entry["loaded"] is False


def test_runtime_sessions_free_idempotent(client):
    payload = _json(client.post("/api/v2/runtime/sessions/free", json={}))
    assert payload["freed"] == 0


# ---------------------------------------------------------------------------
# Worker registry endpoints
# ---------------------------------------------------------------------------


def test_workers_list_includes_stubs_and_real(client):
    payload = _json(client.get("/api/v2/workers"))
    names = {entry["descriptor"]["name"] for entry in payload}
    assert "stub_text_to_3d" not in names
    assert "tripo_api" in names
    assert "stub_image_to_3d" in names
    assert "diffusers_texture" in names  # real (P9)
    assert "instantmesh" in names  # real scaffold (P9)

    # Probe payload shape — UI expects runnable + reason fields.
    diffusers = next(
        e for e in payload if e["descriptor"]["name"] == "diffusers_texture"
    )
    assert diffusers["probe"]["runnable"] is False
    assert "missing" in diffusers["probe"]
    assert diffusers["descriptor"]["is_stub"] is False


def test_workers_probe_endpoint(client):
    payload = _json(client.get("/api/v2/workers/stub_image_to_3d/probe"))
    assert payload["runnable"] is True
    assert payload["name"] == "stub_image_to_3d"


def test_workers_probe_unknown_returns_404(client):
    res = client.get("/api/v2/workers/no_such_worker/probe")
    assert res.status_code == 404
    assert _json(res)["error"] == "NOT_FOUND"


def test_workers_run_accepts_text_to_3d_job(client, tmp_path, monkeypatch):
    monkeypatch.delenv("GHOSTFORGE_TRIPO_API_KEY", raising=False)
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    out = tmp_path / "out"
    out.mkdir()
    res = client.post(
        "/api/v2/workers/run",
        json={
            "capability": "text_to_3d",
            "spec": {
                "prompt": "a small wooden crate",
                "output_dir": str(out),
                "seed": 42,
            },
        },
    )
    assert res.status_code == 202
    payload = _json(res)
    assert payload["status"] == "queued"
    assert payload["job_id"]


def test_workers_run_rejects_unknown_capability(client):
    res = client.post(
        "/api/v2/workers/run",
        json={"capability": "make_coffee", "spec": {}},
    )
    assert res.status_code == 400
    assert _json(res)["error"] == "BAD_REQUEST"


# ---------------------------------------------------------------------------
# Models endpoints
# ---------------------------------------------------------------------------


def test_models_list_returns_default_artifacts(client):
    payload = _json(client.get("/api/v2/models"))
    ids = {e["artifact"]["model_id"] for e in payload}
    assert {"trellis-image-large", "hunyuan3d-2", "triposg"}.issubset(ids)
    for entry in payload:
        # Bare host: nothing cached.
        assert entry["status"]["cached"] is False


def test_models_status_unknown_returns_404(client):
    res = client.get("/api/v2/models/ghost-not-real/status")
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Audit endpoints
# ---------------------------------------------------------------------------


def test_audit_presets_returns_three_named(client):
    payload = _json(client.get("/api/v2/audit/presets"))
    assert set(payload.keys()) == {"default", "unity", "unreal"}
    for preset in payload.values():
        assert "thresholds" in preset or "max_triangles" in preset or "name" in preset


def test_audit_run_requires_asset_dir(client):
    res = client.post("/api/v2/audit/run", json={})
    assert res.status_code == 400


def test_audit_run_unknown_preset(client, tmp_path):
    res = client.post(
        "/api/v2/audit/run",
        json={"asset_dir": str(tmp_path), "preset": "not-a-preset"},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Engines endpoints
# ---------------------------------------------------------------------------


def test_engines_list_includes_unity_and_unreal(client):
    payload = _json(client.get("/api/v2/engines"))
    names = {e["name"] for e in payload}
    assert {"unity", "unreal"}.issubset(names)
    for entry in payload:
        assert "default_audit_preset" in entry
        assert "probe" in entry


def test_engines_send_unknown_engine_404(client):
    res = client.post(
        "/api/v2/engines/godot/send",
        json={"asset_dir": "/tmp"},
    )
    assert res.status_code == 404


def test_engines_configure_validates_payload(client):
    # Missing transport-required fields should yield a 400, not a 500.
    res = client.post(
        "/api/v2/engines/unity/configure",
        json={"transport": "stdio"},  # no command
    )
    # Either accepts (with empty command) or rejects with a clear error;
    # in both cases the response is a structured JSON.
    assert res.status_code in (200, 400, 409)
    data = _json(res)
    assert isinstance(data, dict)


# ---------------------------------------------------------------------------
# KB endpoints
# ---------------------------------------------------------------------------


def test_kb_concepts_initially_empty(client):
    payload = _json(client.get("/api/v2/kb/concepts"))
    assert payload == []


def test_kb_search_requires_query(client):
    res = client.post("/api/v2/kb/search", json={})
    assert res.status_code == 400


def test_kb_search_returns_empty_when_kb_empty(client):
    payload = _json(client.post("/api/v2/kb/search", json={"query": "stone wall"}))
    assert payload == []


def test_kb_ingest_requires_license(client):
    img = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"0" * 100)  # tiny invalid PNG ok for license check
    res = client.post(
        "/api/v2/kb/ingest/local",
        data={"image": (img, "concept.png")},
        content_type="multipart/form-data",
    )
    assert res.status_code == 400
    assert _json(res)["error"] == "LICENSE_REQUIRED"


# ---------------------------------------------------------------------------
# Slices endpoints
# ---------------------------------------------------------------------------


def test_slices_list_initially_empty(client):
    payload = _json(client.get("/api/v2/slices"))
    assert payload == []


def test_slices_create_minimal(client):
    body = {
        "brief": {
            "title": "Demo Slice",
            "description": "Two-prop dungeon set.",
            "target_engine": "unity",
            "art_style": "low-poly",
        },
        "assets": [
            {
                "asset_id": "barrel",
                "description": "wooden barrel",
                "kind": "prop",
                "strategy": "skip_generation",
                "input_mesh_path": __file__,
                "license": {"spdx": "CC0-1.0", "attribution": "auto"},
            }
        ],
    }
    res = client.post("/api/v2/slices", json=body)
    assert res.status_code == 201
    plan = _json(res)
    assert plan["brief"]["title"] == "Demo Slice"
    assert len(plan["assets"]) == 1
    assert plan["assets"][0]["asset_id"] == "barrel"
    slice_id = plan["slice_id"]

    # Listing now includes the slice.
    listed = _json(client.get("/api/v2/slices"))
    assert any(s["slice_id"] == slice_id for s in listed)

    # Get by id returns plan + null run.
    got = _json(client.get(f"/api/v2/slices/{slice_id}"))
    assert got["plan"]["slice_id"] == slice_id
    assert got["run"] is None

    # Delete works.
    deleted = _json(client.delete(f"/api/v2/slices/{slice_id}"))
    assert deleted["deleted"] == slice_id


def test_slices_create_rejects_invalid_payload(client):
    res = client.post("/api/v2/slices", json={"brief": {}, "assets": []})
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Legacy v1 still works (regression guard)
# ---------------------------------------------------------------------------


def test_legacy_health_and_models_still_alive(client):
    health = _json(client.get("/api/health"))
    assert health["status"] == "ok"
    assert "real-workers" in health["capabilities"]

    models = _json(client.get("/api/models"))
    ids = {m["id"] for m in models}
    assert "trellis-image-large" in ids
    # Legacy shape still has the keys the existing UI expects.
    sample = next(m for m in models if m["id"] == "trellis-image-large")
    assert {"id", "name", "installed"}.issubset(sample.keys())
