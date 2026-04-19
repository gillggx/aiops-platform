# SPEC — Pipeline Builder Phase 3: Agent Glass Box

**Status:** Draft — 待使用者授權後實作
**Version:** v0.2（跳過 batch MVP，直接做 SSE streaming；batch 保留為 fallback）
**Date:** 2026-04-18

## 0. v0.2 Revision 決策

使用者回饋「先試 SSE streaming，真的不行再 fallback batch」。接受。

**變更：**
- 原 Phase 3.1（batch replay）**降級為 fallback 設計**（§14 Appendix）— 若 streaming 實作遇到硬傷才退回來
- 原 Phase 3.2（SSE streaming）**升為 MVP**
- 原 Phase 3.3（HITL）**照常延後**
- 時間預估：原 5–7 days + 2–3 days → 合併為 **~7–8 days**（不比 batch-only 多太多，因 Anthropic SDK 本身 support streaming，部分邏輯可共用）

**Risk acceptance：** 有 ~20% 機率實作中撞到 streaming 邊緣問題（SSE 斷線、tool call 中途失敗、async generator cancellation 語意）。若碰到，同一份 backend 邏輯可 serve batch endpoint 做為 graceful degradation。

---
**Prerequisites:**
- ✅ Phase 1 PoC（DAG executor + 5 積木）
- ✅ Phase 2 MVP UI（11 積木、context-aware Inspector、per-node cache）
- ✅ v1.1–v1.3 polish（Schema annotation、ghost drag、chart render、row limit）
- ⏳ 本 spec 待 review 並回答 §10 決策後啟動

**Relates to:**
- `SPEC_pipeline_builder.md` §6（Agent-as-User 原始設計）
- `SPEC_pipeline_builder_phase2.md` §11（Phase 2 MVP）

---

## 1. Context & Objective

### 1.1 回顧

Phase 1+2 完成後，人類 PE 可以：
- 拖積木到畫布
- 連線 + 設參數
- 跑 Preview、看結果、調整
- Save → Deploy

Phase 3 的目標：**把上面每一個動作，變成 Agent 可以呼叫的 Tool API**。Agent 不直接生 Pipeline JSON，也不寫 Python code — 它像 Claude Code 使用 Edit/Bash 一樣，呼叫 `builder.add_node` / `builder.connect` / `builder.preview` / `builder.set_param`，**一步步組裝出完整 pipeline**。

### 1.2 核心價值（Glass Box）

| 對照 | Black Box | **Glass Box（Phase 3）** |
|---|---|---|
| Agent 輸出 | 最終 Pipeline JSON 一次給出 | **每步操作可見**，PE 邊看邊學 |
| 信任建立 | PE 要接受「整包 AI 決策」 | 每步 PE 都能暫停、接手、否決 |
| 教育效果 | 無 | PE 看久了會學會怎麼組 |
| 失敗可查 | 整個 pipeline 報錯 | **出錯在第幾步、為什麼一清二楚** |
| 與 UI 一致性 | UI 只是渲染結果 | **Agent 跟人操作同一個 UI** — 單一 mental model |

### 1.3 非目標（Phase 3 不做）

- ❌ 不做 multi-turn 複雜推理（Agent 僅「根據 user 需求組 pipeline」一次性任務）
- ❌ 不做 RL / self-improvement
- ❌ 不整合 LangGraph Phase 2-C（HITL / memory lifecycle）— 那是 orchestrator 架構升級
- ❌ 不取代 Copilot（Copilot 仍負責 Q&A + 臨時分析）
- ❌ 不做 「Agent 自訂新積木」—  積木庫演進由 PE admin 管（見 CLAUDE.md 原則）

### 1.4 成功標準

- [ ] PE 在 Copilot 打「幫我建一個 EQP-01 SPC xbar 連續 3 次 OOC 的告警 rule」
- [ ] Agent 呼叫 5–8 個 builder tools，canvas 上看到節點逐步浮現
- [ ] 組完後的 Pipeline 能 Run 成功
- [ ] PE 可中斷 Agent 接手、或請 Agent 調整
- [ ] 15 個典型 SPC 場景測試（§9 QA），Agent 成功率 ≥ 80%

---

## 2. Architecture

### 2.1 三個選項

| # | 模式 | 描述 | Pros | Cons |
|---|---|---|---|---|
| **A** | **Batch replay（MVP 建議）** | Agent 在後端完整跑完產 operations_log → 一次回傳 → UI 逐步動畫播放 | 簡單、穩定、不需 realtime infra | 不是真正「即時看 Agent 思考」 |
| B | SSE streaming | Agent 每個 tool call 透過 Server-Sent Events 推到 UI → 即時呈現 | 真正 glass box 體感 | 需處理斷線、亂序、取消 |
| C | Shared backend session + WebSocket | 後端維護 session 狀態，UI + Agent 都 WebSocket 雙向讀寫 | 最完整、未來可多人協作 | 工程複雜度高（> 3 人週）|

### 2.2 v0.2 採納：**Phase 3 直接做 SSE streaming**

| Sub-Phase | 範圍 | 時間 |
|---|---|---|
| ~~3.1 Batch~~ | ~~Agent 在 backend 產 op log → UI replay 動畫~~ | **降級 fallback**（§14） |
| **3.2 SSE streaming（MVP）** | Agent 每個 tool call 即時 SSE 推到 UI，PE 可中途 cancel | **7–8 days** |
| 3.3 HITL | `ask_user` 對話整合 Copilot。Agent 不確定時問 PE → PE 回答繼續 | 2 days（後做） |

