"""Unit tests for BuilderToolset (Phase 3.2)."""

from __future__ import annotations

import pytest

from app.services.agent_builder.session import AgentBuilderSession
from app.services.agent_builder.tools import BuilderToolset, ToolError
from app.services.pipeline_builder.block_registry import BlockRegistry
from app.services.pipeline_builder.blocks import BUILTIN_EXECUTORS
from app.services.pipeline_builder.seed import _blocks


@pytest.fixture
def registry() -> BlockRegistry:
    reg = BlockRegistry()
    cat = {}
    for spec in _blocks():
        cat[(spec["name"], spec["version"])] = {**spec, "is_custom": False}
    reg._catalog = cat
    reg._executors = {k: BUILTIN_EXECUTORS[k[0]]() for k in cat if k[0] in BUILTIN_EXECUTORS}
    return reg


@pytest.fixture
def toolset(registry):
    session = AgentBuilderSession.new("test prompt")
    return BuilderToolset(session, registry), session


@pytest.mark.asyncio
async def test_list_blocks_returns_all(toolset):
    t, _ = toolset
    r = await t.dispatch("list_blocks", {})
    # PR-E1 added block_data_view → 26. Catalog grows over time; assert at-least.
    assert r["count"] >= 25
    assert all("description" in b and "param_schema" in b for b in r["blocks"])


@pytest.mark.asyncio
async def test_list_blocks_filter_by_category(toolset):
    t, _ = toolset
    r = await t.dispatch("list_blocks", {"category": "logic"})
    assert r["count"] > 0
    assert all(b["category"] == "logic" for b in r["blocks"])


@pytest.mark.asyncio
async def test_add_node_autogens_id_and_position(toolset):
    t, s = toolset
    r1 = await t.dispatch("add_node", {"block_name": "block_process_history"})
    assert r1["node_id"] == "n1"
    r2 = await t.dispatch("add_node", {"block_name": "block_filter"})
    assert r2["node_id"] == "n2"
    assert len(s.pipeline_json.nodes) == 2


@pytest.mark.asyncio
async def test_add_node_unknown_block_errors(toolset):
    t, _ = toolset
    with pytest.raises(ToolError) as ei:
        await t.dispatch("add_node", {"block_name": "block_does_not_exist"})
    assert ei.value.code == "BLOCK_NOT_FOUND"


@pytest.mark.asyncio
async def test_add_node_smart_offset_on_collision(toolset):
    t, s = toolset
    await t.dispatch("add_node", {"block_name": "block_process_history", "position": {"x": 100, "y": 100}})
    r2 = await t.dispatch("add_node", {"block_name": "block_filter", "position": {"x": 100, "y": 100}})
    assert r2["position"]["x"] == 130  # 30px offset
    assert r2["position"]["y"] == 130


