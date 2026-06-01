"""Server bootstrap for the GhostForge MCP adapter.

The MCP server is a peer adapter that talks to the same `ghostforge_core`
library as the Flask desktop API. Two adapters can share the SQLite job store,
but only one process should dispatch pending jobs. Set
``GHOSTFORGE_DISPATCH_JOBS=0`` in the MCP process when the desktop app is the
runner owner; leave it unset (default ``1``) to let the MCP server own the
dispatcher.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from ghostforge_core import CoreConfig, CoreContext, bootstrap
from ghostforge_core.tenancy import (
    DEFAULT_TENANT_ID,
    TenantRegistry,
    tenant_id_from_request,
)

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP


_CONTEXT: CoreContext | None = None
_TENANTS: TenantRegistry | None = None
_ACTIVE_TENANT: str | None = None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"", "0", "false", "no", "off"}


def _build_base_config() -> CoreConfig:
    data_root = Path(os.environ.get("GHOSTFORGE_DATA_ROOT", "./data"))
    max_workers = int(os.environ.get("GHOSTFORGE_MAX_WORKERS", "2"))
    dispatch = _env_bool("GHOSTFORGE_DISPATCH_JOBS", True)
    return CoreConfig(
        data_root=data_root,
        max_workers=max_workers,
        dispatch_jobs=dispatch,
    )


def _multi_tenant_enabled() -> bool:
    return _env_bool("GHOSTFORGE_MULTI_TENANT", False)


def _tenant_registry() -> TenantRegistry:
    global _TENANTS
    if _TENANTS is None:
        _TENANTS = TenantRegistry(
            base_config=_build_base_config(),
            context_factory=bootstrap,
        )
    return _TENANTS


def get_context(tenant_id: str | None = None) -> CoreContext:
    """Return the :class:`CoreContext` for the requested tenant.

    Single-tenant mode (the default): cached singleton, identical to
    the pre-multi-tenant code path.

    Multi-tenant mode (``GHOSTFORGE_MULTI_TENANT=1``): the tenant id
    resolves from the explicit argument first, then the
    ``GHOSTFORGE_TENANT`` env var, then the *active* tenant pinned by
    a recent :func:`bind_tenant` call (used by per-call wrappers in
    higher-level transports), then the default tenant.
    """

    global _CONTEXT
    if _multi_tenant_enabled():
        registry = _tenant_registry()
        active = (
            tenant_id
            or _ACTIVE_TENANT
            or os.environ.get("GHOSTFORGE_TENANT")
            or DEFAULT_TENANT_ID
        )
        return registry.resolve(active)

    if _CONTEXT is None:
        _CONTEXT = bootstrap(_build_base_config())
    return _CONTEXT


def bind_tenant(tenant_id: str | None) -> None:
    """Pin the active tenant for subsequent :func:`get_context` calls.

    Used by the FastMCP transport layer to propagate a tenant id from
    a tool's ``Context`` (which carries client metadata) down into
    code paths that don't know about MCP. Set ``None`` to clear.
    """

    global _ACTIVE_TENANT
    _ACTIVE_TENANT = tenant_id


def reset_context_for_tests() -> None:
    """Drop the cached CoreContext (tests only)."""
    global _CONTEXT, _TENANTS, _ACTIVE_TENANT
    if _CONTEXT is not None:
        try:
            _CONTEXT.runner.shutdown(wait=False)
        except Exception:
            pass
    _CONTEXT = None
    if _TENANTS is not None:
        try:
            _TENANTS.shutdown()
        except Exception:
            pass
    _TENANTS = None
    _ACTIVE_TENANT = None


def build_server() -> "FastMCP":
    """Construct the FastMCP server with all GhostForge tools registered.

    Importing :mod:`mcp.server.fastmcp` is deferred so that core-only test
    runs do not require the optional `mcp` dependency.
    """
    from mcp.server.fastmcp import FastMCP

    from . import tools

    server = FastMCP(
        name="ghostforge",
        instructions=(
            "GhostForge is a dual-mode 3D asset foundry. Use these tools to "
            "inspect meshes, submit UV unwrap or texture generation jobs, and "
            "track job progress. Long-running operations return a `job_id`; "
            "call `wait_for_job` (with a progress token) or poll `get_job`."
        ),
    )
    tools.register_tools(server)
    return server
