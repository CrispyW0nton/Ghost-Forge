"""Slice store + planner persistence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from ghostforge_core.slice import (
    AssetSpec,
    GameBrief,
    PlanValidationError,
    SliceNotFound,
    SliceStore,
    StageStatus,
    plan_vertical_slice,
    update_plan_assets,
)
from ghostforge_core.storage import Storage


@pytest.fixture
def store(tmp_path: Path) -> SliceStore:
    return SliceStore(Storage(root=tmp_path))


def _brief() -> GameBrief:
    return GameBrief(title="Test Slice")


def _asset(asset_id: str = "a1") -> AssetSpec:
    return AssetSpec(
        asset_id=asset_id,
        description="An item.",
        reference_image_path=Path(__file__),
        worker="stub_image_to_3d",
    )


def test_plan_save_and_load_round_trip(store):
    plan = plan_vertical_slice(
        store=store,
        brief=_brief(),
        assets=[_asset("rock"), _asset("tree")],
        slice_id="slice-rt",
    )
    loaded = store.load_plan("slice-rt")
    assert loaded.slice_id == "slice-rt"
    assert {a.asset_id for a in loaded.assets} == {"rock", "tree"}


def test_plan_missing_slice_raises(store):
    with pytest.raises(SliceNotFound):
        store.load_plan("nope")


def test_plan_validates_duplicate_asset_ids(store):
    with pytest.raises(PlanValidationError):
        plan_vertical_slice(
            store=store,
            brief=_brief(),
            assets=[_asset("dup"), _asset("dup")],
            slice_id="slice-dup",
        )


def test_plan_validates_missing_reference_image(store, tmp_path):
    spec = AssetSpec(
        asset_id="a",
        description="d",
        strategy="image_to_3d",
        reference_image_path=tmp_path / "missing.png",
    )
    with pytest.raises(PlanValidationError):
        plan_vertical_slice(
            store=store,
            brief=_brief(),
            assets=[spec],
            slice_id="slice-img",
        )


def test_plan_assigns_default_target_engine_from_brief(store):
    brief = GameBrief(title="X", target_engine="unreal")
    plan = plan_vertical_slice(
        store=store,
        brief=brief,
        assets=[_asset("a")],
        slice_id="slice-engine",
    )
    assert plan.assets[0].target_engine.value == "unreal"


def test_update_plan_assets_marks_updated_at(store):
    plan = plan_vertical_slice(
        store=store,
        brief=_brief(),
        assets=[_asset("first")],
        slice_id="slice-up",
    )
    original_updated = plan.updated_at
    new_plan = update_plan_assets(store, "slice-up", [_asset("second"), _asset("third")])
    assert new_plan.updated_at >= original_updated
    assert {a.asset_id for a in new_plan.assets} == {"second", "third"}


def test_get_or_init_run_seeds_asset_states(store):
    plan = plan_vertical_slice(
        store=store,
        brief=_brief(),
        assets=[_asset("a"), _asset("b")],
        slice_id="slice-init",
    )
    run = store.get_or_init_run(plan)
    assert set(run.assets) == {"a", "b"}
    assert all(s.status == StageStatus.pending for s in run.assets.values())

    run2 = store.get_or_init_run(plan)  # idempotent — returns existing
    assert run2.slice_id == run.slice_id


def test_list_summaries(store):
    plan_vertical_slice(
        store=store,
        brief=_brief(),
        assets=[_asset("a")],
        slice_id="slice-list-1",
    )
    plan_vertical_slice(
        store=store,
        brief=GameBrief(title="Other", target_engine="unreal"),
        assets=[_asset("b"), _asset("c")],
        slice_id="slice-list-2",
    )
    summaries = store.list_summaries()
    by_id = {s.slice_id: s for s in summaries}
    assert by_id["slice-list-1"].asset_count == 1
    assert by_id["slice-list-2"].asset_count == 2
    assert by_id["slice-list-2"].target_engine == "unreal"


def test_delete_removes_slice_dir(store):
    plan_vertical_slice(
        store=store,
        brief=_brief(),
        assets=[_asset("a")],
        slice_id="slice-del",
    )
    assert store.slice_dir("slice-del").exists()
    store.delete("slice-del")
    assert not store.slice_dir("slice-del").exists()
    with pytest.raises(SliceNotFound):
        store.delete("slice-del")
