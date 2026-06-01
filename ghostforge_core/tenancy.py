"""Tenant isolation for shared GhostForge deployments.

When GhostForge runs as a single-user desktop app, every request lands
in one ``CoreContext`` rooted at one ``data_root``. When it runs as a
shared service (cloud, team server, multi-project agent gateway),
each tenant needs its own filesystem subtree, SQLite job queue, edit
graph store, slice store, and KB cache — but should share singletons
where it's safe (worker registry, model registry, engine adapters).

This module provides:

* :class:`TenantConfig` — declarative description of a tenant.
* :func:`tenant_id_from_request` — header / env / explicit-arg
  resolution helper used by both Flask and MCP adapters.
* :class:`TenantRegistry` — process-wide lazy directory of
  per-tenant :class:`CoreContext` objects, with a
  :func:`get_or_create` entry point.

Tenants are *namespaces* on disk: ``<data_root>/tenants/<tenant_id>/``.
The legacy ``data_root`` itself remains the home for the single
default tenant (id ``"default"``) so existing single-tenant
deployments don't have to migrate. Switching ``allow_legacy_root=False``
forces every request through a tenant.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Mapping

from .types import FrozenModel

if TYPE_CHECKING:  # pragma: no cover — only for typing
    from . import CoreConfig, CoreContext


_TENANT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_\-.]{0,63}$")
DEFAULT_TENANT_ID = "default"


class TenantNotAllowed(ValueError):
    """Raised when an incoming tenant id fails validation."""


class TenantConfig(FrozenModel):
    """Per-tenant configuration overrides applied on top of the base CoreConfig."""

    tenant_id: str
    data_root: Path
    display_name: str | None = None
    notes: str | None = None


def _validate_tenant_id(tenant_id: str) -> str:
    if not tenant_id:
        raise TenantNotAllowed("tenant id must be a non-empty string")
    if not _TENANT_ID_RE.match(tenant_id):
        raise TenantNotAllowed(
            f"tenant id {tenant_id!r} must match {_TENANT_ID_RE.pattern} "
            "(letters, digits, _ - .; max 64 chars)"
        )
    return tenant_id


def tenant_id_from_request(
    *,
    headers: Mapping[str, str] | None = None,
    explicit: str | None = None,
    env: Mapping[str, str] | None = None,
    fallback: str | None = DEFAULT_TENANT_ID,
) -> str:
    """Resolve the active tenant id for a request.

    Resolution order:

    1. ``explicit`` argument (used by tests and CLI tooling).
    2. ``X-Ghostforge-Tenant`` header (case-insensitive lookup).
    3. ``GHOSTFORGE_TENANT`` env var.
    4. ``fallback`` (defaults to ``"default"``).

    Returns the validated tenant id; raises :class:`TenantNotAllowed`
    if the resolved value fails the format check or no candidate
    survived the resolution chain (when ``fallback`` is ``None``).
    """

    candidate: str | None = None
    if explicit:
        candidate = explicit
    elif headers:
        for key, value in headers.items():
            if key.lower() == "x-ghostforge-tenant" and value:
                candidate = value
                break
    if candidate is None and env is not None:
        candidate = env.get("GHOSTFORGE_TENANT")
    if not candidate:
        if fallback is None:
            raise TenantNotAllowed("no tenant id supplied")
        candidate = fallback
    return _validate_tenant_id(candidate)


@dataclass
class _TenantEntry:
    config: TenantConfig
    context: Any  # CoreContext — late binding to dodge circular imports


class TenantRegistry:
    """Lazy directory of per-tenant :class:`CoreContext` instances.

    Construction takes a *base* :class:`CoreConfig` plus a
    ``context_factory`` callable that converts a ``(tenant_id, data_root,
    base_config)`` triple into a CoreContext. The factory layer keeps
    this module free of ``bootstrap()``'s heavy import surface so unit
    tests can spin up dummy contexts.

    Design notes:

    * The default tenant always points at ``base_config.data_root`` so
      single-tenant deployments are bit-for-bit identical to the
      legacy code path.
    * Other tenants are rooted at
      ``base_config.data_root / "tenants" / <tenant_id>``.
    * The registry is process-wide; safe for use under threaded WSGI
      and asyncio MCP servers.
    """

    def __init__(
        self,
        *,
        base_config: "CoreConfig",
        context_factory: Callable[["CoreConfig"], "CoreContext"],
        allow_legacy_root: bool = True,
    ) -> None:
        self._base_config = base_config
        self._factory = context_factory
        self._allow_legacy_root = allow_legacy_root
        self._entries: dict[str, _TenantEntry] = {}
        self._lock = threading.RLock()

    def base_config(self) -> "CoreConfig":
        return self._base_config

    def list(self) -> list[TenantConfig]:
        with self._lock:
            return [entry.config for entry in self._entries.values()]

    def known(self, tenant_id: str) -> bool:
        with self._lock:
            return tenant_id in self._entries

    def resolve(
        self,
        tenant_id: str | None,
        *,
        create: bool = True,
    ) -> "CoreContext":
        """Return the :class:`CoreContext` for ``tenant_id``.

        ``tenant_id=None`` resolves to the default tenant.
        Set ``create=False`` to require the tenant to already exist.
        """

        actual = _validate_tenant_id(tenant_id or DEFAULT_TENANT_ID)
        with self._lock:
            entry = self._entries.get(actual)
            if entry is not None:
                return entry.context
            if not create:
                raise KeyError(f"tenant {actual!r} not registered")

            data_root = self._tenant_data_root(actual)
            data_root.mkdir(parents=True, exist_ok=True)
            tenant_config = TenantConfig(tenant_id=actual, data_root=data_root)
            tenant_core_config = self._base_config_for_tenant(data_root)
            tenant_context = self._factory(tenant_core_config)
            self._entries[actual] = _TenantEntry(
                config=tenant_config, context=tenant_context
            )
            return tenant_context

    def evict(self, tenant_id: str) -> None:
        with self._lock:
            entry = self._entries.pop(tenant_id, None)
        if entry is None:
            return
        # Best-effort runner shutdown so worker threads don't leak.
        runner = getattr(entry.context, "runner", None)
        shutdown = getattr(runner, "shutdown", None)
        if callable(shutdown):
            try:
                shutdown(wait=False)
            except Exception:  # pragma: no cover — defensive
                pass

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._entries.keys())
        for tid in ids:
            self.evict(tid)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _tenant_data_root(self, tenant_id: str) -> Path:
        base_root = Path(self._base_config.data_root)
        if tenant_id == DEFAULT_TENANT_ID and self._allow_legacy_root:
            return base_root
        return base_root / "tenants" / tenant_id

    def _base_config_for_tenant(self, data_root: Path) -> "CoreConfig":
        # Lazy import — avoid forcing tenancy users to pay for the full
        # core import surface when they only want the resolver helpers.
        from . import CoreConfig

        config_kwargs: dict[str, Any] = {
            field.name: getattr(self._base_config, field.name)
            for field in self._base_config.__dataclass_fields__.values()
        }
        config_kwargs["data_root"] = data_root
        return CoreConfig(**config_kwargs)


__all__ = [
    "DEFAULT_TENANT_ID",
    "TenantConfig",
    "TenantNotAllowed",
    "TenantRegistry",
    "tenant_id_from_request",
]
