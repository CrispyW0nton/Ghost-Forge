"""Unity-MCP-Ghost adapter.

Defaults are tuned for the conventions Unity-MCP-Ghost follows in its
README: the import tool is exposed as ``import_asset``, asset directories
land under ``Assets/GhostForge/<asset_id>``, and the optional
``project_path`` argument is forwarded so the engine MCP can route the
import to the right Unity project when more than one is open.

The defaults are intentionally minimal — the adapter is designed to be
re-targeted at any Unity-side MCP that follows the same payload contract
just by overriding :class:`EngineConfig`.
"""

from __future__ import annotations

from typing import Any

from ..manifest import AssetManifest, EngineTarget
from .adapter import BaseEngineAdapter
from .base import EngineConfig


class UnityEngineAdapter(BaseEngineAdapter):
    name: str = "unity"
    engine_target: EngineTarget = EngineTarget.unity
    default_import_tool: str = "import_asset"
    default_audit_preset: str = "unity"
    default_description: str = (
        "Hand off finished assets to a Unity-MCP-Ghost server "
        "(stdio or streamable-http)."
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
        # Unity asset paths are slash-rooted at "Assets/" by convention.
        return f"Assets/GhostForge/{manifest.asset_id}"

    def payload_extra(self, manifest: AssetManifest) -> dict[str, Any]:
        cfg = self.get_config()
        extras: dict[str, Any] = {"engine": "unity"}
        if cfg.project_path:
            extras["project_path"] = cfg.project_path
        return extras


__all__ = ["UnityEngineAdapter"]
