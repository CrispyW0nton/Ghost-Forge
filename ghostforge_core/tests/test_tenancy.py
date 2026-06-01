"""Unit tests for the multi-tenant resolver and registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core import CoreConfig, bootstrap
from ghostforge_core.tenancy import (
    DEFAULT_TENANT_ID,
    TenantNotAllowed,
    TenantRegistry,
    tenant_id_from_request,
)


# ---------------------------------------------------------------------------
# tenant_id_from_request
# ---------------------------------------------------------------------------


def test_explicit_argument_wins_over_header_and_env():
    tid = tenant_id_from_request(
        explicit="acme",
        headers={"X-Ghostforge-Tenant": "header"},
        env={"GHOSTFORGE_TENANT": "env"},
    )
    assert tid == "acme"


def test_header_resolves_when_no_explicit():
    tid = tenant_id_from_request(
        headers={"X-Ghostforge-Tenant": "team_one"},
        env={"GHOSTFORGE_TENANT": "ignored"},
    )
    assert tid == "team_one"


def test_header_lookup_is_case_insensitive():
    tid = tenant_id_from_request(headers={"x-ghostforge-tenant": "lower"})
    assert tid == "lower"


def test_env_used_when_no_header():
    tid = tenant_id_from_request(headers={}, env={"GHOSTFORGE_TENANT": "from_env"})
    assert tid == "from_env"


def test_fallback_returned_when_nothing_else():
    tid = tenant_id_from_request(headers={}, env={})
    assert tid == DEFAULT_TENANT_ID


def test_fallback_none_raises_when_no_id():
    with pytest.raises(TenantNotAllowed):
        tenant_id_from_request(headers={}, env={}, fallback=None)


@pytest.mark.parametrize("bad", ["has spaces", "../escape", "x" * 65, "@nope"])
def test_invalid_tenant_id_rejected(bad):
    with pytest.raises(TenantNotAllowed):
        tenant_id_from_request(explicit=bad)


# ---------------------------------------------------------------------------
# TenantRegistry
# ---------------------------------------------------------------------------


@pytest.fixture
def registry(tmp_path) -> TenantRegistry:
    return TenantRegistry(
        base_config=CoreConfig(data_root=tmp_path, dispatch_jobs=False),
        context_factory=bootstrap,
    )


def test_default_tenant_uses_legacy_root(registry, tmp_path):
    ctx = registry.resolve(None)
    assert Path(ctx.storage.root) == tmp_path


def test_named_tenant_gets_dedicated_subdirectory(registry, tmp_path):
    ctx = registry.resolve("acme")
    expected = tmp_path / "tenants" / "acme"
    assert Path(ctx.storage.root) == expected
    assert expected.exists()


def test_resolve_caches_per_tenant(registry):
    a1 = registry.resolve("alpha")
    a2 = registry.resolve("alpha")
    assert a1 is a2


def test_two_tenants_have_isolated_storage(registry):
    a = registry.resolve("alpha")
    b = registry.resolve("beta")
    assert Path(a.storage.root) != Path(b.storage.root)
    assert a.jobs is not b.jobs
    assert a.graphs is not b.graphs


def test_resolve_missing_with_create_false_raises(registry):
    with pytest.raises(KeyError):
        registry.resolve("nonexistent", create=False)


def test_evict_drops_tenant_and_releases_runner(registry):
    ctx = registry.resolve("disposable")
    assert registry.known("disposable")
    registry.evict("disposable")
    assert not registry.known("disposable")
    # Re-resolving creates a brand-new context.
    ctx2 = registry.resolve("disposable")
    assert ctx2 is not ctx


def test_shutdown_clears_all(registry):
    registry.resolve("a")
    registry.resolve("b")
    assert {t.tenant_id for t in registry.list()} >= {"a", "b"}
    registry.shutdown()
    assert registry.list() == []


def test_writes_in_one_tenant_invisible_to_another(registry):
    a = registry.resolve("alpha")
    b = registry.resolve("beta")

    from ghostforge_core.authoring import EditGraph

    graph = EditGraph(graph_id="only_in_alpha", name="hi")
    a.graphs.save(graph)

    assert any(g.graph_id == "only_in_alpha" for g in a.graphs.list())
    assert all(g.graph_id != "only_in_alpha" for g in b.graphs.list())
