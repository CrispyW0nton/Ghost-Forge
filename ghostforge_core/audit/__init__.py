"""Game-readiness audit pipeline.

GhostForge produces assets; engines consume them. The audit layer is
the bridge that asks, *before any engine handoff*, "is this asset
actually ready for that engine?". It answers via:

* A rule registry (:mod:`ghostforge_core.audit.rules`) covering
  manifest completeness, geometry counts/scale/normals, UV channels,
  texture color spaces, LODs, collision intent, and naming.
* Engine-specific presets (:mod:`ghostforge_core.audit.presets`) that
  switch thresholds and required checks per target engine.
* An optional shell-out to the Khronos glTF Validator
  (:mod:`ghostforge_core.audit.gltf_validator`).
* A persistent record in ``manifest.custom['audit_history']`` plus the
  existing ``manifest.validation`` summary, so the next process to read
  the manifest sees the same verdict the audit returned.

The main entry point is :func:`audit_asset`. Engine adapters call it
before sending; agents and tooling can call it directly via the
``audit_asset`` MCP tool.
"""

from __future__ import annotations

from .gltf_validator import GLTF_VALIDATOR_RULE_ID, check_gltf_validator
from .presets import (
    PRESET_FACTORIES,
    AuditPreset,
    default_preset,
    get_preset,
    list_presets,
    unity_preset,
    unreal_preset,
)
from .report import (
    AuditIssue,
    AuditReport,
    AuditRuleResult,
    AuditSeverity,
    AuditStatus,
    aggregate_status,
    rule_status,
)
from .rules import DEFAULT_RULES, AuditContext, AuditRule, run_rule
from .runner import AUDIT_HISTORY_KEY, audit_asset

__all__ = [
    "AUDIT_HISTORY_KEY",
    "AuditContext",
    "AuditIssue",
    "AuditPreset",
    "AuditReport",
    "AuditRule",
    "AuditRuleResult",
    "AuditSeverity",
    "AuditStatus",
    "DEFAULT_RULES",
    "GLTF_VALIDATOR_RULE_ID",
    "PRESET_FACTORIES",
    "aggregate_status",
    "audit_asset",
    "check_gltf_validator",
    "default_preset",
    "get_preset",
    "list_presets",
    "rule_status",
    "run_rule",
    "unity_preset",
    "unreal_preset",
]