本 spec 以下內容 **focus on SSE streaming MVP**。

### 2.3 SSE streaming 架構圖

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend: aiops-app                                             │
│                                                                  │
│   Copilot Panel                       Pipeline Builder UI        │
│   ┌────────────────────┐   ┌─────────────────────────────────┐  │
│   │ User:              │   │                                  │  │
│   │  幫我建一個 OOC   │   │  ← node n1 淡入（add_node 事件） │  │
│   │  告警 rule        │   │  ← edge 繪出（connect 事件）     │  │
│   │                   │   │  ← Inspector 更新（set_param）   │  │
│   │ ● Thinking...    │   │  ← node 亮藍框 1.5s（explain）   │  │
│   │   ✓ added n1     │   │                                  │  │
│   │   ✓ connected    │   │  [ Accept / Cancel ]              │  │
│   │   ● Running prev │   │                                  │  │
│   │   [ Cancel ]     │   │                                  │  │
│   └──┬─────────────────┘   └─────────────────────────────────┘  │
│      │ EventSource (SSE)                                         │
│      │ data: {type:"operation", op:"add_node", ...}              │
│      │ data: {type:"chat", content:"..."}                        │
│      │ data: {type:"preview", node_id:"n1", rows:10}             │
│      │ data: {type:"error", op:"connect", message:"..."}         │
│      │ data: {type:"done", status:"finished", pipeline_json:...} │
└──────┼───────────────────────────────────────────────────────────┘
       │
       │  (1) POST /api/v1/agent/build            → returns {session_id}
       │  (2) GET  /api/v1/agent/build/stream/{id} → SSE event stream
       │  (3) POST /api/v1/agent/build/{id}/cancel → user pressed cancel
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backend: fastapi_backend_service                                │
│                                                                  │
│  NEW: app/services/agent_builder/                                │
│  ├─ session.py       AgentBuilderSession + Operation + StreamEvt │
│  ├─ tools.py         BuilderToolset (14 tools)                   │
│  ├─ prompt.py        System prompt from DB catalog               │
│  ├─ orchestrator.py  async generator: yield StreamEvent ...      │
│  └─ registry.py      active-session registry (for cancel)        │
│                                                                  │
│  Stream emits:                                                   │
│    - "chat"       Agent explain() messages                       │
│    - "operation"  each tool call (add_node/connect/set_param/...)│
│    - "error"      tool call failure (Agent retries internally)   │
│    - "done"       final {status, pipeline_json}                  │
└───────────────┬──────────────────────────────────────────────────┘
                │ uses (unchanged)
                ▼
┌──────────────────────────────────────────────────────────────────┐
│  BlockRegistry / Validator / Executor / PipelineRepo             │
└──────────────────────────────────────────────────────────────────┘
```

### 2.4 SSE event protocol

```typescript
type StreamEvent =
  | { type: "chat",      content: string, highlight_nodes?: string[], ts: number }
  | { type: "operation", op: OpName, args: object, result?: object, elapsed_ms: number, ts: number }
  | { type: "error",     op: OpName, message: string, hint?: string, ts: number }
  | { type: "done",      status: "finished" | "failed", pipeline_json: PipelineJSON, ts: number };
```

**順序保證：** Backend 以同一個 async generator 序列化輸出 → UI 收到的順序就是 Agent 操作的順序。

**斷線策略（MVP）：** 前端偵測 EventSource `onerror` → 標記 session dead → show 「Connection lost, retry」按鈕。**不自動 resume**（Phase 3.1a/3.3 再做 checkpoint / resume）。

### 2.4 關鍵設計決定

1. **Tool API 就是「改寫 PipelineJSON + 回傳狀態」** — 不是 REST endpoints。內部在 session 的 in-memory pipeline_json 上操作，避免每步打 DB。
2. **Validator 在每個 mutation tool 後自動跑** — Agent 立刻知道是否出錯，不等最後才炸。
3. **Preview tool 走既有 Executor** — 不重寫執行邏輯。
4. **不直接 commit DB** — Agent 跑完只回 pipeline_json + op log。**使用者在 UI 看完 replay 按「Accept」才寫入**（類似 git staged changes）。
5. **錯誤不中斷整個 agent run** — BlockExecutionError / ValidationError 回給 Agent，Agent 可嘗試修正（類似 Claude Code 看到 Edit 失敗會再試）。

---

## 3. Tool API 完整規格（14 tools）

### 3.1 Canvas 操作類（8）

| Tool | 輸入 | 輸出 | 附註 |
|---|---|---|---|
| `list_blocks(category?)` | optional category filter | `[{name, version, category, status, description, input_schema, output_schema, param_schema}]` | 從 DB 讀 catalog。**符合 CLAUDE.md 原則**：prompt 不 hardcode 積木文件 |
| `add_node(block_name, block_version, position?, params?)` | block name + version + optional xy + optional params | `{node_id: "n3"}` | 自動 smart offset（避免重疊，與 v1.3 一致） |
| `remove_node(node_id)` | node id | `{}` | 同時清連到這 node 的 edges |
| `connect(from_node, from_port, to_node, to_port)` | 四個字串 | `{edge_id: "e2"}` | 自動跑 port type 相容檢查，不相容則拋錯給 Agent 重試 |
| `disconnect(edge_id)` | edge id | `{}` | |
| `set_param(node_id, key, value)` | | `{}` | Schema validation — 錯就拋錯訊息 |
| `move_node(node_id, position)` | | `{}` | 純視覺 |
| `rename_node(node_id, label)` | | `{}` | 顯示用，不影響 execution |

### 3.2 檢視類（3）

| Tool | 輸入 | 輸出 | 附註 |
|---|---|---|---|
| `get_state()` | — | `{pipeline_json, node_count, edge_count, selected_node_id}` | Agent 隨時檢查當前狀態 |
| `preview(node_id, sample_size?=50)` | | `{status, rows, columns, sample_rows, error?}` | 執行到該 node 回資料樣本。**這是 Agent 決定下一步的核心工具** |
| `validate()` | — | `{valid, errors: [{rule, message, node_id?}]}` | 7 條規則（§4.2 in main spec） |

### 3.3 溝通類（2）

| Tool | 輸入 | 輸出 | UI 呈現 |
|---|---|---|---|
| `explain(message, highlight_nodes?=[])` | 自然語言說明 + 可選強調節點 | `{}` | Chat 氣泡 + 對應節點亮藍框 |
| `ask_user(question, options?=[])` | **Phase 3.3 才做** | 阻塞等 user 回答 | Chat 彈出選項按鈕 |

### 3.4 生命週期（1）

| Tool | 輸入 | 輸出 | 附註 |
|---|---|---|---|
| `finish(summary)` | Agent 總結這次做了什麼 | `{}` | 標記任務完成。觸發 UI 顯示 Accept / Discard 按鈕 |

**註：** 沒有 `commit` 或 `save` tool。Agent 決定「已完成」後呼叫 `finish()`，**實際寫 DB 由 user 在 UI 按 Accept 觸發**。

---

## 4. Session 物件

```python
@dataclass
class AgentBuilderSession:
    session_id: str              # UUID, 對應一次 agent run
    user_request: str            # 原始 user prompt
    # Working state (in-memory)
    pipeline_json: PipelineJSON  # mutated by tools
    # Audit log
    operations: list[Operation]  # ordered tool calls with timestamps
    chat: list[ChatMsg]          # Agent's explain() messages
    errors: list[ErrorEvent]     # tool call errors Agent saw
    # Flags
    status: Literal["running", "finished", "failed", "needs_input"]
    started_at: datetime
    finished_at: Optional[datetime]


