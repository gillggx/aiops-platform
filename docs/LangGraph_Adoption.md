# Spec: Phase 2 — LangGraph 全面遷移 + LangSmith 觀測

**Status**: Approved, in progress
**Owner**: Agent platform refactor
**Target completion**: ~8 working days

---

## 1. Context & Objective

### 1.1 現狀問題

1. `agent_orchestrator.py` 1900+ 行手寫 state machine，每加一個功能（HITL, self-critique, chart rendered, memory lifecycle）都要打補丁
2. Debug 只能靠 stdout log + grep，跨 session 追蹤靠 session_id 人肉關聯
3. `AgentOrchestrator` 同時承擔：while loop、SSE events、HITL gating、soft/hard compaction、programmatic distillation、contract resolution、hallucination detection、memory lifecycle scheduling、self-critique — 單一類別責任過重
4. 多 LLM provider（Anthropic / OpenRouter / Ollama）的 tool calling normalize 散在 `app/utils/llm_client.py`；LangGraph 有現成 adapter 生態

### 1.2 為什麼現在做

- **Phase 0** 已把 DB 切到 Postgres（LangGraph checkpointer 前置條件）
- **Phase 1** 已建 pgvector（LangGraph Store 同一底層）
- Agent behavior 現在穩定，有 baseline 可對照
- 每次加 feature 的邊際成本持續上升，到了該重構的點

### 1.3 目標

- **功能等價**：使用者行為、SSE event 格式、前端依賴的所有 render_card types 保持不變
- **後端重構**：orchestrator loop → LangGraph StateGraph；HITL → `interrupt()`；observability → LangSmith
- **可回滾**：每個 sub-phase 都能切 feature flag 回舊版
- **不追求 LangGraph 化為目的**：任何路徑只要 LangGraph 做得比手寫更麻煩就保留手寫版

### 1.4 不做的事

- 不遷移 `ExperienceMemoryService`（Phase 1 自己做的，比 LangGraph Store 更精準）
- 不遷移 Diagnostic Rule 的 Phase 2a/2b 生成流程（獨立 LLM pipeline）
- 不遷移 Auto-Patrol execution（走 Skill Executor，跟 agent chat 不同路徑）
- 不動 Next.js frontend 一行（靠 event adapter 保持 SSE 相容）
- 不用 LangGraph `@tool` decorator 重寫 ToolDispatcher（內部 custom logic 太多）

---

## 2. Architecture Overview

### 2.1 Sub-Phase 拆解

```
┌─────────────────────────────────────────────────────────┐
│ Phase 2-A:  LangSmith only (0.5 day)                     │
│   - 加 langsmith/langchain-core 套件                      │
│   - LLM client 加 @traceable callback                    │
│   - 零行為改變                                            │
│   🔁 回滾：unset LANGSMITH_API_KEY                        │
├─────────────────────────────────────────────────────────┤
│ Phase 2-B:  v2 orchestrator 並存 (3-4 工作天)             │
│   - 建 agent_orchestrator_v2/ (LangGraph StateGraph)      │
│   - Feature flag AGENT_ORCHESTRATOR_VERSION=v1|v2         │
│   - Event adapter 層                                      │
│   - Happy path + tool calling only                        │
│   🔁 回滾：flag → v1                                      │
├─────────────────────────────────────────────────────────┤
│ Phase 2-C:  特殊路徑 + 最終切換 (2-3 工作天)              │
│   - HITL approval → interrupt()                           │
│   - Self-critique, hallucination detection → nodes        │
│   - Memory lifecycle → graph node                         │
│   - Golden test + 完整 QA → flag 預設 v2                  │
│   - 觀察 1 週 → 刪 v1                                     │
│   🔁 回滾：flag → v1                                      │
└─────────────────────────────────────────────────────────┘
```

### 2.2 目標架構（Phase 2-C 完成後）

