"""PR-C — Publish endpoint + registry + telemetry + doc_generator tests."""

from __future__ import annotations

import importlib
import json
import os
import pathlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sample_pipeline.json"


def _fake_mcp_payload() -> dict:
    return {"data": {"events": []}}


@pytest.fixture
def client():
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("ONTOLOGY_SIM_URL", "http://fake-sim")
    os.environ.setdefault("DEBUG", "false")

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


def _make(client: TestClient, kind: str = "skill") -> int:
    """Create a pipeline + walk draft → validating. Returns pipeline id."""
    payload = {
        "name": f"PR-C {kind} case",
        "description": "Sample diagnostic rule for PR-C publish tests",
        "pipeline_kind": kind,
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    pid = client.post("/api/v1/pipeline-builder/pipelines", json=payload).json()["id"]
    # draft → validating always passes (base validation)
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "validating"})
    assert r.status_code == 200, r.text
    return pid


def test_draft_doc_generates_for_validating(client) -> None:
    """draft-doc endpoint produces structured DraftDoc."""
    pid = _make(client, "auto_patrol")
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/publish/draft-doc")
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "slug" in doc
    assert "use_case" in doc
    assert "when_to_use" in doc and isinstance(doc["when_to_use"], list)
    assert "inputs_schema" in doc and isinstance(doc["inputs_schema"], list)
    assert "tags" in doc and "auto_patrol" in doc["tags"]


def test_draft_doc_rejected_for_draft(client) -> None:
    """draft-doc requires validating/locked state."""
    pid = client.post(
        "/api/v1/pipeline-builder/pipelines",
        json={
            "name": "still draft",
            "description": "",
            "pipeline_kind": "skill",
            "pipeline_json": json.loads(_FIXTURE.read_text()),
        },
    ).json()["id"]
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/publish/draft-doc")
    assert r.status_code == 409


def test_publish_rejects_auto_patrol_kind(client) -> None:
    """Only diagnostic pipelines go to Skill Registry."""
    pid = _make(client, "auto_patrol")
    # Move to locked (auto_patrol fixture has block_alert → C11 OK)
    client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "locked"})
    # Get a draft doc to use as reviewed_doc
    doc = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/publish/draft-doc").json()
    r = client.post(
        f"/api/v1/pipeline-builder/pipelines/{pid}/publish",
        json={"reviewed_doc": doc},
    )
    assert r.status_code == 409
    assert "skill" in r.text.lower()


def test_published_skills_list_empty_initial(client) -> None:
    """Registry starts empty."""
    r = client.get("/api/v1/pipeline-builder/published-skills")
    assert r.status_code == 200
    assert r.json() == []


def test_published_skills_search_on_empty_returns_list(client) -> None:
    """Search endpoint works even when registry is empty."""
    r = client.post(
        "/api/v1/pipeline-builder/published-skills/search",
        json={"query": "anything", "top_k": 5},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_telemetry_bumps_usage_stats_on_execute(client) -> None:
    """ExecuteRequest with pipeline_id → usage_stats.invoke_count increments."""
    # Setup: create a saved pipeline (draft is enough for executor)
    payload = {
        "name": "telemetry test",
        "description": "",
        "pipeline_kind": "auto_patrol",
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    pid = client.post("/api/v1/pipeline-builder/pipelines", json=payload).json()["id"]

    # Execute with pipeline_id
    pj = json.loads(_FIXTURE.read_text())
    r = client.post(
        "/api/v1/pipeline-builder/execute",
        json={"pipeline_json": pj, "pipeline_id": pid, "triggered_by": "user", "inputs": {}},
    )
    assert r.status_code == 200, r.text
    exec_body = r.json()
    # Telemetry bumps for success OR failed (any complete invocation with a run record)
    assert exec_body.get("status") in {"success", "failed"}, f"unexpected status {exec_body.get('status')}"

    # Check usage_stats bumped
    rec = client.get(f"/api/v1/pipeline-builder/pipelines/{pid}").json()
    stats = rec.get("usage_stats") or {}
    assert stats.get("invoke_count", 0) >= 1, f"stats={stats}"
    assert stats.get("last_invoked_at") is not None
