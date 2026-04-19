"""Phase 2 — Pipeline CRUD + lifecycle endpoints + 3 new block executors.

Reuses the `client` fixture from test_smoke_e2e.py style setup.
"""

from __future__ import annotations

import os
import pathlib
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient


_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_pipeline.json"


def _fake_mcp_payload() -> dict:
    events = [
        {
            "eventTime": f"2026-04-18T10:{i:02d}:00Z",
            "toolID": "EQP-01",
            "lotID": f"LOT-{i:03d}",
            "step": "STEP_002",
            "spc_status": "OOC" if i >= 3 else "PASS",
            "SPC": {
                "charts": {
                    "xbar_chart": {"value": 100.0 + 30.0 * i, "ucl": 150.0, "lcl": 50.0, "is_ooc": i >= 3}
                }
            },
        }
        for i in range(5)
    ]
    return {"total": len(events), "events": events}


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("ONTOLOGY_SIM_URL", "http://fake-sim")
    os.environ.setdefault("DEBUG", "false")

    import importlib
    from app import database
    database._engine = None
    database._async_session_factory = None

    import main as main_mod
    importlib.reload(main_mod)

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: _fake_mcp_payload()

    with patch("app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient") as mc:
        mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        with TestClient(main_mod.app) as c:
            yield c


# ───────────────── A. CRUD endpoints ─────────────────


