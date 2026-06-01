"""Offline export bridge for Unity/Unreal MCP handoff.

Ghost-Forge does not directly drive Unreal or Unity. It creates game-ready
asset bundles, then hands a structured bridge package to a separate engine MCP
server (Unity-MCP-Ghost / Unreal-MCP-Ghost) or any importer that understands
the same JSON contract.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .manifest import (
    AssetManifest,
    EngineTarget,
    EngineTargetSpec,
    ManifestBuilder,
    ProvenanceStep,
    manifest_exists,
    read_manifest,
)
from .storage import compute_artifact
from .types import FrozenModel, utc_now

BRIDGE_VERSION: Literal["1.0"] = "1.0"


class ExportBridgeError(RuntimeError):
    """Raised when an asset cannot be packaged for engine bridge handoff."""


class ExportBridgePackage(FrozenModel):
    """Serializable bridge package consumed by external engine MCP tools."""

    bridge_version: Literal["1.0"] = BRIDGE_VERSION
    target_engine: EngineTarget
    recommended_mcp_server: str
    recommended_tool: str = "import_asset"
    asset_id: str
    asset_dir: Path
    asset_path: Path
    manifest_path: Path
    target_path: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    manifest: dict[str, Any]
    notes: str | None = None


def create_export_bridge_package(
    asset_dir: Path | str,
    *,
    target_engine: str | EngineTarget,
    target_path: str | None = None,
    bridge_dir: Path | str | None = None,
    recommended_tool: str = "import_asset",
    notes: str | None = None,
) -> tuple[ExportBridgePackage, Path]:
    """Write a JSON bridge package for an external engine MCP importer.

    The package is intentionally offline: it validates the manifest, locates the
    primary mesh, writes ``ghostforge_bridge_<engine>.json``, and records that
    file back into the asset manifest. It does **not** call Unreal-MCP-Ghost or
    Unity-MCP-Ghost directly.
    """

    asset_path = Path(asset_dir).resolve()
    if not asset_path.is_dir():
        raise ExportBridgeError(f"asset_dir does not exist: {asset_path}")
    if not manifest_exists(asset_path):
        raise ExportBridgeError(f"missing asset_manifest.json under {asset_path}")

    try:
        engine = (
            target_engine
            if isinstance(target_engine, EngineTarget)
            else EngineTarget(str(target_engine))
        )
    except ValueError as exc:
        raise ExportBridgeError(
            f"unsupported target_engine {target_engine!r}; expected unity or unreal"
        ) from exc
    if engine not in {EngineTarget.unity, EngineTarget.unreal}:
        raise ExportBridgeError(
            f"export bridge currently supports unity/unreal, got {engine.value!r}"
        )

    manifest = read_manifest(asset_path)
    primary_mesh = _find_primary_mesh(manifest, asset_path)
    if primary_mesh is None or not primary_mesh.exists():
        raise ExportBridgeError("manifest has no existing mesh.primary artifact")

    package = ExportBridgePackage(
        target_engine=engine,
        recommended_mcp_server=_recommended_server(engine),
        recommended_tool=recommended_tool,
        asset_id=manifest.asset_id,
        asset_dir=asset_path,
        asset_path=primary_mesh,
        manifest_path=asset_path / "asset_manifest.json",
        target_path=target_path,
        manifest=manifest.model_dump(mode="json"),
        notes=notes
        or (
            "Offline bridge package only. Import this JSON with the "
            f"{_recommended_server(engine)} toolchain; Ghost-Forge does not "
            "directly control the game editor."
        ),
    )

    out_dir = Path(bridge_dir).resolve() if bridge_dir else asset_path
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"ghostforge_bridge_{engine.value}.json"
    _atomic_write_json(out_path, package.model_dump(mode="json"))
    _record_bridge(asset_path, package, out_path)
    return package, out_path


def _recommended_server(engine: EngineTarget) -> str:
    if engine == EngineTarget.unity:
        return "Unity-MCP-Ghost"
    if engine == EngineTarget.unreal:
        return "Unreal-MCP-Ghost"
    return "Engine-MCP"


def _find_primary_mesh(manifest: AssetManifest, asset_dir: Path) -> Path | None:
    for artifact in manifest.artifacts:
        if artifact.role == "mesh.primary":
            candidate = Path(artifact.path)
            return candidate if candidate.is_absolute() else (asset_dir / candidate).resolve()
    for artifact in manifest.artifacts:
        if artifact.role.startswith("mesh"):
            candidate = Path(artifact.path)
            return candidate if candidate.is_absolute() else (asset_dir / candidate).resolve()
    return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _record_bridge(
    asset_dir: Path,
    package: ExportBridgePackage,
    package_path: Path,
) -> None:
    builder = ManifestBuilder.for_dir(asset_dir)
    if not builder.has_engine_target(package.target_engine):
        builder.add_engine_target(EngineTargetSpec(engine=package.target_engine))
    builder.add_artifact(compute_artifact(package_path, role=f"engine.bridge.{package.target_engine.value}"))

    history = list(builder.get_custom("engine_export_bridges", []) or [])
    history.append(
        {
            "target_engine": package.target_engine.value,
            "recommended_mcp_server": package.recommended_mcp_server,
            "recommended_tool": package.recommended_tool,
            "package_path": str(package_path),
            "created_at": utc_now().isoformat(),
            "direct_engine_call": False,
        }
    )
    builder.with_custom("engine_export_bridges", history)
    builder.add_provenance(
        ProvenanceStep(
            kind=f"export_bridge_{package.target_engine.value}",
            started_at=utc_now(),
            finished_at=utc_now(),
            parameters={
                "package_path": str(package_path),
                "recommended_tool": package.recommended_tool,
                "direct_engine_call": False,
            },
            notes=package.notes,
        )
    )
    builder.write()


__all__ = [
    "BRIDGE_VERSION",
    "ExportBridgeError",
    "ExportBridgePackage",
    "create_export_bridge_package",
]
