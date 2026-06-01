"""Optional integration with the Khronos glTF-Validator CLI.

The validator is shipped as an npm package (``gltf-validator``) and
several platform-specific binaries. We don't want to make it a hard
dep — most contributors run the audit without Node installed — so this
module:

* Locates the CLI on PATH (or honours ``GHOSTFORGE_GLTF_VALIDATOR``).
* If found, runs it against the primary mesh and parses the JSON
  report into our :class:`AuditIssue` list.
* If not found, returns a single ``skipped`` rule result so the
  audit report is honest about what ran.

The validator's JSON report has ``messages`` with severity ``0=Error``,
``1=Warning``, ``2=Info``, ``3=Hint``. We map those to our scheme.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .report import AuditIssue, AuditRuleResult, AuditSeverity, rule_status
from .rules import AuditContext

GLTF_VALIDATOR_RULE_ID = "gltf.validator"

_SEVERITY_MAP = {
    0: AuditSeverity.error,
    1: AuditSeverity.warning,
    2: AuditSeverity.info,
    3: AuditSeverity.info,
}


def _resolve_validator_path() -> str | None:
    """Return the validator executable path, or None if unavailable."""

    explicit = os.environ.get("GHOSTFORGE_GLTF_VALIDATOR")
    if explicit:
        # Allow an explicit override pointing at a binary that may not
        # be on PATH yet.
        if Path(explicit).exists() or shutil.which(explicit):
            return explicit
    return shutil.which("gltf-validator") or shutil.which("gltf_validator.exe")


def _primary_mesh(ctx: AuditContext) -> Path | None:
    for artifact in ctx.manifest.artifacts:
        if artifact.role == "mesh.primary":
            candidate = Path(artifact.path)
            if not candidate.is_absolute():
                candidate = (ctx.asset_dir / candidate).resolve()
            return candidate
    return None


def _run_validator(executable: str, mesh_path: Path) -> dict:
    """Invoke the validator and return the parsed JSON report.

    The validator can write to stdout with ``-o`` and ``-r``; we keep
    things simple by passing the file path and parsing whatever lands
    on stdout. ``-w`` ensures full warning/info output. ``-q`` would
    silence them, which we don't want in an audit context.
    """

    proc = subprocess.run(
        [executable, str(mesh_path), "-o", "-r"],
        capture_output=True,
        text=True,
        check=False,
        timeout=120.0,
    )
    if not proc.stdout.strip():
        # Fallback: validator may have written a sidecar JSON file next
        # to the mesh.
        sidecar = mesh_path.with_suffix(mesh_path.suffix + "_report.json")
        if sidecar.exists():
            return json.loads(sidecar.read_text(encoding="utf-8"))
        raise RuntimeError(
            f"gltf-validator returned no stdout (exit {proc.returncode}): "
            f"{proc.stderr.strip()}"
        )
    return json.loads(proc.stdout)


def check_gltf_validator(ctx: AuditContext) -> AuditRuleResult:
    started = time.monotonic()
    executable = _resolve_validator_path()
    if executable is None:
        return AuditRuleResult(
            rule=GLTF_VALIDATOR_RULE_ID,
            title="glTF Validator (Khronos)",
            description=(
                "Run the official Khronos glTF Validator on the primary "
                "mesh. Skipped when the gltf-validator CLI is not on PATH."
            ),
            status="skipped",
            skipped=True,
            skip_reason=(
                "gltf-validator CLI not found. Install via `npm install -g "
                "gltf-validator` or set GHOSTFORGE_GLTF_VALIDATOR to the binary path."
            ),
            duration_seconds=time.monotonic() - started,
        )

    mesh_path = _primary_mesh(ctx)
    if mesh_path is None or not mesh_path.exists():
        return AuditRuleResult(
            rule=GLTF_VALIDATOR_RULE_ID,
            title="glTF Validator (Khronos)",
            description="Run Khronos glTF Validator over mesh.primary.",
            status="skipped",
            skipped=True,
            skip_reason="No mesh.primary artifact resolved on disk.",
            duration_seconds=time.monotonic() - started,
        )

    if mesh_path.suffix.lower() not in {".glb", ".gltf"}:
        return AuditRuleResult(
            rule=GLTF_VALIDATOR_RULE_ID,
            title="glTF Validator (Khronos)",
            description="Run Khronos glTF Validator over mesh.primary.",
            status="skipped",
            skipped=True,
            skip_reason=(
                f"Primary mesh is {mesh_path.suffix}; validator only inspects glTF/GLB. "
                "Re-export as glb to enable this rule."
            ),
            duration_seconds=time.monotonic() - started,
        )

    try:
        report = _run_validator(executable, mesh_path)
    except Exception as exc:
        return AuditRuleResult(
            rule=GLTF_VALIDATOR_RULE_ID,
            title="glTF Validator (Khronos)",
            description="Run Khronos glTF Validator over mesh.primary.",
            status="skipped",
            skipped=True,
            skip_reason=f"validator invocation failed: {type(exc).__name__}: {exc}",
            duration_seconds=time.monotonic() - started,
        )

    issues: list[AuditIssue] = []
    issues_block = report.get("issues") or {}
    for message in issues_block.get("messages", []):
        severity_int = int(message.get("severity", 1))
        severity = _SEVERITY_MAP.get(severity_int, AuditSeverity.warning)
        issues.append(
            AuditIssue(
                rule=GLTF_VALIDATOR_RULE_ID,
                severity=severity,
                code=str(message.get("code", "gltf_validator")),
                message=str(message.get("message", "")),
                target=str(mesh_path),
                details={
                    "pointer": message.get("pointer"),
                    "offset": message.get("offset"),
                    "validator_severity": severity_int,
                },
            )
        )

    duration = time.monotonic() - started
    return AuditRuleResult(
        rule=GLTF_VALIDATOR_RULE_ID,
        title="glTF Validator (Khronos)",
        description="Run Khronos glTF Validator over mesh.primary.",
        status=rule_status(issues),
        skipped=False,
        issues=issues,
        duration_seconds=duration,
    )


__all__ = [
    "GLTF_VALIDATOR_RULE_ID",
    "check_gltf_validator",
]