```
POST /api/v1/agent/chat/stream
        │
        ▼
┌─────────────────────────────┐
│  agent_chat_router.py        │
│  (minimal — SSE wrap only)   │
└─────────────┬────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────┐
│  AgentOrchestratorV2 (LangGraph StateGraph)      │
│                                                   │
│    ┌─────────┐    ┌──────────┐    ┌──────────┐   │
│    │ load_   │ →  │ llm_     │ →  │ tool_    │   │
│    │ context │    │ call     │    │ execute  │   │
│    └─────────┘    └──────────┘    └────┬─────┘   │
│         │              ↑                │         │
│         │              │                ▼         │
│         │         ┌────┴─────┐    ┌──────────┐   │
│         │         │  loop?   │ ←  │ preflight│   │
│         │         └────┬─────┘    └──────────┘   │
│         │              │ no                       │
│         ▼              ▼                           │
│    ┌─────────┐    ┌──────────┐    ┌──────────┐   │
│    │ hitl_   │    │ synthesis│ →  │ self_    │   │
│    │ gate    │    │          │    │ critique │   │
│    └─────────┘    └──────────┘    └────┬─────┘   │
│         ▲                                │         │
│         └──(destructive tool)────────────┤         │
│                                          ▼         │
│                                    ┌──────────┐   │
│                                    │ memory_  │   │
│                                    │ lifecycle│   │
│                                    └────┬─────┘   │
│                                         │         │
│                                         ▼         │
│                                    ┌──────────┐   │
│                                    │  done    │   │
│                                    └──────────┘   │
│                                                   │
│  Checkpointer: PostgresSaver (aiops DB)           │
│  Interrupts:   hitl_gate(destructive_tool=True)   │
│  Streaming:    .astream_events() → event_adapter  │
└───────────────────────────────────────────────────┘
                         │
                         ▼
              ┌────────────────────┐
              │ SSE Event Adapter  │
              │  langgraph events  │
              │      ↓             │
              │  v1 custom events  │
              │  (前端相容)         │
              └────────────────────┘
```

### 2.3 State Definition

```python
from typing import TypedDict, Annotated, List, Dict, Any, Optional
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Input
    user_id: int
    session_id: Optional[str]
    user_message: str

    # Conversation
    messages: Annotated[List[Dict[str, Any]], add_messages]

    # Context (built by load_context node)
    system_prompt_blocks: List[Dict[str, Any]]
    retrieved_memory_ids: List[int]
    history_turns: int

    # Tool execution tracking
    tools_used: List[Dict[str, Any]]       # [{tool, mcp_name, params, result_text}]
    current_iteration: int

    # Flags (from current code — now centralized)
    chart_already_rendered: bool
    last_spc_result: Optional[tuple]
    force_synthesis: bool
    plan_extracted: bool

    # Outputs
    final_text: str
    contract: Optional[Dict[str, Any]]
    reflection_result: Optional[Dict[str, Any]]

    # HITL
    pending_approval_token: Optional[str]
    pending_approval_tool: Optional[Dict[str, Any]]
```

**Rationale**: single source of truth — nodes read from / write to state. Eliminates scattered instance variables (`_last_spc_result`, `_chart_already_rendered`, `_retrieved_memory_ids`, etc.) from v1.

### 2.4 Nodes 清單

| Node | 取代的舊代碼 | 輸入 state | 輸出 state 更新 |
|---|---|---|---|
| `load_context` | `ContextLoader.build()` + `_load_session` | user_message, user_id | system_prompt_blocks, messages, retrieved_memory_ids |
| `llm_call` | `while iter < MAX: self._llm.create(...)` | messages, system | 新增 assistant message |
| `preflight_validate` | `_preflight_validate` | tool_calls | 若錯誤 → tool_results with error |
| `hitl_gate` | `_DESTRUCTIVE_TOOLS` + manual wait | tool_calls | **interrupt()** — 等使用者 approve |
| `tool_execute` | `dispatcher.execute` + `_distill_svc` | tool_calls | tools_used, tool_results |
| `check_chart_rendered` | `_notify_chart_rendered` flag set | tool_results | chart_already_rendered |
| `synthesis` | force synthesis LLM call | messages, tools_used | final_text, contract |
| `self_critique` | `_run_reflection` + `_detect_id_hallucinations` | final_text, tools_used | reflection_result |
| `memory_lifecycle` | `_run_memory_lifecycle_background` | tools_used, final_text | (side effect: Phase 1 store write) |
| `done` | 流程結束 | all | — |

### 2.5 Conditional Edges

