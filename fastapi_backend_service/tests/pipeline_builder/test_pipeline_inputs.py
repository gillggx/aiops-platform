"""Phase 4-B0 — pipeline-level inputs (parameterization) tests.

Covers:
  - schema: PipelineJSON.inputs
  - resolver: $ref replacement + type coercion
  - executor: missing required / invalid coercion → failed run
  - validator: C10 UNDECLARED_INPUT_REF; C6 skips $ref type-check
"""

from __future__ import annotations

import pytest

from app.schemas.pipeline import PipelineJSON
from app.services.pipeline_builder.executor import (
    _coerce_input,
    _resolve_inputs,
    _resolve_params,
    PipelineExecutor,
)
from app.services.pipeline_builder.blocks.base import BlockExecutionError
from app.services.pipeline_builder.validator import PipelineValidator


# ─── _coerce_input ──────────────────────────────────────────────────────────
def test_coerce_string_integer_number_boolean() -> None:
    assert _coerce_input(3, "string") == "3"
    assert _coerce_input("3", "integer") == 3
    assert _coerce_input("3.5", "number") == 3.5
    assert _coerce_input("true", "boolean") is True
    assert _coerce_input("False", "boolean") is False
    assert _coerce_input(None, "string") is None


def test_coerce_rejects_bool_as_integer() -> None:
    with pytest.raises(ValueError):
        _coerce_input(True, "integer")


def test_coerce_invalid_bool_string() -> None:
    with pytest.raises(ValueError):
        _coerce_input("notabool", "boolean")


# ─── _resolve_inputs ─────────────────────────────────────────────────────────
def _make_pipeline(
    inputs: list[dict],
    nodes: list[dict] | None = None,
    edges: list[dict] | None = None,
) -> PipelineJSON:
    return PipelineJSON.model_validate({
        "name": "test",
        "inputs": inputs,
        "nodes": nodes or [{
            "id": "n1", "block_id": "block_process_history",
            "position": {"x": 0, "y": 0}, "params": {"tool_id": "$tool_id"},
        }],
        "edges": edges or [],
    })


def test_resolve_uses_runtime_over_default() -> None:
    p = _make_pipeline([{"name": "tool_id", "type": "string", "default": "EQP-99"}])
    got = _resolve_inputs(p, {"tool_id": "EQP-01"})
    assert got == {"tool_id": "EQP-01"}


def test_resolve_falls_back_to_default() -> None:
    p = _make_pipeline([{"name": "tool_id", "type": "string", "default": "EQP-99"}])
    got = _resolve_inputs(p, {})
    assert got == {"tool_id": "EQP-99"}


def test_resolve_missing_required_raises() -> None:
    p = _make_pipeline([{"name": "tool_id", "type": "string", "required": True}])
    with pytest.raises(BlockExecutionError) as ei:
        _resolve_inputs(p, {})
    assert ei.value.code == "MISSING_INPUT"


def test_resolve_coerces_integer() -> None:
    p = _make_pipeline([{"name": "count", "type": "integer"}])
    got = _resolve_inputs(p, {"count": "5"})
    assert got == {"count": 5}


def test_resolve_invalid_coercion_raises_invalid_input() -> None:
    p = _make_pipeline([{"name": "count", "type": "integer"}])
    with pytest.raises(BlockExecutionError) as ei:
        _resolve_inputs(p, {"count": "not-a-number"})
    assert ei.value.code == "INVALID_INPUT"


def test_resolve_unknown_runtime_key_is_ignored(caplog) -> None:
    p = _make_pipeline([{"name": "tool_id", "type": "string", "default": "X"}])
    got = _resolve_inputs(p, {"tool_id": "Y", "bogus": 1})
    assert got == {"tool_id": "Y"}


# ─── _resolve_params ────────────────────────────────────────────────────────
def test_resolve_params_replaces_dollar_refs() -> None:
    out = _resolve_params(
        {"tool_id": "$tool_id", "plain": "keep"},
        {"tool_id": "EQP-01"},
        declared_names={"tool_id"},
        node_id="n1",
    )
    assert out == {"tool_id": "EQP-01", "plain": "keep"}


