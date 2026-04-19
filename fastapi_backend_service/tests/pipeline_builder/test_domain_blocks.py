"""Unit tests for v1.2b domain blocks: shift_lag, rolling_window, weco_rules."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.rolling_window import RollingWindowBlockExecutor
from app.services.pipeline_builder.blocks.shift_lag import ShiftLagBlockExecutor
from app.services.pipeline_builder.blocks.weco_rules import WecoRulesBlockExecutor


CTX = ExecutionContext()


# ─── block_shift_lag ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_shift_lag_basic_offset_1() -> None:
    df = pd.DataFrame(
        [
            {"eventTime": "t1", "value": 100.0},
            {"eventTime": "t2", "value": 110.0},
            {"eventTime": "t3", "value": 120.0},
        ]
    )
    block = ShiftLagBlockExecutor()
    out = await block.execute(
        params={"column": "value", "offset": 1, "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    result = out["data"]
    assert result["value_lag1"].iloc[0] != result["value_lag1"].iloc[0]  # NaN at first row
    assert result["value_lag1"].iloc[1] == 100.0
    assert result["value_lag1"].iloc[2] == 110.0
    assert result["value_delta"].iloc[1] == 10.0
    assert result["value_delta"].iloc[2] == 10.0


@pytest.mark.asyncio
async def test_shift_lag_group_by() -> None:
    df = pd.DataFrame(
        [
            {"lot": "A", "eventTime": "t1", "v": 1.0},
            {"lot": "A", "eventTime": "t2", "v": 2.0},
            {"lot": "B", "eventTime": "t1", "v": 10.0},
            {"lot": "B", "eventTime": "t2", "v": 20.0},
        ]
    )
    block = ShiftLagBlockExecutor()
    out = await block.execute(
        params={"column": "v", "offset": 1, "group_by": "lot", "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    # Each group independently shifts — first row of each lot is NaN
    result = out["data"].sort_values(["lot", "eventTime"]).reset_index(drop=True)
    assert pd.isna(result[result["lot"] == "A"]["v_lag1"].iloc[0])
    assert result[result["lot"] == "A"]["v_lag1"].iloc[1] == 1.0
    assert pd.isna(result[result["lot"] == "B"]["v_lag1"].iloc[0])
    assert result[result["lot"] == "B"]["v_lag1"].iloc[1] == 10.0


@pytest.mark.asyncio
async def test_shift_lag_rejects_zero_offset() -> None:
    df = pd.DataFrame([{"v": 1.0}])
    block = ShiftLagBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(params={"column": "v", "offset": 0}, inputs={"data": df}, context=CTX)
    assert ei.value.code == "INVALID_PARAM"


# ─── block_rolling_window ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rolling_window_mean() -> None:
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0]})
    block = RollingWindowBlockExecutor()
    out = await block.execute(
        params={"column": "v", "window": 3, "func": "mean"},
        inputs={"data": df},
        context=CTX,
    )
    result = out["data"]
    # With min_periods=1 (default), first value = 1, second = 1.5, ...
    assert result["v_rolling_mean"].iloc[0] == 1.0
    assert result["v_rolling_mean"].iloc[1] == 1.5
    assert result["v_rolling_mean"].iloc[2] == 2.0  # (1+2+3)/3
    assert result["v_rolling_mean"].iloc[4] == 4.0  # (3+4+5)/3


@pytest.mark.asyncio
async def test_rolling_window_std() -> None:
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0]})
    block = RollingWindowBlockExecutor()
    out = await block.execute(
        params={"column": "v", "window": 2, "func": "std", "min_periods": 2},
        inputs={"data": df},
        context=CTX,
    )
    result = out["data"]
    # First row has NaN (min_periods=2), second row std([1,2]) = 0.707...
    assert pd.isna(result["v_rolling_std"].iloc[0])
    assert result["v_rolling_std"].iloc[1] == pytest.approx(0.7071, abs=0.001)


@pytest.mark.asyncio
async def test_rolling_window_invalid_func() -> None:
    df = pd.DataFrame({"v": [1, 2]})
    block = RollingWindowBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"column": "v", "window": 2, "func": "BAD"}, inputs={"data": df}, context=CTX
        )
    assert ei.value.code == "INVALID_PARAM"


# ─── block_weco_rules ──────────────────────────────────────────────────────


def _weco_df(values: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"eventTime": f"t{i:02d}", "value": v, "ucl": 113.0} for i, v in enumerate(values)]
    )


@pytest.mark.asyncio
async def test_weco_r1_single_point_beyond_3sigma() -> None:
    # With center=100, UCL=113 → σ = (113-100)/3 ≈ 4.33
    # Value 115 > 100 + 3*4.33 = 113 → R1 above
    # Value 85 < 100 - 3*4.33 = 87 → R1 below
    values = [99, 101, 100, 115, 100, 85, 100]
    df = pd.DataFrame(
        [{"eventTime": f"t{i:02d}", "value": v, "ucl": 113.0} for i, v in enumerate(values)]
    )
    block = WecoRulesBlockExecutor()
    out = await block.execute(
        params={
            "value_column": "value",
            "sigma_source": "manual",
            "manual_sigma": 4.33,
            "rules": ["R1"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    # PR-A: weco evidence = per-input-row audit with triggered_rules CSV + violation_side
    triggered_rows = ev[ev["triggered_row"]]
    rule_sides = list(zip(triggered_rows["triggered_rules"].tolist(), triggered_rows["violation_side"].tolist()))
    assert ("R1", "above") in rule_sides
    assert ("R1", "below") in rule_sides


@pytest.mark.asyncio
async def test_weco_r2_nine_consecutive_same_side() -> None:
    # 10 consecutive above explicit center (100) → R2 above trigger.
    # We provide `center` via a center_column whose mean = 100.
    values = [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]
    df = pd.DataFrame(
        [{"eventTime": f"t{i:02d}", "value": v, "center": 100.0} for i, v in enumerate(values)]
    )
    block = WecoRulesBlockExecutor()
    out = await block.execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "manual",
            "manual_sigma": 10.0,
            "rules": ["R2"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    # PR-A: per-row evidence; R2 fires at tail
    ev = out["evidence"]
    assert ev["triggered_rules"].fillna("").str.contains("R2").any()


@pytest.mark.asyncio
async def test_weco_sigma_from_ucl_lcl() -> None:
    """With explicit center=100 column and UCL=130 → σ = (130-100)/3 = 10.
    2 of 3 consecutive > 2σ (>120) same side → R5 triggers."""
    values = [100, 100, 100, 122, 125, 101, 100]
    df = pd.DataFrame(
        [{"eventTime": f"t{i:02d}", "value": v, "center": 100.0, "ucl": 130.0} for i, v in enumerate(values)]
    )
    block = WecoRulesBlockExecutor()
    out = await block.execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "from_ucl_lcl",
            "ucl_column": "ucl",
            "rules": ["R5"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert ev["triggered_rules"].fillna("").str.contains("R5").any()


@pytest.mark.asyncio
async def test_weco_invalid_rule_rejected() -> None:
    df = _weco_df([1, 2, 3])
    block = WecoRulesBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"value_column": "value", "rules": ["R99"], "sigma_source": "manual", "manual_sigma": 1},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


@pytest.mark.asyncio
async def test_weco_from_ucl_lcl_missing_ucl_column() -> None:
    df = _weco_df([1, 2, 3])
    block = WecoRulesBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"value_column": "value", "sigma_source": "from_ucl_lcl"},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "MISSING_PARAM"
