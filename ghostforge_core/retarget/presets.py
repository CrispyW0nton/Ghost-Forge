"""Audit presets that include the cross-engine retarget rules.

The default ``unity`` / ``unreal`` presets in ``audit.presets`` focus on
sanity (poly counts, UV/normal presence). The retarget presets add
cross-engine concerns on top so a single audit run produces both:

* Game-readiness signal (geometry counts, license, naming safety)
* Cross-engine retargeting hints (axis, units, lightmap UV, naming
  prefixes, pivot, collision, textures)

Each retarget preset emits an *override* of the corresponding base
preset; the planner uses the same rule set later when generating an
auto-retarget edit graph.
"""

from __future__ import annotations

from ..audit.presets import AuditPreset, unity_preset, unreal_preset
from ..audit.rules import DEFAULT_RULES, AuditRule
from .rules import CROSS_ENGINE_RULES


def unity_retarget_preset() -> AuditPreset:
    base = unity_preset()
    return base.model_copy(
        update={
            "name": "unity",
            "description": (
                "Unity preset extended with cross-engine retargeting rules. "
                "Use before handoff to surface axis / unit / naming / lightmap UV "
                "fixes the auto-retarget planner would apply."
            ),
        }
    )


def unreal_retarget_preset() -> AuditPreset:
    base = unreal_preset()
    return base.model_copy(
        update={
            "name": "unreal",
            "description": (
                "Unreal Engine 5 preset extended with cross-engine retargeting "
                "rules. Adds collision, naming-prefix, and unit-scale checks "
                "so an Unreal handoff catches them before import."
            ),
        }
    )


def retarget_rules_for_preset(preset_name: str) -> list[AuditRule]:
    """Return the full rule list (default + cross-engine) for a preset."""

    return list(DEFAULT_RULES) + list(CROSS_ENGINE_RULES)


__all__ = [
    "retarget_rules_for_preset",
    "unity_retarget_preset",
    "unreal_retarget_preset",
]