```python
graph.add_conditional_edges(
    "llm_call",
    lambda state: (
        "hitl_gate" if _has_destructive_tool_calls(state)
        else "tool_execute" if _has_tool_calls(state)
        else "synthesis"
    ),
    {
        "hitl_gate": "hitl_gate",
        "tool_execute": "tool_execute",
        "synthesis": "synthesis",
    },
)

graph.add_conditional_edges(
    "tool_execute",
    lambda state: (
        "synthesis" if state["force_synthesis"] or state["current_iteration"] >= MAX_ITERATIONS
        else "llm_call"
    ),
    {"synthesis": "synthesis", "llm_call": "llm_call"},
)
```

---

## 3. Phase 2-A: LangSmith Only

**目標**：2 小時內搞定，零行為改變，立即拿到 tracing。

### 3.1 改動範圍

| # | 檔案 | 動作 |
|---|---|---|
| A1 | `requirements.txt` | 加 `langsmith>=0.1.0`, `langchain-core>=0.3.0` |
| A2 | `.env.example` | 加 `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT=aiops-agent`, `LANGCHAIN_TRACING_V2=true` |
| A3 | `app/utils/llm_client.py` | `AnthropicLLMClient.create()` 加 `@traceable`；`OllamaLLMClient.create()` 同樣 |
| A4 | `app/services/agent_orchestrator.py` | `AgentOrchestrator.run()` 加 `@traceable(name="agent_run", metadata={"session_id": ...})` |

### 3.2 實作細節

```python
# llm_client.py
from langsmith import traceable

class AnthropicLLMClient(BaseLLMClient):
    @traceable(run_type="llm", name="anthropic_create")
    async def create(self, *, system, messages, max_tokens, tools=None):
        ...

class OllamaLLMClient(BaseLLMClient):
    @traceable(run_type="llm", name="ollama_create")
    async def create(self, ...):
        ...
```

```python
# agent_orchestrator.py
from langsmith import traceable

class AgentOrchestrator:
    @traceable(run_type="chain", name="agent_chat_turn")
    async def _run_impl(self, message, session_id):
        ...
```

### 3.3 環境設定

```bash
# .env
LANGCHAIN_TRACING_V2=true
LANGSMITH_API_KEY=lsv2_...
LANGSMITH_PROJECT=aiops-agent
```

LangSmith 免費層 5k runs/month，dev 夠用。

### 3.4 驗證

- 發一個 agent chat request
- `https://smith.langchain.com/o/<org>/projects/p/aiops-agent` 看到 run
- 能展開每個 LLM call，看到 input/output/latency/tokens

### 3.5 Rollback

```bash
unset LANGSMITH_API_KEY
# tracing 安靜關掉，其他一切不變
```

---

## 4. Phase 2-B: v2 Orchestrator 並存

**目標**：3-4 工作天，LangGraph-based v2 建立，feature flag 切換，happy path 通過。

### 4.1 Dependencies

```
langgraph>=0.2.0
langgraph-checkpoint-postgres>=2.0.0
```

### 4.2 新檔案

```
fastapi_backend_service/app/services/
├── agent_orchestrator.py              (舊 v1，保留)
├── agent_orchestrator_v2/              (新)
│   ├── __init__.py                    # export AgentOrchestratorV2
│   ├── state.py                       # AgentState TypedDict
│   ├── graph.py                       # build_graph() → StateGraph
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── load_context.py           # wraps ContextLoader
│   │   ├── llm_call.py               # wraps existing LLM client
│   │   ├── tool_execute.py           # wraps ToolDispatcher
│   │   ├── synthesis.py
│   │   └── done.py
│   ├── adapter.py                     # langgraph events → v1 SSE events
│   └── orchestrator.py                # AgentOrchestratorV2 thin wrapper
```

### 4.3 Feature Flag

```python
# app/config.py
AGENT_ORCHESTRATOR_VERSION: str = Field(default="v1", description="v1 | v2")
```

```python
# app/routers/agent_chat_router.py
async def chat_stream(...):
    settings = get_settings()
    version = request.headers.get("X-Agent-Version") or settings.AGENT_ORCHESTRATOR_VERSION
    if version == "v2":
        from app.services.agent_orchestrator_v2 import AgentOrchestratorV2
        orch = AgentOrchestratorV2(...)
    else:
        from app.services.agent_orchestrator import AgentOrchestrator
        orch = AgentOrchestrator(...)

    async for event in orch.run(message, session_id):
        yield format_sse(event)
```

