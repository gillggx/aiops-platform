"""Unit tests for Phase-1 block executors (v3.2 logic-node schema)."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.alert import AlertBlockExecutor
from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.consecutive_rule import ConsecutiveRuleBlockExecutor
from app.services.pipeline_builder.blocks.delta import DeltaBlockExecutor
from app.services.pipeline_builder.blocks.filter import FilterBlockExecutor
from app.services.pipeline_builder.blocks.threshold import ThresholdBlockExecutor


CTX = ExecutionContext()


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"eventTime": "2026-04-18T10:00", "toolID": "EQP-01", "step": "STEP_002", "value": 100.0},
            {"eventTime": "2026-04-18T10:05", "toolID": "EQP-01", "step": "STEP_002", "value": 105.0},
            {"eventTime": "2026-04-18T10:10", "toolID": "EQP-01", "step": "STEP_002", "value": 130.0},
            {"eventTime": "2026-04-18T10:15", "toolID": "EQP-01", "step": "STEP_002", "value": 135.0},
            {"eventTime": "2026-04-18T10:20", "toolID": "EQP-01", "step": "STEP_003", "value": 90.0},
            {"eventTime": "2026-04-18T10:25", "toolID": "EQP-01", "step": "STEP_002", "value": 140.0},
        ]
    )


# ─── filter ─────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_filter_equals() -> None:
    block = FilterBlockExecutor()
    out = await block.execute(
        params={"column": "step", "operator": "==", "value": "STEP_002"},
        inputs={"data": _sample_df()},
        context=CTX,
    )
    assert len(out["data"]) == 5


@pytest.mark.asyncio
async def test_filter_numeric_gt() -> None:
    block = FilterBlockExecutor()
    out = await block.execute(
        params={"column": "value", "operator": ">", "value": 120},
        inputs={"data": _sample_df()},
        context=CTX,
    )
    assert len(out["data"]) == 3


@pytest.mark.asyncio
async def test_filter_missing_column() -> None:
    block = FilterBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"column": "nonexistent", "operator": "==", "value": "x"},
            inputs={"data": _sample_df()},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


@pytest.mark.asyncio
async def test_filter_invalid_operator() -> None:
    block = FilterBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"column": "value", "operator": "BOGUS", "value": 1},
            inputs={"data": _sample_df()},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


# ─── threshold (logic-node schema) ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_threshold_upper_triggers() -> None:
    block = ThresholdBlockExecutor()
    df = _sample_df()
    out = await block.execute(
        params={"column": "value", "bound_type": "upper", "upper_bound": 120},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    # PR-A: evidence is full rows audit trail, not filtered subset
    assert len(ev) == len(df)
    assert ev["triggered_row"].sum() == 3
    # violation_side filled only on triggered rows
    triggered = ev[ev["triggered_row"]]
    assert triggered["violation_side"].tolist() == ["above"] * 3
    assert triggered["violated_bound"].tolist() == [120] * 3
    assert all("> upper_bound" in s for s in triggered["explanation"])


@pytest.mark.asyncio
async def test_threshold_both_triggers() -> None:
    block = ThresholdBlockExecutor()
    df = _sample_df()
    out = await block.execute(
        params={"column": "value", "bound_type": "both", "upper_bound": 120, "lower_bound": 95},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert len(ev) == len(df)
    assert ev["triggered_row"].sum() == 4


@pytest.mark.asyncio
async def test_threshold_no_trigger() -> None:
    block = ThresholdBlockExecutor()
    df = _sample_df()
    out = await block.execute(
        params={"column": "value", "bound_type": "upper", "upper_bound": 1000},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is False
    # PR-A: evidence is audit trail — still full rows even when nothing triggered
    ev = out["evidence"]
    assert len(ev) == len(df)
    assert ev["triggered_row"].sum() == 0


@pytest.mark.asyncio
async def test_threshold_missing_bound() -> None:
    block = ThresholdBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"column": "value", "bound_type": "upper"},
            inputs={"data": _sample_df()},
            context=CTX,
        )
    assert ei.value.code == "MISSING_PARAM"


# ─── consecutive_rule (tail-based) ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_consecutive_rule_tail_triggers() -> None:
    # last 3 rows are True → should trigger
    df = pd.DataFrame(
        [
            {"eventTime": "t1", "violates": False},
            {"eventTime": "t2", "violates": True},
            {"eventTime": "t3", "violates": True},
            {"eventTime": "t4", "violates": True},
        ]
    )
    block = ConsecutiveRuleBlockExecutor()
    out = await block.execute(
        params={"flag_column": "violates", "count": 3, "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    # PR-A: evidence = all evaluated rows (4 here)
    assert len(ev) == 4
    triggered = ev[ev["triggered_row"]]
    assert len(triggered) == 3
    assert triggered["run_position"].tolist() == [1, 2, 3]
    assert triggered["run_length"].tolist() == [3, 3, 3]
    assert len(set(triggered["trigger_id"])) == 1


@pytest.mark.asyncio
async def test_consecutive_rule_tail_no_trigger_when_last_is_false() -> None:
    # historical run of 3, but most recent is False → should NOT trigger
    df = pd.DataFrame(
        [
            {"eventTime": "t1", "violates": True},
            {"eventTime": "t2", "violates": True},
            {"eventTime": "t3", "violates": True},
            {"eventTime": "t4", "violates": False},
        ]
    )
    block = ConsecutiveRuleBlockExecutor()
    out = await block.execute(
        params={"flag_column": "violates", "count": 3, "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is False
    ev = out["evidence"]
    # PR-A: evidence contains all 4 evaluated rows even when not triggered
    assert len(ev) == 4
    assert ev["triggered_row"].sum() == 0


@pytest.mark.asyncio
async def test_consecutive_rule_group_by_only_one_group_triggers() -> None:
    df = pd.DataFrame(
        [
            {"eventTime": "t1", "violates": True, "toolID": "A"},
            {"eventTime": "t2", "violates": True, "toolID": "A"},
            {"eventTime": "t3", "violates": False, "toolID": "A"},
            {"eventTime": "t1", "violates": True, "toolID": "B"},
            {"eventTime": "t2", "violates": True, "toolID": "B"},
            {"eventTime": "t3", "violates": True, "toolID": "B"},
        ]
    )
    block = ConsecutiveRuleBlockExecutor()
    out = await block.execute(
        params={
            "flag_column": "violates",
            "count": 3,
            "sort_by": "eventTime",
            "group_by": "toolID",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    # PR-A: evidence = all 6 evaluated rows (both groups)
    assert len(ev) == 6
    triggered = ev[ev["triggered_row"]]
    # Only group B tail N is triggered
    assert len(triggered) == 3
    assert all(triggered["group"] == "B")


@pytest.mark.asyncio
async def test_consecutive_rule_required_sort_by() -> None:
    block = ConsecutiveRuleBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"flag_column": "violates", "count": 3},  # no sort_by
            inputs={"data": pd.DataFrame([{"violates": True}])},
            context=CTX,
        )
    assert ei.value.code == "MISSING_PARAM"


@pytest.mark.asyncio
async def test_consecutive_rule_sort_by_column_not_found() -> None:
    df = pd.DataFrame([{"violates": True}, {"violates": True}, {"violates": True}])
    block = ConsecutiveRuleBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"flag_column": "violates", "count": 3, "sort_by": "nonexistent"},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


# ─── delta ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_delta_basic_rising() -> None:
    df = pd.DataFrame(
        [
            {"eventTime": "t1", "v": 10.0},
            {"eventTime": "t2", "v": 12.0},
            {"eventTime": "t3", "v": 11.0},
            {"eventTime": "t4", "v": 15.0},
        ]
    )
    block = DeltaBlockExecutor()
    out = await block.execute(
        params={"value_column": "v", "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    d = out["data"]
    assert d["v_delta"].tolist()[1:] == [2.0, -1.0, 4.0]
    assert d["v_is_rising"].tolist() == [False, True, False, True]
    assert d["v_is_falling"].tolist() == [False, False, True, False]


@pytest.mark.asyncio
async def test_delta_group_by_independent_series() -> None:
    df = pd.DataFrame(
        [
            {"tool": "A", "t": 1, "v": 1.0},
            {"tool": "A", "t": 2, "v": 2.0},
            {"tool": "B", "t": 1, "v": 9.0},
            {"tool": "B", "t": 2, "v": 8.0},
        ]
    )
    block = DeltaBlockExecutor()
    out = await block.execute(
        params={"value_column": "v", "sort_by": "t", "group_by": "tool"},
        inputs={"data": df},
        context=CTX,
    )
    d = out["data"]
    # Both groups' first rows have NaN delta
    assert d.loc[d["t"] == 1, "v_delta"].isna().all()
    assert bool(d.loc[(d["tool"] == "A") & (d["t"] == 2), "v_is_rising"].iloc[0]) is True
    assert bool(d.loc[(d["tool"] == "B") & (d["t"] == 2), "v_is_falling"].iloc[0]) is True


@pytest.mark.asyncio
async def test_delta_missing_column() -> None:
    block = DeltaBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"value_column": "nope", "sort_by": "eventTime"},
            inputs={"data": pd.DataFrame([{"eventTime": "x"}])},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


# ─── alert (logic-node upstream) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_alert_triggered_produces_one_row() -> None:
    evidence = pd.DataFrame(
        [
            {"eventTime": "2026-04-18T10:00", "value": 13.5},
            {"eventTime": "2026-04-18T10:05", "value": 14.1},
            {"eventTime": "2026-04-18T10:10", "value": 15.2},
        ]
    )
    block = AlertBlockExecutor()
    out = await block.execute(
        params={
            "severity": "HIGH",
            "title_template": "xbar over bound",
            "message_template": "3 events, last value {value}",
        },
        inputs={"triggered": True, "evidence": evidence},
        context=CTX,
    )
    alert = out["alert"]
    assert len(alert) == 1
    row = alert.iloc[0]
    assert row["severity"] == "HIGH"
    assert bool(row["triggered"]) is True
    assert row["evidence_count"] == 3
    assert row["first_event_time"] == "2026-04-18T10:00"
    assert row["last_event_time"] == "2026-04-18T10:10"
    assert "13.5" in row["message"]  # {value} rendered from first evidence row


@pytest.mark.asyncio
async def test_alert_not_triggered_emits_empty() -> None:
    block = AlertBlockExecutor()
    out = await block.execute(
        params={"severity": "LOW"},
        inputs={"triggered": False, "evidence": pd.DataFrame()},
        context=CTX,
    )
    assert out["alert"].empty


@pytest.mark.asyncio
async def test_alert_requires_bool_triggered() -> None:
    block = AlertBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"severity": "LOW"},
            inputs={"triggered": "yes", "evidence": pd.DataFrame()},
            context=CTX,
        )
    assert ei.value.code == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_alert_invalid_severity() -> None:
    block = AlertBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"severity": "XXL"},
            inputs={"triggered": True, "evidence": pd.DataFrame([{"a": 1}])},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"
