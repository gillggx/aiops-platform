"""V3 Test Cases — JSON TC (CI-friendly, no LLM needed).

Covers Section 2 of docs/TEST_CASES_V3.md (Groups A/B/C/D/E):
  Group A — Phase α (5)
  Group B — Phase β (7)
  Group C — Phase γ (7)
  Group D — Phase δ (3 — mcp_call uses mocks)
  Group E — 綜合 (2)

Each TC builds a pipeline_json + runs the PipelineExecutor directly, asserting
the shape/content of node_results. Mock ontology MCP so tests don't need a
live simulator.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.any_trigger import AnyTriggerBlockExecutor
from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor
from app.services.pipeline_builder.blocks.correlation import CorrelationBlockExecutor
from app.services.pipeline_builder.blocks.cpk import CpkBlockExecutor
from app.services.pipeline_builder.blocks.ewma import EwmaBlockExecutor
from app.services.pipeline_builder.blocks.histogram import HistogramBlockExecutor
from app.services.pipeline_builder.blocks.hypothesis_test import HypothesisTestBlockExecutor
from app.services.pipeline_builder.blocks.linear_regression import LinearRegressionBlockExecutor
from app.services.pipeline_builder.blocks.mcp_call import McpCallBlockExecutor
from app.services.pipeline_builder.blocks.sort import SortBlockExecutor
from app.services.pipeline_builder.blocks.union import UnionBlockExecutor
from app.services.pipeline_builder.blocks.unpivot import UnpivotBlockExecutor
from app.services.pipeline_builder.blocks.weco_rules import WecoRulesBlockExecutor


CTX = ExecutionContext()


def _spc_sample(n: int = 50, mu: float = 100.0, sigma: float = 2.0, tool_id: str = "EQP-01") -> pd.DataFrame:
    """Generate a synthetic SPC-wide DataFrame with xbar / r / s / p / c columns."""
    rng = np.random.default_rng(seed=42)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        xbar = float(mu + rng.normal(0, sigma))
        rows.append({
            "eventTime": f"2026-04-18T10:{i:02d}:00",
            "toolID": tool_id,
            "lotID": f"LOT-{i:03d}",
            "step": "STEP_002" if i % 2 == 0 else "STEP_003",
            "spc_status": "OOC" if abs(xbar - mu) > 2 * sigma else "PASS",
            "spc_xbar_chart_value": xbar,
            "spc_xbar_chart_ucl": mu + 3 * sigma,
            "spc_xbar_chart_lcl": mu - 3 * sigma,
            "spc_xbar_chart_is_ooc": abs(xbar - mu) > 3 * sigma,
            "spc_r_chart_value": float(abs(rng.normal(5, 1))),
            "spc_s_chart_value": float(abs(rng.normal(2, 0.3))),
            "spc_p_chart_value": float(rng.uniform(0, 0.1)),
            "spc_c_chart_value": float(rng.poisson(3)),
            "apc_rf_power_bias": float(1.0 + rng.normal(0, 0.05)),
            "apc_gas_flow_comp": float(10.0 + rng.normal(0, 0.5)),
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Group A — Phase α (5 cases)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tca1_histogram_xbar_20_bins() -> None:
    """TCα1: STEP_001 xbar 常態 histogram bins=20."""
    df = _spc_sample(100)
    out = await HistogramBlockExecutor().execute(
        params={"value_column": "spc_xbar_chart_value", "bins": 20},
        inputs={"data": df},
        context=CTX,
    )
    assert len(out["data"]) == 20
    assert out["data"]["count"].sum() == 100


@pytest.mark.asyncio
async def test_tca2_sort_top_3_ooc_tools() -> None:
    """TCα2: groupby + sort desc + limit=3."""
    df = pd.DataFrame([
        {"toolID": "EQP-01", "ooc_count": 5},
        {"toolID": "EQP-02", "ooc_count": 12},
        {"toolID": "EQP-03", "ooc_count": 3},
        {"toolID": "EQP-04", "ooc_count": 8},
        {"toolID": "EQP-05", "ooc_count": 1},
    ])
    out = await SortBlockExecutor().execute(
        params={"columns": [{"column": "ooc_count", "order": "desc"}], "limit": 3},
        inputs={"data": df},
        context=CTX,
    )
    assert out["data"]["toolID"].tolist() == ["EQP-02", "EQP-04", "EQP-01"]


@pytest.mark.asyncio
async def test_tca3_boxplot_chart_mode() -> None:
    """TCα3: chart boxplot with group_by."""
    df = _spc_sample(40)
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "boxplot", "y": "spc_xbar_chart_value", "group_by": "toolID"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["chart_spec"]["type"] == "boxplot"
    assert out["chart_spec"]["__dsl"] is True


@pytest.mark.asyncio
async def test_tca4_dual_axis_chart() -> None:
    """TCα4: chart with y_secondary."""
    df = _spc_sample(20)
    out = await ChartBlockExecutor().execute(
        params={
            "chart_type": "line",
            "x": "eventTime",
            "y": "spc_xbar_chart_value",
            "y_secondary": ["apc_rf_power_bias"],
        },
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["__dsl"] is True
    assert spec["y_secondary"] == ["apc_rf_power_bias"]


@pytest.mark.asyncio
async def test_tca5_linear_regression_full_ports() -> None:
    """TCα5: regression with CI band — verify 3 ports."""
    df = _spc_sample(50)
    out = await LinearRegressionBlockExecutor().execute(
        params={"x_column": "apc_rf_power_bias", "y_column": "spc_xbar_chart_value", "confidence": 0.95},
        inputs={"data": df},
        context=CTX,
    )
    assert set(out.keys()) == {"stats", "data", "ci"}
    assert "r_squared" in out["stats"].columns
    assert "spc_xbar_chart_value_pred" in out["data"].columns
    assert (out["ci"]["ci_upper"] >= out["ci"]["ci_lower"]).all()


# ═══════════════════════════════════════════════════════════════════════════
# Group B — Phase β (7 cases)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tcb1_unpivot_then_groupby_regression() -> None:
    """TCβ1: 5 SPC chart_type R² in one go via unpivot + group_by."""
    df = _spc_sample(40)
    # Unpivot wide → long
    unp_out = await UnpivotBlockExecutor().execute(
        params={
            "id_columns": ["eventTime", "toolID", "step", "apc_rf_power_bias"],
            "value_columns": [
                "spc_xbar_chart_value", "spc_r_chart_value",
                "spc_s_chart_value", "spc_p_chart_value", "spc_c_chart_value",
            ],
            "variable_name": "chart_type",
            "value_name": "spc_value",
        },
        inputs={"data": df},
        context=CTX,
    )
    long_df = unp_out["data"]
    assert len(long_df) == 40 * 5
    # Regression per chart_type
    reg_out = await LinearRegressionBlockExecutor().execute(
        params={"x_column": "apc_rf_power_bias", "y_column": "spc_value", "group_by": "chart_type"},
        inputs={"data": long_df},
        context=CTX,
    )
    stats = reg_out["stats"]
    assert len(stats) == 5
    assert set(stats["group"]) == {
        "spc_xbar_chart_value", "spc_r_chart_value",
        "spc_s_chart_value", "spc_p_chart_value", "spc_c_chart_value",
    }


@pytest.mark.asyncio
async def test_tcb2_cpk_full_tool() -> None:
    """TCβ2: Cpk with USL/LSL."""
    df = _spc_sample(60, mu=100.0, sigma=2.0)
    out = await CpkBlockExecutor().execute(
        params={"value_column": "spc_xbar_chart_value", "usl": 115.0, "lsl": 85.0},
        inputs={"data": df},
        context=CTX,
    )
    stats = out["stats"].iloc[0]
    assert stats["cpk"] > 0
    assert stats["n"] == 60


@pytest.mark.asyncio
async def test_tcb3_cpk_per_step() -> None:
    """TCβ3: Cpk group_by=step emits one row per step."""
    df = _spc_sample(100)
    out = await CpkBlockExecutor().execute(
        params={"value_column": "spc_xbar_chart_value", "usl": 115.0, "lsl": 85.0, "group_by": "step"},
        inputs={"data": df},
        context=CTX,
    )
    assert len(out["stats"]) == 2  # STEP_002 + STEP_003


@pytest.mark.asyncio
async def test_tcb4_union_two_tools_overlay() -> None:
    """TCβ4: union(outer) merges two tools' DataFrames row-wise."""
    df_a = _spc_sample(20, tool_id="EQP-01")
    df_b = _spc_sample(25, tool_id="EQP-02")
    out = await UnionBlockExecutor().execute(
        params={"on_schema_mismatch": "outer"},
        inputs={"primary": df_a, "secondary": df_b},
        context=CTX,
    )
    merged = out["data"]
    assert len(merged) == 45
    assert set(merged["toolID"].unique()) == {"EQP-01", "EQP-02"}