HTTP header `X-Agent-Version: v2` 覆蓋 env var，方便測試單次請求。

### 4.4 Event Adapter

LangGraph `astream_events(version="v2")` 產生 `{event, name, data, ...}`。Adapter 把這些轉成 v1 格式：

| LangGraph event | v1 SSE type | 備註 |
|---|---|---|
| `on_chain_start` (load_context) | `stage_update` | stage=1 |
| `on_chain_end` (load_context) | `context_load` | system_prompt_preview, rag_hits |
| `on_chat_model_start` | `stage_update` | stage=2 or 3 |
| `on_chat_model_end` | `llm_usage` | input_tokens, output_tokens |
| `on_tool_start` | `tool_start` | tool, input |
| `on_tool_end` | `tool_done` | result_summary, render_card |
| `on_chain_start` (synthesis) | `stage_update` | stage=4 |
| `on_chain_end` (synthesis) | `synthesis` | text, contract |
| `on_chain_start` (self_critique) | `reflection_running` | — |
| `on_chain_end` (self_critique) | `reflection_pass` / `reflection_amendment` | — |
| `interrupt` | `approval_required` | approval_token, tool, input |
| final | `done` | session_id |

**Custom events**（在 node 內用 `adispatch_custom_event`）：
- `chart_rendered` — 替代 `_notify_chart_rendered`
- `approval_required` — HITL gate 觸發
- `memory_retrieved` — RAG hit 通知

### 4.5 Happy Path 範圍

Phase 2-B 只處理：
- ✅ load context → LLM → tool call → LLM → ... → synthesis → done
- ✅ 單次/多次 tool 呼叫
- ✅ 錯誤處理（LLM call 失敗、tool execution 失敗）
- ✅ SSE event 格式對齊 v1
- ✅ Postgres checkpointer

**不處理**（留給 Phase 2-C）：
- ❌ HITL approval gate
- ❌ Self-critique / hallucination detection
- ❌ Memory lifecycle background task
- ❌ Soft/hard compaction
- ❌ Force synthesis on error

**Phase 2-B 期間 flag 不切預設**，只有開發者手動切 `X-Agent-Version: v2` 測試。

### 4.6 Checkpointer 設定

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def build_checkpointer():
    conn_string = settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql://"
    )
    saver = AsyncPostgresSaver.from_conn_string(conn_string)
    await saver.setup()  # creates langgraph schema tables
    return saver
```

LangGraph 建自己的表（`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`）— 跟我們現有 schema 正交，不衝突。

### 4.7 LangChain Runnable adapter for 現有 LLM client

**問題**：LangGraph 期望 `ChatModel.ainvoke(messages)`。現有 `BaseLLMClient.create(system, messages, tools, max_tokens)` 不同。

**方案**：`RunnableLambda` wrapper：

```python
# app/services/agent_orchestrator_v2/llm_wrapper.py
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import AIMessage

def wrap_legacy_llm(client: BaseLLMClient) -> Runnable:
    async def _ainvoke(input_dict):
        system = _extract_system(input_dict["messages"])
        messages = _convert_to_legacy_format(input_dict["messages"])
        tools = input_dict.get("tools")

        response = await client.create(
            system=system,
            messages=messages,
            tools=tools,
            max_tokens=input_dict.get("max_tokens", 8192),
        )
        return _response_to_aimessage(response)

    return RunnableLambda(_ainvoke)
