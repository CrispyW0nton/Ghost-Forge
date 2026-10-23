from __future__ import annotations

from ghostforge_core.scene_links import plan_graph_history_followup_actions


def test_graph_history_followups_suggest_repair_nodes_and_audit_task(tmp_path):
    left = {
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "audit_badge": "passed",
        "details": {
            "asset_dirs": [str(tmp_path / "asset")],
            "retarget_target": "unreal",
            "retarget_remaining": [],
            "audit_history": {
                "preset": "unreal",
                "status": "passed",
                "warning_count": 0,
                "audit_issue_list": [],
            },
        },
    }
    right = {
        "graph_id": "obj_cube_graph",
        "status": "succeeded",
        "audit_badge": "warnings",
        "details": {
            "asset_dirs": [str(tmp_path / "asset")],
            "retarget_target": "unreal",
            "retarget_remaining": [
                "retarget.units:units_scale_required",
                "retarget.pivot:pivot_not_at_base",
            ],
            "audit_history": {
                "preset": "unreal",
                "status": "warnings",
                "warning_count": 1,
                "audit_issue_list": [
                    {
                        "severity": "warning",
                        "rule": "retarget.units",
                        "code": "units_scale_required",
                        "message": "Scale needs engine conversion.",
                    }
                ],
            },
        },
    }

    plan = plan_graph_history_followup_actions(left, right, base_name="Crate")

    assert plan["has_actions"] is True
    assert [node["node_kind"] for node in plan["repair_nodes"]] == [
        "retarget_units",
        "retarget_pivot_for_engine",
    ]
    assert plan["repair_nodes"][0]["params"] == {"to": "unreal"}
    assert plan["repair_nodes"][0]["mcp_arguments"]["graph_id"] == "obj_cube_graph"
    assert plan["audit_tasks"] == [
        {
            "action_type": "submit_audit",
            "label": "Run unreal audit",
            "preset": "unreal",
            "reason": "Re-run audit after 1 new issue(s) appeared in graph history.",
            "mcp_tool": "submit_audit",
            "asset_dir": str(tmp_path / "asset"),
            "mcp_arguments": {
                "asset_dir": str(tmp_path / "asset"),
                "preset": "unreal",
                "run_gltf_validator": False,
                "persist": True,
            },
        }
    ]


def test_graph_history_followups_skip_unknown_repair_without_target_engine():
    plan = plan_graph_history_followup_actions(
        {"details": {"retarget_remaining": []}},
        {"details": {"retarget_remaining": ["retarget.units:units_scale_required"]}},
    )

    assert plan == {
        "has_actions": False,
        "summary": "No follow-up actions suggested.",
        "repair_nodes": [],
        "audit_tasks": [],
    }