def test_a1_list_pipelines_empty_initially(client) -> None:
    resp = client.get("/api/v1/pipeline-builder/pipelines")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_a2_create_pipeline(client) -> None:
    import json
    payload = {
        "name": "Test CRUD Pipeline",
        "description": "test",
        "pipeline_kind": "auto_patrol",  # PR-B: fixture has block_alert → auto_patrol kind
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    resp = client.post("/api/v1/pipeline-builder/pipelines", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Test CRUD Pipeline"
    assert body["status"] == "draft"
    assert body["pipeline_kind"] == "auto_patrol"
    assert body["id"] > 0


def test_a3_get_pipeline_reads_json(client) -> None:
    # Find a pipeline from list
    resp = client.get("/api/v1/pipeline-builder/pipelines")
    rows = resp.json()
    assert len(rows) > 0
    pid = rows[0]["id"]

    r2 = client.get(f"/api/v1/pipeline-builder/pipelines/{pid}")
    assert r2.status_code == 200
    body = r2.json()
    assert body["id"] == pid
    assert "pipeline_json" in body
    assert "nodes" in body["pipeline_json"]


def test_a4_update_pipeline_draft_ok(client) -> None:
    rows = client.get("/api/v1/pipeline-builder/pipelines").json()
    pid = rows[0]["id"]
    resp = client.put(
        f"/api/v1/pipeline-builder/pipelines/{pid}",
        json={"name": "Renamed Draft"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Draft"


def test_a5_promote_draft_to_pi_run(client) -> None:
    """Legacy promote shim maps pi_run → validating."""
    rows = client.get("/api/v1/pipeline-builder/pipelines").json()
    pid = rows[0]["id"]
    resp = client.post(
        f"/api/v1/pipeline-builder/pipelines/{pid}/promote",
        json={"target_status": "pi_run"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "validating"


def test_a5b_promote_to_production_requires_valid_pipeline(client) -> None:
    """Legacy promote shim maps production → active; also walks through locked first."""
    rows = client.get("/api/v1/pipeline-builder/pipelines?status=validating").json()
    assert len(rows) >= 1
    pid = rows[0]["id"]
    resp = client.post(
        f"/api/v1/pipeline-builder/pipelines/{pid}/promote",
        json={"target_status": "production"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_a5c_draft_to_production_blocked(client) -> None:
    # Create new draft; attempt direct promote to production should 409
    import json
    payload = {
        "name": "Skip-levels attempt",
        "description": "",
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    created = client.post("/api/v1/pipeline-builder/pipelines", json=payload).json()
    resp = client.post(
        f"/api/v1/pipeline-builder/pipelines/{created['id']}/promote",
        json={"target_status": "production"},
    )
    assert resp.status_code == 409


def test_a5d_production_update_blocked(client) -> None:
    """PR-B: active/locked/archived are read-only."""
    rows = client.get("/api/v1/pipeline-builder/pipelines?status=active").json()
    assert len(rows) >= 1
    pid = rows[0]["id"]
    resp = client.put(
        f"/api/v1/pipeline-builder/pipelines/{pid}",
        json={"name": "should fail"},
    )
    assert resp.status_code == 409


def test_a6_fork_production_to_draft(client) -> None:
    """PR-B: Clone & Edit from active → draft copy."""
    rows = client.get("/api/v1/pipeline-builder/pipelines?status=active").json()
    pid = rows[0]["id"]
    resp = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/fork")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "draft"
    assert body["parent_id"] == pid
    assert body["pipeline_json"]["metadata"]["fork_of"] == pid


def test_a7_deprecate(client) -> None:
    """Legacy /deprecate → archive."""
    import json
    payload = {
        "name": "To deprecate",
        "description": "",
        "pipeline_kind": "auto_patrol",
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    rec = client.post("/api/v1/pipeline-builder/pipelines", json=payload).json()
    resp = client.post(f"/api/v1/pipeline-builder/pipelines/{rec['id']}/deprecate")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"


def test_a8_preview_up_to_node(client) -> None:
    import json
    pj = json.loads(_FIXTURE.read_text())
    resp = client.post(
        "/api/v1/pipeline-builder/preview",
        json={"pipeline_json": pj, "node_id": "n2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"
    assert body["target"] == "n2"
    assert body["node_result"]["status"] == "success"


def test_a8b_preview_accepts_float_positions(client) -> None:
    """Regression: React Flow sends sub-pixel drag positions as floats.
    Previously NodePosition.x:int rejected these with 422."""
    pipeline = {
        "version": "1.0",
        "name": "float pos",
        "metadata": {},
        "nodes": [
            {
                "id": "n1",
                "block_id": "block_process_history",
                "block_version": "1.0.0",
                "position": {"x": 42.7, "y": 88.3},  # ← sub-pixel floats
                "params": {"tool_id": "EQP-01"},
                "display_label": "My Source",  # ← user-overridden label should also persist
            }
        ],
        "edges": [],
    }
    resp = client.post(
        "/api/v1/pipeline-builder/preview",
        json={"pipeline_json": pipeline, "node_id": "n1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success"


# ───────────────── B. 3 new block executors ─────────────────


@pytest.mark.asyncio
async def test_b1_block_join() -> None:
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.join import JoinBlockExecutor

    left = pd.DataFrame([{"k": 1, "a": 10}, {"k": 2, "a": 20}])
    right = pd.DataFrame([{"k": 1, "b": 100}, {"k": 3, "b": 300}])
    block = JoinBlockExecutor()
    out = await block.execute(
        params={"key": "k", "how": "inner"},
        inputs={"left": left, "right": right},
        context=ExecutionContext(),
    )
    assert len(out["data"]) == 1
    assert list(out["data"].columns) == ["k", "a", "b"]


@pytest.mark.asyncio
async def test_b2_block_groupby_agg() -> None:
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.groupby_agg import GroupByAggBlockExecutor

    df = pd.DataFrame(
        [
            {"tool": "A", "v": 10},
            {"tool": "A", "v": 30},
            {"tool": "B", "v": 20},
        ]
    )
    block = GroupByAggBlockExecutor()
    out = await block.execute(
        params={"group_by": "tool", "agg_column": "v", "agg_func": "mean"},
        inputs={"data": df},
        context=ExecutionContext(),
    )
    result = out["data"].set_index("tool")["v_mean"].to_dict()
    assert result == {"A": 20.0, "B": 20.0}


@pytest.mark.asyncio
async def test_b3_block_chart() -> None:
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor

    df = pd.DataFrame([{"t": 1, "v": 10}, {"t": 2, "v": 20}])
    block = ChartBlockExecutor()
    out = await block.execute(
        params={"chart_type": "line", "x": "t", "y": "v"},
        inputs={"data": df},
        context=ExecutionContext(),
    )
    spec = out["chart_spec"]
    assert spec["mark"] == "line"
    assert spec["encoding"]["x"]["field"] == "t"
    assert spec["encoding"]["x"]["type"] == "quantitative"  # numeric x
    assert spec["encoding"]["y"]["field"] == "v"
    assert spec["encoding"]["y"]["type"] == "quantitative"
    assert len(spec["data"]["values"]) == 2


@pytest.mark.asyncio
async def test_b3_block_chart_nominal_x_with_string_column() -> None:
    """Regression: when x is a string column (e.g. 'step' → 'STEP_001'), the
    axis type must be 'nominal', not 'quantitative', or Vega-Lite will fail to
    plot the bars."""
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor

    df = pd.DataFrame(
        [{"step": "STEP_001", "count": 2}, {"step": "STEP_002", "count": 3}]
    )
    block = ChartBlockExecutor()
    out = await block.execute(
        params={"chart_type": "bar", "x": "step", "y": "count"},
        inputs={"data": df},
        context=ExecutionContext(),
    )
    spec = out["chart_spec"]
    assert spec["encoding"]["x"]["type"] == "nominal", spec["encoding"]
    assert spec["encoding"]["y"]["type"] == "quantitative"


@pytest.mark.asyncio
async def test_b3_block_chart_temporal_x() -> None:
    """Datetime column should be 'temporal'."""
    import pandas as pd
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor

    df = pd.DataFrame(
        [
            {"t": pd.Timestamp("2026-01-01"), "v": 1},
            {"t": pd.Timestamp("2026-01-02"), "v": 2},
        ]
    )
    block = ChartBlockExecutor()
    out = await block.execute(
        params={"chart_type": "line", "x": "t", "y": "v"},
        inputs={"data": df},
        context=ExecutionContext(),
    )
    assert out["chart_spec"]["encoding"]["x"]["type"] == "temporal"


@pytest.mark.asyncio
async def test_b3_block_chart_spc_mode_emits_chartdsl() -> None:
    """Passing ucl/lcl/highlight columns switches output to ChartDSL (Plotly) format."""
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor

    df = pd.DataFrame(
        [
            {"t": f"t{i}", "v": 100.0 + i * 5, "ucl": 150.0, "lcl": 50.0, "is_ooc": i >= 3}
            for i in range(5)
        ]
    )
    block = ChartBlockExecutor()
    out = await block.execute(
        params={
            "chart_type": "line",
            "x": "t",
            "y": "v",
            "ucl_column": "ucl",
            "lcl_column": "lcl",
            "highlight_column": "is_ooc",
        },
        inputs={"data": df},
        context=ExecutionContext(),
    )
    spec = out["chart_spec"]
    assert spec.get("__dsl") is True
    assert spec["type"] == "line"
    assert spec["x"] == "t"
    assert spec["y"] == ["v"]
    labels = [r["label"] for r in spec["rules"]]
    assert "UCL" in labels and "LCL" in labels and "Center" in labels
    ucl_rule = next(r for r in spec["rules"] if r["label"] == "UCL")
    assert ucl_rule["value"] == 150.0
    assert ucl_rule["style"] == "danger"
    assert spec["highlight"] == {"field": "is_ooc", "eq": True}


@pytest.mark.asyncio
async def test_b3_block_chart_spc_missing_highlight_col_silently_dropped() -> None:
    """PR-F runtime-QA: optional overlay columns (highlight/ucl/lcl/center)
    are now graceful — missing ones are dropped rather than raising. Core
    chart still renders."""
    from app.services.pipeline_builder.blocks.base import ExecutionContext
    from app.services.pipeline_builder.blocks.chart import ChartBlockExecutor

    df = pd.DataFrame([{"t": 1, "v": 10}, {"t": 2, "v": 20}])
    out = await ChartBlockExecutor().execute(
        params={"chart_type": "line", "x": "t", "y": "v", "highlight_column": "nope"},
        inputs={"data": df},
        context=ExecutionContext(),
    )
    # Chart spec produced; no highlight key because "nope" wasn't in data
    assert "chart_spec" in out
    assert "highlight" not in out["chart_spec"]
