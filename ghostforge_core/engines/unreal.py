"""Unreal-MCP-Ghost adapter.

Mirrors :mod:`ghostforge_core.engines.unity` but for the Unreal-side MCP.
Unreal projects place imported assets under ``/Game/...`` content paths,
so the default target slot follows that convention.
"""

from __future__ import annotations

from typing import Any

from ..manifest import AssetManifest, EngineTarget
from .adapter import BaseEngineAdapter
from .base import EngineConfig


class UnrealEngineAdapter(BaseEngineAdapter):
    name: str = "unreal"
    engine_target: EngineTarget = EngineTarget.unreal
    default_import_tool: str = "import_asset"
    default_audit_preset: str = "unreal"
    default_description: str = (
        "Optional direct handoff to an explicitly configured Unreal-MCP-Ghost "
        "transport. Default workflow is the offline export bridge."
    )

    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        transport=None,
    ) -> None:
        super().__init__(
            config
            or EngineConfig(
                name=self.name,
                transport="none",
                import_tool=self.default_import_tool,
                description=self.default_description,
            ),
            transport=transport,
        )

    def _default_target_path(self, manifest: AssetManifest) -> str:
        return f"/Game/GhostForge/{manifest.asset_id}"

    def payload_extra(self, manifest: AssetManifest) -> dict[str, Any]:
        cfg = self.get_config()
        extras: dict[str, Any] = {"engine": "unreal"}
        if cfg.project_path:
            extras["project_path"] = cfg.project_path
        return extras


__all__ = ["UnrealEngineAdapter"]