@pytest.mark.asyncio
async def test_tcb5_weco_nelson_all_eight_rules() -> None:
    """TCβ5: Rules=R1..R8 full scan emits evidence without error."""
    df = _spc_sample(100)
    out = await WecoRulesBlockExecutor().execute(
        params={
            "value_column": "spc_xbar_chart_value",
            "center_column": "spc_xbar_chart_value",  # use series mean as center
            "sigma_source": "manual",
            "manual_sigma": 2.0,
            "rules": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"],
            "sort_by": "eventTime",
        },
        inputs={"data": df},
        context=CTX,
    )
    assert "triggered" in out
    assert "evidence" in out


@pytest.mark.asyncio
async def test_tcb6_any_trigger_aggregation_and_source_port() -> None:
    """TCβ6: any_trigger merges evidence with source_port attribution."""
    ev_a = pd.DataFrame([{"val": 1}])
    ev_b = pd.DataFrame([{"val": 2}])
    out = await AnyTriggerBlockExecutor().execute(
        params={},
        inputs={
            "trigger_1": True, "evidence_1": ev_a,
            "trigger_2": False, "evidence_2": pd.DataFrame(),
            "trigger_3": True, "evidence_3": ev_b,
        },
        context=CTX,
    )
    assert out["triggered"] is True
    ev = out["evidence"]
    assert "source_port" in ev.columns
    assert set(ev["source_port"]) == {"trigger_1", "trigger_3"}


