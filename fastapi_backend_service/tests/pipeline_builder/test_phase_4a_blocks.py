"""Phase 4-A helper blocks — count_rows + threshold operator mode + mcp_foreach."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.count_rows import CountRowsBlockExecutor
from app.services.pipeline_builder.blocks.mcp_foreach import McpForeachBlockExecutor
from app.services.pipeline_builder.blocks.threshold import ThresholdBlockExecutor


CTX = ExecutionContext()


# ─── block_count_rows ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_count_rows_no_group() -> None:
    df = pd.DataFrame({"x": [1, 2, 3, 4]})
    out = await CountRowsBlockExecutor().execute(params={}, inputs={"data": df}, context=CTX)
    assert list(out["data"]["count"]) == [4]


@pytest.mark.asyncio
async def test_count_rows_with_group() -> None:
    df = pd.DataFrame([
        {"recipe": "R1"}, {"recipe": "R1"}, {"recipe": "R2"}, {"recipe": "R2"}, {"recipe": "R2"},
    ])
    out = await CountRowsBlockExecutor().execute(
        params={"group_by": "recipe"}, inputs={"data": df}, context=CTX,
    )
    d = out["data"].set_index("recipe")["count"].to_dict()
    assert d == {"R1": 2, "R2": 3}


# ─── block_threshold — operator mode ────────────────────────────────────────
@pytest.mark.asyncio
async def test_threshold_operator_eq_numeric() -> None:
    df = pd.DataFrame({"count": [1]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "count", "operator": "==", "target": 1},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    assert len(out["evidence"]) == 1


@pytest.mark.asyncio
async def test_threshold_operator_ne_triggers_on_multi_recipe() -> None:
    df = pd.DataFrame({"count": [3]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "count", "operator": "==", "target": 1},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is False


@pytest.mark.asyncio
async def test_threshold_operator_gt() -> None:
    df = pd.DataFrame({"count": [0, 2, 5]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "count", "operator": ">", "target": 1},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    # PR-A: evidence = all 3 rows; 2 triggered
    assert len(out["evidence"]) == 3
    assert out["evidence"]["triggered_row"].sum() == 2


@pytest.mark.asyncio
async def test_threshold_operator_string_eq() -> None:
    df = pd.DataFrame({"status": ["OK", "FAIL", "OK"]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "status", "operator": "==", "target": "FAIL"},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    # PR-A: evidence = all 3 rows; the FAIL row is the only triggered one
    ev = out["evidence"]
    assert len(ev) == 3
    assert list(ev[ev["triggered_row"]]["status"]) == ["FAIL"]


@pytest.mark.asyncio
async def test_threshold_missing_target_with_operator() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        await ThresholdBlockExecutor().execute(
            params={"column": "count", "operator": "=="},
            inputs={"data": pd.DataFrame({"count": [1]})},
            context=CTX,
        )
    assert ei.value.code == "MISSING_PARAM"


@pytest.mark.asyncio
async def test_threshold_legacy_bound_type_still_works() -> None:
    """Regression: legacy path (bound_type + upper_bound) unchanged."""
    df = pd.DataFrame({"v": [1, 5, 10, 15, 20]})
    out = await ThresholdBlockExecutor().execute(
        params={"column": "v", "bound_type": "upper", "upper_bound": 10},
        inputs={"data": df},
        context=CTX,
    )
    assert out["triggered"] is True
    # PR-A: evidence = all 5 rows; 15 and 20 triggered
    assert len(out["evidence"]) == 5
    assert out["evidence"]["triggered_row"].sum() == 2


# ─── block_mcp_foreach ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mcp_foreach_merges_responses() -> None:
    """Each row gets a MCP call; response dict merges as new columns."""
    df = pd.DataFrame([
        {"lotID": "L001", "step": "STEP_A"},
        {"lotID": "L002", "step": "STEP_B"},
    ])

    # Fake MCP config
    fake_mcp = MagicMock()
    fake_mcp.api_config = '{"endpoint_url": "http://fake/ctx", "method": "POST"}'
    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=fake_mcp)

    # Response varies per lot (returns {power: N, gas_flow: M})
    def make_resp(power, gas):
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json = MagicMock(return_value={"rf_power": power, "gas_flow": gas})
        return r

    fake_client = MagicMock()
    call_count = {"n": 0}

    async def fake_post(url, json=None, headers=None):
        call_count["n"] += 1
        # Different response per call
        return make_resp(call_count["n"] * 100, call_count["n"] * 10)

    fake_client.post = AsyncMock(side_effect=fake_post)

    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.pipeline_builder.blocks.mcp_foreach._get_session_factory",
        return_value=lambda: fake_session,
    ), patch(
        "app.services.pipeline_builder.blocks.mcp_foreach.MCPDefinitionRepository",
        return_value=fake_repo,
    ), patch("app.services.pipeline_builder.blocks.mcp_foreach.httpx.AsyncClient") as mock_httpx:
        mock_httpx.return_value.__aenter__.return_value = fake_client
        mock_httpx.return_value.__aexit__.return_value = None
        out = await McpForeachBlockExecutor().execute(
            params={
                "mcp_name": "get_process_context",
                "args_template": {"targetID": "$lotID", "step": "$step"},
                "result_prefix": "apc_",
            },
            inputs={"data": df},
            context=CTX,
        )

    d = out["data"]
    assert len(d) == 2
    assert {"lotID", "step", "apc_rf_power", "apc_gas_flow"}.issubset(d.columns)
    # Each row got its own response merged
    assert d.iloc[0]["apc_rf_power"] != d.iloc[1]["apc_rf_power"]


@pytest.mark.asyncio
async def test_mcp_foreach_args_template_ref_missing_column() -> None:
    df = pd.DataFrame([{"lotID": "L1"}])  # no "step" column

    fake_mcp = MagicMock()
    fake_mcp.api_config = '{"endpoint_url": "http://fake", "method": "POST"}'
    fake_repo = MagicMock()
    fake_repo.get_by_name = AsyncMock(return_value=fake_mcp)
    fake_session = MagicMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)

    with patch(
        "app.services.pipeline_builder.blocks.mcp_foreach._get_session_factory",
        return_value=lambda: fake_session,
    ), patch(
        "app.services.pipeline_builder.blocks.mcp_foreach.MCPDefinitionRepository",
        return_value=fake_repo,
    ):
        with pytest.raises(BlockExecutionError) as ei:
            await McpForeachBlockExecutor().execute(
                params={
                    "mcp_name": "x",
                    "args_template": {"step": "$step"},
                },
                inputs={"data": df},
                context=CTX,
            )
        assert ei.value.code == "COLUMN_NOT_FOUND"


@pytest.mark.asyncio
async def test_mcp_foreach_too_many_rows() -> None:
    df = pd.DataFrame([{"x": i} for i in range(501)])
    with pytest.raises(BlockExecutionError) as ei:
        await McpForeachBlockExecutor().execute(
            params={"mcp_name": "m", "args_template": {}},
            inputs={"data": df},
            context=CTX,
        )
    assert ei.value.code == "TOO_MANY_ROWS"
