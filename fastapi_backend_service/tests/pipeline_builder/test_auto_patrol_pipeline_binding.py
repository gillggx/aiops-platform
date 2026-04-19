"""Phase 4-B — auto_patrol pipeline binding tests.

Covers the input-binding resolver directly + a smoke test for the end-to-end
flow using an in-memory pipeline + mocked repositories.
"""

from __future__ import annotations

import pytest

from app.services.auto_patrol_service import _resolve_input_binding


# ─── _resolve_input_binding ─────────────────────────────────────────────────
def test_resolve_literal_values_pass_through() -> None:
    out = _resolve_input_binding(
        {"tool_id": "EQP-01", "count": 3, "is_strict": True},
        context={},
    )
    assert out == {"tool_id": "EQP-01", "count": 3, "is_strict": True}


def test_resolve_event_ref() -> None:
    out = _resolve_input_binding(
        {"tool_id": "$event.toolID", "step": "$event.step"},
        context={"toolID": "EQP-01", "step": "STEP_002", "extra": "ignore"},
    )
    assert out == {"tool_id": "EQP-01", "step": "STEP_002"}


def test_resolve_context_ref_same_as_event() -> None:
    # context.x and event.x both read from the same flat dict
    out = _resolve_input_binding(
        {"tool_id": "$context.equipment_id"},
        context={"equipment_id": "EQP-07"},
    )
    assert out == {"tool_id": "EQP-07"}


def test_resolve_missing_event_key_yields_none() -> None:
    out = _resolve_input_binding(
        {"tool_id": "$event.missing"},
        context={"other": "x"},
    )
    assert out == {"tool_id": None}


def test_resolve_env_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_VAR", "from_env")
    out = _resolve_input_binding(
        {"x": "$ENV.TEST_VAR"},
        context={},
    )
    assert out == {"x": "from_env"}


def test_resolve_empty_binding_returns_empty() -> None:
    assert _resolve_input_binding(None, context={"a": 1}) == {}
    assert _resolve_input_binding({}, context={"a": 1}) == {}


def test_resolve_unknown_prefix_left_literal() -> None:
    """$foo.bar (no known scope) → pass through as string for executor to handle."""
    out = _resolve_input_binding({"x": "$random.value"}, context={})
    assert out == {"x": "$random.value"}


def test_resolve_mixed_literal_and_ref() -> None:
    out = _resolve_input_binding(
        {"tool_id": "$event.toolID", "threshold": 5, "name": "daily"},
        context={"toolID": "EQP-02"},
    )
    assert out == {"tool_id": "EQP-02", "threshold": 5, "name": "daily"}