@dataclass
class Operation:
    op: str                   # tool name
    args: dict                # arguments passed
    result: dict              # tool return value
    elapsed_ms: float
    timestamp: datetime


@dataclass
class ChatMsg:
    role: Literal["agent"]
    content: str
    highlight_nodes: list[str]
    timestamp: datetime
```

**Persistence：** Phase 3.1 不存 DB。Agent 跑完回傳整包 session（operations + pipeline_json），使用者 Accept 才寫入 pipelines 表。

**Phase 3.2+：** session 可考慮存 DB 以便 resume / audit。

---

## 5. LLM 整合

### 5.1 Orchestrator 流程

```python
async def run_agent_build(user_request: str, base_pipeline: Optional[PipelineJSON] = None):
    session = AgentBuilderSession.new(user_request, base_pipeline)
    tools = BuilderToolset(session, registry, executor)  # injects session
    system_prompt = build_system_prompt(registry)        # includes block catalog

    # Claude tool-use loop
    messages = [{"role": "user", "content": user_request}]
    for _ in range(MAX_TURNS):  # safety cap (e.g. 30)
        response = await claude.messages.create(
            model="claude-sonnet-4-6",
            system=system_prompt,
            tools=tools.tool_definitions(),
            messages=messages,
        )
        if response.stop_reason == "tool_use":
            tool_results = []
            for tool_use in response.tool_uses:
                result = await tools.dispatch(tool_use.name, tool_use.input)
                tool_results.append(result)
                if result.get("tool") == "finish":
                    session.status = "finished"
                    return session
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break  # Agent stopped without calling finish — treat as abandoned
    session.status = "failed" if session.status == "running" else session.status
    return session
```

### 5.2 System Prompt 結構

**動態組裝（from DB；符合 CLAUDE.md 第 1 原則）：**

```
你是 AIOps Pipeline Builder Agent。使用者會請你組裝一條 Pipeline 來解決他們的製程監控需求。

== 你的工作方式 ==
- 你 **不寫 Python code**，也**不直接輸出 Pipeline JSON**
- 你呼叫提供的 tools（add_node / connect / set_param / preview / ...）一步步組裝
- 每加完一個關鍵節點，呼叫 explain() 向 user 說明你為什麼這樣做
- 組完後呼叫 finish(summary) 結束

== 可用積木（{count} 個）==
{for block in blocks:}
  {block.name} (category: {block.category})
    描述: {block.description}
    輸入 ports: {block.input_schema}
    輸出 ports: {block.output_schema}
    參數: {block.param_schema}
{endfor}

== 操作準則 ==
1. 拿到需求後先規劃（可不呼叫 tool，只在 content 說明規劃）
2. 先 list_blocks() 確認可用資源
3. 從 source node 開始依序 add_node → connect → set_param
4. 對欄位類型參數（Filter.column 等），**先 preview 上游看有哪些欄位**再決定
5. 關鍵決策後 explain() 一句話
6. 最後 validate() 確認通過，然後 finish()

