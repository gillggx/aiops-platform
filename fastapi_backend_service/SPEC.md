# fastapi_backend_service — Spec 2.0

**Date:** 2026-04-06
**Status:** Living Document (Current Implementation)

---

## 1. 定位

AIOps 平台的 **Backend API + AI Agent 核心**。負責：

- AI Agent 對話 orchestration（LangGraph v2 + v1 fallback）
- MCP（Model Context Protocol）tool dispatch — 代理 Agent 呼叫外部資料源
- Skill / Diagnostic Rule 管理 — 定義、LLM 生成、sandbox 執行
- Auto-Patrol 自動巡檢排程
- 長期記憶系統（pgvector 向量搜尋 + 反思式生命週期）
- 使用者認證 / 系統設定

## 2. 技術棧

| Category | Tech | Version |
|----------|------|---------|
| Framework | FastAPI + Uvicorn | 0.115 / 0.32 |
| Database | PostgreSQL + pgvector | asyncpg 0.30 |
| Agent Framework | LangGraph (StateGraph) | >= 0.2.0 |
| LLM | Anthropic Claude | anthropic >= 0.49 |
| Embeddings | bge-m3 via Ollama | 1024-dim |
| Vector Search | pgvector HNSW | cosine similarity |
| Scheduler | APScheduler | 3.11 |
| Message Bus | NATS (optional) | nats-py >= 2.9 |
| Data Science Sandbox | numpy, pandas, scipy, scikit-learn | — |
| HTTP Client | httpx | 0.28 |
| Auth | JWT (python-jose) + bcrypt | — |

## 3. 目錄結構

```
fastapi_backend_service/
├── main.py                    # App startup, middleware, data seeding
├── app/
│   ├── config.py              # Settings (env-based via pydantic-settings)
│   ├── core/
│   │   ├── exceptions.py      # Custom exception classes
│   │   ├── logging.py         # Structured logging setup
│   │   ├── response.py        # StandardResponse wrapper
│   │   └── security.py        # JWT encode/decode, password hashing
│   ├── models/                # SQLAlchemy ORM models (§4)
│   ├── schemas/               # Pydantic request/response schemas
│   ├── repositories/          # DB query layer (Repository pattern)
│   ├── routers/               # FastAPI route handlers (§5)
│   └── services/              # Business logic (§6)
├── requirements.txt
└── docs/history/              # Archived documentation
```

## 4. 資料模型 (PostgreSQL)

### 4.1 核心 Models

| Model | Table | 說明 |
|-------|-------|------|
| `SkillDefinitionModel` | `skill_definitions` | 統一 Skill（source + binding_type 決定用途） |
| `MCPDefinitionModel` | `mcp_definitions` | System MCP（資料源端點）+ Custom MCP |
| `AutoPatrolModel` | `auto_patrols` | 自動巡檢定義（綁定 Skill + Alarm 規則） |
| `AlarmModel` | `alarms` | Auto-Patrol 產生的告警（severity + evidence） |
| `AgentExperienceMemoryModel` | `agent_experience_memory` | 反思式長期記憶（含 pgvector embedding） |
| `AgentSessionModel` | `agent_sessions` | 對話 session（滑動視窗 + 階層摘要） |
| `AgentMemoryModel` | `agent_memories` | Legacy RAG 記憶（v1） |

### 4.2 支援 Models

| Model | Table | 說明 |
|-------|-------|------|
| `UserModel` | `users` | 使用者帳號 + 角色 (JSON) |
| `DataSubjectModel` | `data_subjects` | 資料主題定義（input/output schema） |
| `EventTypeModel` | `event_types` | 事件類型登錄（SPC_OOC, RECIPE_CHANGE, etc.） |
| `CronJobModel` | `cron_jobs` | APScheduler Cron 排程紀錄 |
| `ScriptVersionModel` | `script_versions` | Skill 腳本版本管理（draft → active → archived） |
| `ExecutionLogModel` | `execution_logs` | Skill 執行歷史（duration, status, output） |
| `NatsEventLogModel` | `nats_event_log` | NATS 事件接收紀錄 |

### 4.3 Skill 資料結構（Unified Skill Architecture）

所有 source 類型共用相同 schema：

```
steps_mapping:  [{step_id, nl_segment, python_code}]
input_schema:   [{key, type, required, description}]
output_schema:  [{key, type, label, unit?, columns?, x_key?, y_keys?}]
```

**source 欄位**（誰建立的）：
- `source="skill"` — 使用者透過 My Skills 建立（LLM 生成或手動）
- `source="rule"` — AI 兩階段生成（Phase 2a: step plan → Phase 2b: per-step code）
- `source="auto_patrol"` — 手動定義，嵌在 patrol 實體內
- `source="legacy"` — 通用 Skill

