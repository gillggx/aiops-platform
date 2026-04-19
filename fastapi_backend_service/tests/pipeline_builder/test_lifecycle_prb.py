"""PR-B — 5-stage lifecycle + pipeline_kind + C11/C12 validators."""

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


def _make(client: TestClient, kind: str = "auto_patrol") -> int:
    payload = {
        "name": f"PR-B {kind} case",
        "description": "",
        "pipeline_kind": kind,
        "pipeline_json": json.loads(_FIXTURE.read_text()),
    }
    return client.post("/api/v1/pipeline-builder/pipelines", json=payload).json()["id"]


def test_transition_draft_to_validating_happy(client) -> None:
    pid = _make(client, "auto_patrol")
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "validating"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "validating"


def test_transition_rejects_illegal_jump(client) -> None:
    pid = _make(client, "auto_patrol")
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "active"})
    assert r.status_code == 409


def test_transition_validating_to_locked_runs_c11_for_autopatrol(client) -> None:
    pid = _make(client, "auto_patrol")
    r1 = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "validating"})
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "locked"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "locked"


def test_transition_validating_to_locked_rejects_skill_with_alert(client) -> None:
    """Phase 5-UX-7: skill pipelines must NOT contain block_alert.

    Fixture has block_alert. Skill kind therefore should fail C12.
    """
    pid = _make(client, "skill")
    r1 = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "validating"})
    assert r1.status_code == 200
    r2 = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "locked"})
    assert r2.status_code == 422, r2.text
    body = r2.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    errors: list[dict] = []
    if isinstance(detail, dict):
        errors = detail.get("errors", [])
    assert any(e.get("rule") == "C12_SKILL_NEEDS_CHART" for e in errors) or "C12" in r2.text


def test_active_update_blocked_but_clone_allowed(client) -> None:
    pid = _make(client, "auto_patrol")
    for target in ["validating", "locked", "active"]:
        r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": target})
        assert r.status_code == 200, r.text

    put = client.put(f"/api/v1/pipeline-builder/pipelines/{pid}", json={"name": "edit blocked"})
    assert put.status_code == 409

    fork = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/fork")
    assert fork.status_code == 201
    cloned = fork.json()
    assert cloned["status"] == "draft"
    assert cloned["pipeline_kind"] == "auto_patrol"
    assert cloned["parent_id"] == pid


def test_archive_terminal_cannot_transition_out(client) -> None:
    pid = _make(client, "auto_patrol")
    r = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "archived"})
    assert r.status_code == 200
    r2 = client.post(f"/api/v1/pipeline-builder/pipelines/{pid}/transition", json={"to": "draft"})
    assert r2.status_code == 409
