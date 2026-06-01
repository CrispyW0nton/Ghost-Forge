"""Slice schema sanity checks."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostforge_core.manifest import EngineTarget, LicenseSpec
from ghostforge_core.slice import (
    AssetKind,
    AssetSpec,
    GameBrief,
    GenerationStrategy,
    SLICE_SCHEMA_VERSION,
    StageStatus,
    VerticalSlicePlan,
    VerticalSliceRun,
)
from ghostforge_core.types import utc_now


def test_game_brief_defaults():
    brief = GameBrief(title="Haunted Forest")
    assert brief.target_engine == EngineTarget.unity
    assert brief.license.spdx == "CC0-1.0"
    assert brief.tags == []


def test_asset_spec_defaults():
    spec = AssetSpec(asset_id="rune_stone", description="A weathered rune stone")
    assert spec.kind == AssetKind.prop
    assert spec.strategy == GenerationStrategy.image_to_3d
    assert spec.run_unwrap is False
    assert spec.run_texture is False
    assert spec.concept_k == 3


def test_asset_spec_rejects_zero_concept_k():
    with pytest.raises(ValidationError):
        AssetSpec(asset_id="x", description="d", concept_k=0)


def test_plan_round_trip_json():
    brief = GameBrief(title="Slice", target_engine=EngineTarget.unreal)
    plan = VerticalSlicePlan(
        slice_id="slice-test",
        brief=brief,
        assets=[AssetSpec(asset_id="a", description="d")],
    )
    raw = plan.model_dump_json()
    parsed = VerticalSlicePlan.model_validate_json(raw)
    assert parsed.slice_id == "slice-test"
    assert parsed.brief.target_engine == EngineTarget.unreal
    assert parsed.schema_version == SLICE_SCHEMA_VERSION


def test_run_initial_status_pending():
    run = VerticalSliceRun(
        slice_id="s",
        plan_path="plan.json",
    )
    assert run.status == StageStatus.pending
    assert run.assets == {}


def test_plan_is_immutable():
    brief = GameBrief(title="Slice")
    plan = VerticalSlicePlan(slice_id="s", brief=brief, assets=[])
    with pytest.raises(ValidationError):
        plan.slice_id = "different"  # type: ignore[misc]