== 重要邊界 ==
- 絕不 add_node 沒見過的 block_name
- set_param 的 value 必須符合 param_schema 型別
- 遇到 tool error，讀錯誤訊息修正後再試（最多 3 次）
- 不確定欄位名時呼叫 preview 而非猜
```

**不含：** 任何具體 SOP / 使用情境範例（那會 bias Agent 行為；讓 block description 自己說明）。

### 5.3 Tool Use JSON Schema

每個 tool 產生一個 Claude tool definition：
```json
{
  "name": "add_node",
  "description": "Add a new node to the canvas...",
  "input_schema": {
    "type": "object",
    "required": ["block_name"],
    "properties": {
      "block_name": {"type": "string", "description": "Must be one of the names from list_blocks"},
      "block_version": {"type": "string", "default": "1.0.0"},
      "position": {"type": "object", "properties": {"x": {"type": "number"}, "y": {"type": "number"}}},
      "params": {"type": "object"}
    }
  }
}
```

### 5.4 Prompt Caching（符合 global CLAUDE.md）

- `system` prompt（含 block catalog）→ cache_control: ephemeral
- `tools` definitions → cache_control: ephemeral
- 使用者 `messages` → 不 cache

---

## 6. Frontend 整合

### 6.1 新增 Copilot 入口

既有 Copilot 面板加一個 button：**「🤖 Ask agent to build a pipeline」**

點擊 → 彈出 prompt input → user 打需求 → 送 `POST /api/agent/build`。

### 6.2 Replay 動畫

接到 backend 回 `{pipeline_json, operations, chat}` 後，UI **逐步 replay**：

```typescript
for (const op of operations) {
  await applyOp(op, builderContext);  // dispatch to reducer
  await delay(REPLAY_INTERVAL);        // e.g. 400ms
  await highlightRelevantNodes(op);    // briefly flash active nodes
}
// replay 結束後顯示 Accept / Discard 按鈕
```

**細節：**
- `REPLAY_INTERVAL` 預設 400ms，UI 頂部有 slider（慢 / 中 / 快 / 跳過）
- `ask_user` 操作暫停 replay 等 user 回答（Phase 3.3 才做）
- `explain` 操作在 Copilot panel 冒出氣泡 + canvas 節點亮藍框 1.5s

### 6.3 Accept / Discard

Replay 結束後畫面底下出現固定 toolbar：
- **Accept** → 把 pipeline_json 寫進 backend（`POST /pipelines` 存 Draft）
- **Discard** → 清空 canvas
- **Adjust** → 留著當 Draft，使用者繼續手動編輯

### 6.4 錯誤呈現

如果 agent `status: "failed"`（達上限仍未完成）：
- 部分 ops 已經 apply 到 canvas
- Copilot 顯示 Agent 最後的 chat + errors
- User 可選擇「手動接手」或「discard」

### 6.5 test-ids（為 Playwright 預埋）

- `agent-start-btn`（Copilot 裡的按鈕）
- `agent-prompt-input`
- `agent-chat-msg`（每個 explain 氣泡）
- `agent-replay-status`（running / finished / failed 狀態）
- `agent-accept-btn` / `agent-discard-btn`

---

## 7. Backend 結構

### 7.1 新增模組

```
app/services/agent_builder/
├── __init__.py
├── session.py         # AgentBuilderSession + Operation dataclass
├── tools.py           # BuilderToolset (14 tools)
├── prompt.py          # build_system_prompt(registry) + tool_definitions
├── orchestrator.py    # run_agent_build() tool-use loop
└── replay.py          # (Phase 3.2) SSE streaming helper
```

### 7.2 新增 endpoints（SSE streaming）

```
POST /api/v1/agent/build
Request:  {prompt: str, base_pipeline_id?: int}
Response: {session_id: str}
# 只建 session，不跑。實際執行在 stream endpoint 訂閱時觸發。

GET /api/v1/agent/build/stream/{session_id}
Response: text/event-stream
# SSE event stream — 見 §2.4 protocol。
# Connection 保持直到 "done" 事件或 cancel / error。

POST /api/v1/agent/build/{session_id}/cancel
Response: {status: "cancelled"}
# 設 session cancellation flag。orchestrator 檢查點（tool call 之間）遇到 flag 即結束。

