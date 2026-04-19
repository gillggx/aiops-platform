"""Phase β — any_trigger / unpivot / cpk / union / weco R3/R4/R7/R8 tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.any_trigger import AnyTriggerBlockExecutor
from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.cpk import CpkBlockExecutor
from app.services.pipeline_builder.blocks.union import UnionBlockExecutor
from app.services.pipeline_builder.blocks.unpivot import UnpivotBlockExecutor
from app.services.pipeline_builder.blocks.weco_rules import WecoRulesBlockExecutor


CTX = ExecutionContext()


# ─── block_any_trigger ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_any_trigger_or_semantics() -> None:
    out = await AnyTriggerBlockExecutor().execute(
        params={},
        inputs={"trigger_1": False, "trigger_2": True, "trigger_3": False},
        context=CTX,
    )
    assert out["triggered"] is True


@pytest.mark.asyncio
async def test_any_trigger_merges_evidence_with_source_port() -> None:
    ev2 = pd.DataFrame([{"eventTime": "t1", "value": 10.0}])
    ev3 = pd.DataFrame([{"eventTime": "t2", "value": 20.0}])
    out = await AnyTriggerBlockExecutor().execute(
        params={},
        inputs={
            "trigger_1": False, "evidence_1": pd.DataFrame(),
            "trigger_2": True,  "evidence_2": ev2,
            "trigger_3": True,  "evidence_3": ev3,
        },
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert len(ev) == 2
    assert set(ev["source_port"].unique()) == {"trigger_2", "trigger_3"}


@pytest.mark.asyncio
async def test_any_trigger_no_inputs_errors() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await AnyTriggerBlockExecutor().execute(params={}, inputs={}, context=CTX)
    assert ei.value.code == "MISSING_INPUT"


@pytest.mark.asyncio
async def test_any_trigger_rejects_non_bool() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await AnyTriggerBlockExecutor().execute(
            params={}, inputs={"trigger_1": "yes"}, context=CTX
        )
    assert ei.value.code == "INVALID_INPUT"


# ─── block_unpivot ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_unpivot_wide_to_long_for_spc_chart_types() -> None:
    df = pd.DataFrame([
        {"t": "t1", "tool": "EQP-01", "xbar": 100.0, "r_chart": 5.0, "s_chart": 2.0},
        {"t": "t2", "tool": "EQP-01", "xbar": 102.0, "r_chart": 4.5, "s_chart": 2.1},
    ])
    out = await UnpivotBlockExecutor().execute(
        params={
            "id_columns": ["t", "tool"],
            "value_columns": ["xbar", "r_chart", "s_chart"],
            "variable_name": "chart_type",
            "value_name": "value",
        },
        inputs={"data": df},
        context=CTX,
    )
    long_df = out["data"]
    # 2 rows × 3 cols = 6 long rows
    assert len(long_df) == 6
    assert set(long_df["chart_type"].unique()) == {"xbar", "r_chart", "s_chart"}
    assert "value" in long_df.columns


@pytest.mark.asyncio
async def test_unpivot_missing_column_errors() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await UnpivotBlockExecutor().execute(
            params={"id_columns": ["id"], "value_columns": ["bogus"]},
            inputs={"data": pd.DataFrame({"id": [1], "x": [10]})},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


# ─── block_cpk ───────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cpk_two_sided() -> None:
    df = pd.DataFrame({"v": [9.8, 10.0, 10.2, 9.9, 10.1, 10.0, 10.3, 9.7]})
    out = await CpkBlockExecutor().execute(
        params={"value_column": "v", "usl": 11.0, "lsl": 9.0},
        inputs={"data": df},
        context=CTX,
    )
    stats = out["stats"].iloc[0]
    assert stats["cp"] is not None and stats["cp"] > 0
    assert stats["cpk"] is not None
    assert stats["cpk"] <= stats["cp"]  # Cpk ≤ Cp always


@pytest.mark.asyncio
async def test_cpk_requires_at_least_one_limit() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await CpkBlockExecutor().execute(
            params={"value_column": "v"},
            inputs={"data": pd.DataFrame({"v": [1, 2, 3]})},
            context=CTX,
        )
    assert ei.value.code == "MISSING_PARAM"


@pytest.mark.asyncio
async def test_cpk_constant_data_errors() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await CpkBlockExecutor().execute(
            params={"value_column": "v", "usl": 10, "lsl": 0},
            inputs={"data": pd.DataFrame({"v": [5, 5, 5, 5]})},
            context=CTX,
        )
    assert ei.value.code == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_cpk_group_by() -> None:
    df = pd.DataFrame(
        [{"tool": "A", "v": v} for v in [9.8, 10.0, 10.2, 10.0, 9.9]]
        + [{"tool": "B", "v": v} for v in [10.5, 10.4, 10.6, 10.5, 10.3]]
    )
    out = await CpkBlockExecutor().execute(
        params={"value_column": "v", "usl": 11.0, "lsl": 9.0, "group_by": "tool"},
        inputs={"data": df},
        context=CTX,
    )
    stats = out["stats"].set_index("group")
    assert "A" in stats.index and "B" in stats.index
    # Tool A is more centered → Cpk(A) should be > Cpk(B)
    assert stats.loc["A", "cpk"] > stats.loc["B", "cpk"]


# ─── block_union ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_union_outer_keeps_all_columns() -> None:
    p = pd.DataFrame([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
    s = pd.DataFrame([{"a": 3, "c": True}])
    out = await UnionBlockExecutor().execute(
        params={"on_schema_mismatch": "outer"},
        inputs={"primary": p, "secondary": s},
        context=CTX,
    )
    merged = out["data"]
    assert len(merged) == 3
    assert set(merged.columns) == {"a", "b", "c"}


@pytest.mark.asyncio
async def test_union_intersect_only_common() -> None:
    p = pd.DataFrame([{"a": 1, "b": "x"}])
    s = pd.DataFrame([{"a": 2, "c": True}])
    out = await UnionBlockExecutor().execute(
        params={"on_schema_mismatch": "intersect"},
        inputs={"primary": p, "secondary": s},
        context=CTX,
    )
    merged = out["data"]
    assert list(merged.columns) == ["a"]
    assert merged["a"].tolist() == [1, 2]


# ─── block_weco_rules — new rules R3/R4/R7/R8 ────────────────────────────────
@pytest.mark.asyncio
async def test_weco_r3_six_consecutive_rising() -> None:
    # 6 strictly rising → R3 above
    values = [10.0, 11, 12, 13, 14, 15, 16]
    df = pd.DataFrame([{"eventTime": f"t{i:02d}", "value": v, "center": 10, "ucl": 30} for i, v in enumerate(values)])
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "manual",
            "manual_sigma": 5.0,
            "rules": ["R3"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    assert out["evidence"]["triggered_rules"].fillna("").str.contains("R3").any()


@pytest.mark.asyncio
async def test_weco_r4_fourteen_alternating() -> None:
    # 15 points alternating — should trigger R4
    values = [10.0, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10, 12, 10]
    df = pd.DataFrame([{"eventTime": f"t{i:02d}", "value": v, "center": 11} for i, v in enumerate(values)])
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "manual",
            "manual_sigma": 1.0,
            "rules": ["R4"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    assert out["evidence"]["triggered_rules"].fillna("").str.contains("R4").any()


@pytest.mark.asyncio
async def test_weco_r7_fifteen_within_one_sigma() -> None:
    # 15 points within center±1σ → R7
    df = pd.DataFrame([
        {"eventTime": f"t{i:02d}", "value": 100.0 + (i % 3) * 0.1, "center": 100, "ucl": 130}
        for i in range(15)
    ])
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "manual",
            "manual_sigma": 10.0,
            "rules": ["R7"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    assert out["evidence"]["triggered_rules"].fillna("").str.contains("R7").any()


@pytest.mark.asyncio
async def test_weco_r8_eight_outside_one_sigma() -> None:
    # 8 consecutive points all > center + 1σ
    df = pd.DataFrame([
        {"eventTime": f"t{i:02d}", "value": 120.0 + i * 0.1, "center": 100}
        for i in range(8)
    ])
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "value",
            "center_column": "center",
            "sigma_source": "manual",
            "manual_sigma": 5.0,  # 1σ = 5, so values > 105 are outside
            "rules": ["R8"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    assert out["evidence"]["triggered_rules"].fillna("").str.contains("R8").any()
