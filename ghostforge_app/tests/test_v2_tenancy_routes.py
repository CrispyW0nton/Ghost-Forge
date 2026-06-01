"""HTTP integration tests for multi-tenant routing.

Spins up the Flask app in multi-tenant mode and verifies that requests
carrying different ``X-Ghostforge-Tenant`` headers see fully isolated
data — graphs created against tenant A are not visible to tenant B.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_app.app import create_app


@pytest.fixture()
def mt_app(tmp_path):
    flask_app = create_app(data_root=tmp_path, multi_tenant=True)
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture()
def mt_client(mt_app):
    return mt_app.test_client()


def _create_graph(client, tenant: str, name: str) -> str:
    resp = client.post(
        "/api/v2/graphs",
        json={"name": name},
        headers={"X-Ghostforge-Tenant": tenant},
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["graph_id"]


def _list_graph_ids(client, tenant: str) -> list[str]:
    resp = client.get(
        "/api/v2/graphs", headers={"X-Ghostforge-Tenant": tenant}
    )
    assert resp.status_code == 200, resp.get_json()
    return [g["graph_id"] for g in resp.get_json()["graphs"]]


def test_create_graph_isolates_per_tenant(mt_client):
    gid_a = _create_graph(mt_client, "alpha", "from-alpha")
    gid_b = _create_graph(mt_client, "beta", "from-beta")

    alpha_ids = _list_graph_ids(mt_client, "alpha")
    beta_ids = _list_graph_ids(mt_client, "beta")
    assert gid_a in alpha_ids
    assert gid_a not in beta_ids
    assert gid_b in beta_ids
    assert gid_b not in alpha_ids


def test_default_tenant_falls_back_to_legacy_root(mt_client, tmp_path):
    gid = _create_graph(mt_client, "default", "default-graph")
    # Default tenant uses the bare data_root, not the tenants/ subtree.
    graphs_dir = tmp_path / "graphs"
    assert graphs_dir.exists()
    # Tenant subdirs should not exist for "default".
    assert not (tmp_path / "tenants" / "default").exists()


def test_named_tenant_writes_inside_tenants_subdirectory(mt_client, tmp_path):
    gid = _create_graph(mt_client, "acme", "acme-graph")
    tenant_root = tmp_path / "tenants" / "acme"
    assert tenant_root.exists()
    assert (tenant_root / "graphs").exists()


def test_invalid_tenant_id_rejected(mt_client):
    resp = mt_client.get(
        "/api/v2/graphs",
        headers={"X-Ghostforge-Tenant": "../escape"},
    )
    assert resp.status_code == 400


def test_no_header_falls_back_to_default(mt_client):
    resp = mt_client.get("/api/v2/graphs")
    assert resp.status_code == 200


def test_legacy_single_tenant_still_works(tmp_path):
    """Smoke: the non-multi_tenant code path is unchanged."""

    flask_app = create_app(data_root=tmp_path, multi_tenant=False)
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    resp = c.post("/api/v2/graphs", json={"name": "legacy"})
    assert resp.status_code == 201
    listed = c.get("/api/v2/graphs")
    assert listed.status_code == 200
    assert any(g["name"] == "legacy" for g in listed.get_json()["graphs"])
