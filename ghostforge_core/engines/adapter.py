"""Common engine adapter implementation.

Every concrete adapter (Unity, Unreal) shares the same pipeline:

1. Read and validate the manifest at ``asset_dir``.
2. Locate the primary mesh artifact (``role="mesh.primary"``) and any
   companion textures.
3. Verify the destination engine is in ``manifest.engine_targets`` (or
   skip the check when ``force=True`` and add the engine afterwards).
4. Build a payload that's intentionally engine-agnostic — the engine
   MCP gets paths plus the full manifest dict and decides what to do.
5. Either invoke the configured transport (``dry_run=False``) or skip
   the call but still record the planned invocation for inspection.
6. Append a ``ProvenanceStep`` to the manifest naming the engine,
   transport, and tool, plus the engine response in ``custom``.

Concrete adapter subclasses customise only ``name``,
``engine_target``, the default :class:`EngineConfig`, and an optional
``payload_extra`` hook for engine-specific metadata.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..audit import AuditReport, audit_asset
from ..manifest import (
    AssetManifest,
    EngineTarget,
    EngineTargetSpec,
    ManifestBuilder,
    ProvenanceStep,
    manifest_exists,
    read_manifest,
)
from ..types import utc_now
from .base import (
    EngineAssetInvalid,
    EngineCallError,
    EngineConfig,
    EngineHandoffResult,
    EngineNotConfigured,
    EngineProbeResult,
    TransportName,
)
from .transport import (
    EngineTransport,
    HttpMcpTransport,
    StdioMcpTransport,
)

ENGINE_HANDOFFS_KEY = "engine_handoffs"


class EngineAuditFailed(EngineAssetInvalid):
    """Raised when the pre-handoff audit reports errors and force=False.

    Carries the failed :class:`AuditReport` so callers can surface its
    issues without re-running the audit.
    """

    def __init__(self, report: AuditReport, message: str | None = None) -> None:
        super().__init__(message or f"audit failed with {report.error_count} error(s)")
        self.report = report


class BaseEngineAdapter:
    """Concrete-but-overridable engine adapter.

    Subclasses set the four class attributes and may override
    :meth:`payload_extra` to inject engine-specific fields. Everything
    else (manifest validation, payload assembly, provenance recording)
    stays identical so adapters don't drift.
    """

    name: str = "engine"
    engine_target: EngineTarget = EngineTarget.any
    default_import_tool: str = "import_asset"
    default_description: str = "Generic engine adapter"
    default_audit_preset: str = "default"

    def __init__(
        self,
        config: EngineConfig | None = None,
        *,
        transport: EngineTransport | None = None,
    ) -> None:
        self._config = config or EngineConfig(
            name=self.name,
            transport="none",
            import_tool=self.default_import_tool,
            description=self.default_description,
        )
        self._transport = transport

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    def configure(self, config: EngineConfig) -> None:
        if config.name != self.name:
            # Adapters expose a fixed name to the registry; accidentally
            # passing a config keyed for a different adapter is almost
            # always a wiring bug, so fail loudly.
            raise ValueError(
                f"Config name '{config.name}' does not match adapter '{self.name}'"
            )
        self._config = config
        self._transport = None

    def get_config(self) -> EngineConfig:
        return self._config

    def set_transport(self, transport: EngineTransport | None) -> None:
        """Inject a transport directly (tests, in-process scenarios)."""

        self._transport = transport

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke an arbitrary engine MCP tool.

        Used for engine actions that aren't asset handoffs — placement,
        screenshots, scene loads, play-mode toggling. The adapter still
        gates on transport configuration so callers get a clear
        :class:`EngineNotConfigured` instead of a silent no-op.
        """

        transport = self._resolve_transport()
        return transport.call_tool(name, arguments or {})

    # ------------------------------------------------------------------
    # Probing
    # ------------------------------------------------------------------

    def probe(self) -> EngineProbeResult:
        if self._transport is not None:
            return EngineProbeResult(
                name=self.name,
                configured=True,
                transport="injected",
                metadata={"injected": True, "import_tool": self._config.import_tool},
            )
        cfg = self._config
        if cfg.transport == "stdio":
            if not cfg.command:
                return EngineProbeResult(
                    name=self.name,
                    configured=False,
                    transport="stdio",
                    reason="command not set; configure with a stdio command/args list",
                )
            return EngineProbeResult(
                name=self.name,
                configured=True,
                transport="stdio",
                metadata={
                    "command": cfg.command,
                    "import_tool": cfg.import_tool,
                    "project_path": cfg.project_path,
                },
            )
        if cfg.transport == "http":
            if not cfg.url:
                return EngineProbeResult(
                    name=self.name,
                    configured=False,
                    transport="http",
                    reason="url not set; configure with an MCP streamable-http URL",
                )
            return EngineProbeResult(
                name=self.name,
                configured=True,
                transport="http",
                metadata={
                    "url": cfg.url,
                    "import_tool": cfg.import_tool,
                    "project_path": cfg.project_path,
                },
            )
        return EngineProbeResult(
            name=self.name,
            configured=False,
            transport="none",
            reason=(
                "adapter not configured; set "
                f"GHOSTFORGE_{self.name.upper()}_MCP_* env vars or call "
                "configure_engine_adapter."
            ),
        )

    def _resolve_transport(self) -> EngineTransport:
        if self._transport is not None:
            return self._transport
        cfg = self._config
        if cfg.transport == "stdio":
            if not cfg.command:
                raise EngineNotConfigured(
                    f"Adapter '{self.name}' has stdio transport but no command set"
                )
            return StdioMcpTransport(
                name=self.name,
                command=cfg.command[0],
                args=cfg.command[1:],
                cwd=cfg.cwd,
                env=cfg.env,
                timeout_seconds=cfg.timeout_seconds,
            )
        if cfg.transport == "http":
            if not cfg.url:
                raise EngineNotConfigured(
                    f"Adapter '{self.name}' has http transport but no url set"
                )
            return HttpMcpTransport(
                name=self.name,
                url=cfg.url,
                headers=cfg.headers,
                timeout_seconds=cfg.timeout_seconds,
            )
        raise EngineNotConfigured(
            f"Adapter '{self.name}' has no transport configured "
            "(transport='none'). Provide an injected transport or "
            "configure stdio/http."
        )

    # ------------------------------------------------------------------
    # Send pipeline
    # ------------------------------------------------------------------

    def payload_extra(self, manifest: AssetManifest) -> dict[str, Any]:
        """Hook for subclasses to add engine-specific payload fields."""

        return {}

    def send_asset(
        self,
        asset_dir: Path,
        *,
        target_path: str | None = None,
        dry_run: bool = False,
        force: bool = False,
        extra_args: dict[str, Any] | None = None,
        audit: bool = True,
        audit_preset: str | None = None,
    ) -> EngineHandoffResult:
        asset_path = Path(asset_dir).resolve()
        if not asset_path.is_dir():
            raise EngineAssetInvalid(f"Asset directory does not exist: {asset_path}")
        if not manifest_exists(asset_path):
            raise EngineAssetInvalid(
                f"No asset_manifest.json under {asset_path}; run a generation/"
                "unwrap/texture op first."
            )

        manifest = read_manifest(asset_path)
        primary_mesh = self._find_primary_mesh(manifest, asset_path)
        if primary_mesh is None:
            raise EngineAssetInvalid(
                f"Manifest at {asset_path} has no mesh.primary artifact; "
                "engine adapters require at least one mesh to deliver."
            )
        if not primary_mesh.exists():
            raise EngineAssetInvalid(
                f"Manifest declares mesh.primary at {primary_mesh} but the "
                "file is missing on disk."
            )

        engine_in_targets = any(
            spec.engine == self.engine_target or spec.engine == EngineTarget.any
            for spec in manifest.engine_targets
        )
        if not engine_in_targets and not force:
            raise EngineAssetInvalid(
                f"Asset's engine_targets does not include {self.engine_target.value}. "
                "Pass force=True to deliver anyway (the adapter will record the "
                "engine target on success)."
            )

        audit_report: AuditReport | None = None
        if audit:
            audit_report = audit_asset(
                asset_path,
                preset=audit_preset or self.default_audit_preset,
                run_gltf_validator=True,
                persist=True,
            )
            if audit_report.status == "failed" and not force:
                raise EngineAuditFailed(audit_report)
            # Refresh the manifest because the audit persisted updates.
            manifest = read_manifest(asset_path)

        license_summary = self._summarize_license(manifest)
        target_slot = target_path or self._default_target_path(manifest)

        # Prefer the asset_id-based name in extras so engine MCPs that
        # group imports by namespace can disambiguate easily.
        payload: dict[str, Any] = {
            "asset_id": manifest.asset_id,
            "asset_dir": str(asset_path),
            "asset_path": str(primary_mesh),
            "manifest_path": str(asset_path / "asset_manifest.json"),
            "target_path": target_slot,
            "manifest": manifest.model_dump(mode="json"),
            "license": license_summary,
            "force": force,
            "dry_run": dry_run,
            "audit": audit_report.model_dump(mode="json") if audit_report else None,
        }
        payload.update(self.payload_extra(manifest))
        for key, value in self._config.import_args_extra.items():
            payload.setdefault(key, value)
        if extra_args:
            payload.update(extra_args)

        tool_name = self._config.import_tool
        started = time.monotonic()
        engine_response: dict[str, Any] = {}
        notes: str | None = None

        if dry_run:
            engine_response = {
                "dry_run": True,
                "tool": tool_name,
                "would_call_arguments": payload,
            }
            transport_name: TransportName = self._probe_transport_name()
            notes = "dry_run=True; transport not invoked"
        else:
            transport = self._resolve_transport()
            transport_name = self._probe_transport_name()
            try:
                engine_response = transport.call_tool(tool_name, payload)
            except EngineNotConfigured:
                raise
            except Exception as exc:
                raise EngineCallError(
                    f"Engine '{self.name}' tool '{tool_name}' failed: {exc}"
                ) from exc
            if engine_response.get("isError"):
                raise EngineCallError(
                    f"Engine '{self.name}' tool '{tool_name}' returned an error: "
                    f"{engine_response}"
                )

        duration = time.monotonic() - started
        self._record_handoff_in_manifest(
            asset_dir=asset_path,
            tool_name=tool_name,
            transport_name=transport_name,
            target_slot=target_slot,
            payload=payload,
            engine_response=engine_response,
            duration=duration,
            dry_run=dry_run,
            force=force,
        )

        return EngineHandoffResult(
            engine=self.name,
            asset_dir=asset_path,
            asset_id=manifest.asset_id,
            asset_path=primary_mesh,
            target_path=target_slot,
            transport=transport_name,
            tool=tool_name,
            duration_seconds=max(duration, 0.0),
            dry_run=dry_run,
            engine_response=engine_response,
            notes=notes,
            audit=audit_report.model_dump(mode="json") if audit_report else None,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _probe_transport_name(self) -> TransportName:
        if self._transport is not None:
            return "injected"
        return self._config.transport

    def _find_primary_mesh(
        self,
        manifest: AssetManifest,
        asset_dir: Path,
    ) -> Path | None:
        for artifact in manifest.artifacts:
            if artifact.role == "mesh.primary":
                candidate = Path(artifact.path)
                if not candidate.is_absolute():
                    candidate = (asset_dir / candidate).resolve()
                return candidate
        for artifact in manifest.artifacts:
            if artifact.role.startswith("mesh"):
                candidate = Path(artifact.path)
                if not candidate.is_absolute():
                    candidate = (asset_dir / candidate).resolve()
                return candidate
        return None

    def _default_target_path(self, manifest: AssetManifest) -> str:
        # Engine importers prefer slash-separated logical paths inside
        # their project tree; the asset_id is already filesystem-safe.
        return f"GhostForge/{manifest.asset_id}"

    def _summarize_license(self, manifest: AssetManifest) -> dict[str, Any]:
        spec = manifest.license
        return {
            "spdx": spec.spdx,
            "name": spec.name,
            "holder": spec.holder,
            "attribution": spec.attribution,
            "source_url": spec.source_url,
            "concept_citations": [
                c.model_dump(mode="json") for c in manifest.concept_citations
            ],
        }

    def _record_handoff_in_manifest(
        self,
        *,
        asset_dir: Path,
        tool_name: str,
        transport_name: TransportName,
        target_slot: str | None,
        payload: dict[str, Any],
        engine_response: dict[str, Any],
        duration: float,
        dry_run: bool,
        force: bool,
    ) -> None:
        builder = ManifestBuilder.for_dir(asset_dir)

        if not builder.has_engine_target(self.engine_target):
            builder.add_engine_target(EngineTargetSpec(engine=self.engine_target))

        history = list(builder.get_custom(ENGINE_HANDOFFS_KEY, []) or [])
        history.append(
            {
                "engine": self.name,
                "engine_target": self.engine_target.value,
                "tool": tool_name,
                "transport": transport_name,
                "target_path": target_slot,
                "delivered_at": utc_now().isoformat(),
                "duration_seconds": duration,
                "dry_run": dry_run,
                "force": force,
                "engine_response": engine_response,
            }
        )
        builder.with_custom(ENGINE_HANDOFFS_KEY, history)

        # Provenance is the canonical, ordered audit trail; the custom
        # field above carries richer per-handoff diagnostics for tooling.
        builder.add_provenance(
            ProvenanceStep(
                kind=f"send_to_{self.name}",
                started_at=utc_now(),
                finished_at=utc_now(),
                parameters={
                    "tool": tool_name,
                    "transport": transport_name,
                    "target_path": target_slot,
                    "dry_run": dry_run,
                    "force": force,
                    "import_args_extra_keys": sorted(self._config.import_args_extra.keys()),
                },
                notes=(
                    "dry_run=True; engine MCP not invoked"
                    if dry_run
                    else f"engine response keys: {sorted(engine_response.keys())}"
                ),
            )
        )

        builder.write()


__all__ = ["BaseEngineAdapter", "ENGINE_HANDOFFS_KEY"]