GET /api/v1/agent/build/{session_id}
Response: {status, pipeline_json, operations, chat, errors}
# 查詢最終狀態（session 結束後用）
```

**為什麼兩個階段？**
- EventSource（標準 SSE client）只支援 GET、無 body
- 所以 `POST` 先建 session（含 prompt body），再 `GET /stream/{id}` 訂閱
- Session 為 ephemeral（in-memory dict），TTL 5 分鐘

**Fallback（若 SSE 硬傷）：** 直接 `POST /api/v1/agent/build` 回 batch full response（同 v0.1 的協定）。同一份 orchestrator 程式碼用 `async for` 收齊即可，**不用分叉實作**。

### 7.3 與 existing `agent_orchestrator_v2` 的關係

| Legacy v2 | New v3（Phase 3）|
|---|---|
| 生 Python code → sandbox exec | 呼叫 builder tools → 改 PipelineJSON |
| 用於：Copilot Q&A、ad-hoc analysis | 用於：**建構可重用的 Pipeline** |
| 保留不動 | 新增 module，不 touch v2 |

判斷邏輯：
- User 問「EQP-01 過去 1 小時 OOC 幾次？」→ v2（一次性 Q&A）
- User 問「幫我建一個 EQP-01 OOC 超過 3 次就告警的 rule」→ v3（建 Pipeline）

Copilot 可能內建 **意圖分類**：prompt 開頭 / 關鍵字匹配 → 分流到 v2 或 v3。Phase 3 階段手動加個按鈕就好。

---

## 8. Step-by-Step Execution Plan（SSE MVP，7–8 days，1 人）

### Day 1–2：Backend 骨架
- [ ] `AgentBuilderSession` / `Operation` / `ChatMsg` / `StreamEvent` dataclass
- [ ] `BuilderToolset` 14 個 tool 實作（純 in-memory 操作 session.pipeline_json）
- [ ] `build_system_prompt(registry)` 動態讀 catalog + prompt cache 設定
- [ ] **orchestrator.py 寫成 async generator** `async def stream_agent_build(...) -> AsyncGenerator[StreamEvent, None]`
- [ ] Unit tests：每個 tool 驗證 in/out + session mutation

### Day 3：Endpoints + session registry
- [ ] In-memory session registry（thread-safe dict + TTL cleanup）
- [ ] `POST /agent/build` → 建 session，回 `{session_id}`
- [ ] `GET /agent/build/stream/{id}` → `StreamingResponse` + `async for` 吐 SSE events
- [ ] `POST /agent/build/{id}/cancel` → 設 flag，orchestrator checkpoint 讀 flag
- [ ] Integration test：固定 prompt → 驗 SSE events 順序 + 最終 pipeline valid

### Day 4–5：Frontend streaming client
- [ ] Copilot 加「🤖 Ask agent」button + prompt input
- [ ] `useAgentStream(sessionId)` hook：EventSource + event dispatcher
- [ ] BuilderContext 加 `applyStreamEvent(evt)` — 直接改 pipeline state
- [ ] UI：
  - Chat panel 顯示 Agent chat / 工具執行中「● Running...」狀態
  - Canvas 節點 fade-in 動畫（200ms CSS transition）
  - explain 事件觸發節點藍框 1.5s 脈衝
  - Cancel button（發 POST cancel + close EventSource）
  - Accept / Discard 按鈕（done 事件後出現）

### Day 6：場景測試
- [ ] 15 個 SPC 場景 prompt → 驗 agent 成功率 ≥ 80%（12/15 pass）
- [ ] Playwright E2E：
  - 完整 agent run → 截圖每步 → 驗 node 數 / edge 數 / final status
  - Cancel 中途 → 驗 backend 確實停止
  - 故意錯誤 prompt → 驗 Agent graceful failure

### Day 7–8：穩定度 + 邊緣 case + 報告
- [ ] 斷線處理：frontend EventSource error → 顯示 Retry
- [ ] Session TTL：5 分鐘內無訂閱 → 自動清
- [ ] Token cost 測量 + 優化（prompt cache 命中率 ≥ 90%）
- [ ] 效能：Agent run p95 < 30s（含 Claude latency）
- [ ] `docs/phase_3_test_report.md`

### Phase 3.3（後做）— HITL
- [ ] `ask_user()` tool + UI options dialog（阻塞 agent，等 user 點選項）
- [ ] Orchestrator 對應 pause / resume 語意
- [ ] Playwright test：agent asks → user picks → agent continues

---

## 9. QA Checklist（Phase 3.1 MVP）

### A. 單元測試
- [ ] A1 每個 tool 基本 in/out 正確
- [ ] A2 `add_node` smart offset 生效
- [ ] A3 `connect` port 型別不相容時拋錯
- [ ] A4 `preview` 回傳正確欄位 / 失敗時錯誤可讀
- [ ] A5 `validate` 7 條規則都能被 agent 收到

### B. LLM 整合
- [ ] B1 system prompt 成功包含所有 11 個積木的 description + schema
- [ ] B2 tool_use 回圈可正確處理 Claude API 的 parallel tool calls
- [ ] B3 tool error 能完整回到 Agent（messages append 結構正確）

### C. End-to-end 場景（15 個典型 SPC）
- [ ] C1「EQP-01 SPC xbar 連續 3 次 OOC 告警」
- [ ] C2「EQP-01 所有 step 的 OOC 統計 bar chart」
- [ ] C3「EQP-01 APC rf_power_bias 近 5 筆移動平均超過閾值告警」
- [ ] C4「WECO R1+R5 rule 掃 EQP-01」
- [ ] C5「EQP-01 與 EQP-02 的 xbar 對比折線圖」
- [ ] ... 共 15 個
- [ ] **成功率 ≥ 80%（12 / 15 pass）**

### D. UI / UX
- [ ] D1 Replay 順序與 operations 一致
- [ ] D2 explain 氣泡出現在正確時機 + 節點高亮正確
- [ ] D3 Accept 後 DB 有新 pipeline（draft status）
- [ ] D4 Discard 後 canvas 清空
- [ ] D5 失敗時可看到已執行的部分 + 接手編輯

### E. 非功能
- [ ] E1 Agent build 完整 run p95 < 30s（含 Claude latency）
- [ ] E2 Token cost：system prompt cache 命中率 ≥ 90%
- [ ] E3 Frontend 動畫 5–10 步流暢無卡頓

### F. SSE streaming 特有
- [ ] F1 SSE events 順序與 Agent 實際操作順序一致
- [ ] F2 首個 event（chat "Thinking..."）在 POST 建 session 後 ≤ 1.5s 抵達
- [ ] F3 Cancel：POST cancel 後 ≤ 2s 內 backend 停止，EventSource 收到 done (status:cancelled)
- [ ] F4 斷線：middle-stream 切網 → frontend 顯示 Retry；reconnect 後不 resume 舊 session
- [ ] F5 Session 過期：> 5 分鐘未訂閱 → 自動清理
- [ ] F6 Done event 一定最後出現（無 race condition）

---

## 10. 開放議題（需決策）

### Q1 — MVP 先做 3.1 batch 還是直接 3.2 streaming？
- **建議 3.1**：降低風險、快速驗證。2–3 週後如實測順、用戶要 realtime，再升 3.2
- 另解：直接 3.2（工程加 2–3 天）

### Q2 — 動畫速度？
- 預設 400ms / op，UI 有 slider（100ms / 400ms / 1000ms / 即時）
- 這個決策影響 Agent 示範的節奏感

### Q3 — Agent 可用 `finish()` 前必須 `validate()` 通過嗎？
- **建議：是**（ orchestrator 強制最後一步必驗證通過才允許 finish）
- 否則：Agent 可能吐出無效 pipeline，使用者 Accept 後跑 Run 才失敗

### Q4 — Accept 後 pipeline 預設 status？
- **建議 `draft`**（需要 user 再手動 promote）
- 或：跳過 draft 直接 `pi_run`？不建議，因 AI 生成應該有人工驗收關卡

### Q5 — 模型選擇：Sonnet 4.6 vs Opus 4.7？
- **建議 Sonnet 4.6** for MVP：便宜 20x、夠用
- Opus 用於極複雜的 compound rule（WECO + multi-join）場景

### Q6 — 改既有 pipeline 模式？
- Phase 3.1 支援 "base_pipeline_id" 參數 — Agent 可在既有 draft 上增修
- 範例：user 選中既有 pipeline → 「幫我加一個 WECO rule 檢查」→ Agent 加 node 不動既有
- **建議：納入 Phase 3.1 範圍**（難度增加不多）

### Q7 — Copilot 意圖分流（v2 vs v3）？
- 最簡：UI 加「Ask Agent to build」明確按鈕（v3 專用）
- 進階：Copilot prompt 前加一個 classifier LLM 做 routing
- **建議：MVP 用按鈕，classifier 延後**

### Q8 — Error retry 上限？
- Agent 一個 tool call 失敗最多重試幾次？
- **建議 3 次**（超過就 explain 給 user 並 finish with partial state）

### Q9 — Session 記錄是否存 DB？
- Phase 3.1 不存（ephemeral），跑完 response 給 UI 就丟
- Phase 3.2 可存 session，support resume
- **建議 Phase 3.1 不存 DB**

---

## 11. 風險 & Mitigation

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| R1 | Agent 挑錯積木（如把 groupby 當 filter 用） | 中 | 中 | 積木 description 寫得足夠清楚（§5.2 的 prompt 依賴這個）+ validator 抓 |
| R2 | Agent 進入死循環反覆 set_param → validate 出錯 | 低 | 中 | MAX_TURNS=30 硬限制 + 每個 tool 失敗 retry ≤ 3 |
| R3 | Token 成本失控 | 中 | 中 | prompt cache + 限制單一 session 最大 turn 數 |
| R4 | UI replay 與 backend 狀態不一致 | 低 | 低 | Agent 回傳 pipeline_json 作為 ground truth；replay 只是視覺化 |
| R5 | Agent 要呼叫 preview 拿上游 columns，但上游跑失敗 | 中 | 中 | preview tool 回 structured error，Agent 被訓練看錯誤調整（類似 Claude Code 處理 Bash 失敗） |
| R6 | 積木太多（>20 個）prompt 爆量 | 低（目前 11 個） | 低 | prompt cache + 未來若破 20 個時切 category 分批載入 |

---

## 12. 成本估算

- **工時：** Phase 3.1 ~ 1 人週；3.2 ~ 0.5；3.3 ~ 0.5 → 合計 **~2 人週**
- **LLM 成本（per Agent run, Sonnet 4.6 with caching）：**
  - System prompt ≈ 3K tokens（cached after first call）
  - 平均 15 tool calls × 500 tokens each ≈ 7.5K output
  - **約 $0.02 / agent run**。月 1000 次 ≈ $20

---

## 13. 決策總整

請使用者就以下逐項回覆：

1. **Q1 先做 3.1 batch？** A（建議）= 先 3.1 / B = 直接 3.2
2. **Q2 動畫速度預設 400ms + slider？** A（建議）= 是 / B = 其他
3. **Q3 `finish()` 強制先 validate() 通過？** A（建議）= 是 / B = 否（Agent 自主）
4. **Q4 Accept 後狀態 = draft？** A（建議）= 是 / B = 直接 pi_run
5. **Q5 模型 = Sonnet 4.6？** A（建議）= 是 / B = Opus
6. **Q6 Phase 3.1 支援 base_pipeline_id（改既有）？** A（建議）= 支援 / B = 新 pipeline only
7. **Q7 Copilot 分流 = 明確按鈕？** A（建議）= 按鈕 / B = classifier LLM
8. **Q8 Tool error retry 上限 3 次？** A（建議）= 3 / B = 其他
9. **Q9 Phase 3.1 session 不存 DB？** A（建議）= 不存 / B = 存

另：**範圍決策** — 先做 Phase 3.1（5–7 days） / 一次做到 3.2 / 一次做到 3.3？

回覆後我照流程（先不動 code）補出 **Phase 3.1 實作子規格 + QA checklist** 才啟動實作。

---

---

## 14. Appendix — Batch Fallback 設計（原 v0.1 Phase 3.1）

若 SSE streaming 實作中碰到硬傷（常見 candidate）：
- Uvicorn + StreamingResponse 邊緣 bug
- `asyncio.CancelledError` 語意在 async generator 內不穩
- Anthropic SDK streaming 的 tool_use 邊界處理複雜化
- 前端 EventSource 於某些企業 proxy 被緩衝

**Graceful degradation 路徑：**

1. Backend orchestrator 本身**不改**（已是 async generator）
2. 新增 fallback endpoint：
   ```
   POST /api/v1/agent/build/batch
   Request: {prompt, base_pipeline_id?}
   Response: {
     session_id, status, pipeline_json,
     operations: [Operation],
     chat:       [ChatMsg],
     errors:     [ErrorEvent]
   }
   ```
   實作內容：
   ```python
   events: list[StreamEvent] = []
   async for evt in stream_agent_build(prompt):
       events.append(evt)
   return assemble_batch_response(events)
   ```
3. Frontend 加 env flag `NEXT_PUBLIC_AGENT_STREAMING=false` → 切 fetch + replay animation（類原 Phase 3.1 方案）
4. **Replay animation** 邏輯留 frontend（即便 SSE path 也能 fallback 到 "slow down" 模式供 demo）

**此設計確保** SSE 若失敗，切 fallback 是 **config toggle + endpoint 切換**，不是重寫。

---

**END OF SPEC Phase 3 v0.2**

---

## 15. Phase 3.2 實作子規格（Approved 2026-04-18）

> 對照 Phase 1 §14、Phase 2 §14、v1.1 §14 — 同樣格式：決策落地、檔案結構、T 清單、QA 驗收。

### 15.1 已鎖定決策（§10 closed）

| # | Decision |
|---|---|
| Q1 | **SSE streaming 直接做 MVP**，batch 為 fallback 設計（§14 Appendix） |
| Q2 | 動畫速度：**CSS natural 漸變**（不加速度 slider，Claude 節奏自然） |
| Q3 | Agent 呼叫 `finish()` 前**強制 validate() 通過**，否則 orchestrator 攔截重試 |
| Q4 | User accept 後 pipeline **預設 `draft` status** |
| Q5 | 模型：**`claude-sonnet-4-6`** |
| Q6 | **支援 `base_pipeline_id`**（Agent 可在既有 draft 上增修） |
| Q7 | Copilot 入口：**明確按鈕「🤖 Ask agent」**，不做 classifier 分流 |
| Q8 | Tool error retry：Agent 自己看錯誤重試，orchestrator **硬限 MAX_TURNS=30 + 每 tool 同樣內容重試 3 次後放棄** |
| Q9 | **Session 不存 DB**（in-memory dict + 5 分鐘 TTL） |

### 15.2 技術選型

| 項目 | 選擇 |
|---|---|
| Anthropic SDK | 0.89.0（已裝），用 `client.messages.stream(...)` async interface |
| Model | `claude-sonnet-4-6` |
| Prompt cache | system + tools 都加 `cache_control: {type: "ephemeral"}` |
| SSE | FastAPI `StreamingResponse` + media_type `text/event-stream`, `async for` 吐 `f"data: {json}\n\n"` |
| Session store | 模組層級 `_SESSIONS: dict[str, AgentBuilderSession]` + 背景 asyncio.task 清 TTL |
| Cancellation | `session.cancel_event = asyncio.Event()`；orchestrator 在 tool 間檢查 `is_set()` |
| Frontend streaming | 原生 `EventSource`（標準 DOM API，無新 dep） |

### 15.3 檔案結構

```
fastapi_backend_service/app/
├── services/agent_builder/            ★ 新增
│   ├── __init__.py
│   ├── session.py                       # AgentBuilderSession + Operation + ChatMsg + StreamEvent
│   ├── tools.py                         # BuilderToolset (14 tools)
│   ├── prompt.py                        # build_system_prompt(registry) + claude_tool_defs()
│   ├── orchestrator.py                  # stream_agent_build() async generator
│   └── registry.py                      # session store + TTL cleanup
├── routers/
│   └── agent_builder_router.py          ★ 新增 — /agent/build endpoints
└── tests/pipeline_builder/              (擴充既有目錄)
    ├── test_agent_tools.py              # 14 tools 單測
    ├── test_agent_orchestrator.py       # full agent run integration (real LLM)
    └── test_agent_sse.py                # SSE endpoint + cancel test

