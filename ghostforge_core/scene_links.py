"""Stable resource links for Ghost Forge scene graph history."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


_LINK_FIELDS = {
    "history_id",
    "resource_id",
    "resource_uri",
    "scene_id",
    "scene_path",
    "scene_object_id",
    "mcp_links",
}


def scene_id_for_path(path: Path | str) -> str:
    stem = Path(path).stem or "scene"
    return _safe_token(stem, fallback="scene")


def scene_resource_uri(scene_id: str) -> str:
    return f"ghostforge://scenes/{_safe_token(scene_id, fallback='scene')}"


def graph_resource_uri(graph_id: str) -> str:
    return f"ghostforge://graphs/{_safe_token(graph_id, fallback='graph')}"


def graph_evaluation_resource_uri(graph_id: str) -> str:
    return f"{graph_resource_uri(graph_id)}/evaluation"


def graph_history_resource_uri(scene_id: str, object_id: str, history_id: str) -> str:
    return (
        f"{scene_resource_uri(scene_id)}/objects/"
        f"{_safe_token(object_id, fallback='object')}/graph-history/"
        f"{_safe_token(history_id, fallback='history')}"
    )


def graph_history_comparison_resource_uri(
    scene_id: str,
    object_id: str,
    left_history_id: str,
    right_history_id: str,
) -> str:
    return (
        f"{graph_history_resource_uri(scene_id, object_id, left_history_id)}"
        f"/compare/{_safe_token(right_history_id, fallback='history')}"
    )


def graph_history_comparison_resource_uri_from_payloads(
    left: dict[str, object],
    right: dict[str, object],
) -> str:
    """Return a comparison resource URI when saved history identity is present."""

    left_history_id = str(left.get("history_id") or "")
    right_history_id = str(right.get("history_id") or "")
    if not left_history_id or not right_history_id:
        return ""

    left_resource_uri = _history_resource_uri(left)
    if left_resource_uri:
        return f"{left_resource_uri}/compare/{_safe_token(right_history_id, fallback='history')}"

    scene_id = str(left.get("scene_id") or right.get("scene_id") or "")
    object_id = str(left.get("scene_object_id") or right.get("scene_object_id") or "")
    if scene_id and object_id:
        return graph_history_comparison_resource_uri(
            scene_id,
            object_id,
            left_history_id,
            right_history_id,
        )
    return ""


def compare_graph_history_payloads(
    left: dict[str, object],
    right: dict[str, object],
) -> dict[str, object]:
    """Return a compact structured diff between two graph-history rows."""

    changed_fields: dict[str, dict[str, object]] = {}
    for key in ("status", "audit_badge", "output_path", "artifact_count", "message", "duration_ms"):
        left_value = left.get(key)
        right_value = right.get(key)
        if left_value != right_value:
            changed_fields[key] = {"left": left_value, "right": right_value}

    left_details = left.get("details") if isinstance(left.get("details"), dict) else {}
    right_details = right.get("details") if isinstance(right.get("details"), dict) else {}
    detail_changes: dict[str, dict[str, list[object]]] = {}
    for key in (
        "artifact_paths",
        "asset_dirs",
        "bridge_paths",
        "manifest_paths",
        "retarget_resolved",
        "retarget_remaining",
        "retarget_new",
    ):
        change = _list_change(
            _detail_list(left_details, key),
            _detail_list(right_details, key),
        )
        if change["added"] or change["removed"]:
            detail_changes[key] = change

    audit_change = _audit_change(left_details, right_details)
    return {
        "left": _history_summary(left),
        "right": _history_summary(right),
        "changed_fields": changed_fields,
        "detail_changes": detail_changes,
        "audit_changes": audit_change,
        "has_changes": bool(changed_fields or detail_changes or audit_change["has_changes"]),
    }


def plan_graph_history_followup_actions(
    left: dict[str, object],
    right: dict[str, object],
    *,
    base_name: str | None = None,
) -> dict[str, object]:
    """Suggest graph/audit actions from a graph-history comparison pair."""

    comparison = compare_graph_history_payloads(left, right)
    left_details = left.get("details") if isinstance(left.get("details"), dict) else {}
    right_details = right.get("details") if isinstance(right.get("details"), dict) else {}
    target_engine = _target_engine_from_details(left_details, right_details)
    graph_id = str(right.get("graph_id") or left.get("graph_id") or "")

    repair_nodes = _retarget_repair_node_actions(
        comparison,
        target_engine=target_engine,
        graph_id=graph_id,
        base_name=base_name,
    )
    audit_tasks = _audit_followup_tasks(
        comparison,
        left_details=left_details,
        right_details=right_details,
        target_engine=target_engine,
    )
    summary_parts: list[str] = []
    if repair_nodes:
        summary_parts.append(f"{len(repair_nodes)} repair node(s)")
    if audit_tasks:
        summary_parts.append(f"{len(audit_tasks)} audit task(s)")
    return {
        "has_actions": bool(repair_nodes or audit_tasks),
        "summary": ", ".join(summary_parts) if summary_parts else "No follow-up actions suggested.",
        "repair_nodes": repair_nodes,
        "audit_tasks": audit_tasks,
    }


def annotate_graph_history_payload(
    payload: dict[str, object],
    *,
    scene_id: str | None = None,
    scene_path: Path | str | None = None,
    object_id: str | None = None,
    history_index: int = 0,
) -> dict[str, object]:
    """Return a graph-history payload with stable resource IDs and MCP links."""

    out = dict(payload)
    graph_id = str(out.get("graph_id") or "")
    history_id = str(out.get("history_id") or "") or _history_id(out, history_index)
    out["history_id"] = history_id
    out["resource_id"] = f"graph_history:{history_id}"

    links = dict(out.get("mcp_links") if isinstance(out.get("mcp_links"), dict) else {})
    if graph_id:
        links["graph"] = graph_resource_uri(graph_id)
        links["graph_evaluation"] = graph_evaluation_resource_uri(graph_id)
    if scene_id:
        safe_scene_id = _safe_token(scene_id, fallback="scene")
        out["scene_id"] = safe_scene_id
        links["scene"] = scene_resource_uri(safe_scene_id)
    if scene_path is not None:
        out["scene_path"] = str(scene_path)
    if object_id:
        out["scene_object_id"] = str(object_id)
        if scene_id:
            links["scene_object_graph_history"] = graph_history_resource_uri(
                scene_id,
                object_id,
                history_id,
            )
            out["resource_uri"] = links["scene_object_graph_history"]
    elif scene_id:
        out["resource_uri"] = links["scene"]
    if links:
        out["mcp_links"] = links
    return out


def annotate_graph_history_sequence(
    payloads: list[dict[str, object]] | tuple[dict[str, object], ...],
    *,
    scene_id: str | None = None,
    scene_path: Path | str | None = None,
    object_id: str | None = None,
) -> tuple[dict[str, object], ...]:
    return tuple(
        annotate_graph_history_payload(
            payload,
            scene_id=scene_id,
            scene_path=scene_path,
            object_id=object_id,
            history_index=index,
        )
        for index, payload in enumerate(payloads)
        if isinstance(payload, dict)
    )


def _history_id(payload: dict[str, object], history_index: int) -> str:
    graph_id = _safe_token(str(payload.get("graph_id") or "graph"), fallback="graph")
    status = _safe_token(str(payload.get("status") or "history"), fallback="history")
    stable = _strip_link_fields(payload)
    encoded = json.dumps(stable, sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:12]
    return f"{graph_id}_{status}_{history_index}_{digest}"


def _history_summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "history_id": payload.get("history_id"),
        "resource_uri": payload.get("resource_uri"),
        "graph_id": payload.get("graph_id"),
        "status": payload.get("status"),
        "audit_badge": payload.get("audit_badge"),
        "output_path": payload.get("output_path"),
        "artifact_count": payload.get("artifact_count"),
        "message": payload.get("message"),
    }


def _history_resource_uri(payload: dict[str, object]) -> str:
    resource_uri = str(payload.get("resource_uri") or "")
    if resource_uri:
        return resource_uri
    links = payload.get("mcp_links")
    if isinstance(links, dict):
        return str(links.get("scene_object_graph_history") or "")
    return ""


def _detail_list(details: object, key: str) -> list[object]:
    if not isinstance(details, dict):
        return []
    value = details.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if item not in (None, "")]


def _list_change(left: list[object], right: list[object]) -> dict[str, list[object]]:
    left_keys = {_stable_item_key(item): item for item in left}
    right_keys = {_stable_item_key(item): item for item in right}
    added = [right_keys[key] for key in sorted(set(right_keys) - set(left_keys))]
    removed = [left_keys[key] for key in sorted(set(left_keys) - set(right_keys))]
    unchanged = [right_keys[key] for key in sorted(set(left_keys) & set(right_keys))]
    return {"added": added, "removed": removed, "unchanged": unchanged}


def _audit_change(left_details: object, right_details: object) -> dict[str, object]:
    left_audit = left_details.get("audit_history") if isinstance(left_details, dict) else None
    right_audit = right_details.get("audit_history") if isinstance(right_details, dict) else None
    left_audit = left_audit if isinstance(left_audit, dict) else {}
    right_audit = right_audit if isinstance(right_audit, dict) else {}
    changed_fields: dict[str, dict[str, object]] = {}
    for key in ("preset", "status", "error_count", "warning_count", "info_count"):
        left_value = left_audit.get(key)
        right_value = right_audit.get(key)
        if left_value != right_value:
            changed_fields[key] = {"left": left_value, "right": right_value}
    issue_change = _list_change(
        _detail_list(left_audit, "audit_issue_list"),
        _detail_list(right_audit, "audit_issue_list"),
    )
    return {
        "changed_fields": changed_fields,
        "issues_added": issue_change["added"],
        "issues_removed": issue_change["removed"],
        "issues_unchanged": issue_change["unchanged"],
        "has_changes": bool(changed_fields or issue_change["added"] or issue_change["removed"]),
    }


def _target_engine_from_details(left_details: object, right_details: object) -> str:
    for details in (right_details, left_details):
        if not isinstance(details, dict):
            continue
        target = str(details.get("retarget_target") or "")
        if target:
            return target
        audit = details.get("audit_history")
        if isinstance(audit, dict):
            preset = str(audit.get("preset") or "")
            if preset in {"unity", "unreal"}:
                return preset
    return ""


def _retarget_repair_node_actions(
    comparison: dict[str, object],
    *,
    target_engine: str,
    graph_id: str,
    base_name: str | None,
) -> list[dict[str, object]]:
    if target_engine not in {"unity", "unreal"}:
        return []
    detail_changes = comparison.get("detail_changes")
    if not isinstance(detail_changes, dict):
        return []
    diagnostics: list[tuple[str, str, str]] = []
    for key in ("retarget_remaining", "retarget_new"):
        change = detail_changes.get(key)
        if not isinstance(change, dict):
            continue
        added = change.get("added")
        if not isinstance(added, list):
            continue
        for item in added:
            rule, code, text = _diagnostic_key_parts(item)
            if rule:
                diagnostics.append((rule, code, text))

    actions: list[dict[str, object]] = []
    emitted: set[str] = set()
    for rule, code, text in diagnostics:
        action = _retarget_repair_node_action(
            rule,
            code,
            target_engine=target_engine,
            graph_id=graph_id,
            base_name=base_name,
            diagnostic_key=text,
        )
        if action is None:
            continue
        node_kind = str(action["node_kind"])
        if node_kind in emitted:
            continue
        emitted.add(node_kind)
        actions.append(action)
    return sorted(actions, key=lambda item: _repair_node_order(str(item.get("node_kind") or "")))


def _retarget_repair_node_action(
    rule: str,
    code: str,
    *,
    target_engine: str,
    graph_id: str,
    base_name: str | None,
    diagnostic_key: str,
) -> dict[str, object] | None:
    node_kind = ""
    params: dict[str, object] = {}
    if rule == "retarget.axis" or code == "axis_mismatch_assumed":
        node_kind = "retarget_axis"
        params = {"from": "gltf_canonical", "to": target_engine}
    elif rule == "retarget.units" or code == "units_scale_required":
        node_kind = "retarget_units"
        params = {"to": target_engine}
    elif rule == "retarget.pivot" or code == "pivot_not_at_base":
        node_kind = "retarget_pivot_for_engine"
        params = {"to": target_engine}
    elif rule == "retarget.naming" or code in {"static_mesh_prefix_missing", "material_prefix_missing"}:
        node_kind = "retarget_apply_naming"
        params = {"to": target_engine, "base_name": base_name or "Asset"}
    if not node_kind:
        return None

    action: dict[str, object] = {
        "action_type": "append_graph_node",
        "node_kind": node_kind,
        "params": params,
        "label": f"Add {node_kind}",
        "reason": f"Repair unresolved {diagnostic_key} for {target_engine}.",
        "diagnostic_key": diagnostic_key,
        "mcp_tool": "append_graph_node",
    }
    if graph_id:
        action["mcp_arguments"] = {
            "graph_id": graph_id,
            "kind": node_kind,
            "params": params,
            "label": f"History repair: {diagnostic_key}",
        }
    return action


def _repair_node_order(node_kind: str) -> int:
    order = {
        "retarget_axis": 0,
        "retarget_units": 1,
        "retarget_pivot_for_engine": 2,
        "retarget_apply_naming": 3,
    }
    return order.get(node_kind, 99)


def _audit_followup_tasks(
    comparison: dict[str, object],
    *,
    left_details: object,
    right_details: object,
    target_engine: str,
) -> list[dict[str, object]]:
    audit_changes = comparison.get("audit_changes")
    if not isinstance(audit_changes, dict) or not audit_changes.get("has_changes"):
        return []
    preset = _audit_preset(right_details) or target_engine or _audit_preset(left_details) or "default"
    asset_dir = _first_detail_path(right_details, "asset_dirs")
    reason = "Re-run audit after graph-history comparison changed validation evidence."
    issues_added = audit_changes.get("issues_added")
    if isinstance(issues_added, list) and issues_added:
        reason = f"Re-run audit after {len(issues_added)} new issue(s) appeared in graph history."
    task: dict[str, object] = {
        "action_type": "submit_audit",
        "label": f"Run {preset} audit",
        "preset": preset,
        "reason": reason,
        "mcp_tool": "submit_audit",
    }
    if asset_dir:
        task["asset_dir"] = asset_dir
        task["mcp_arguments"] = {
            "asset_dir": asset_dir,
            "preset": preset,
            "run_gltf_validator": False,
            "persist": True,
        }
    return [task]


def _audit_preset(details: object) -> str:
    if not isinstance(details, dict):
        return ""
    audit = details.get("audit_history")
    if not isinstance(audit, dict):
        return ""
    return str(audit.get("preset") or "")


def _first_detail_path(details: object, key: str) -> str:
    values = _detail_list(details, key)
    if not values:
        return ""
    return str(values[0])


def _diagnostic_key_parts(item: object) -> tuple[str, str, str]:
    if isinstance(item, dict):
        rule = str(item.get("rule") or "")
        code = str(item.get("code") or "")
        text = f"{rule}:{code}".strip(":") or json.dumps(item, sort_keys=True, default=str)
        return rule, code, text
    text = str(item)
    if ":" in text:
        rule, code = text.split(":", 1)
        return rule.strip(), code.strip(), text
    return text.strip(), "", text


def _stable_item_key(item: object) -> str:
    return json.dumps(_strip_link_fields(item), sort_keys=True, default=str, separators=(",", ":"))


def _strip_link_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _strip_link_fields(item)
            for key, item in value.items()
            if str(key) not in _LINK_FIELDS
        }
    if isinstance(value, (list, tuple)):
        return [_strip_link_fields(item) for item in value]
    return copy.deepcopy(value)


def _safe_token(value: str, *, fallback: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value).strip("_")
    return safe or fallback


__all__ = [
    "annotate_graph_history_payload",
    "annotate_graph_history_sequence",
    "compare_graph_history_payloads",
    "graph_evaluation_resource_uri",
    "graph_history_comparison_resource_uri",
    "graph_history_comparison_resource_uri_from_payloads",
    "graph_history_resource_uri",
    "graph_resource_uri",
    "plan_graph_history_followup_actions",
    "scene_id_for_path",
    "scene_resource_uri",
]