```

**好處**：
- 現有 multi-provider 邏輯 100% 保留（XML tool call parsing, `<think>` stripping, Qwen3 quirks）
- LangSmith 還是能 trace（RunnableLambda 也會被 trace）
- LangChain tool_calls schema 對接（我們轉成 AIMessage 格式）

### 4.8 Phase 2-B DoD（Definition of Done）

| 測試 | v1 | v2 | 標準 |
|---|---|---|---|
| 「列出目前可用的 Skills」 | ✓ | ✓ | 回答正確，1 次 LLM call |
| 「統計 EQP-02 今天表現」 | ✓ | ✓ | list_recent_events(since=24h) → execute_jit → synthesis |
| 「看 STEP_022 的 p_chart」 | ✓ | ✓ | execute_skill(id=8) → chart_intents rendered |
| SSE events 序列 | ✓ | ✓ | 事件順序一致、內容近似（tokens 可不同） |
| 前端 copilot 正常顯示 | ✓ | ✓ | **不改前端** |
| LangSmith trace 完整 | — | ✓ | 每個 node 都有 trace |
| Postgres checkpoint 寫入 | — | ✓ | `SELECT COUNT(*) FROM checkpoints > 0` |

---

## 5. Phase 2-C: 特殊路徑 + 最終切換

**目標**：2-3 工作天，剩下的特殊路徑遷移到 graph，切 flag 到 v2，觀察 1 週後刪 v1。

### 5.1 HITL Approval Gate

LangGraph 原生 `interrupt()`：

```python
# nodes/hitl_gate.py
from langgraph.types import interrupt

async def hitl_gate_node(state: AgentState) -> AgentState:
    tool_call = state["pending_approval_tool"]

    # interrupt() 會暫停 graph、把 state 存到 checkpointer、等 resume
    approval = interrupt({
        "type": "approval_required",
        "tool": tool_call["name"],
        "input": tool_call["input"],
        "message": f"⚠️ 工具「{tool_call['name']}」需要您的批准。",
    })

    if approval.get("approved"):
        return {"pending_approval_tool": None}
    else:
        return {
            "pending_approval_tool": None,
            "tool_results": [{
                "tool_use_id": tool_call["id"],
                "error": "APPROVAL_REJECTED",
            }],
            "force_synthesis": True,
        }
```

前端 approve API 改成 resume graph：

```python
# routers/agent_router.py
@router.post("/approve/{token}")
async def approve(token: str, approved: bool):
    thread_id = approval_token_to_thread_id(token)
    config = {"configurable": {"thread_id": thread_id}}

    async for chunk in graph.astream(
        Command(resume={"approved": approved}),
        config=config,
    ):
        pass
    return {"status": "resumed"}
```

### 5.2 Self-Critique Node

```python
# nodes/self_critique.py
async def self_critique_node(state: AgentState) -> AgentState:
    # 1. ID hallucination check (deterministic, no LLM)
    hallucinated = _detect_id_hallucinations(
        state["final_text"],
        state["tools_used"],
    )
    if hallucinated:
        return {"reflection_result": {...}}

    # 2. LLM-based value check
    result = await _run_llm_reflection(state["final_text"], state["tools_used"])
    return {"reflection_result": result}
```

### 5.3 Memory Lifecycle Node

```python
# nodes/memory_lifecycle.py
async def memory_lifecycle_node(state: AgentState) -> AgentState:
    # 不再 asyncio.create_task —— 作為明確 graph node
    # LangGraph checkpointer 捕獲執行，失敗能重試

    cited_ids = _extract_memory_citations(state["final_text"])
    feedback_ids = cited_ids or state["retrieved_memory_ids"]

    async with AsyncSessionLocal() as db:
        svc = ExperienceMemoryService(db)
        for mem_id in feedback_ids:
            await svc.record_feedback(mem_id, "success")

        abstraction = await abstract_memory(
            llm_client=get_llm_client(),
            user_query=state["user_message"],
            agent_final_text=state["final_text"],
            tool_chain=state["tools_used"],
        )
        if abstraction:
            await svc.write(
                user_id=state["user_id"],
                intent_summary=abstraction["intent_summary"],
                abstract_action=abstraction["abstract_action"],
                source="auto",
                source_session_id=state["session_id"],
            )

    return {}