aiops-app/src/
├── components/pipeline-builder/
│   └── AgentPanel.tsx                   ★ 新增 — chat + status + cancel + accept/discard
├── context/pipeline-builder/
│   └── useAgentStream.ts                ★ 新增 — EventSource hook + BuilderContext dispatcher
├── lib/pipeline-builder/
│   └── agent-api.ts                     ★ 新增 — POST create / cancel helpers
└── app/api/agent/build/                 ★ 新增 frontend proxy
    ├── route.ts                         # POST create session
    ├── stream/[id]/route.ts             # proxy SSE stream
    └── [id]/cancel/route.ts
```

### 15.4 任務清單（T1–T12，7–8 working days）

| # | 任務 | 預估 | 檔案 |
|---|---|---|---|
| T1 | `session.py` — dataclasses | 0.3d | AgentBuilderSession / Operation / ChatMsg / StreamEvent |
| T2 | `tools.py` — 14 tools 實作 | 2.0d | 每個 tool 操作 `session.pipeline_json`，validator/executor 整合 |
| T3 | `prompt.py` — system prompt + tool defs | 0.5d | 從 BlockRegistry 動態組；prompt cache |
| T4 | `orchestrator.py` — streaming tool-use loop | 1.0d | Anthropic async stream + yield StreamEvent |
| T5 | `registry.py` — session store + TTL | 0.3d | asyncio.Task 定期清 > 5 min sessions |
| T6 | `agent_builder_router.py` — 4 endpoints | 0.5d | POST create / GET stream / POST cancel / GET get |
| T7 | Backend unit tests（每個 tool） | 0.5d | `test_agent_tools.py` |
| T8 | Backend integration test（SSE + 真 LLM call） | 0.5d | 需 ANTHROPIC_API_KEY；marker skip if absent |
| T9 | Frontend `useAgentStream` hook | 0.5d | EventSource + event → BuilderContext dispatch |
| T10 | Frontend `AgentPanel` UI | 1.0d | chat list + status + cancel / accept / discard |
| T11 | Playwright E2E — 15 個 SPC 場景 prompts | 1.0d | 驗 success rate ≥ 80% |
| T12 | `docs/phase_3_test_report.md` + 清 DB + 總結 | 0.4d | |
| — | 合計 | **~8 days** | |

### 15.5 14 Tools 詳細實作 spec

所有 tools 都是 `BuilderToolset` 的 async method，return `dict` (tool result)。操作 `self.session.pipeline_json` in-place。Mutation tools 完後自動 append Operation + 跑 validator — errors 作為 structured error return，Agent 讀錯誤訊息決定是否重試。

```python
class BuilderToolset:
    def __init__(self, session, registry, executor):
        self.session = session
        self.registry = registry
        self.executor = executor

    # Canvas ops
    async def list_blocks(self, category: Optional[str] = None) -> dict: ...
    async def add_node(self, block_name: str, block_version: str = "1.0.0",
                       position: Optional[dict] = None, params: Optional[dict] = None) -> dict: ...
    async def remove_node(self, node_id: str) -> dict: ...
    async def connect(self, from_node: str, from_port: str,
                      to_node: str, to_port: str) -> dict: ...
    async def disconnect(self, edge_id: str) -> dict: ...
    async def set_param(self, node_id: str, key: str, value: Any) -> dict: ...
    async def move_node(self, node_id: str, position: dict) -> dict: ...
    async def rename_node(self, node_id: str, label: str) -> dict: ...

    # Introspection
    async def get_state(self) -> dict: ...
    async def preview(self, node_id: str, sample_size: int = 50) -> dict: ...
    async def validate(self) -> dict: ...

    # Communication
    async def explain(self, message: str, highlight_nodes: Optional[list] = None) -> dict: ...
    # ask_user — Phase 3.3（本 MVP 不做）

    # Lifecycle
    async def finish(self, summary: str) -> dict:
        # gate: must validate() with zero errors first
        v = await self.validate()
        if not v["valid"]:
            raise ToolGateError("Cannot finish: validator errors remain")
        self.session.mark_finished(summary=summary)
        return {"status": "finished"}
