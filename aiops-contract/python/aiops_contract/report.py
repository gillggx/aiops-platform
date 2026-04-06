"""
AIOps Report Contract — Pydantic Schema Definitions

共同語言：Agent 與 AIOps 之間的溝通標準。
"""

from __future__ import annotations

from typing import Dict, Any, List, Literal, Optional, Union
from pydantic import BaseModel, Field


SCHEMA_VERSION = "aiops-report/v1"


# ---------------------------------------------------------------------------
# Evidence Chain
# ---------------------------------------------------------------------------

class EvidenceItem(BaseModel):
    """單一工具執行結果對應的證據條目。"""

    step: int = Field(..., description="執行順序（從 1 開始）")
    tool: str = Field(..., description="mcp_name 或 skill_id")
    finding: str = Field(..., description="一句話結論，給人類閱讀")
    viz_ref: Optional[str] = Field(
        None, description="對應 visualization[].id，可 null"
    )


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

class VisualizationItem(BaseModel):
    """單一視覺化區塊，type 決定前端使用哪個 renderer。"""

    id: str = Field(..., description="唯一識別，供 evidence_chain.viz_ref 引用")
    type: str = Field(
        ...,
        description=(
            "renderer 類型。"
            "標準值：vega-lite | kpi-card | topology | gantt | table。"
            "未知 type 前端顯示 unsupported placeholder。"
        ),
    )
    spec: Dict[str, Any] = Field(
        ...,
        description="對應 type 的 spec。vega-lite 使用標準 Vega-Lite JSON spec。",
    )


# ---------------------------------------------------------------------------
# Suggested Actions
# ---------------------------------------------------------------------------

class AgentAction(BaseModel):
    """重新觸發 Agent 的動作。"""

    label: str
    trigger: Literal["agent"]
    message: str = Field(..., description="帶入 Agent 的 next message")


class HandoffAction(BaseModel):
    """移交給 AIOps 處理的動作，AIOps 接管後續 UI 互動。"""

    label: str
    trigger: Literal["aiops_handoff"]
    mcp: str = Field(..., description="AIOps Handoff MCP name")
    params: Optional[Dict[str, Any]] = None


SuggestedAction = Union[AgentAction, HandoffAction]


# ---------------------------------------------------------------------------
# Root Contract
# ---------------------------------------------------------------------------

class AIOpsReportContract(BaseModel):
    """
    AIOps Report Contract v1

    Agent 輸出的標準化結果，任何實作此 Contract 的前端皆可渲染。
    """

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        alias="$schema",
        description="Contract 版本識別",
    )
    summary: str = Field(..., description="給人類閱讀的根因結論或回應摘要")
    evidence_chain: List[EvidenceItem] = Field(
        default_factory=list,
        description="推理過程中每個工具呼叫的關鍵發現",
    )
    visualization: List[VisualizationItem] = Field(
        default_factory=list,
        description="視覺化區塊列表",
    )
    suggested_actions: List[SuggestedAction] = Field(
        default_factory=list,
        description="建議的後續動作，前端渲染為可點擊按鈕",
    )

    model_config = {"populate_by_name": True}