```

### 5.4 Compaction

保留現有 `_soft_compact` / `_hard_compact` helper，從 `llm_call` node 裡呼叫。LangGraph 有 `RemoveMessage` 機制但現有邏輯比較客製，換過去得不償失。

### 5.5 完整 QA（v2 全功能）

| # | 測試 | 驗證點 |
|---|---|---|
| 1 | Phase 0 的 9 題 QA 全跑（login, skills, MCPs, auto-patrols, SPC skill, agent chat...） | 全部通過 |
| 2 | HITL: draft_skill → approval_required → approve → 執行 | Flow 完整 |
| 3 | HITL: draft_skill → reject → 不執行 | 正確終止 |
| 4 | Self-critique: 產生含 LOT-9999（不存在）的答案 | 被偵測、amended_text 正確 |
| 5 | Memory lifecycle: 成功 chat 後 | `agent_experience_memory` 有新 row / 或正確 dedup |
| 6 | Memory lifecycle: 記憶被引用 | `use_count`, `success_count` 正確遞增 |
| 7 | Chart intents: SPC skill 產出 | 前端正確渲染 |
| 8 | Checkpoint: 中斷 → resume | 正確保存 |
| 9 | LangSmith: 每個 node 有 trace | UI 可見 |
| 10 | 回歸: 「EQP-02 有問題的 SPC chart」 | 不再出現之前 5 個 bug |

### 5.6 切換策略

**T=0**：Phase 2-C 完成，flag `AGENT_ORCHESTRATOR_VERSION=v2`（預設改）

**T+1 週**：
- 如果沒問題 → 刪除 `agent_orchestrator.py`、移除 feature flag、清理相關測試
- 如果有問題 → 立即 `export AGENT_ORCHESTRATOR_VERSION=v1`，開 issue debug

**T+2 週**：
- 刪除 v1 所有程式碼（包含 `_run_reflection`, `_preflight_validate` 等 standalone helpers 如果 v2 已經包含）
- 更新 README / docs

---

## 6. Golden Test Strategy（關鍵緩解）

為了確保 v2 跟 v1 行為等價：

```
fastapi_backend_service/tests/golden/
├── cases.yaml                    # 測試案例清單
├── captures/
│   ├── v1/
│   │   ├── case_01_list_skills.jsonl       # v1 SSE event 序列
│   │   ├── case_02_stats_today.jsonl
│   │   └── ...
│   └── v2/
│       ├── case_01_list_skills.jsonl       # v2 SSE event 序列
│       └── ...
└── compare.py                    # 比對 v1 vs v2
```

**比對規則**（非精確匹配）：
- ✅ Event type 順序一致
- ✅ 必要欄位相同（tool name, tool_count, final_text 長度近似）
- ❌ 忽略：tokens 數、耗時、具體 LLM 回應文字、session_id

如果 v2 event sequence diverge，立即發現。

---

## 7. Risk Matrix

| 風險 | 概率 | 影響 | 緩解 |
|---|---|---|---|
| LangGraph checkpointer schema 和現有衝突 | 低 | 中 | LangGraph 用自己的 namespace prefix，實測確認 |
| `astream_events` 順序跟 v1 不同 | 中 | 中 | Event adapter 順序對齊 + golden test |
| Ollama/OpenRouter 經 LangChain wrapper 後 tool calling 爆掉 | 中 | 高 | 保留 `OllamaLLMClient`，用 `RunnableLambda` 包成 LangChain 介面而非重寫 |
| Phase 2-C interrupt() 跟前端 approve flow 對不起來 | 中 | 高 | Phase 2-B 結束前做 HITL spike（1 天）驗證 |
| LangSmith 免費額度不夠 | 低 | 低 | sampling 10% traffic；付費 $39/月不貴 |
| v1 某個 render_card type v2 沒覆蓋 | 中 | 中 | 列 render_card type 清單，每個都有對應 node 輸出 |
| 遷移期間引入 bug 影響生產 | 中 | 中 | Feature flag 預設 v1 直到 Phase 2-C 完整 QA 通過 |
| Event adapter 漏 event type | 高 | 中 | Golden test 直接 diff |

---

## 8. Dependencies

```bash
# Phase 2-A
pip install langsmith langchain-core

# Phase 2-B
pip install langgraph langgraph-checkpoint-postgres