```

每個 tool 的詳細 signature + input_schema + 範例 I/O 在 `docs/phase_3_tool_api_reference.md`（T3 產出，spec 太長不展開）。

### 15.6 SSE event protocol（最終版）

```
event: chat
data: {"content":"Looking up available blocks...","highlight_nodes":[],"ts":1718...}

event: operation
data: {"op":"add_node","args":{...},"result":{"node_id":"n1"},"elapsed_ms":12,"ts":...}

event: error
data: {"op":"connect","message":"Port type mismatch","hint":"...","ts":...}

event: done
data: {"status":"finished","pipeline_json":{...},"summary":"..."}
```

每個 event 用 named event type（easier filtering in `EventSource` listeners）。

### 15.7 Phase 3.2 QA Checklist（涵蓋 §9 A–F + 新增）

詳見 §9 A–F（共 ~35 條）。**全部在 `phase_3_test_report.md` 逐項勾選**。

額外新增：
- [ ] G1 **`finish()` 強制 validate 通過** — Agent 沒驗就 finish → orchestrator 回錯誤給 Agent 重跑 validate
- [ ] G2 `base_pipeline_id` 流程：既有 draft + "加一個 WECO rule" → Agent 不動既有節點，只加新的
- [ ] G3 Prompt cache 命中率實測 ≥ 90%（第 2 次相同 prompt 的 TTFT 顯著下降）
- [ ] G4 Session TTL：倒數 5 分鐘後 session 確實被清
- [ ] G5 15 個 SPC 場景 prompts（詳列）：
  1. `EQP-01 SPC xbar 連續 3 次 OOC 告警`
  2. `EQP-01 所有 step OOC 次數 bar chart`
  3. `EQP-01 APC rf_power_bias 近 5 筆 MA 超 100 就告警`
  4. `掃 EQP-01 WECO R1 + R5 rule`
  5. `EQP-01 各 lot 的 spc_xbar_chart_value delta (本批-上批)`
  6. `EQP-01 近 24h OOC event 清單（filter + chart）`
  7. `EQP-02 consecutive 5 次某 chart 超 UCL`
  8. `EQP-01 STEP_002 的 xbar 線圖`
  9. `EQP-01 APC vs SPC xbar 關聯圖（join by lotID）`
  10. `EQP-01 rolling window std 超 10 告警`
  11. `EQP-01 近 7d 各 step 平均 xbar`
  12. `EQP-01 所有 chart 類型（xbar/r/s/p/c）的 OOC 統計`
  13. `EQP-03 STEP_007 近 50 筆 r_chart bar`
  14. `EQP-01 近 1h 任何 chart OOC 就 HIGH 告警`
  15. `EQP-01 + EQP-02 對比 xbar 折線圖`

目標 **12 / 15 成功**（success = Agent finish + 組出的 pipeline Run 通過）。

### 15.8 完成後產出

1. `docs/phase_3_test_report.md` — 逐項 QA + 15 場景實測結果
2. `docs/phase_3_tool_api_reference.md` — 14 tools 完整 signature + examples（for future maintainers）
3. Backend 增量 ~600 LOC / Frontend ~400 LOC
4. 若 Phase 3.2 MVP 全綠 → 啟動 Phase 3.3 HITL 補充 spec

---

**END OF SPEC Phase 3 v0.2（含 §15 實作子規格）— Approved for implementation**