@pytest.mark.asyncio
async def test_tcb7_union_intersect_keeps_only_common() -> None:
    """TCβ7: intersect drops columns not present in both sides."""
    p = pd.DataFrame([{"a": 1, "only_p": "x"}])
    s = pd.DataFrame([{"a": 2, "only_s": True}])
    out = await UnionBlockExecutor().execute(
        params={"on_schema_mismatch": "intersect"},
        inputs={"primary": p, "secondary": s},
        context=CTX,
    )
    assert list(out["data"].columns) == ["a"]


# ═══════════════════════════════════════════════════════════════════════════
# Group C — Phase γ (7 cases)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tcc1_correlation_matrix_long_format() -> None:
    """TCγ1: multi-column correlation matrix → long format."""
    df = _spc_sample(50)
    out = await CorrelationBlockExecutor().execute(
        params={"columns": ["apc_rf_power_bias", "apc_gas_flow_comp", "spc_xbar_chart_value"]},
        inputs={"data": df},
        context=CTX,
    )
    m = out["matrix"]
    # 3×3 → 9 rows
    assert len(m) == 9
    assert {"col_a", "col_b", "correlation", "p_value", "n"}.issubset(m.columns)


@pytest.mark.asyncio
async def test_tcc2_t_test_significant_difference() -> None:
    """TCγ2: t-test detects clear mean diff."""
    df = _spc_sample(40, tool_id="EQP-01")
    df_b = _spc_sample(40, mu=120.0, tool_id="EQP-02")  # shifted mean
    merged = pd.concat([df, df_b], ignore_index=True)
    out = await HypothesisTestBlockExecutor().execute(
        params={"test_type": "t_test", "value_column": "spc_xbar_chart_value", "group_column": "toolID"},
        inputs={"data": merged},
        context=CTX,
    )
    row = out["stats"].iloc[0]
    assert row["p_value"] < 0.001


