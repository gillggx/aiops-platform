"""SSE endpoint + orchestrator integration tests (stubbed LLM).

We replace anthropic.AsyncAnthropic with a fake that emits a scripted sequence
of tool_use blocks, so we can test orchestrator + SSE wire end-to-end without
incurring real API costs or network.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@dataclass
class _StubBlock:
    type: str
    id: str = ""
    name: str = ""
    input: dict = None  # type: ignore
    text: str = ""


@dataclass
class _StubResponse:
    content: list
    stop_reason: str = "tool_use"


def _make_fake_claude(script: list[list[dict]]):
    """Build a fake AsyncAnthropic whose messages.create returns each `turn`
    from `script` in order. Each turn is a list of content blocks (dicts).
    """
    turns = iter(script)

    class _FakeMessages:
        async def create(self, **kwargs):
            try:
                blocks_spec = next(turns)
            except StopIteration:
                # If script exhausted, synthesize no-tool response → orchestrator aborts
                return _StubResponse(content=[], stop_reason="end_turn")
            blocks = []
            for b in blocks_spec:
                if b["type"] == "tool_use":
                    blocks.append(_StubBlock(
                        type="tool_use",
                        id=b.get("id", "tu_1"),
                        name=b["name"],
                        input=b.get("input", {}),
                    ))
                elif b["type"] == "text":
                    blocks.append(_StubBlock(type="text", text=b["text"]))
            return _StubResponse(content=blocks, stop_reason="tool_use")

    class _FakeClient:
        def __init__(self, **_kwargs):
            self.messages = _FakeMessages()

    return _FakeClient


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    os.environ.setdefault("ONTOLOGY_SIM_URL", "http://fake-sim")
    os.environ.setdefault("ANTHROPIC_API_KEY", "fake-key")
    import importlib
    from app import database
    database._engine = None
    database._async_session_factory = None
    import main as main_mod
    importlib.reload(main_mod)
    with TestClient(main_mod.app) as c:
        yield c


# ---------------------------------------------------------------------------


def test_create_session_returns_id(client):
    resp = client.post("/api/v1/agent/build", json={"prompt": "build something"})
    assert resp.status_code == 201
    body = resp.json()
    assert "session_id" in body
    assert len(body["session_id"]) > 0


def test_stream_404_when_session_missing(client):
    resp = client.get("/api/v1/agent/build/stream/does-not-exist")
    assert resp.status_code == 404


def test_full_sse_run_with_stubbed_llm(client):
    """Happy path: agent builds a 3-node logic pipeline (source → consecutive → alert)."""
    script = [
        # Turn 1: list_blocks
        [{"type": "tool_use", "id": "tu_1", "name": "list_blocks", "input": {}}],
        # Turn 2: add three nodes + connect
        [
            {"type": "tool_use", "id": "tu_2", "name": "add_node",
             "input": {"block_name": "block_process_history", "params": {"tool_id": "EQP-01"}}},
            {"type": "tool_use", "id": "tu_3", "name": "add_node",
             "input": {"block_name": "block_consecutive_rule",
                       "params": {"flag_column": "spc_xbar_chart_is_ooc",
                                  "count": 3, "sort_by": "eventTime"}}},
            {"type": "tool_use", "id": "tu_4", "name": "add_node",
             "input": {"block_name": "block_alert", "params": {"severity": "LOW"}}},
            {"type": "tool_use", "id": "tu_5", "name": "connect",
             "input": {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"}},
            {"type": "tool_use", "id": "tu_6", "name": "connect",
             "input": {"from_node": "n2", "from_port": "triggered", "to_node": "n3", "to_port": "triggered"}},
            {"type": "tool_use", "id": "tu_7", "name": "connect",
             "input": {"from_node": "n2", "from_port": "evidence", "to_node": "n3", "to_port": "evidence"}},
            {"type": "tool_use", "id": "tu_8", "name": "explain",
             "input": {"message": "Connected source → consecutive_rule → alert."}},
        ],
        # Turn 3: validate + finish
        [
            {"type": "tool_use", "id": "tu_9", "name": "validate", "input": {}},
            {"type": "tool_use", "id": "tu_10", "name": "finish",
             "input": {"summary": "3-node consecutive-OOC pipeline"}},
        ],
    ]

    create = client.post("/api/v1/agent/build", json={"prompt": "alert on 3 consecutive OOC"})
    session_id = create.json()["session_id"]

    FakeClient = _make_fake_claude(script)
    with patch("app.services.agent_builder.orchestrator.anthropic.AsyncAnthropic", FakeClient):
        with client.stream("GET", f"/api/v1/agent/build/stream/{session_id}") as r:
            events = []
            for raw in r.iter_lines():
                if raw.startswith("event: "):
                    event_name = raw[7:]
                    continue
                if raw.startswith("data: "):
                    data = json.loads(raw[6:])
                    events.append({"type": event_name, "data": data})
                    if event_name == "done":
                        break

    ops = [e for e in events if e["type"] == "operation"]
    chats = [e for e in events if e["type"] == "chat"]
    dones = [e for e in events if e["type"] == "done"]
    assert len(dones) == 1
    assert dones[0]["data"]["status"] == "finished"
    assert any(op["data"]["op"] == "add_node" for op in ops)
    assert any(op["data"]["op"] == "finish" for op in ops)
    assert len(chats) >= 1
    pj = dones[0]["data"]["pipeline_json"]
    assert len(pj["nodes"]) == 3
    assert len(pj["edges"]) == 3


def test_cancel_mid_run(client):
    """User cancels mid-stream: orchestrator stops, session marked cancelled."""
    # Script that would add many nodes — we'll cancel before we exhaust it
    script = [
        [{"type": "tool_use", "id": f"tu_{i}", "name": "add_node",
          "input": {"block_name": "block_process_history"}}]
        for i in range(20)
    ]

    create = client.post("/api/v1/agent/build", json={"prompt": "add many"})
    sid = create.json()["session_id"]

    # Cancel immediately — orchestrator should observe the flag at next check
    client.post(f"/api/v1/agent/build/{sid}/cancel")

    FakeClient = _make_fake_claude(script)
    with patch("app.services.agent_builder.orchestrator.anthropic.AsyncAnthropic", FakeClient):
        with client.stream("GET", f"/api/v1/agent/build/stream/{sid}") as r:
            events = []
            event_name = None
            for raw in r.iter_lines():
                if raw.startswith("event: "):
                    event_name = raw[7:]
                    continue
                if raw.startswith("data: "):
                    data = json.loads(raw[6:])
                    events.append({"type": event_name, "data": data})
                    if event_name == "done":
                        break

    dones = [e for e in events if e["type"] == "done"]
    assert len(dones) == 1
    assert dones[0]["data"]["status"] == "cancelled"


def test_get_session_after_finish(client):
    """After a successful run, GET /{id} returns the final state."""
    script = [
        [{"type": "tool_use", "id": "tu_1", "name": "add_node",
          "input": {"block_name": "block_process_history", "params": {"tool_id": "EQP-01"}}}],
        [{"type": "tool_use", "id": "tu_2", "name": "add_node",
          "input": {"block_name": "block_consecutive_rule",
                    "params": {"flag_column": "spc_xbar_chart_is_ooc",
                               "count": 3, "sort_by": "eventTime"}}},
         {"type": "tool_use", "id": "tu_3", "name": "add_node",
          "input": {"block_name": "block_alert", "params": {"severity": "LOW"}}},
         {"type": "tool_use", "id": "tu_4", "name": "connect",
          "input": {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"}},
         {"type": "tool_use", "id": "tu_5", "name": "connect",
          "input": {"from_node": "n2", "from_port": "triggered", "to_node": "n3", "to_port": "triggered"}},
         {"type": "tool_use", "id": "tu_6", "name": "connect",
          "input": {"from_node": "n2", "from_port": "evidence", "to_node": "n3", "to_port": "evidence"}}],
        [{"type": "tool_use", "id": "tu_7", "name": "finish",
          "input": {"summary": "done"}}],
    ]
    create = client.post("/api/v1/agent/build", json={"prompt": "x"})
    sid = create.json()["session_id"]
    FakeClient = _make_fake_claude(script)
    with patch("app.services.agent_builder.orchestrator.anthropic.AsyncAnthropic", FakeClient):
        with client.stream("GET", f"/api/v1/agent/build/stream/{sid}") as r:
            for raw in r.iter_lines():
                if raw.startswith("event: done"):
                    break

    # Now fetch session
    r = client.get(f"/api/v1/agent/build/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "finished"
    assert len(body["pipeline_json"]["nodes"]) == 3


def test_batch_endpoint_fallback(client):
    """POST /batch runs same orchestrator but returns all events at once."""
    script = [
        [{"type": "tool_use", "id": "tu_1", "name": "add_node",
          "input": {"block_name": "block_process_history", "params": {"tool_id": "EQP-01"}}}],
        [{"type": "tool_use", "id": "tu_2", "name": "add_node",
          "input": {"block_name": "block_consecutive_rule",
                    "params": {"flag_column": "spc_xbar_chart_is_ooc",
                               "count": 3, "sort_by": "eventTime"}}},
         {"type": "tool_use", "id": "tu_3", "name": "add_node",
          "input": {"block_name": "block_alert", "params": {"severity": "LOW"}}},
         {"type": "tool_use", "id": "tu_4", "name": "connect",
          "input": {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"}},
         {"type": "tool_use", "id": "tu_5", "name": "connect",
          "input": {"from_node": "n2", "from_port": "triggered", "to_node": "n3", "to_port": "triggered"}},
         {"type": "tool_use", "id": "tu_6", "name": "connect",
          "input": {"from_node": "n2", "from_port": "evidence", "to_node": "n3", "to_port": "evidence"}}],
        [{"type": "tool_use", "id": "tu_7", "name": "finish",
          "input": {"summary": "done"}}],
    ]
    FakeClient = _make_fake_claude(script)
    with patch("app.services.agent_builder.orchestrator.anthropic.AsyncAnthropic", FakeClient):
        r = client.post("/api/v1/agent/build/batch", json={"prompt": "x"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "finished"
    assert any(e["type"] == "operation" and e["data"]["op"] == "finish" for e in body["events"])
