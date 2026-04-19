"""Phase 4-A — skill → pipeline migrator tests.

Uses the 6 production skills (dumped to fixtures/skills/*.json) as real-world
regression cases. For each skill:
  1. run migrator
  2. assert status is one of {full, skeleton, manual}
  3. if status != manual → validate generated pipeline_json via PipelineValidator
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.schemas.pipeline import PipelineJSON
from app.services.pipeline_builder.skill_migrator import (
    MigrationResult,
    migrate_skill,
    _extract_mcp_calls,
    _detect_logic_pattern,
)


FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "skills"


def _load(id_: int) -> dict:
    return json.loads((FIXTURES / f"skill_{id_}.json").read_text())


# ─── Parser unit tests ──────────────────────────────────────────────────────
def test_extract_mcp_call_single() -> None:
    code = "result = await execute_mcp('get_process_info', {'toolID': x})"
    calls = _extract_mcp_calls(code)
    assert len(calls) == 1
    assert calls[0][0] == "get_process_info"


def test_extract_mcp_call_multiple_with_args() -> None:
    code = """
history = await execute_mcp('get_object_snapshot_history', {'targetID': equipment_id, 'objectName': 'SPC'})
ctx = await execute_mcp("get_process_context", {"targetID": lot, "step": s})
"""
    calls = _extract_mcp_calls(code)
    assert len(calls) == 2
    assert calls[0][0] == "get_object_snapshot_history"
    assert calls[1][0] == "get_process_context"


def test_detect_rolling_count_pattern() -> None:
    code = """
recent_5 = records[-5:] if len(records) >= 5 else records
ooc_count = sum(1 for rec in recent_5 if rec["is_ooc"])
condition_met = ooc_count >= 2
"""
    p = _detect_logic_pattern(code)
    assert p is not None
    assert p["pattern"] == "rolling_count_threshold"
    assert p["window"] == 5
    assert p["threshold"] == 2


def test_detect_same_group_check() -> None:
    code = "is_same_recipe = len(ooc_recipe_list) == 1 if ooc_records else False"
    p = _detect_logic_pattern(code)
    assert p is not None
    assert p["pattern"] == "same_group_check"


# ─── Per-skill integration tests (6 real skills) ────────────────────────────
@pytest.mark.parametrize("skill_id", [3, 4, 5, 6, 7, 10])
def test_migrate_skill_produces_valid_pipeline_or_manual(skill_id: int) -> None:
    skill = _load(skill_id)
    result = migrate_skill(skill)
    assert isinstance(result, MigrationResult)
    assert result.status in {"full", "skeleton", "manual"}

    if result.status == "manual":
        # manual = no MCP detected; pipeline_json may be empty
        assert result.pipeline_json == {} or "nodes" in result.pipeline_json
        return

    # Pipeline JSON must at minimum be structurally parseable
    pipeline = PipelineJSON.model_validate(result.pipeline_json)
    assert pipeline.name.startswith("[migrated]")
    assert len(pipeline.nodes) >= 1
    # tool_id input is either declared or the migrator auto-injected it
    input_names = {i.name for i in pipeline.inputs}
    assert "tool_id" in input_names
    # source block present
    source_block_ids = {"block_process_history", "block_mcp_call"}
    assert any(n.block_id in source_block_ids for n in pipeline.nodes)


def test_skill_10_stub_is_skeleton_with_source_only() -> None:
    """Skill 10 has only a basic fetch — should migrate cleanly but stay as skeleton."""
    r = migrate_skill(_load(10))
    assert r.status in {"skeleton", "full"}
    assert "block_process_history" in {n["block_id"] for n in r.pipeline_json["nodes"]}


def test_skill_4_5_in_3_out_detects_rolling_pattern() -> None:
    """Skill 4 = 5-in-3-out should pattern-match rolling_count_threshold."""
    r = migrate_skill(_load(4))
    block_ids = [n["block_id"] for n in r.pipeline_json["nodes"]]
    assert "block_rolling_window" in block_ids


def test_skill_6_same_recipe_uses_count_rows_threshold() -> None:
    """Phase 4-A+: same-recipe check now fully migrates with count_rows + threshold(>)."""
    r = migrate_skill(_load(6))
    block_ids = [n["block_id"] for n in r.pipeline_json["nodes"]]
    assert "block_filter" in block_ids
    assert "block_count_rows" in block_ids
    assert "block_threshold" in block_ids


def test_skill_5_multi_mcp_uses_foreach() -> None:
    """Skill 5 calls get_process_context in a for-loop — migrator wires block_mcp_foreach."""
    r = migrate_skill(_load(5))
    block_ids = [n["block_id"] for n in r.pipeline_json["nodes"]]
    assert "block_mcp_foreach" in block_ids