@pytest.mark.asyncio
async def test_tcc3_chi_square_independence() -> None:
    """TCγ3: chi-square OOC vs toolID."""
    df = pd.DataFrame(
        [{"toolID": "EQP-01", "spc_status": "PASS"}] * 35
        + [{"toolID": "EQP-01", "spc_status": "OOC"}] * 5
        + [{"toolID": "EQP-02", "spc_status": "PASS"}] * 10
        + [{"toolID": "EQP-02", "spc_status": "OOC"}] * 30
    )
    out = await HypothesisTestBlockExecutor().execute(
        params={"test_type": "chi_square", "group_column": "toolID", "target_column": "spc_status"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["stats"].iloc[0]["p_value"] < 0.001


@pytest.mark.asyncio
async def test_tcc4_anova_five_groups() -> None:
    """TCγ4: ANOVA on 5 step groups."""
    rows = []
    for g_idx, step in enumerate(["S1", "S2", "S3", "S4", "S5"]):
        rows.extend({"step": step, "v": float(g_idx * 5 + i * 0.1)} for i in range(8))
    df = pd.DataFrame(rows)
    out = await HypothesisTestBlockExecutor().execute(
        params={"test_type": "anova", "value_column": "v", "group_column": "step"},
        inputs={"data": df},
        context=CTX,
    )
    row = out["stats"].iloc[0]
    assert row["test"] == "anova"
    assert row["k"] == 5


@pytest.mark.asyncio
async def test_tcc5_ewma_smoothing_preserves_order() -> None:
    """TCγ5: EWMA produces smoother series (std lower than raw)."""
    df = _spc_sample(50)
    out = await EwmaBlockExecutor().execute(
        params={"value_column": "spc_xbar_chart_value", "alpha": 0.2, "sort_by": "eventTime"},
        inputs={"data": df},
        context=CTX,
    )
    d = out["data"]
    assert "spc_xbar_chart_value_ewma" in d.columns
    # EWMA std should be less than or roughly equal to raw std (lower for noisy data)
    raw_std = float(d["spc_xbar_chart_value"].std())
    ewma_std = float(d["spc_xbar_chart_value_ewma"].std())
    assert ewma_std <= raw_std + 0.01


@pytest.mark.asyncio
async def test_tcc6_anova_rejects_only_two_groups() -> None:
    """TCγ6: ANOVA with k<3 → INVALID_INPUT."""
    df = pd.DataFrame([{"g": "A", "v": 1}, {"g": "B", "v": 2}, {"g": "B", "v": 3}])
    with pytest.raises(BlockExecutionError) as ei:
        await HypothesisTestBlockExecutor().execute(
            params={"test_type": "anova", "value_column": "v", "group_column": "g"},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_tcc7_ewma_alpha_out_of_range() -> None:
    """TCγ7: EWMA alpha=1.5 → INVALID_PARAM."""
    with pytest.raises(BlockExecutionError) as ei:
        await EwmaBlockExecutor().execute(
            params={"value_column": "v", "alpha": 1.5, "sort_by": "t"},
            inputs={"data": pd.DataFrame({"t": [1], "v": [1]})},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


# ═══════════════════════════════════════════════════════════════════════════
# Group D — Phase δ (3 cases)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tcd1_mcp_call_list_tools_flattens_events() -> None:
    """TCδ1: mock a list_tools MCP, verify DataFrame."""
    fake_mcp = MagicMock()
    fake_mcp.api_config = '{"endpoint_url": "http://fake/tools", "method": "GET"}'
    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=fake_mcp)
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"events": [
        {"toolID": "EQP-01", "status": "RUN"}, {"toolID": "EQP-02", "status": "IDLE"}
    ]})
    fake_client = MagicMock()
    fake_client.get = AsyncMock(return_value=fake_resp)
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.pipeline_builder.blocks.mcp_call._get_session_factory",
        return_value=lambda: fake_session,
    ), patch(
        "app.services.pipeline_builder.blocks.mcp_call.MCPDefinitionRepository",
        return_value=fake_repo,
    ), patch("app.services.pipeline_builder.blocks.mcp_call.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__.return_value = fake_client
        mock_httpx.return_value.__aexit__.return_value = None
        out = await McpCallBlockExecutor().execute(
            params={"mcp_name": "list_tools", "args": {}},
            inputs={},
            context=CTX,
        )
    assert len(out["data"]) == 2


@pytest.mark.asyncio
async def test_tcd2_mcp_call_not_found() -> None:
    """TCδ2: missing MCP."""
    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=None)
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.pipeline_builder.blocks.mcp_call._get_session_factory",
        return_value=lambda: fake_session,
    ), patch(
        "app.services.pipeline_builder.blocks.mcp_call.MCPDefinitionRepository",
        return_value=fake_repo,
    ):
        with pytest.raises(BlockExecutionError) as ei:
            await McpCallBlockExecutor().execute(
                params={"mcp_name": "missing"}, inputs={}, context=CTX
            )
    assert ei.value.code == "MCP_NOT_FOUND"


