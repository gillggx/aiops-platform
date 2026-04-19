"""Executor tests — end-to-end pipeline logic (MCP mocked)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest

from app.schemas.pipeline import PipelineJSON
from app.services.pipeline_builder.executor import PipelineExecutor, _topological_order
from app.services.pipeline_builder.blocks.base import ExecutionContext


def _mock_mcp_response(rows: list[dict]) -> dict:
    """Build a fake ontology simulator /process/info payload."""
    events = []
    for r in rows:
        events.append(
            {
                "eventTime": r["eventTime"],
                "toolID": r["toolID"],
                "lotID": r.get("lotID", "LOT-000"),
                "step": r["step"],
                "spc_status": r.get("spc_status", "PASS"),
                "SPC": {
                    "charts": {
                        "xbar_chart": {
                            "value": r["xbar"],
                            "ucl": 150.0,
                            "lcl": 50.0,
                            "is_ooc": r["xbar"] > 150.0,
                        }
                    }
                },
            }
        )
    return {"total": len(events), "events": events}


def test_topological_order_linear() -> None:
    p = PipelineJSON.model_validate(
        {
            "name": "x",
            "nodes": [
                {"id": "a", "block_id": "block_process_history", "position": {"x": 0, "y": 0}, "params": {"tool_id": "T"}},
                {"id": "b", "block_id": "block_filter", "position": {"x": 0, "y": 0},
                 "params": {"column": "toolID", "operator": "==", "value": "T"}},
            ],
            "edges": [{"id": "e1", "from": {"node": "a", "port": "data"}, "to": {"node": "b", "port": "data"}}],
        }
    )
    assert _topological_order(p) == ["a", "b"]


def test_topological_order_diamond() -> None:
    p = PipelineJSON.model_validate(
        {
            "name": "diamond",
            "nodes": [
                {"id": "a", "block_id": "b1", "position": {"x": 0, "y": 0}},
                {"id": "b", "block_id": "b2", "position": {"x": 0, "y": 0}},
                {"id": "c", "block_id": "b3", "position": {"x": 0, "y": 0}},
                {"id": "d", "block_id": "b4", "position": {"x": 0, "y": 0}},
            ],
            "edges": [
                {"id": "e1", "from": {"node": "a", "port": "p"}, "to": {"node": "b", "port": "p"}},
                {"id": "e2", "from": {"node": "a", "port": "p"}, "to": {"node": "c", "port": "p"}},
                {"id": "e3", "from": {"node": "b", "port": "p"}, "to": {"node": "d", "port": "p"}},
                {"id": "e4", "from": {"node": "c", "port": "p"}, "to": {"node": "d", "port": "p"}},
            ],
        }
    )
    order = _topological_order(p)
    assert order[0] == "a" and order[-1] == "d"
    assert order.index("b") < order.index("d")
    assert order.index("c") < order.index("d")


@pytest.mark.asyncio
async def test_full_pipeline_happy_path(block_registry) -> None:
    """Full pipeline with mocked MCP: tail-based 3-consecutive-OOC → alert.

    Flow (v3.2 logic-node schema):
      process_history → filter(STEP_002) → consecutive_rule(is_ooc, tail=3) → alert
      consecutive_rule exposes (triggered, evidence); alert consumes both ports.
    """
    rows = [
        {"eventTime": "2026-04-18T10:00", "toolID": "EQP-01", "step": "STEP_002", "xbar": 200.0, "spc_status": "OOC"},
        {"eventTime": "2026-04-18T10:05", "toolID": "EQP-01", "step": "STEP_002", "xbar": 210.0, "spc_status": "OOC"},
        {"eventTime": "2026-04-18T10:10", "toolID": "EQP-01", "step": "STEP_002", "xbar": 220.0, "spc_status": "OOC"},
        {"eventTime": "2026-04-18T10:15", "toolID": "EQP-01", "step": "STEP_001", "xbar": 100.0},
    ]
    pipeline = PipelineJSON.model_validate(
        {
            "name": "E2E",
            "nodes": [
                {"id": "n1", "block_id": "block_process_history", "position": {"x": 0, "y": 0},
                 "params": {"tool_id": "EQP-01", "time_range": "24h"}},
                {"id": "n2", "block_id": "block_filter", "position": {"x": 0, "y": 0},
                 "params": {"column": "step", "operator": "==", "value": "STEP_002"}},
                {"id": "n3", "block_id": "block_consecutive_rule", "position": {"x": 0, "y": 0},
                 "params": {"flag_column": "spc_xbar_chart_is_ooc", "count": 3, "sort_by": "eventTime"}},
                {"id": "n4", "block_id": "block_alert", "position": {"x": 0, "y": 0},
                 "params": {"severity": "HIGH",
                            "title_template": "xbar OOC",
                            "message_template": "連續 {run_length} 次 OOC"}},
            ],
            "edges": [
                {"id": "e1", "from": {"node": "n1", "port": "data"}, "to": {"node": "n2", "port": "data"}},
                {"id": "e2", "from": {"node": "n2", "port": "data"}, "to": {"node": "n3", "port": "data"}},
                {"id": "e3", "from": {"node": "n3", "port": "triggered"}, "to": {"node": "n4", "port": "triggered"}},
                {"id": "e4", "from": {"node": "n3", "port": "evidence"}, "to": {"node": "n4", "port": "evidence"}},
            ],
        }
    )

    fake_resp = _mock_mcp_response(rows)

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: fake_resp

    with patch("app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.pipeline_builder.blocks.process_history.get_settings") as mock_settings:
            mock_settings.return_value.ONTOLOGY_SIM_URL = "http://fake"
            executor = PipelineExecutor(block_registry)
            result = await executor.execute(pipeline, run_id=None)

    assert result["status"] == "success", result.get("error_message")
    node_results = result["node_results"]
    for nid in ("n1", "n2", "n3", "n4"):
        assert node_results[nid]["status"] == "success", f"{nid}: {node_results[nid]}"

    # n3 is the terminal logic node → triggered=True, 3 rows of evidence
    n3_preview = node_results["n3"]["preview"]
    assert n3_preview["triggered"]["type"] == "bool"
    assert n3_preview["triggered"]["value"] is True
    assert n3_preview["evidence"]["total"] == 3

    # n4 alert → one row with run_length=3 rendered in message
    n4_preview = node_results["n4"]["preview"]
    assert n4_preview["alert"]["type"] == "dataframe"
    assert n4_preview["alert"]["total"] == 1
    assert n4_preview["alert"]["rows"][0]["severity"] == "HIGH"
    assert "3" in n4_preview["alert"]["rows"][0]["message"]

    # Pipeline-level result_summary picks the terminal logic node (n3).
    rs = result["result_summary"]
    assert rs["triggered"] is True
    assert rs["evidence_node_id"] == "n3"
    assert rs["evidence_rows"] == 3


@pytest.mark.asyncio
async def test_result_summary_aggregates_charts_by_sequence(block_registry) -> None:
    """With two chart nodes (sequences 2 and 1), result_summary.charts must be ordered 1,2."""
    rows = [{"eventTime": f"2026-04-18T10:{i:02d}", "toolID": "EQP-01", "step": "STEP_002", "xbar": 100.0 + i} for i in range(3)]
    pipeline = PipelineJSON.model_validate(
        {
            "name": "charts",
            "nodes": [
                {"id": "n1", "block_id": "block_process_history", "position": {"x": 0, "y": 0},
                 "params": {"tool_id": "EQP-01"}},
                {"id": "c_second", "block_id": "block_chart", "position": {"x": 400, "y": 0},
                 "params": {"chart_type": "line", "x": "eventTime", "y": "spc_xbar_chart_value", "sequence": 2, "title": "B"}},
                {"id": "c_first", "block_id": "block_chart", "position": {"x": 200, "y": 0},
                 "params": {"chart_type": "bar", "x": "eventTime", "y": "spc_xbar_chart_value", "sequence": 1, "title": "A"}},
            ],
            "edges": [
                {"id": "e1", "from": {"node": "n1", "port": "data"}, "to": {"node": "c_second", "port": "data"}},
                {"id": "e2", "from": {"node": "n1", "port": "data"}, "to": {"node": "c_first", "port": "data"}},
            ],
        }
    )
    fake_resp = _mock_mcp_response(rows)
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = lambda: fake_resp
    with patch("app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient") as mock_client:
        instance = mock_client.return_value.__aenter__.return_value
        instance.get = AsyncMock(return_value=mock_response)
        with patch("app.services.pipeline_builder.blocks.process_history.get_settings") as mock_settings:
            mock_settings.return_value.ONTOLOGY_SIM_URL = "http://fake"
            executor = PipelineExecutor(block_registry)
            result = await executor.execute(pipeline, run_id=None)

    assert result["status"] == "success", result.get("error_message")
    rs = result["result_summary"]
    assert rs is not None
    assert rs["triggered"] is False  # no logic node
    assert rs["evidence_node_id"] is None
    # charts ordered by sequence 1, 2
    assert [c["sequence"] for c in rs["charts"]] == [1, 2]
    assert [c["title"] for c in rs["charts"]] == ["A", "B"]
    assert [c["node_id"] for c in rs["charts"]] == ["c_first", "c_second"]


@pytest.mark.asyncio
async def test_executor_fail_fast_on_upstream_error(block_registry) -> None:
    """When n1 fails, downstream nodes should be marked skipped."""
    pipeline = PipelineJSON.model_validate(
        {
            "name": "fail_fast",
            "nodes": [
                {"id": "n1", "block_id": "block_process_history", "position": {"x": 0, "y": 0},
                 "params": {"tool_id": "EQP-01"}},
                {"id": "n2", "block_id": "block_filter", "position": {"x": 0, "y": 0},
                 "params": {"column": "step", "operator": "==", "value": "X"}},
            ],
            "edges": [{"id": "e1", "from": {"node": "n1", "port": "data"}, "to": {"node": "n2", "port": "data"}}],
        }
    )

    # Force MCP fetch to fail by simulating missing ONTOLOGY_SIM_URL
    with patch("app.services.pipeline_builder.blocks.process_history.get_settings") as mock_settings:
        mock_settings.return_value.ONTOLOGY_SIM_URL = ""
        executor = PipelineExecutor(block_registry)
        result = await executor.execute(pipeline)

    assert result["status"] == "failed"
    assert result["node_results"]["n1"]["status"] == "failed"
    assert result["node_results"]["n2"]["status"] == "skipped"
