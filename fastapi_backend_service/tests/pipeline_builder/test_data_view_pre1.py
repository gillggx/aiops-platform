"""PR-E1 — block_data_view executor + result_summary.data_views tests."""

from __future__ import annotations

import pandas as pd
import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.data_view import DataViewBlockExecutor


CTX = ExecutionContext()


@pytest.mark.asyncio
async def test_data_view_default_shows_all_columns() -> None:
    df = pd.DataFrame(
        [
            {"eventTime": "2026-04-19T10:00", "toolID": "EQP-01", "value": 1.23},
            {"eventTime": "2026-04-19T10:05", "toolID": "EQP-01", "value": 2.34},
        ]
    )
    out = await DataViewBlockExecutor().execute(
        params={"title": "最近 Process"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert spec["type"] == "data_view"
    assert spec["title"] == "最近 Process"
    assert spec["columns"] == ["eventTime", "toolID", "value"]
    assert spec["total_rows"] == 2
    assert len(spec["rows"]) == 2


@pytest.mark.asyncio
async def test_data_view_subset_columns() -> None:
    df = pd.DataFrame([{"a": 1, "b": 2, "c": 3}, {"a": 4, "b": 5, "c": 6}])
    out = await DataViewBlockExecutor().execute(
        params={"columns": ["a", "c"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert spec["columns"] == ["a", "c"]
    assert spec["rows"][0] == {"a": 1, "c": 3}


@pytest.mark.asyncio
async def test_data_view_missing_column_gracefully_dropped() -> None:
    """PR-F runtime-QA: data_view tolerates missing columns — drops them and
    surfaces via `dropped_columns` instead of raising. Makes migrated pipelines
    survive when the skill's output_schema lists cols the data doesn't have."""
    df = pd.DataFrame([{"a": 1}])
    out = await DataViewBlockExecutor().execute(
        params={"columns": ["a", "missing", "also_missing"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert spec["columns"] == ["a"]  # only existing col kept
    assert spec["dropped_columns"] == ["missing", "also_missing"]


@pytest.mark.asyncio
async def test_data_view_all_columns_missing_falls_back_to_all() -> None:
    """Edge: if every requested column is missing, use all available columns."""
    df = pd.DataFrame([{"a": 1, "b": 2}])
    out = await DataViewBlockExecutor().execute(
        params={"columns": ["x", "y"]},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert spec["columns"] == ["a", "b"]
    assert spec["dropped_columns"] == ["x", "y"]


@pytest.mark.asyncio
async def test_data_view_max_rows_truncation() -> None:
    df = pd.DataFrame({"x": range(500)})
    out = await DataViewBlockExecutor().execute(
        params={"max_rows": 20},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert len(spec["rows"]) == 20
    assert spec["total_rows"] == 500


@pytest.mark.asyncio
async def test_data_view_sequence_param_preserved() -> None:
    df = pd.DataFrame([{"a": 1}])
    out = await DataViewBlockExecutor().execute(
        params={"sequence": 3, "description": "abc"},
        inputs={"data": df},
        context=CTX,
    )
    spec = out["data_view"]
    assert spec["sequence"] == 3
    assert spec["description"] == "abc"


# ── End-to-end: executor _build_result_summary includes data_views ──────────
from app.services.pipeline_builder.executor import _collect_data_view_summaries
from app.schemas.pipeline import PipelineJSON, PipelineNode, NodePosition


class _FakeCache:
    """Minimal RunCache stand-in for _collect_data_view_summaries."""

    def __init__(self, data: dict[str, dict]) -> None:
        self._data = data

    def get(self, node_id: str):
        return self._data.get(node_id)


def test_collect_data_views_orders_by_sequence_then_position() -> None:
    pipeline = PipelineJSON(
        version="1.0",
        name="test",
        nodes=[
            PipelineNode(id="n1", block_id="block_data_view", block_version="1.0.0",
                         position=NodePosition(x=100, y=0), params={"sequence": 2}),
            PipelineNode(id="n2", block_id="block_data_view", block_version="1.0.0",
                         position=NodePosition(x=200, y=0), params={"sequence": 1}),
            PipelineNode(id="n3", block_id="block_data_view", block_version="1.0.0",
                         position=NodePosition(x=50, y=0), params={}),
        ],
        edges=[],
    )
    cache = _FakeCache({
        "n1": {"data_view": {"title": "T1", "columns": [], "rows": [], "total_rows": 0}},
        "n2": {"data_view": {"title": "T2", "columns": [], "rows": [], "total_rows": 0}},
        "n3": {"data_view": {"title": "T3", "columns": [], "rows": [], "total_rows": 0}},
    })
    views = _collect_data_view_summaries(pipeline, cache)
    # n2 (seq=1) → n1 (seq=2) → n3 (unsequenced, sequence=None, seq-fallback 10000)
    assert [v["title"] for v in views] == ["T2", "T1", "T3"]


def test_collect_data_views_skips_nodes_without_cache() -> None:
    pipeline = PipelineJSON(
        version="1.0",
        name="t",
        nodes=[
            PipelineNode(id="n1", block_id="block_data_view", block_version="1.0.0",
                         position=NodePosition(x=0, y=0), params={}),
            PipelineNode(id="n_chart", block_id="block_chart", block_version="1.0.0",
                         position=NodePosition(x=0, y=0), params={}),
        ],
        edges=[],
    )
    cache = _FakeCache({})  # nothing cached
    assert _collect_data_view_summaries(pipeline, cache) == []
