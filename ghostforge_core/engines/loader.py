"""Default engine adapters and env-driven configuration.

Reads ``GHOSTFORGE_<NAME>_MCP_*`` environment variables on startup so
operators can turn on either engine handoff with a couple of exports —
no code edits, no on-disk config file required. The same logic powers
the runtime ``configure_engine_adapter`` MCP tool, ensuring adapters
configured at boot and adapters reconfigured later go through the same
validation paths.

Recognised env vars per engine (``<NAME>`` ∈ ``UNITY``, ``UNREAL``):

* ``GHOSTFORGE_<NAME>_MCP_TRANSPORT`` — ``stdio`` | ``http`` | ``none``
* ``GHOSTFORGE_<NAME>_MCP_COMMAND`` — shell-like command string for
  stdio transport (split with ``shlex``).
* ``GHOSTFORGE_<NAME>_MCP_CWD`` — working directory for stdio command.
* ``GHOSTFORGE_<NAME>_MCP_URL`` — MCP streamable-http endpoint.
* ``GHOSTFORGE_<NAME>_MCP_HEADERS`` — JSON dict of headers for http.
* ``GHOSTFORGE_<NAME>_MCP_TOOL`` — override import tool name.
* ``GHOSTFORGE_<NAME>_MCP_PROJECT`` — project_path forwarded with calls.
* ``GHOSTFORGE_<NAME>_MCP_TIMEOUT`` — call timeout in seconds.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
from dataclasses import dataclass
from typing import Iterable

from .base import EngineConfig
from .unity import UnityEngineAdapter
from .unreal import UnrealEngineAdapter

logger = logging.getLogger(__name__)


@dataclass
class EngineRegistry:
    """Lookup table of engine adapters keyed by ``adapter.name``."""

    adapters: dict[str, "object"]  # actually BaseEngineAdapter, kept loose to avoid import cycles

    def get(self, name: str):
        try:
            return self.adapters[name]
        except KeyError:
            raise KeyError(
                f"No engine adapter named '{name}'. Known: {sorted(self.adapters)}"
            ) from None

    def all(self) -> Iterable:
        return list(self.adapters.values())

    def names(self) -> list[str]:
        return sorted(self.adapters.keys())


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_command(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        return shlex.split(raw, posix=os.name != "nt")
    except ValueError as exc:
        logger.warning("could not shlex-parse command %r: %s", raw, exc)
        return []


def _parse_headers(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("could not parse JSON headers %r", raw)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("headers env var must decode to a JSON object, got %s", type(parsed))
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


def config_from_env(name: str) -> EngineConfig:
    """Build an :class:`EngineConfig` from ``GHOSTFORGE_<NAME>_MCP_*`` vars.

    Falls back to ``transport="none"`` whenever a transport's required
    fields are missing. The resulting config is always valid; probing
    surfaces unconfigured state to callers.
    """

    upper = name.upper()
    transport = (_env(f"GHOSTFORGE_{upper}_MCP_TRANSPORT") or "none").lower()
    if transport not in {"stdio", "http", "none"}:
        logger.warning(
            "unknown transport %r for %s; defaulting to 'none'", transport, name
        )
        transport = "none"

    command = _parse_command(_env(f"GHOSTFORGE_{upper}_MCP_COMMAND"))
    cwd = _env(f"GHOSTFORGE_{upper}_MCP_CWD")
    url = _env(f"GHOSTFORGE_{upper}_MCP_URL")
    headers = _parse_headers(_env(f"GHOSTFORGE_{upper}_MCP_HEADERS"))
    import_tool = _env(f"GHOSTFORGE_{upper}_MCP_TOOL") or "import_asset"
    project_path = _env(f"GHOSTFORGE_{upper}_MCP_PROJECT")
    timeout_raw = _env(f"GHOSTFORGE_{upper}_MCP_TIMEOUT")
    try:
        timeout = float(timeout_raw) if timeout_raw else 120.0
    except ValueError:
        logger.warning("invalid timeout %r for %s; defaulting to 120s", timeout_raw, name)
        timeout = 120.0

    if transport == "stdio" and not command:
        logger.info(
            "%s configured for stdio but GHOSTFORGE_%s_MCP_COMMAND is empty; "
            "leaving adapter unconfigured.",
            name,
            upper,
        )
        transport = "none"
    if transport == "http" and not url:
        logger.info(
            "%s configured for http but GHOSTFORGE_%s_MCP_URL is empty; "
            "leaving adapter unconfigured.",
            name,
            upper,
        )
        transport = "none"

    return EngineConfig(
        name=name,
        transport=transport,  # type: ignore[arg-type]
        command=command,
        cwd=cwd,
        url=url,
        headers=headers,
        import_tool=import_tool,
        timeout_seconds=timeout,
        project_path=project_path,
    )


def default_engine_adapters() -> EngineRegistry:
    """Build the default set of engine adapters with env-derived configs."""

    unity = UnityEngineAdapter(config_from_env("unity"))
    unreal = UnrealEngineAdapter(config_from_env("unreal"))
    return EngineRegistry(adapters={unity.name: unity, unreal.name: unreal})


__all__ = [
    "EngineRegistry",
    "config_from_env",
    "default_engine_adapters",
]
