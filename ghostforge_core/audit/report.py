"""Audit result types.

A *game-readiness audit* runs a set of rules over an asset directory
and emits a structured :class:`AuditReport`. Reports are designed to be
both human- and machine-friendly: severities follow the same
``error/warning/info`` scheme as :class:`ValidationReport`, plus a
per-rule grouping so MCP clients can show a checklist UI without
re-grouping flat issues.

Reports are FrozenModels so they can be serialised in MCP responses,
embedded in :attr:`AssetManifest.validation`, or stored as audit
history in ``manifest.custom["audit_history"]`` without anyone mutating
the values out from under us.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from ..types import FrozenModel, utc_now


class AuditSeverity(str, Enum):
    error = "error"
    warning = "warning"
    info = "info"


AuditStatus = Literal["passed", "warnings", "failed", "skipped"]


class AuditIssue(FrozenModel):
    """One findable thing the audit wants you to know about.

    ``rule`` matches the id of the rule that surfaced the issue (e.g.
    ``"geometry.scale"``). ``code`` is a short machine-readable label
    that's stable across invocations so dashboards can deduplicate.
    """

    rule: str
    severity: AuditSeverity
    code: str
    message: str
    target: str | None = None
    suggestion: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditRuleResult(FrozenModel):
    """Outcome for a single rule.

    Rules are skipped (rather than failed) when they can't run — for
    example, ``gltf.validator`` skips if the external CLI isn't
    installed. Skipping records ``skip_reason`` so reports remain
    actionable.
    """

    rule: str
    title: str
    description: str = ""
    status: AuditStatus = "skipped"
    skipped: bool = False
    skip_reason: str | None = None
    issues: list[AuditIssue] = Field(default_factory=list)
    duration_seconds: float = Field(default=0.0, ge=0.0)


class AuditReport(FrozenModel):
    """Top-level audit document attached to an asset."""

    asset_id: str
    asset_dir: Path
    preset: str
    target_engines: list[str] = Field(default_factory=list)
    status: AuditStatus = "skipped"
    error_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    rules: list[AuditRuleResult] = Field(default_factory=list)
    issues: list[AuditIssue] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    duration_seconds: float = Field(default=0.0, ge=0.0)


def aggregate_status(rules: list[AuditRuleResult]) -> AuditStatus:
    """Roll up rule statuses into a single audit verdict.

    The order matters: any failure trumps everything else, then any
    warning, then any passed rule, then "skipped" if every rule was
    skipped (otherwise an empty audit would falsely look "passed").
    """

    has_error = any(r.status == "failed" for r in rules)
    has_warning = any(r.status == "warnings" for r in rules)
    has_pass = any(r.status == "passed" for r in rules)
    if has_error:
        return "failed"
    if has_warning:
        return "warnings"
    if has_pass:
        return "passed"
    return "skipped"


def rule_status(issues: list[AuditIssue]) -> AuditStatus:
    """Status for a single rule based on the issues it surfaced."""

    if any(i.severity == AuditSeverity.error for i in issues):
        return "failed"
    if any(i.severity == AuditSeverity.warning for i in issues):
        return "warnings"
    return "passed"


__all__ = [
    "AuditIssue",
    "AuditReport",
    "AuditRuleResult",
    "AuditSeverity",
    "AuditStatus",
    "aggregate_status",
    "rule_status",
]