@pytest.mark.asyncio
async def test_tcd3_mcp_call_dataset_key_flattens() -> None:
    """TCδ3: response uses 'dataset' key → still flattens."""
    fake_mcp = MagicMock()
    fake_mcp.api_config = '{"endpoint_url": "http://fake/x", "method": "POST"}'
    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=fake_mcp)
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"dataset": [{"a": 1}, {"a": 2}, {"a": 3}]})
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=fake_resp)
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.pipeline_builder.blocks.mcp_call._get_session_factory",
        return_value=lambda: fake_session,
    ), patch(
        "app.services.pipeline_builder.blocks.mcp_call.MCPDefinitionRepository",
        return_value=fake_repo,
    ), patch("app.services.pipeline_builder.blocks.mcp_call.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__.return_value = fake_client
        mock_httpx.return_value.__aexit__.return_value = None
        out = await McpCallBlockExecutor().execute(
            params={"mcp_name": "x", "args": {"key": "v"}}, inputs={}, context=CTX
        )
    assert len(out["data"]) == 3


# ═══════════════════════════════════════════════════════════════════════════
# Group E — 綜合 (2 cases)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_tc_all_1_catalog_blocks_have_examples() -> None:
    """TC-all-1: every seeded block has at least one example (grows with PR cycles)."""
    from app.services.pipeline_builder.seed import _blocks
    from app.services.pipeline_builder.seed_examples import examples_by_name
    specs = _blocks()
    examples_map = examples_by_name()
    # PR-E1 added block_data_view → 26; expect at least the original 25.
    assert len(specs) >= 25
    for spec in specs:
        name = spec["name"]
        assert name in examples_map, f"{name} missing examples"
        assert len(examples_map[name]) >= 1, f"{name} has empty examples"


@pytest.mark.asyncio
async def test_tc_all_2_v2_baseline_coverage() -> None:
    """TC-all-2: Spot-check that the 23-block catalog covers key V2 patterns.

    V2's 3 failing cases (A5 / A7 / A8) required:
      - multi-tool comparison (union)
      - multi-chart_type (unpivot + group_by)
      - full all-rules SPC scan (weco_rules Nelson-8)
    All 3 are now available as concrete blocks.
    """
    from app.services.pipeline_builder.seed_examples import examples_by_name
    exs = examples_by_name()
    # Multi-tool overlay
    assert any("兩機台" in e["name"] for e in exs.get("block_union", []))
    # Multi chart_type unpivot
    assert any("SPC" in e["name"] for e in exs.get("block_unpivot", []))
    # Nelson 8 via weco
    assert any("Nelson" in e["name"] for e in exs.get("block_weco_rules", []))
    # MCP extensibility (TC06 list_tools now doable)
    assert any("list_tools" in e["summary"] for e in exs.get("block_mcp_call", []))
