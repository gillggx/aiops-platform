"""Phase α — linear regression / histogram / sort / chart-extensions tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor
from app.services.pipeline_builder.blocks.histogram import HistogramBlockExecutor
from app.services.pipeline_builder.blocks.linear_regression import LinearRegressionBlockExecutor
from app.services.pipeline_builder.blocks.sort import SortBlockExecutor


CTX = ExecutionContext()


# ─── block_linear_regression ────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_linreg_happy_path_produces_three_ports() -> None:
    df = pd.DataFrame({"x": list(range(10)), "y": [2 * i + 1 + (0.1 if i % 2 else 0) for i in range(10)]})
    out = await LinearRegressionBlockExecutor().execute(
        params={"x_column": "x", "y_column": "y"}, inputs={"data": df}, context=CTX
    )
    assert set(out.keys()) == {"stats", "data", "ci"}
    stats = out["stats"]
    assert len(stats) == 1
    row = stats.iloc[0]
    assert abs(row["slope"] - 2.0) < 0.1
    assert row["r_squared"] > 0.99
    assert row["n"] == 10
    # data port has prediction + residual cols
    assert "y_pred" in out["data"].columns
    assert "y_residual" in out["data"].columns
    # ci port has ci_lower/upper columns and is non-empty
    ci = out["ci"]
    assert {"x", "pred", "ci_lower", "ci_upper"}.issubset(ci.columns)
    assert len(ci) > 0
    assert (ci["ci_upper"] >= ci["ci_lower"]).all()


@pytest.mark.asyncio
async def test_linreg_group_by_emits_per_group_stats() -> None:
    rows = []
    for g in ("A", "B"):
        slope = 1.0 if g == "A" else 3.0
        rows.extend({"g": g, "x": i, "y": slope * i} for i in range(8))
    df = pd.DataFrame(rows)
    out = await LinearRegressionBlockExecutor().execute(
        params={"x_column": "x", "y_column": "y", "group_by": "g"},
        inputs={"data": df},
        context=CTX,
    )
    stats = out["stats"].set_index("group")
    assert abs(stats.loc["A", "slope"] - 1.0) < 1e-6
    assert abs(stats.loc["B", "slope"] - 3.0) < 1e-6


@pytest.mark.asyncio
async def test_linreg_insufficient_data_errors() -> None:
    df = pd.DataFrame({"x": [1, 2], "y": [1, 2]})  # n=2 < 3
    with pytest.raises(BlockExecutionError) as ei:
        await LinearRegressionBlockExecutor().execute(
            params={"x_column": "x", "y_column": "y"}, inputs={"data": df}, context=CTX
        )
    assert ei.value.code == "INSUFFICIENT_DATA"


@pytest.mark.asyncio
async def test_linreg_zero_variance_x_errors() -> None:
    df = pd.DataFrame({"x": [5, 5, 5, 5], "y": [1, 2, 3, 4]})
    with pytest.raises(BlockExecutionError) as ei:
        await LinearRegressionBlockExecutor().execute(
            params={"x_column": "x", "y_column": "y"}, inputs={"data": df}, context=CTX
        )
    assert ei.value.code == "INSUFFICIENT_DATA"


# ─── block_histogram ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_histogram_produces_expected_bins() -> None:
    df = pd.DataFrame({"v": list(range(100))})
    out = await HistogramBlockExecutor().execute(
        params={"value_column": "v", "bins": 10}, inputs={"data": df}, context=CTX
    )
    data = out["data"]
    assert len(data) == 10
    assert data["count"].sum() == 100
    assert {"bin_left", "bin_right", "bin_center", "count", "density"}.issubset(data.columns)


@pytest.mark.asyncio
async def test_histogram_group_by_independent() -> None:
    df = pd.DataFrame(
        [{"g": "A", "v": v} for v in range(20)]
        + [{"g": "B", "v": v} for v in range(40)]
    )
    out = await HistogramBlockExecutor().execute(
        params={"value_column": "v", "bins": 5, "group_by": "g"},
        inputs={"data": df},
        context=CTX,
    )
    data = out["data"]
    assert set(data["group"].unique()) == {"A", "B"}
    assert data[data["group"] == "A"]["count"].sum() == 20
    assert data[data["group"] == "B"]["count"].sum() == 40


@pytest.mark.asyncio
async def test_histogram_missing_column_errors() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await HistogramBlockExecutor().execute(
            params={"value_column": "nope"},
            inputs={"data": pd.DataFrame({"x": [1]})},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


# ─── block_sort ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_sort_desc_with_limit_top_n() -> None:
    df = pd.DataFrame(
        [{"tool": "T1", "n": 3}, {"tool": "T2", "n": 10}, {"tool": "T3", "n": 5}, {"tool": "T4", "n": 7}]
    )
    out = await SortBlockExecutor().execute(
        params={"columns": [{"column": "n", "order": "desc"}], "limit": 2},
        inputs={"data": df},
        context=CTX,
    )
    assert out["data"]["tool"].tolist() == ["T2", "T4"]


@pytest.mark.asyncio
async def test_sort_multi_column_stable() -> None:
    df = pd.DataFrame(
        [
            {"a": 1, "b": 2},
            {"a": 1, "b": 1},
            {"a": 2, "b": 2},
        ]
    )
    out = await SortBlockExecutor().execute(
        params={"columns": [{"column": "a", "order": "asc"}, {"column": "b", "order": "asc"}]},
        inputs={"data": df},
        context=CTX,
    )
    assert out["data"][["a", "b"]].values.tolist() == [[1, 1], [1, 2], [2, 2]]


@pytest.mark.asyncio
async def test_sort_unknown_column_errors() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await SortBlockExecutor().execute(
            params={"columns": [{"column": "nope", "order": "asc"}]},
            inputs={"data": pd.DataFrame({"a": [1]})},
            context=CTX,
        )
    assert ei.value.code == "COLUMN_NOT_FOUND"


# ─── block_chart extensions ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_chart_multi_y_array_produces_dsl() -> None:
    df = pd.DataFrame({"t": list(range(5)), "a": range(5), "b": [i * 2 for i in range(5)]})
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "line", "x": "t", "y": ["a", "b"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["__dsl"] is True
    assert spec["y"] == ["a", "b"]


@pytest.mark.asyncio
async def test_chart_dual_axis_via_y_secondary() -> None:
    df = pd.DataFrame({"t": list(range(3)), "a": [1, 2, 3], "b": [100, 200, 300]})
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "line", "x": "t", "y": "a", "y_secondary": ["b"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["__dsl"] is True
    assert spec["y"] == ["a"]
    assert spec["y_secondary"] == ["b"]


@pytest.mark.asyncio
async def test_chart_boxplot_mode() -> None:
    df = pd.DataFrame({"tool": ["A"] * 5 + ["B"] * 5, "v": list(range(10))})
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "boxplot", "x": "tool", "y": "v", "group_by": "tool"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["__dsl"] is True
    assert spec["type"] == "boxplot"
    assert spec["y"] == ["v"]


@pytest.mark.asyncio
async def test_chart_heatmap_mode() -> None:
    df = pd.DataFrame(
        [{"a": "A1", "b": "B1", "val": 0.5}, {"a": "A1", "b": "B2", "val": 0.8}]
    )
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "heatmap", "x": "a", "y": "b", "value_column": "val"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["type"] == "heatmap"
    assert spec["value_key"] == "val"
    assert len(spec["data"]) == 2


@pytest.mark.asyncio
async def test_chart_classic_single_y_still_vega() -> None:
    """Backward-compat: single y string, no SPC → stays Vega-Lite."""
    df = pd.DataFrame({"t": [1, 2, 3], "v": [10, 20, 30]})
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "line", "x": "t", "y": "v"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert "__dsl" not in spec
    assert spec["mark"] == "line"