# Phase 2-C: 無新套件
```

加入 `requirements.txt`:
```
langsmith>=0.1.0
langchain-core>=0.3.0
langgraph>=0.2.0
langgraph-checkpoint-postgres>=2.0.0
```

---

## 9. Timeline 預估

| Sub-phase | 工作內容 | 預估 |
|---|---|---|
| **2-A** | LangSmith tracing | **0.5 天** (2-3h 實作 + 測試) |
| **2-B.1** | 套件安裝 + state/graph skeleton | 0.5 天 |
| **2-B.2** | load_context + llm_call node | 0.5 天 |
| **2-B.3** | tool_execute node (ToolDispatcher 接入) | 0.5 天 |
| **2-B.4** | synthesis node + contract 處理 | 0.5 天 |
| **2-B.5** | Event adapter 層 | 1 天 |
| **2-B.6** | Feature flag + router wiring + happy path QA | 0.5 天 |
| **2-C.1** | HITL via interrupt() + approve router | 1 天 |
| **2-C.2** | Self-critique + hallucination node | 0.5 天 |
| **2-C.3** | Memory lifecycle node | 0.5 天 |
| **2-C.4** | Golden test harness + 完整 QA | 1 天 |
| **2-C.5** | 切 flag + 觀察 | 0 天 |
| **2-C.6** (+1 週後) | 刪 v1 cleanup | 0.5 天 |
| **總計** | | **~8 工作天** |

---

## 10. Success Criteria

Phase 2 完成時應達到：

1. ✅ **功能等價**：前端一行不改、SSE 格式一致、所有 render_card types 都有
2. ✅ **LangSmith trace 可見**：每個 agent run 在 UI 完整展開
3. ✅ **Postgres checkpoint 可用**：interrupt/resume 靠 LangGraph 內建機制
4. ✅ **`agent_orchestrator.py` 從 1900 行砍到 < 200 行**（剩 v2 thin wrapper）
5. ✅ **QA**：Phase 0 的 9 題 + Phase 1 記憶測試 + Phase 2 新加的 10 題全通過
6. ✅ **可回滾**：至少 1 週內 flag 切回 v1 還能 work

---

## Appendix A: 對應現有功能的逐項處理

| 功能 | 現有位置 | 新位置 | 處理方式 |
|---|---|---|---|
| Soul + user pref + RAG memory 注入 | `ContextLoader.build` | `nodes/load_context.py` | 直接呼叫現有 service |
| Skill catalog + MCP catalog 注入 | `ContextLoader._load_*` | 同上 | 不動 |
| Experience memory retrieve + `[memory:X]` guard | `ContextLoader` Phase 1 code | 同上 | 不動 |
| Task context extractor | `extract_task_context` | pre-node 步驟 | 不動 |
| Multi-provider LLM | `BaseLLMClient` + subclasses | 包 Runnable adapter | 關鍵（見 §4.7） |
| Tool preflight validation | `_preflight_validate` | `tool_execute` node 內 | 邏輯不動 |
| HITL destructive tool gate | `_DESTRUCTIVE_TOOLS` + wait | `hitl_gate` node + `interrupt()` | 換 API |
| Pre/post tool render_card build | `_build_render_card` | `tool_execute` post-process | 不動 |
| Chart rendered notification | `_notify_chart_rendered` | `tool_execute` post-process | 不動 |
| Auto-contract SPC fallback | `_build_spc_contract` | synthesis node 呼叫 | 不動 |
| Data distillation | `DataDistillationService` | `tool_execute` 內呼叫 | 不動 |
| Self-critique (LLM) | `_run_reflection` | `self_critique` node | 邏輯不動 |
| ID hallucination detection | `_detect_id_hallucinations` | `self_critique` node | 邏輯不動 |
| Memory lifecycle | `_run_memory_lifecycle_background` | `memory_lifecycle` node | 改 graph node |
| Token compaction | `_hard_compact` / `_soft_compact` | `llm_call` pre-hook | 保留 |
| Session 管理 | `_load_session` + `agent_sessions` table | LangGraph PostgresSaver | **換 LangGraph 原生** |
| Canvas overrides | param → context_loader | 同上 | 不動 |
| Auto-JIT-persistence | `_maybe_persist_tool` | `tool_execute` post-hook | 不動 |
| Trap rule derivation | `_derive_fix_rule` | `tool_execute` error handler | 不動 |

---

## Appendix B: LangGraph 原生取代的東西

| 舊 | 新 |
|---|---|
| 自己寫 while loop + iteration counter | LangGraph 自動管 iteration state |
| `asyncio.create_task` fire-and-forget memory write | 獨立 `memory_lifecycle` node |
| 自己管 session 狀態 (`agent_sessions` table) | LangGraph PostgresSaver checkpointer |
| 自己處理 HITL timeout / approval_token | LangGraph `interrupt()` + `Command.resume()` |
| 自己 yield SSE events | `astream_events(v2)` + event adapter |
</content>