@pytest.mark.asyncio
async def test_connect_validates_port_types(toolset):
    t, _ = toolset
    await t.dispatch("add_node", {"block_name": "block_process_history"})
    await t.dispatch("add_node", {"block_name": "block_filter"})
    r = await t.dispatch("connect", {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"})
    assert r["edge_id"] == "e1"


@pytest.mark.asyncio
async def test_connect_mismatched_port_type_errors(toolset):
    t, _ = toolset
    # process_history output 'data' (dataframe) → alert input 'records' (dataframe) → OK (both df)
    # process_history output 'data' (dataframe) → chart input 'data' — also dataframe → OK too
    # Use invalid: non-existent port
    await t.dispatch("add_node", {"block_name": "block_process_history"})
    await t.dispatch("add_node", {"block_name": "block_filter"})
    with pytest.raises(ToolError) as ei:
        await t.dispatch("connect", {"from_node": "n1", "from_port": "data",
                                     "to_node": "n2", "to_port": "nonexistent"})
    assert ei.value.code == "PORT_NOT_FOUND"


@pytest.mark.asyncio
async def test_set_param_validates_schema(toolset):
    t, _ = toolset
    await t.dispatch("add_node", {"block_name": "block_filter"})
    # Unknown param key
    with pytest.raises(ToolError) as ei:
        await t.dispatch("set_param", {"node_id": "n1", "key": "bogus", "value": 1})
    assert ei.value.code == "PARAM_NOT_IN_SCHEMA"
    # Enum violation
    with pytest.raises(ToolError) as ei:
        await t.dispatch("set_param", {"node_id": "n1", "key": "operator", "value": "LIKE"})
    assert ei.value.code == "PARAM_ENUM_VIOLATION"
    # Valid
    r = await t.dispatch("set_param", {"node_id": "n1", "key": "operator", "value": "=="})
    assert r["params"]["operator"] == "=="


@pytest.mark.asyncio
async def test_validate_detects_missing_source(toolset):
    t, _ = toolset
    # Add a filter node with no source — validator should complain
    await t.dispatch("add_node", {"block_name": "block_filter", "params": {"column": "x", "operator": "==", "value": "1"}})
    r = await t.dispatch("validate", {})
    assert r["valid"] is False
    rules = {e["rule"] for e in r["errors"]}
    assert "C7_ENDPOINTS" in rules


@pytest.mark.asyncio
async def test_get_state_reports_structure(toolset):
    t, _ = toolset
    await t.dispatch("add_node", {"block_name": "block_process_history"})
    await t.dispatch("add_node", {"block_name": "block_filter"})
    await t.dispatch("connect", {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"})
    r = await t.dispatch("get_state", {})
    assert r["node_count"] == 2
    assert r["edge_count"] == 1
    assert r["nodes"][0]["id"] == "n1"


@pytest.mark.asyncio
async def test_explain_appends_chat(toolset):
    t, s = toolset
    await t.dispatch("explain", {"message": "I'm adding a filter.", "highlight_nodes": ["n1"]})
    assert len(s.chat) == 1
    assert s.chat[0].content == "I'm adding a filter."


@pytest.mark.asyncio
async def test_finish_blocked_when_invalid(toolset):
    t, _ = toolset
    await t.dispatch("add_node", {"block_name": "block_filter"})  # orphan filter → validator fails
    with pytest.raises(ToolError) as ei:
        await t.dispatch("finish", {"summary": "oops"})
    assert ei.value.code == "FINISH_BLOCKED"


@pytest.mark.asyncio
async def test_finish_succeeds_when_valid(toolset):
    t, s = toolset
    # v3.2 logic-node schema: need source → logic → alert (triggered + evidence both)
    await t.dispatch("add_node", {"block_name": "block_process_history", "params": {"tool_id": "EQP-01"}})
    await t.dispatch("add_node", {
        "block_name": "block_consecutive_rule",
        "params": {"flag_column": "spc_xbar_chart_is_ooc", "count": 3, "sort_by": "eventTime"},
    })
    await t.dispatch("add_node", {"block_name": "block_alert", "params": {"severity": "LOW"}})
    await t.dispatch("connect", {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"})
    await t.dispatch("connect", {"from_node": "n2", "from_port": "triggered", "to_node": "n3", "to_port": "triggered"})
    await t.dispatch("connect", {"from_node": "n2", "from_port": "evidence", "to_node": "n3", "to_port": "evidence"})
    v = await t.dispatch("validate", {})
    assert v["valid"] is True, v
    r = await t.dispatch("finish", {"summary": "built a 3-node pipeline"})
    assert r["status"] == "finished"
    assert s.status == "finished"


@pytest.mark.asyncio
async def test_remove_node_removes_touching_edges(toolset):
    t, _ = toolset
    await t.dispatch("add_node", {"block_name": "block_process_history"})
    await t.dispatch("add_node", {"block_name": "block_filter"})
    await t.dispatch("connect", {"from_node": "n1", "from_port": "data", "to_node": "n2", "to_port": "data"})
    r = await t.dispatch("remove_node", {"node_id": "n1"})
    assert r["removed_node"] == "n1"
    assert "e1" in r["removed_edges"]


@pytest.mark.asyncio
async def test_rename_node(toolset):
    t, s = toolset
    await t.dispatch("add_node", {"block_name": "block_process_history"})
    r = await t.dispatch("rename_node", {"node_id": "n1", "label": "My Source"})
    assert r["display_label"] == "My Source"
    assert s.pipeline_json.nodes[0].display_label == "My Source"


@pytest.mark.asyncio
async def test_dispatch_unknown_tool(toolset):
    t, _ = toolset
    with pytest.raises(ToolError) as ei:
        await t.dispatch("__nonexistent", {})
    assert ei.value.code == "UNKNOWN_TOOL"
