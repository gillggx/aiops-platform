"""Phase v3.5 — distribution chart + sigma_zones + histogram stats tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor
from app.services.pipeline_builder.blocks.histogram import HistogramBlockExecutor


CTX = ExecutionContext()


# ─── chart_type="distribution" ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_distribution_emits_bars_pdf_sigma_rules() -> None:
    import numpy as np
    rng = np.random.default_rng(42)
    df = pd.DataFrame({"v": rng.normal(100, 2, size=400)})
    out = await ChartBlockExecutor().execute(
        params={
            "chart_type": "distribution",
            "value_column": "v",
            "bins": 20,
            "show_sigma_lines": [1, 2, 3, 4],
        },
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["type"] == "distribution"
    assert spec["__dsl"] is True
    assert len(spec["data"]) == 20
    assert len(spec["pdf_data"]) > 0
    labels = [r["label"] for r in spec["rules"]]
    assert "μ" in labels
    for k in (1, 2, 3, 4):
        assert f"+{k}σ" in labels
        assert f"-{k}σ" in labels
    assert spec["stats"]["n"] == 400
    assert abs(spec["stats"]["mu"] - 100) < 0.5
    assert abs(spec["stats"]["sigma"] - 2) < 0.5


@pytest.mark.asyncio
async def test_distribution_with_usl_lsl() -> None:
    df = pd.DataFrame({"v": list(range(50))})
    out = await ChartBlockExecutor().execute(
        params={
            "chart_type": "distribution",
            "value_column": "v",
            "bins": 10,
            "usl": 45.0,
            "lsl": 5.0,
        },
        inputs={"data": df},
        context=CTX,
    )
    labels = [r["label"] for r in out["chart_spec"]["rules"]]
    assert "USL" in labels
    assert "LSL" in labels


@pytest.mark.asyncio
async def test_distribution_insufficient_data() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await ChartBlockExecutor().execute(
            params={"chart_type": "distribution", "value_column": "v"},
            inputs={"data": pd.DataFrame({"v": [1.0]})},  # n<2
            context=CTX,
        )
    assert ei.value.code == "INSUFFICIENT_DATA"


# ─── sigma_zones on SPC line chart ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_sigma_zones_add_rules_with_colors() -> None:
    df = pd.DataFrame([
        {"t": i, "v": 100 + (i % 5) * 0.1, "ucl": 110.0, "lcl": 90.0}
        for i in range(30)
    ])
    out = await ChartBlockExecutor().execute(
        params={
            "chart_type": "line",
            "x": "t", "y": "v",
            "ucl_column": "ucl", "lcl_column": "lcl",
            "sigma_zones": [1, 2],
        },
        inputs={"data": df},
        context=CTX,
    )
    rules = out["chart_spec"]["rules"]
    labels = [r["label"] for r in rules]
    assert "UCL" in labels and "LCL" in labels
    assert "+1σ" in labels and "-1σ" in labels
    assert "+2σ" in labels and "-2σ" in labels
    # σ rules carry a color override (per-rule color)
    sigma_rules = [r for r in rules if r["style"] == "sigma"]
    assert all("color" in r for r in sigma_rules)


@pytest.mark.asyncio
async def test_sigma_zones_invalid_type() -> None:
    df = pd.DataFrame({"t": [1], "v": [1.0], "ucl": [10.0]})
    with pytest.raises(BlockExecutionError) as ei:
        await ChartBlockExecutor().execute(
            params={
                "chart_type": "line", "x": "t", "y": "v",
                "ucl_column": "ucl",
                "sigma_zones": "not-a-list",
            },
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


# ─── histogram stats port ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_histogram_stats_port_emits_mu_sigma() -> None:
    df = pd.DataFrame({"v": [10.0, 11, 12, 13, 14, 15, 16, 17, 18, 19]})
    out = await HistogramBlockExecutor().execute(
        params={"value_column": "v", "bins": 5},
        inputs={"data": df},
        context=CTX,
    )
    assert "stats" in out
    stats = out["stats"].iloc[0]
    assert stats["n"] == 10
    assert abs(stats["mu"] - 14.5) < 1e-6
    assert stats["sigma"] > 0


@pytest.mark.asyncio
async def test_histogram_stats_group_by() -> None:
    df = pd.DataFrame(
        [{"g": "A", "v": v} for v in range(10)]
        + [{"g": "B", "v": v} for v in range(20, 40)]
    )
    out = await HistogramBlockExecutor().execute(
        params={"value_column": "v", "bins": 5, "group_by": "g"},
        inputs={"data": df},
        context=CTX,
    )
    stats = out["stats"].set_index("group")
    assert stats.loc["A", "n"] == 10
    assert stats.loc["B", "n"] == 20
    assert stats.loc["B", "mu"] > stats.loc["A", "mu"]  # B centered higher