def test_resolve_params_undeclared_ref_raises() -> None:
    with pytest.raises(BlockExecutionError) as ei:
        _resolve_params(
            {"tool_id": "$bogus"},
            {"tool_id": "EQP-01"},
            declared_names={"tool_id"},
            node_id="n1",
        )
    assert ei.value.code == "UNDECLARED_INPUT_REF"


# ─── Full executor integration ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_executor_reports_failed_when_missing_required_input() -> None:
    from app.services.pipeline_builder.block_registry import BlockRegistry
    registry = BlockRegistry()
    registry._catalog = {}
    registry._executors = {}
    p = _make_pipeline([{"name": "tool_id", "type": "string", "required": True}])
    out = await PipelineExecutor(registry).execute(p)
    assert out["status"] == "failed"
    assert "MISSING_INPUT" in (out.get("error_message") or "")


# ─── Validator C10 ──────────────────────────────────────────────────────────
def test_c10_undeclared_ref_fails(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = {
        "version": "1.0",
        "name": "x",
        "inputs": [],
        "nodes": [
            {"id": "n1", "block_id": "block_process_history", "block_version": "1.0.0",
             "position": {"x": 0, "y": 0}, "params": {"tool_id": "$tool_id"}},
            {"id": "n2", "block_id": "block_alert", "block_version": "1.0.0",
             "position": {"x": 100, "y": 0}, "params": {"severity": "LOW"}},
        ],
        "edges": [],
    }
    errors = v.validate(p)
    assert any(e["rule"] == "C10_UNDECLARED_INPUT_REF" for e in errors)


def test_c10_declared_ref_passes(block_catalog) -> None:
    v = PipelineValidator(block_catalog)
    p = {
        "version": "1.0",
        "name": "x",
        "inputs": [{"name": "tool_id", "type": "string", "default": "EQP-01"}],
        "nodes": [
            {"id": "n1", "block_id": "block_process_history", "block_version": "1.0.0",
             "position": {"x": 0, "y": 0}, "params": {"tool_id": "$tool_id"}},
        ],
        "edges": [],
    }
    errors = v.validate(p)
    assert not any(e["rule"] == "C10_UNDECLARED_INPUT_REF" for e in errors)


def test_c6_skips_type_check_for_dollar_refs(block_catalog) -> None:
    """$-refs are resolved at runtime — C6 shouldn't complain about 'count' being a string."""
    v = PipelineValidator(block_catalog)
    p = {
        "version": "1.0",
        "name": "x",
        "inputs": [{"name": "count", "type": "integer", "default": 3}],
        "nodes": [
            {"id": "n1", "block_id": "block_process_history", "block_version": "1.0.0",
             "position": {"x": 0, "y": 0}, "params": {"tool_id": "EQP-01"}},
            {"id": "n2", "block_id": "block_filter", "block_version": "1.0.0",
             "position": {"x": 200, "y": 0},
             "params": {"column": "step", "operator": "==", "value": "STEP_002"}},
            {"id": "n3", "block_id": "block_consecutive_rule", "block_version": "1.0.0",
             "position": {"x": 400, "y": 0},
             # count = $ref (string), block expects integer — should NOT be C6 error
             "params": {"flag_column": "spc_status", "count": "$count", "sort_by": "eventTime"}},
        ],
        "edges": [
            {"id": "e1", "from": {"node": "n1", "port": "data"}, "to": {"node": "n2", "port": "data"}},
            {"id": "e2", "from": {"node": "n2", "port": "data"}, "to": {"node": "n3", "port": "data"}},
        ],
    }
    errors = v.validate(p)
    # No C6 error on 'count' being string — $ref bypass in place
    c6_errors = [e for e in errors if e["rule"] == "C6_PARAM_SCHEMA" and "count" in e["message"]]
    assert c6_errors == []
