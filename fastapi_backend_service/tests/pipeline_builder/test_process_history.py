"""Unit tests for block_process_history — 3-of-3 input, wide-flatten, object_name filter."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.pipeline_builder.blocks.base import BlockExecutionError, ExecutionContext
from app.services.pipeline_builder.blocks.process_history import (
    ProcessHistoryBlockExecutor,
    _flatten_event,
)


CTX = ExecutionContext()


def _nested_event() -> dict:
    """Build one event with SPC + APC + DC + RECIPE + FDC + EC populated."""
    return {
        "eventTime": "2026-04-18T10:00Z",
        "toolID": "EQP-01",
        "lotID": "LOT-001",
        "step": "STEP_002",
        "spc_status": "OOC",
        "fdc_classification": "WARNING",
        "SPC": {
            "charts": {
                "xbar_chart": {"value": 160.0, "ucl": 150.0, "lcl": 50.0, "is_ooc": True},
                "r_chart": {"value": 12.0, "ucl": 15.0, "lcl": 0.0, "is_ooc": False},
            }
        },
        "APC": {
            "objectID": "APC-1",
            "mode": "auto",
            "parameters": {"etch_time_offset": 0.5, "rf_power_bias": 12.3},
        },
        "DC": {
            "objectID": "DC-1",
            "parameters": {"chamber_pressure": 7.2, "rf_forward_power": 1200.0},
        },
        "RECIPE": {
            "objectID": "RCP-1",
            "recipe_version": "v3.1",
            "parameters": {"etch_time_s": 45.0, "target_thickness_nm": 80.0},
        },
        "FDC": {
            "classification": "WARNING",
            "fault_code": "E104",
            "confidence": 0.82,
            "description": "RF drift detected",
        },
        "EC": {
            "constants": {
                "rf_power_offset": {
                    "value": 1.2,
                    "nominal": 1.0,
                    "tolerance_pct": 20.0,
                    "deviation_pct": 20.0,
                    "status": "WARNING",
                }
            }
        },
    }


# ─── _flatten_event pure logic ─────────────────────────────────────────────


def test_flatten_without_filter_returns_wide_row() -> None:
    row = _flatten_event(_nested_event(), object_name=None)
    # base
    assert row["toolID"] == "EQP-01"
    assert row["spc_status"] == "OOC"
    assert row["fdc_classification"] == "WARNING"
    # spc
    assert row["spc_xbar_chart_value"] == 160.0
    assert row["spc_xbar_chart_is_ooc"] is True
    assert row["spc_r_chart_ucl"] == 15.0
    # apc
    assert row["apc_etch_time_offset"] == 0.5
    assert row["apc_rf_power_bias"] == 12.3
    # dc
    assert row["dc_chamber_pressure"] == 7.2
    # recipe
    assert row["recipe_version"] == "v3.1"
    assert row["recipe_etch_time_s"] == 45.0
    # fdc
    assert row["fdc_fault_code"] == "E104"
    # ec (nested {value, nominal, deviation_pct, status} all flattened)
    assert row["ec_rf_power_offset_value"] == 1.2
    assert row["ec_rf_power_offset_status"] == "WARNING"


def test_flatten_with_SPC_filter_only_keeps_spc_fields() -> None:
    row = _flatten_event(_nested_event(), object_name="SPC")
    assert row["toolID"] == "EQP-01"
    assert row["spc_xbar_chart_value"] == 160.0
    # Other dimensions should NOT be present
    assert "apc_rf_power_bias" not in row
    assert "dc_chamber_pressure" not in row
    assert "recipe_version" not in row
    assert "ec_rf_power_offset_value" not in row


def test_flatten_with_APC_filter() -> None:
    row = _flatten_event(_nested_event(), object_name="APC")
    assert "apc_rf_power_bias" in row
    assert "spc_xbar_chart_value" not in row
    assert "dc_chamber_pressure" not in row


# ─── executor-level 3-of-3 runtime check ────────────────────────────────────


@pytest.mark.asyncio
async def test_require_at_least_one_of_tool_lot_step() -> None:
    block = ProcessHistoryBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(params={}, inputs={}, context=CTX)
    assert ei.value.code == "MISSING_PARAM"
    assert "tool_id" in ei.value.message
    assert "lot_id" in ei.value.message
    assert "step" in ei.value.message


@pytest.mark.asyncio
async def test_only_step_is_enough() -> None:
    """Providing step alone should NOT trigger the 3-of-3 error (it hits MISSING_CONFIG later)."""
    block = ProcessHistoryBlockExecutor()
    with patch(
        "app.services.pipeline_builder.blocks.process_history.get_settings"
    ) as mock_settings:
        mock_settings.return_value.ONTOLOGY_SIM_URL = ""
        with pytest.raises(BlockExecutionError) as ei:
            await block.execute(params={"step": "STEP_002"}, inputs={}, context=CTX)
        # Error comes from missing URL, NOT missing params — proving 3-of-3 accepted step alone
        assert ei.value.code == "MISSING_CONFIG"


@pytest.mark.asyncio
async def test_invalid_object_name_rejected() -> None:
    block = ProcessHistoryBlockExecutor()
    with pytest.raises(BlockExecutionError) as ei:
        await block.execute(
            params={"tool_id": "EQP-01", "object_name": "BOGUS"},
            inputs={},
            context=CTX,
        )
    assert ei.value.code == "INVALID_PARAM"


# ─── end-to-end with mocked httpx ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_returns_wide_dataframe() -> None:
    block = ProcessHistoryBlockExecutor()
    fake_payload = {"total": 1, "events": [_nested_event()]}

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: fake_payload

    with patch(
        "app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient"
    ) as mc:
        mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        with patch(
            "app.services.pipeline_builder.blocks.process_history.get_settings"
        ) as mock_settings:
            mock_settings.return_value.ONTOLOGY_SIM_URL = "http://fake"
            out = await block.execute(
                params={"tool_id": "EQP-01"},
                inputs={},
                context=CTX,
            )

    df = out["data"]
    assert len(df) == 1
    # Wide table should contain all dimensions
    cols = set(df.columns)
    assert {"toolID", "spc_xbar_chart_value", "apc_rf_power_bias", "dc_chamber_pressure",
            "recipe_etch_time_s", "fdc_fault_code", "ec_rf_power_offset_value"}.issubset(cols)


@pytest.mark.asyncio
async def test_execute_with_object_name_filter_returns_narrow_dataframe() -> None:
    block = ProcessHistoryBlockExecutor()
    fake_payload = {"total": 1, "events": [_nested_event()]}

    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: fake_payload

    with patch(
        "app.services.pipeline_builder.blocks.process_history.httpx.AsyncClient"
    ) as mc:
        mc.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        with patch(
            "app.services.pipeline_builder.blocks.process_history.get_settings"
        ) as mock_settings:
            mock_settings.return_value.ONTOLOGY_SIM_URL = "http://fake"
            out = await block.execute(
                params={"tool_id": "EQP-01", "object_name": "APC"},
                inputs={},
                context=CTX,
            )

    df = out["data"]
    cols = set(df.columns)
    # APC-only fields plus base
    assert "apc_rf_power_bias" in cols
    # SPC / DC / RECIPE columns must be absent
    assert "spc_xbar_chart_value" not in cols
    assert "dc_chamber_pressure" not in cols
    assert "recipe_etch_time_s" not in cols