**binding_type 欄位**（綁定到什麼觸發方式）：
- `binding_type="none"` — My Skill / chat 中使用，不綁定觸發器
- `binding_type="event"` — 綁定為 Auto-Patrol（event-driven 觸發）
- `binding_type="alarm"` — 綁定為 Diagnostic Rule（alarm-driven 觸發）

**Skill 生命週期**：
1. Agent 對話分析 → 使用者點擊「儲存為我的 Skill」→ `source=skill, binding_type=none`
2. My Skill 可升級為 Auto-Patrol（`binding_type=event`）或 Diagnostic Rule（`binding_type=alarm`）

## 5. API Routers

### 5.1 Agent 對話

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/agent/chat/stream` | SSE 串流 Agent 對話（v1 orchestrator） |
| `POST` | `/agent/chat/stream?engine=v2` | SSE 串流 Agent 對話（LangGraph v2） |
| `GET` | `/agent/sessions/{sid}/workspace` | 讀取 canvas workspace state |
| `POST` | `/agent/approve/{token}` | HITL approval gate |

### 5.2 Knowledge Studio

| Method | Path | 說明 |
|--------|------|------|
| `GET/POST` | `/diagnostic-rules` | Diagnostic Rule CRUD |
| `POST` | `/diagnostic-rules/generate-steps/stream` | SSE 串流 LLM 生成 steps |
| `POST` | `/diagnostic-rules/{id}/try-run` | Sandbox 試跑 |
| `GET/POST/PATCH/DELETE` | `/my-skills` | My Skills CRUD |
| `POST` | `/my-skills/generate-steps/stream` | SSE 串流 LLM 生成 Skill steps |
| `POST` | `/my-skills/{id}/try-run` | My Skill sandbox 試跑 |
| `POST` | `/my-skills/{id}/bind` | 升級 Skill binding_type（none → event/alarm） |
| `GET/POST/PATCH` | `/auto-patrols` | Auto-Patrol CRUD |
| `POST` | `/auto-patrols/{id}/trigger` | 手動觸發巡檢 |
| `GET/POST/PATCH` | `/mcp-definitions` | MCP 定義 CRUD |
| `POST` | `/mcp-definitions/{id}/sample-fetch` | 測試 MCP 端點 |
| `GET/POST/PATCH` | `/skill-definitions` | Skill 定義 CRUD |

### 5.3 Analysis（Ad-hoc）

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/analysis/run` | 執行 Agent 生成的 ad-hoc 分析腳本 |
| `POST` | `/analysis/promote` | 將 ad-hoc 分析儲存為 My Skill（source=skill, binding_type=none） |

### 5.4 Memory

| Method | Path | 說明 |
|--------|------|------|
| `GET/POST/DELETE` | `/experience-memory` | 反思式記憶 CRUD |
| `GET/POST/DELETE` | `/agent/memory` | Legacy RAG 記憶 CRUD |

### 5.5 System

| Method | Path | 說明 |
|--------|------|------|
| `POST` | `/auth/login` | JWT 登入 |
| `GET/PATCH` | `/users` | 使用者管理 |
| `GET/PATCH` | `/system-parameters` | 系統參數（LLM prompts 等） |
| `POST` | `/system-events/ingest` | Webhook 事件接收 |
| `GET/POST` | `/cron-jobs` | Cron 排程管理 |
| `GET` | `/alarms` | 告警列表 |

## 6. 核心 Services

### 6.1 Agent Orchestrator

兩個版本並存：

- **v1** (`agent_orchestrator.py`, ~98KB) — 單檔 monolith，6-stage pipeline：
  Context Load → Planning → Tool Calls → Reasoning → Self-Critique → Memory Write
- **v2** (`agent_orchestrator_v2/`) — LangGraph StateGraph 重構：
  - `state.py` — TypedDict state 定義
  - `graph.py` — StateGraph 節點串接
  - `nodes/` — load_context, llm_call, tool_execute, synthesis, self_critique, memory_lifecycle
  - `adapter.py` — LangGraph events → v1 SSE format 轉換
  - `session.py` — Session load/save (sliding window + hierarchical summarization)
  - `orchestrator.py` — v2 entry point (v1-compatible `.run()` interface)

Feature flag `?engine=v2` 切換。

### 6.2 Tool Dispatcher

`tool_dispatcher.py` (~43KB) — Agent 呼叫工具的統一入口：

- `execute_skill` — 執行 Skill（sandbox python）
- `execute_analysis` — 執行 ad-hoc 分析（Agent 生成的 steps_mapping）
- `execute_mcp` → 委派到 `mcp_definition_service.py`
- Preflight validation（必填參數、format check）
- render_card 生成（供前端渲染）
- _chart DSL → Vega-Lite 轉換

### 6.3 Context Loader

`context_loader.py` (~32KB) — 建構 LLM System Prompt：

