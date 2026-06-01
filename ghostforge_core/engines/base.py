"""Engine adapter contracts.

An *engine adapter* optionally hands a finished GhostForge asset off to
another MCP server that drives a game engine — Unity-MCP-Ghost or
Unreal-MCP-Ghost today. The default product workflow is the offline export
bridge; direct adapter calls require explicit transport configuration.

The adapter layer deliberately stays small: it does *not* know how to
import a glb into Unity, that's the engine MCP's job. It only:

* Validates the asset directory has a usable manifest + mesh artifact.
* Builds a structured payload (paths, manifest, target slot).
* Delegates to a transport (stdio / http / injected) which speaks MCP.
* Records the handoff back into the asset's manifest provenance so the
  next reader can see when, where, and how the asset was delivered.

Everything below is transport-agnostic. The MCP SDK only enters at
:mod:`ghostforge_core.engines.transport`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from ..manifest import EngineTarget
from ..types import FrozenModel, utc_now


class EngineHandoffError(RuntimeError):
    """Base class for engine handoff failures."""


class EngineNotConfigured(EngineHandoffError):
    """Adapter has no transport configured to talk to the engine MCP."""


class EngineAssetInvalid(EngineHandoffError):
    """Asset directory is missing a manifest or a primary mesh artifact."""


class EngineCallError(EngineHandoffError):
    """The engine MCP returned an error or timed out during the handoff."""


TransportName = Literal["stdio", "http", "none", "injected"]


class EngineConfig(FrozenModel):
    """Static configuration for one engine adapter.

    Adapters reach the engine MCP either by spawning a subprocess
    (``transport="stdio"``) or by connecting to an existing server
    (``transport="http"``). ``transport="none"`` is the unconfigured
    state; the adapter rejects send requests until it is reconfigured.
    """

    name: str
    transport: TransportName = "none"
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    import_tool: str = "import_asset"
    import_args_extra: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=120.0, gt=0.0)
    project_path: str | None = None
    description: str | None = None


class EngineProbeResult(FrozenModel):
    """Health/availability snapshot for an engine adapter."""

    name: str
    configured: bool
    transport: TransportName
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineHandoffResult(FrozenModel):
    """Returned by :meth:`EngineAdapter.send_asset`.

    Captures *what* was sent (mesh path, target slot in the engine
    project), *where* it went (engine name + transport), and the raw
    response payload. The payload shape is engine-defined so we keep it
    as ``dict[str, Any]`` rather than constraining it here.
    """

    engine: str
    asset_dir: Path
    asset_id: str
    asset_path: Path
    target_path: str | None = None
    transport: TransportName
    tool: str
    delivered_at: datetime = Field(default_factory=utc_now)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    dry_run: bool = False
    engine_response: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    audit: dict[str, Any] | None = None


@runtime_checkable
class EngineAdapter(Protocol):
    """Protocol every engine adapter implements."""

    name: str
    engine_target: EngineTarget

    def configure(self, config: EngineConfig) -> None: ...

    def get_config(self) -> EngineConfig: ...

    def probe(self) -> EngineProbeResult: ...

    def send_asset(
        self,
        asset_dir: Path,
        *,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
    ) -> EngineHandoffResult: ...


__all__ = [
    "EngineAdapter",
    "EngineAssetInvalid",
    "EngineCallError",
    "EngineConfig",
    "EngineHandoffError",
    "EngineHandoffResult",
    "EngineNotConfigured",
    "EngineProbeResult",
    "TransportName",
]
