"""Engine handoff adapters for GhostForge.

GhostForge is the asset foundry; once an asset has a manifest with a
mesh artifact, an engine adapter delivers it to the matching engine
MCP server. The two adapters that ship today are:

* :class:`UnityEngineAdapter` → ``Unity-MCP-Ghost``
* :class:`UnrealEngineAdapter` → ``Unreal-MCP-Ghost``

Adapters share a transport layer (:mod:`ghostforge_core.engines.transport`)
that speaks MCP over stdio or streamable-http, and a base implementation
(:mod:`ghostforge_core.engines.adapter`) that handles manifest validation,
payload assembly, and provenance recording. Anything new (Godot, Houdini,
custom in-house engines) only needs to subclass :class:`BaseEngineAdapter`
and pick a default ``EngineConfig``.
"""

from __future__ import annotations

from .adapter import BaseEngineAdapter, EngineAuditFailed, ENGINE_HANDOFFS_KEY
from .base import (
    EngineAdapter,
    EngineAssetInvalid,
    EngineCallError,
    EngineConfig,
    EngineHandoffError,
    EngineHandoffResult,
    EngineNotConfigured,
    EngineProbeResult,
    TransportName,
)
from .loader import EngineRegistry, config_from_env, default_engine_adapters
from .transport import (
    EngineTransport,
    HttpMcpTransport,
    RecordingTransport,
    StdioMcpTransport,
)
from .unity import UnityEngineAdapter
from .unreal import UnrealEngineAdapter

__all__ = [
    "BaseEngineAdapter",
    "ENGINE_HANDOFFS_KEY",
    "EngineAdapter",
    "EngineAssetInvalid",
    "EngineAuditFailed",
    "EngineCallError",
    "EngineConfig",
    "EngineHandoffError",
    "EngineHandoffResult",
    "EngineNotConfigured",
    "EngineProbeResult",
    "EngineRegistry",
    "EngineTransport",
    "HttpMcpTransport",
    "RecordingTransport",
    "StdioMcpTransport",
    "TransportName",
    "UnityEngineAdapter",
    "UnrealEngineAdapter",
    "config_from_env",
    "default_engine_adapters",
]
