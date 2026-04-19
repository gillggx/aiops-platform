"""UX Fix Pack — chart_type='table' tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor


CTX = ExecutionContext()


@pytest.mark.asyncio
async def test_table_chart_emits_all_columns_by_default() -> None:
    df = pd.DataFrame(
        [
            {"eventTime": "2026-04-19T10:00", "toolID": "EQP-01", "value": 1.23},
            {"eventTime": "2026-04-19T10:05", "toolID": "EQP-01", "value": 2.34},
        ]
    )
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "table", "title": "最近 Process"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["type"] == "table"
    assert spec["__dsl"] is True
    assert spec["columns"] == ["eventTime", "toolID", "value"]
    assert len(spec["data"]) == 2
    assert spec["total_rows"] == 2
    assert spec["title"] == "最近 Process"


@pytest.mark.asyncio
async def test_table_chart_subset_columns() -> None:
    df = pd.DataFrame(
        [{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}]
    )
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "table", "columns": ["a", "c"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert spec["columns"] == ["a", "c"]
    assert spec["data"][0] == {"a": 1, "c": 3}


@pytest.mark.asyncio
async def test_table_chart_unknown_column_rejected() -> None:
    df = pd.DataFrame([{"a": 1}])
    with pytest.raises(BlockExecutionError) as exc:
        await ChartBlockExecutor().execute(
            params={"chart_type": "table", "columns": ["a", "nope"]},
            inputs={"data": df},
            context=CTX,
        )
    assert exc.value.code == "COLUMN_NOT_FOUND"


@pytest.mark.asyncio
async def test_table_chart_max_rows_truncation() -> None:
    df = pd.DataFrame({"x": range(100)})
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "table", "max_rows": 10},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["chart_spec"]
    assert len(spec["data"]) == 10
    assert spec["total_rows"] == 100
