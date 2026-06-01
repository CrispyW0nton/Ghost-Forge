"""Audit orchestrator.

Loads the manifest at ``asset_dir``, builds an :class:`AuditContext`,
runs every rule in turn, optionally invokes the external glTF
Validator, and assembles an :class:`AuditReport`. Persists a copy of
the report into ``manifest.validation`` and ``manifest.custom["audit_history"]``
so the next reader (engine adapter, dashboard, CI gate) sees the same
view we returned.

The runner is deliberately decoupled from the JobRunner — it works as
a plain function call too, which keeps unit tests simple and lets the
desktop app run audits synchronously without spinning up the durable
job store.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from ..manifest import (
    AssetManifest,
    ManifestBuilder,
    ProvenanceStep,
    ValidationSummary,
    manifest_exists,
    read_manifest,
)
from ..types import utc_now
from ..validation import Issue, ValidationReport
from .gltf_validator import check_gltf_validator
from .presets import AuditPreset, default_preset, get_preset
from .report import (
    AuditIssue,
    AuditReport,
    AuditRuleResult,
    AuditSeverity,
    aggregate_status,
)
from .rules import DEFAULT_RULES, AuditContext, AuditRule, run_rule

AUDIT_HISTORY_KEY = "audit_history"


def _flatten_issues(rules: list[AuditRuleResult]) -> list[AuditIssue]:
    out: list[AuditIssue] = []
    for r in rules:
        out.extend(r.issues)
    return out


def _counts(issues: list[AuditIssue]) -> tuple[int, int, int]:
    errors = sum(1 for i in issues if i.severity == AuditSeverity.error)
    warnings = sum(1 for i in issues if i.severity == AuditSeverity.warning)
    infos = sum(1 for i in issues if i.severity == AuditSeverity.info)
    return errors, warnings, infos


def _to_validation_summary(report: AuditReport) -> ValidationSummary:
    """Derive the manifest's existing ValidationSummary from an audit.

    The manifest's :class:`ValidationReport` carries flat lists of
    :class:`Issue`. We map audit issues into that shape so existing
    consumers (dashboards, MCP read_asset_manifest) keep working,
    while the richer per-rule structure is stored in
    ``manifest.custom['audit_history']`` for power users.
    """

    errors: list[Issue] = []
    warnings: list[Issue] = []
    info: list[Issue] = []
    for rule in report.rules:
        for issue in rule.issues:
            target = Issue(
                code=f"{issue.rule}:{issue.code}",
                message=issue.message,
                location=issue.target,
            )
            if issue.severity == AuditSeverity.error:
                errors.append(target)
            elif issue.severity == AuditSeverity.warning:
                warnings.append(target)
            else:
                info.append(target)

    return ValidationSummary(
        status=report.status,
        error_count=len(errors),
        warning_count=len(warnings),
        info_count=len(info),
        report=ValidationReport(errors=errors, warnings=warnings, info=info),
    )


def audit_asset(
    asset_dir: Path | str,
    *,
    preset: AuditPreset | str | None = None,
    rules: list[AuditRule] | None = None,
    run_gltf_validator: bool = True,
    persist: bool = True,
    job_id: str | None = None,
    progress: Callable[[str, float, str], None] | None = None,
) -> AuditReport:
    """Run the audit and (by default) persist the result into the manifest.

    Parameters
    ----------
    asset_dir:
        Asset directory containing ``asset_manifest.json``.
    preset:
        Either an :class:`AuditPreset`, a preset name (``"default"`` /
        ``"unity"`` / ``"unreal"``), or ``None`` for the default preset.
    rules:
        Override the default rule list (e.g. for unit tests).
    run_gltf_validator:
        If ``True`` and the validator CLI is installed, append its
        result to the report.
    persist:
        Update ``manifest.validation`` and append to
        ``manifest.custom['audit_history']`` so subsequent reads see
        the verdict. Set ``False`` to dry-run.
    job_id:
        Optional job id to record on the manifest provenance step
        (used by the JobRunner integration).
    progress:
        Optional callback fired between rules with ``(stage, percent,
        message)`` for streaming MCP progress.
    """

    asset_path = Path(asset_dir)
    if not manifest_exists(asset_path):
        raise FileNotFoundError(f"No asset_manifest.json at {asset_path}")

    if isinstance(preset, str):
        resolved_preset = get_preset(preset)
    elif preset is None:
        resolved_preset = default_preset()
    else:
        resolved_preset = preset

    manifest: AssetManifest = read_manifest(asset_path)
    ctx = AuditContext(
        manifest=manifest,
        asset_dir=asset_path.resolve(),
        preset=resolved_preset,
    )

    started_at = utc_now()
    started_perf = time.monotonic()
    rule_list = list(rules or DEFAULT_RULES)
    total_steps = len(rule_list) + (1 if run_gltf_validator else 0)
    completed = 0

    rule_results: list[AuditRuleResult] = []
    for rule in rule_list:
        if progress:
            progress("rule", _percent(completed, total_steps), f"running {rule.id}")
        rule_results.append(run_rule(rule, ctx))
        completed += 1

    if run_gltf_validator:
        if progress:
            progress("rule", _percent(completed, total_steps), "running gltf.validator")
        rule_results.append(check_gltf_validator(ctx))
        completed += 1

    finished_at = utc_now()
    duration = max(time.monotonic() - started_perf, 0.0)
    issues = _flatten_issues(rule_results)
    error_count, warning_count, info_count = _counts(issues)
    report = AuditReport(
        asset_id=manifest.asset_id,
        asset_dir=asset_path.resolve(),
        preset=resolved_preset.name,
        target_engines=[e.value for e in resolved_preset.target_engines],
        status=aggregate_status(rule_results),
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        rules=rule_results,
        issues=issues,
        started_at=started_at,
        finished_at=finished_at,
        duration_seconds=duration,
    )

    if persist:
        _persist_audit(asset_path, report, job_id=job_id)

    if progress:
        progress("done", 100.0, f"audit {report.status}")
    return report


def _percent(done: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return min(100.0, max(0.0, 100.0 * done / total))


def _persist_audit(asset_dir: Path, report: AuditReport, *, job_id: str | None) -> None:
    """Write the audit's ValidationSummary back into the manifest.

    Three things land in the manifest:

    1. ``validation`` is replaced with a fresh summary derived from the
       audit so consumers using the existing field see the latest state.
    2. ``custom['audit_history']`` keeps an append-only trail of audit
       reports (capped to the last 16 to bound manifest size).
    3. A ``ProvenanceStep`` records that an audit ran, with the preset
       name, status, and counts as parameters.
    """

    builder = ManifestBuilder.for_dir(asset_dir)
    builder.with_validation(_to_validation_summary(report))

    history = list(builder.get_custom(AUDIT_HISTORY_KEY, []) or [])
    history.append(report.model_dump(mode="json"))
    if len(history) > 16:
        history = history[-16:]
    builder.with_custom(AUDIT_HISTORY_KEY, history)

    builder.add_provenance(
        ProvenanceStep(
            kind="audit",
            job_id=job_id,
            started_at=report.started_at,
            finished_at=report.finished_at,
            parameters={
                "preset": report.preset,
                "status": report.status,
                "error_count": report.error_count,
                "warning_count": report.warning_count,
                "info_count": report.info_count,
                "rule_ids": [r.rule for r in report.rules],
            },
        )
    )
    builder.write()


__all__ = ["AUDIT_HISTORY_KEY", "audit_asset"]
