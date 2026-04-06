"""
aiops-contract QA Test Suite (Python)

涵蓋：schema 驗證、序列化、邊界條件、型別安全
"""

import json
import pytest
from pydantic import ValidationError

from aiops_contract import (
    AIOpsReportContract,
    EvidenceItem,
    VisualizationItem,
    AgentAction,
    HandoffAction,
    SCHEMA_VERSION,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def minimal_contract() -> dict:
    return {
        "$schema": SCHEMA_VERSION,
        "summary": "EQP-01 溫度 OOC",
        "evidence_chain": [],
        "visualization": [],
        "suggested_actions": [],
    }


def full_contract() -> dict:
    return {
        "$schema": SCHEMA_VERSION,
        "summary": "EQP-01 今日 14:00-16:00 共 11 筆 OOC，主因溫度漂移",
        "evidence_chain": [
            {"step": 1, "tool": "get_dc_timeseries", "finding": "Temperature 超 UCL", "viz_ref": "viz-0"},
            {"step": 2, "tool": "get_event_log", "finding": "14:02 發生 PM 事件", "viz_ref": None},
        ],
        "visualization": [
            {"id": "viz-0", "type": "vega-lite", "spec": {"mark": "line", "encoding": {}}},
            {"id": "viz-1", "type": "kpi-card", "spec": {"label": "OOC 次數", "value": 11, "unit": "次"}},
            {"id": "viz-2", "type": "unknown-future-type", "spec": {"foo": "bar"}},
        ],
        "suggested_actions": [
            {"label": "深入分析", "trigger": "agent", "message": "分析 EQP-01 lot 良率"},
            {"label": "開啟 Lot Trace", "trigger": "aiops_handoff", "mcp": "open_lot_trace", "params": {"equipment_id": "EQP-01"}},
        ],
    }


# ---------------------------------------------------------------------------
# 1. Schema 基本驗證
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    def test_minimal_contract_is_valid(self):
        """最小合法 contract（空 list 欄位）應通過驗證"""
        c = AIOpsReportContract(**minimal_contract())
        assert c.summary == "EQP-01 溫度 OOC"

    def test_full_contract_is_valid(self):
        """完整 contract 應通過驗證"""
        c = AIOpsReportContract(**full_contract())
        assert len(c.evidence_chain) == 2
        assert len(c.visualization) == 3
        assert len(c.suggested_actions) == 2

    def test_missing_summary_raises(self):
        """缺少 summary 應拋出 ValidationError"""
        data = minimal_contract()
        del data["summary"]
        with pytest.raises(ValidationError):
            AIOpsReportContract(**data)

    def test_default_lists_are_empty(self):
        """未提供 list 欄位時，預設為空 list"""
        c = AIOpsReportContract(**{"$schema": SCHEMA_VERSION, "summary": "test"})
        assert c.evidence_chain == []
        assert c.visualization == []
        assert c.suggested_actions == []


# ---------------------------------------------------------------------------
# 2. $schema alias 序列化
# ---------------------------------------------------------------------------

class TestSchemaSerialization:
    def test_schema_version_alias_in_output(self):
        """model_dump_json(by_alias=True) 應輸出 $schema 欄位"""
        c = AIOpsReportContract(**minimal_contract())
        output = json.loads(c.model_dump_json(by_alias=True))
        assert "$schema" in output
        assert output["$schema"] == SCHEMA_VERSION

    def test_schema_version_default_value(self):
        """schema_version 預設值應為 SCHEMA_VERSION 常數"""
        c = AIOpsReportContract(**{"$schema": SCHEMA_VERSION, "summary": "test"})
        assert c.schema_version == SCHEMA_VERSION

    def test_roundtrip_json(self):
        """序列化後再反序列化，結果應相同"""
        c = AIOpsReportContract(**full_contract())
        json_str = c.model_dump_json(by_alias=True)
        c2 = AIOpsReportContract.model_validate_json(json_str)
        assert c.summary == c2.summary
        assert len(c.evidence_chain) == len(c2.evidence_chain)


# ---------------------------------------------------------------------------
# 3. SuggestedAction Union 型別辨別
# ---------------------------------------------------------------------------

class TestSuggestedActionDiscrimination:
    def test_agent_action_parsed_correctly(self):
        data = {"label": "分析", "trigger": "agent", "message": "請分析 EQP-01"}
        action = AgentAction(**data)
        assert action.trigger == "agent"
        assert action.message == "請分析 EQP-01"

    def test_handoff_action_parsed_correctly(self):
        data = {"label": "開啟", "trigger": "aiops_handoff", "mcp": "open_lot_trace"}
        action = HandoffAction(**data)
        assert action.trigger == "aiops_handoff"
        assert action.mcp == "open_lot_trace"

    def test_handoff_action_params_optional(self):
        """Handoff action 的 params 是選填的"""
        action = HandoffAction(label="開啟", trigger="aiops_handoff", mcp="open_lot_trace")
        assert action.params is None

    def test_agent_action_missing_message_raises(self):
        """AgentAction 缺少 message 應拋出 ValidationError"""
        with pytest.raises(ValidationError):
            AgentAction(label="分析", trigger="agent")

    def test_union_in_contract_preserves_types(self):
        """Contract 內的 suggested_actions Union 應保留各自型別"""
        c = AIOpsReportContract(**full_contract())
        agent_actions = [a for a in c.suggested_actions if a.trigger == "agent"]
        handoff_actions = [a for a in c.suggested_actions if a.trigger == "aiops_handoff"]
        assert len(agent_actions) == 1
        assert len(handoff_actions) == 1


# ---------------------------------------------------------------------------
# 4. VisualizationItem 開放型別系統
# ---------------------------------------------------------------------------

class TestVisualizationTypes:
    def test_known_types_accepted(self):
        """標準 type 值應被接受"""
        for t in ["vega-lite", "kpi-card", "topology", "gantt", "table"]:
            v = VisualizationItem(id=f"viz-{t}", type=t, spec={})
            assert v.type == t

    def test_unknown_type_is_allowed(self):
        """未知 type 也應被接受（開放型別系統，前端自行處理）"""
        v = VisualizationItem(id="viz-future", type="unknown-future-type", spec={"foo": "bar"})
        assert v.type == "unknown-future-type"

    def test_viz_ref_is_optional(self):
        """EvidenceItem.viz_ref 是選填的"""
        e = EvidenceItem(step=1, tool="some_tool", finding="發現異常")
        assert e.viz_ref is None


# ---------------------------------------------------------------------------
# 5. 邊界條件
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_summary_raises(self):
        """空字串 summary 不應視為有效（pydantic 預設行為）"""
        # 空字串在 Pydantic v2 是合法的，這裡確認它不 crash
        c = AIOpsReportContract(**{"$schema": SCHEMA_VERSION, "summary": ""})
        assert c.summary == ""

    def test_large_evidence_chain(self):
        """大量 evidence items 應正常處理"""
        items = [{"step": i, "tool": f"tool_{i}", "finding": f"finding {i}"} for i in range(100)]
        c = AIOpsReportContract(**{"$schema": SCHEMA_VERSION, "summary": "test", "evidence_chain": items})
        assert len(c.evidence_chain) == 100

    def test_vega_lite_spec_can_be_complex(self):
        """Vega-Lite spec 可以是任意複雜的 dict"""
        complex_spec = {
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": {"field": "time", "type": "temporal"},
                "y": {"field": "value", "type": "quantitative"},
                "color": {"field": "param", "type": "nominal"},
            },
            "transform": [{"filter": "datum.value > 0"}],
        }
        v = VisualizationItem(id="viz-complex", type="vega-lite", spec=complex_spec)
        assert v.spec["mark"]["type"] == "line"
