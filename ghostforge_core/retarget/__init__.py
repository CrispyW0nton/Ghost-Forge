"""Cross-engine asset linting & retargeting (P12).

Exposes:

* :class:`EngineConventions` profiles (``gltf_canonical``, ``unity``,
  ``unreal``) and a :class:`NamingConventions` schema.
* :data:`CROSS_ENGINE_RULES` — audit rules that surface axis, unit,
  naming, lightmap, pivot, collision, and texture mismatches relative
  to a target engine profile.
* :func:`unity_retarget_preset` / :func:`unreal_retarget_preset` —
  presets that compose the default audit rules with the cross-engine
  rules above.
* :data:`RETARGET_OPERATIONS` — operations registered into the P11
  authoring registry (``retarget_axis``, ``retarget_units``,
  ``retarget_pivot_for_engine``, ``retarget_apply_naming``).
* :func:`plan_retarget_graph_for_asset` — auto-retarget planner: audit
  diagnostics → :class:`EditGraph` of retarget ops.
"""

from __future__ import annotations

from .operations import RETARGET_OPERATIONS
from .planner import (
    plan_retarget_graph_for_asset,
    plan_retarget_graph_from_diagnostics,
)
from .presets import (
    retarget_rules_for_preset,
    unity_retarget_preset,
    unreal_retarget_preset,
)
from .profiles import (
    EngineConventions,
    NamingConventions,
    PROFILE_FACTORIES,
    get_profile,
    gltf_canonical_profile,
    list_profiles,
    unity_profile,
    unreal_profile,
)
from .rules import CROSS_ENGINE_RULES, cross_engine_rule_ids


__all__ = [
    "CROSS_ENGINE_RULES",
    "EngineConventions",
    "NamingConventions",
    "PROFILE_FACTORIES",
    "RETARGET_OPERATIONS",
    "cross_engine_rule_ids",
    "get_profile",
    "gltf_canonical_profile",
    "list_profiles",
    "plan_retarget_graph_for_asset",
    "plan_retarget_graph_from_diagnostics",
    "retarget_rules_for_preset",
    "unity_profile",
    "unity_retarget_preset",
    "unreal_profile",
    "unreal_retarget_preset",
]
