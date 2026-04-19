"""PR-A — Evidence semantics: evidence is the full audit trail, NOT a filtered subset.

Every rows-based logic block emits:
  - triggered (bool)
  - evidence (DataFrame) containing ALL evaluated rows + `triggered_row` bool column
"""
from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import ExecutionContext
from app.services.pipeline_builder.blocks.any_trigger import AnyTriggerBlockExecutor
from app.services.pipeline_builder.blocks.consecutive_rule import ConsecutiveRuleBlockExecutor
from app.services.pipeline_builder.blocks.threshold import ThresholdBlockExecutor
from app.services.pipeline_builder.blocks.weco_rules import WecoRulesBlockExecutor


CTX = ExecutionContext()


# ─── Threshold: evidence = all rows ────────────────────────────────────────
@pytest.mark.asyncio
async def test_threshold_evidence_keeps_all_rows_including_non_triggering() -> None:
    df = pd.DataFrame({"v": [1, 2, 3, 4, 5]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "v", "bound_type": "upper", "upper_bound": 3},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert len(ev) == 5  # all evaluated
    assert ev["triggered_row"].tolist() == [False, False, False, True, True]


@pytest.mark.asyncio
async def test_threshold_no_trigger_still_shows_all_rows() -> None:
    df = pd.DataFrame({"v": [1, 2, 3]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "v", "operator": ">", "target": 100},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is False
    assert len(out["evidence"]) == 3
    assert out["evidence"]["triggered_row"].sum() == 0


# ─── Consecutive: evidence = all rows (sorted), not just tail ──────────────
@pytest.mark.asyncio
async def test_consecutive_evidence_includes_non_tail_rows() -> None:
    df = pd.DataFrame([
        {"t": "01", "flag": False},
        {"t": "02", "flag": True},
        {"t": "03", "flag": True},
        {"t": "04", "flag": True},
    ])
    out = await ConsecutiveRuleBlockExecutor().execute(
        params={"flag_column": "flag", "count": 3, "sort_by": "t"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert len(ev) == 4  # all 4 rows, not just tail 3
    # Only last 3 rows are marked triggered
    assert ev["triggered_row"].tolist() == [False, True, True, True]


@pytest.mark.asyncio
async def test_consecutive_no_trigger_still_emits_all_rows() -> None:
    df = pd.DataFrame([{"t": str(i), "flag": i < 2} for i in range(4)])
    out = await ConsecutiveRuleBlockExecutor().execute(
        params={"flag_column": "flag", "count": 3, "sort_by": "t"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is False
    ev = out["evidence"]
    assert len(ev) == 4
    assert ev["triggered_row"].sum() == 0


# ─── WECO: per-row audit with triggered_rules CSV ─────────────────────────
@pytest.mark.asyncio
async def test_weco_evidence_row_aligned_with_input() -> None:
    # 1 point > 3σ + 9 normal points (none triggering R2) — should fire R1 at row 5.
    values = [100, 100, 100, 100, 100, 130, 100, 100, 100, 100]
    df = pd.DataFrame([{"t": f"{i:02d}", "v": v} for i, v in enumerate(values)])
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "v",
            "sigma_source": "manual",
            "manual_sigma": 5.0,
            "rules": ["R1"],
            "sort_by": "t",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert len(ev) == 10  # one row per input
    assert "triggered_rules" in ev.columns
    assert "violation_side" in ev.columns
    # Row with value 130 should be the only triggering one
    triggered = ev[ev["triggered_row"]]
    assert len(triggered) == 1
    assert triggered.iloc[0]["v"] == 130
    assert triggered.iloc[0]["triggered_rules"] == "R1"


# ─── AnyTrigger: concat all evidences including non-triggering ones ──────
@pytest.mark.asyncio
async def test_any_trigger_concats_all_evidences_not_only_triggered() -> None:
    # ev1 is from non-triggering source; ev2 is from triggering source
    ev1 = pd.DataFrame([{"x": 1, "triggered_row": False}])
    ev2 = pd.DataFrame([{"x": 2, "triggered_row": True}])
    out = await AnyTriggerBlockExecutor().execute(
        params={},
        inputs={
            "trigger_1": False, "evidence_1": ev1,
            "trigger_2": True,  "evidence_2": ev2,
        },
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    # PR-A: both evidences concatenated (not filtered by triggered)
    assert len(ev) == 2
    assert set(ev["source_port"]) == {"trigger_1", "trigger_2"}
    assert ev["triggered_row"].tolist() == [False, True]