- Soul Prompt（行為鐵律 §1.1 ~ §1.16）
- MCP Catalog 注入（DB 中 active 的 System + Custom MCPs）
- User Preference 載入
- RAG Memory 檢索（pgvector cosine + 關鍵字混合）
- Session History 注入

### 6.4 MCP Definition Service

`mcp_definition_service.py` (~65KB) — MCP 端點管理 + 呼叫代理：

- System MCP 代理呼叫（GET/POST → OntologySimulator endpoints）
- `since` 時間窗參數正規化（`24h` → ISO8601 start_time）
- `object_name/object_id` → `toolID/lotID` 參數映射
- SPC chart_name alias 正規化

### 6.5 Memory System

- **Experience Memory** (`experience_memory_service.py`) — Phase 1 反思式記憶：
  - Write: LLM 抽象化 → bge-m3 embedding → pgvector 儲存
  - Retrieve: hybrid filter（cosine + keyword + recency）
  - Feedback: confidence scoring（UP/DOWN/HUMAN_REJECTED）
  - Decay: STALE 標記 + 自動清理
- **Memory Abstraction** (`memory_abstraction.py`) — 記憶摘要模板

### 6.6 Diagnostic Rule Service

`diagnostic_rule_service.py` (~29KB) — AI 診斷規則生成：

- Phase 1: MCP planner — 從 NL 描述規劃需要哪些 MCP 呼叫
- Phase 2a: Step planner — 拆解為多個 step（nl_segment）
- Phase 2b: Per-step code — 逐 step 生成 python_code
- SSE streaming 支援

### 6.7 其他 Services

| Service | 說明 |
|---------|------|
| `auto_patrol_service.py` | Auto-Patrol CRUD + manual trigger + 嵌入 Skill 建立 |
| `skill_executor_service.py` | Sandbox 執行 Skill python_code |
| `cron_scheduler_service.py` | APScheduler cron 排程管理 |
| `alarm_service.py` | Alarm 建立 + severity 判斷 |
| `nats_subscriber_service.py` | NATS event bus 訂閱 |
| `auth_service.py` | JWT token 生成 + 驗證 |
| `sandbox_service.py` | 安全沙盒執行環境（exec + 受限 globals） |

## 7. System MCP 定義（Seed）— MCP v3 三層架構

啟動時自動 seed 到 DB（create or update by name，刪除不在 canonical list 的舊記錄）。

### 7.1 三層資料 MCP（v3 架構）

Agent 透過三個層級的 MCP 漸進式深入調查：

| Layer | MCP Name | Endpoint | 說明 |
|-------|----------|----------|------|
| **L1 — Summary** | `get_process_summary` | `GET /process/summary` | 聚合統計（OOC rates、per-tool breakdown、recent OOC）。MongoDB aggregation pipeline，毫秒回應。適合全廠範圍掃描。 |
| **L2 — Investigation** | `get_process_info` | `GET /process/info` | 範圍調查 + 自動 SPC charts。新增 `objectName` 參數可篩選 SPC/DC/APC/RECIPE。回應扁平化（不再有 `{event, objects}` 巢狀）。`objectName=SPC` 自動產生 `_charts`（xbar/r/s/p/c 5 種 chart DSL）。**一次呼叫取代過去 8 次呼叫。** |
| **L3 — Deep Dive** | `query_object_timeseries` | `POST /objects/query` | 單一參數深度時序 + 3σ OOC（unchanged） |

**已退役 MCP**：
- `get_process_events` — 被 `get_process_info` 取代
- `get_object_info` — 不再需要（data IS the schema）

### 7.2 輔助 MCP

| MCP Name | Endpoint | 說明 |
|----------|----------|------|
| `list_tools` | `GET /tools` | 廠內機台清單 |
| `get_simulation_status` | `GET /status` | 模擬器系統狀態 |

## 8. 啟動流程

```
main.py → @app.on_event("startup")
  1. Create DB tables (SQLAlchemy metadata.create_all)
  2. Seed default users (admin, gill)
  3. Seed DataSubjects + EventTypes
  4. Seed System MCPs (create/update/delete stale)
  5. Seed System Memories (currently empty)
  6. Start NATS subscriber (if NATS_URL configured)
  7. Start APScheduler cron jobs
```

## 9. 環境變數

| Variable | Default | 說明 |
|----------|---------|------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL 連線字串 |
| `ANTHROPIC_API_KEY` | — | Claude API key |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama（bge-m3 embedding） |
| `ONTOLOGY_SIM_URL` | `http://localhost:8012` | OntologySimulator base URL |
| `NATS_URL` | — | NATS server（optional） |
| `JWT_SECRET_KEY` | — | JWT signing secret |
| `RESET_TO_ONTOLOGY_ONLY` | `false` | 啟動時清除非 canonical MCPs |
