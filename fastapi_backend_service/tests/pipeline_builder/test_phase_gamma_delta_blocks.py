"""Phase γ + δ — correlation / hypothesis_test / ewma / mcp_call tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.correlation import CorrelationBlockExecutor
from app.services.pipeline_builder.blocks.ewma import EwmaBlockExecutor
from app.services.pipeline_builder.blocks.hypothesis_test import HypothesisTestBlockExecutor
from app.services.pipeline_builder.blocks.mcp_call import McpCallBlockExecutor


CTX = ExecutionContext()


# ─── block_correlation ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_correlation_long_format_with_perfect_positive() -> None:
    df = pd.DataFrame({"x": list(range(10)), "y": [2 * i for i in range(10)], "z": list(range(10, 0, -1))})
    out = await CorrelationBlockExecutor().execute(
        params={"columns": ["x", "y", "z"]},
        inputs={"data": df},
        context=CTX,
    )
    m = out["matrix"]
    assert {"col_a", "col_b", "correlation", "p_value", "n"}.issubset(m.columns)
    # x vs y should be perfectly correlated (+1)
    xy = m[(m.col_a == "x") & (m.col_b == "y")].iloc[0]
    assert abs(xy["correlation"] - 1.0) < 1e-6
    # x vs z should be perfectly inversely correlated (-1)
    xz = m[(m.col_a == "x") & (m.col_b == "z")].iloc[0]
    assert abs(xz["correlation"] + 1.0) < 1e-6


@pytest.mark.asyncio
async def test_correlation_needs_two_columns() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await CorrelationBlockExecutor().execute(
            params={"columns": ["x"]},
            inputs={"data": pd.DataFrame({"x": [1, 2]})},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


# ─── block_hypothesis_test ───────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_t_test_detects_mean_difference() -> None:
    df = pd.DataFrame(
        [{"g": "A", "v": v} for v in [1.0, 1.1, 0.9, 1.0, 1.05]]
        + [{"g": "B", "v": v} for v in [5.0, 5.1, 4.9, 5.0, 5.05]]
    )
    out = await HypothesisTestBlockExecutor().execute(
        params={"test_type": "t_test", "value_column": "v", "group_column": "g"},
        inputs={"data": df},
        context=CTX,
    )
    row = out["stats"].iloc[0]
    assert row["test"] == "t_test"
    assert row["p_value"] < 0.001
    assert bool(row["significant"]) is True


@pytest.mark.asyncio
async def test_anova_rejects_when_only_two_groups() -> None:
    df = pd.DataFrame(
        [{"g": "A", "v": 1}, {"g": "A", "v": 2}, {"g": "B", "v": 3}, {"g": "B", "v": 4}]
    )
    with pytest.raises(BlockExecutionError) as ei:
        await HypothesisTestBlockExecutor().execute(
            params={"test_type": "anova", "value_column": "v", "group_column": "g"},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "INVALID_INPUT"


@pytest.mark.asyncio
async def test_chi_square_contingency() -> None:
    df = pd.DataFrame(
        [{"tool": "A", "status": "PASS"}] * 40
        + [{"tool": "A", "status": "OOC"}] * 10
        + [{"tool": "B", "status": "PASS"}] * 20
        + [{"tool": "B", "status": "OOC"}] * 30
    )
    out = await HypothesisTestBlockExecutor().execute(
        params={"test_type": "chi_square", "group_column": "tool", "target_column": "status"},
        inputs={"data": df},
        context=CTX,
    )
    row = out["stats"].iloc[0]
    assert row["test"] == "chi_square"
    assert row["p_value"] < 0.001


# ─── block_ewma ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ewma_recursive_form() -> None:
    df = pd.DataFrame({"t": [1, 2, 3, 4], "v": [10.0, 20.0, 10.0, 20.0]})
    out = await EwmaBlockExecutor().execute(
        params={"value_column": "v", "alpha": 0.5, "sort_by": "t"},
        inputs={"data": df},
        context=CTX,
    )
    d = out["data"]
    # First EWMA = first value (10)
    assert abs(d["v_ewma"].iloc[0] - 10.0) < 1e-6
    # Second = 0.5*20 + 0.5*10 = 15
    assert abs(d["v_ewma"].iloc[1] - 15.0) < 1e-6


@pytest.mark.asyncio
async def test_ewma_alpha_must_be_in_range() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await EwmaBlockExecutor().execute(
            params={"value_column": "v", "alpha": 1.5, "sort_by": "t"},
            inputs={"data": pd.DataFrame({"t": [1], "v": [1]})},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


@pytest.mark.asyncio
async def test_ewma_group_by_independent_series() -> None:
    df = pd.DataFrame(
        [{"g": "A", "t": 1, "v": 10.0}, {"g": "A", "t": 2, "v": 20.0},
         {"g": "B", "t": 1, "v": 100.0}, {"g": "B", "t": 2, "v": 200.0}]
    )
    out = await EwmaBlockExecutor().execute(
        params={"value_column": "v", "alpha": 0.5, "sort_by": "t", "group_by": "g"},
        inputs={"data": df},
        context=CTX,
    )
    d = out["data"].sort_values(by=["g", "t"]).reset_index(drop=True)
    # Group A second point: 0.5*20+0.5*10 = 15
    # Group B second point: 0.5*200+0.5*100 = 150
    a_vals = d[d["g"] == "A"]["v_ewma"].tolist()
    b_vals = d[d["g"] == "B"]["v_ewma"].tolist()
    assert abs(a_vals[1] - 15.0) < 1e-6
    assert abs(b_vals[1] - 150.0) < 1e-6


# ─── block_mcp_call ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mcp_call_get_flattens_events() -> None:
    """Successful GET flow: repo → httpx.get → flatten 'events' key → DataFrame."""
    # Fake MCP object returned by the repo
    fake_mcp = MagicMock()
    fake_mcp.api_config = '{"endpoint_url": "http://fake/tools", "method": "GET"}'

    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=fake_mcp)

    # Fake httpx response
    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"events": [{"toolID": "EQP-01", "status": "OK"}]})

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
            params={"mcp_name": "list_tools", "args": {"since": "24h"}},
            inputs={},
            context=CTX,
        )
    df = out["data"]
    assert len(df) == 1
    assert df.iloc[0]["toolID"] == "EQP-01"
    fake_client.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_mcp_call_mcp_not_found() -> None:
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
                params={"mcp_name": "missing_mcp"}, inputs={}, context=CTX
            )
    assert ei.value.code == "MCP_NOT_FOUND"
