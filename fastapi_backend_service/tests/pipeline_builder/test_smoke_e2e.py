"""T11 — End-to-end smoke test via FastAPI TestClient.

Spins up the full app (lifespan → init_db → seed blocks → registry load),
then POSTs the 4-node sample pipeline to /api/v1/pipeline-builder/execute.

MCP HTTP calls are patched to return a fake dataset so this test doesn't
require a live ontology_simulator.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from unittest.mock import AsyncMock, patch

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
                    "xbar_chart": {
                        "value": 100.0 + 30.0 * i,   # i=3..7 cross 150
                        "ucl": 150.0,
                        "lcl": 50.0,
                        "is_ooc": i >= 3,
                    }
                }
            },
        }
        for i in range(8)
    ]
    return {"total": len(events), "events": events}


@pytest.fixture(scope="module")
def client():
    # Use a file-based SQLite so init_db can do create_all without touching Postgres
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("ONTOLOGY_SIM_URL", "http://fake-sim")
    os.environ.setdefault("DEBUG", "false")

    import importlib
    from app import database
    # Reset cached engine/session so our DATABASE_URL takes effect
    database._engine = None
    database._async_session_factory = None

    import main as main_mod  # fresh app with updated env
    importlib.reload(main_mod)

    # Patch MCP HTTP call at module level for the whole module
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: _fake_mcp_payload()

    with patch("app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient") as mc:
        mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        with TestClient(main_mod.app) as c:
            yield c


def test_blocks_catalog_exposed(client) -> None:
    resp = client.get("/api/v1/pipeline-builder/blocks")
    assert resp.status_code == 200
    blocks = resp.json()
    names = [b["name"] for b in blocks]
    for expected in [
        "block_process_history",
        "block_filter",
        "block_threshold",
        "block_consecutive_rule",
        "block_alert",
    ]:
        assert expected in names, f"Missing block {expected}"


def test_validate_endpoint_with_sample(client) -> None:
    payload = json.loads(_FIXTURE.read_text())
    resp = client.post("/api/v1/pipeline-builder/validate", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True, body["errors"]


def test_execute_endpoint_full_run(client) -> None:
    pipeline_json = json.loads(_FIXTURE.read_text())
    start = time.perf_counter()
    resp = client.post(
        "/api/v1/pipeline-builder/execute",
        json={"pipeline_json": pipeline_json, "triggered_by": "user"},
    )
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "success", body
    assert body["run_id"] > 0

    # Every node reports success
    for node_id in ("n1", "n2", "n3", "n4"):
        assert node_id in body["node_results"], f"Missing node_result for {node_id}"
        assert body["node_results"][node_id]["status"] == "success", body["node_results"][node_id]

    # v3.2: n3 terminal logic node → triggered bool; n4 alert emits 1 row
    n3_preview = body["node_results"]["n3"]["preview"]
    assert n3_preview["triggered"]["value"] is True
    assert n3_preview["evidence"]["total"] >= 3

    alert_preview = body["node_results"]["n4"]["preview"]["alert"]
    assert alert_preview["total"] == 1
    assert alert_preview["rows"][0]["severity"] == "HIGH"

    # Pipeline-level result_summary surfaces terminal logic node verdict
    assert body["result_summary"]["triggered"] is True
    assert body["result_summary"]["evidence_node_id"] == "n3"

    # Latency budget (SPEC QA F3: p95 < 5s)
    assert elapsed < 5.0, f"E2E took {elapsed:.2f}s (> 5s SLA)"


def test_execute_validation_error(client) -> None:
    bad_pipeline = {
        "version": "1.0",
        "name": "bad",
        "nodes": [],  # no source, no output
        "edges": [],
    }
    resp = client.post(
        "/api/v1/pipeline-builder/execute",
        json={"pipeline_json": bad_pipeline, "triggered_by": "user"},
    )
    assert resp.status_code == 200  # validation_error still returns 200 with detail
    body = resp.json()
    assert body["status"] == "validation_error"
    assert len(body["errors"]) > 0


def test_get_run_record(client) -> None:
    # Fire an execute first so we have a run
    pipeline_json = json.loads(_FIXTURE.read_text())
    resp = client.post(
        "/api/v1/pipeline-builder/execute",
        json={"pipeline_json": pipeline_json, "triggered_by": "user"},
    )
    run_id = resp.json()["run_id"]

    resp2 = client.get(f"/api/v1/pipeline-builder/runs/{run_id}")
    assert resp2.status_code == 200
    body = resp2.json()
    assert body["id"] == run_id
    assert body["status"] == "success"
    assert body["node_results"] is not None
