# aiops-app — Spec 2.0

**Date:** 2026-04-06
**Status:** Living Document (Current Implementation)

---

## 1. 定位

AIOps 平台的 **Frontend 應用層**。同時扮演兩個角色：

- **Operations Center** — 值班工程師的操作介面（告警看板、Agent 對話、設備下鑽、批次追蹤）
- **Knowledge Studio** — 資深工程師的知識管理（Diagnostic Rules、Auto-Patrols、MCP 管理）
- **System Admin** — IT 管理員的系統設定（Data Sources、Event Registry、All Skills）

## 2. 技術棧

| Category | Tech | Version |
|----------|------|---------|
| Framework | Next.js (App Router) | 15.2.4 |
| React | React 19 | 19.0.0 |
| Language | TypeScript | strict mode |
| Chart (declarative) | Vega-Lite + Vega | 5.21 / 5.30 |
| Chart (interactive) | Plotly.js | 3.4 |
| Graph Layout | @xyflow/react + dagre | 12.10 / 2.0 |
| Markdown | react-markdown + remark-gfm | 10.1 |
| Contract Types | aiops-contract (local) | `file:../aiops-contract/typescript` |
| AI SDK | @anthropic-ai/sdk | 0.80 |

## 3. Navigation & 頁面結構

### 3.0 Sidebar Navigation

```
OPERATIONS CENTER
  ├── Alarm Center         /alarms
  └── Dashboard            /

KNOWLEDGE STUDIO
  ├── ⭐ My Skills         /admin/my-skills        ← NEW
  ├── Auto-Patrols         /admin/auto-patrols
  └── Diagnostic Rules     /admin/skills

ADMIN
  ├── Skills               /system/skills
  ├── Agent Memory         /admin/memories
  ├── Data Sources         /system/data-sources
  ├── Event Registry       /system/event-registry
  └── System Monitor       /system/monitor
```

### 3.1 Operations Center

| Route | Page | 說明 |
|-------|------|------|
| `/` | Dashboard | 單頁 Dashboard — 左右兩 card（告警 + 設備總覽）+ Quick Diagnostics |

Dashboard layout：
- **左 card**：最近關鍵告警 — severity 統計 + alarm list（點擊展開 trigger + diagnostic findings）
- **右 card**：設備總覽 — KPI（稼動率/運行中/告警/維護）+ equipment grid
- **底部**：Quick Diagnostics 快捷按鈕 → 觸發 AI Copilot

隱藏路由（不在 sidebar，Agent handoff 用）：
- `/events` — 全廠事件記錄
- `/lots` — 批次追蹤
- `/topology` — 製程物件拓撲圖

### 3.2 Knowledge Studio（/admin）

| Route | Page | 說明 |
|-------|------|------|
| `/admin/my-skills` | **My Skills** | 使用者個人 Skill 管理 — 列表、LLM 生成、編輯、Try-Run、刪除、升級（→ Auto-Patrol 或 Diagnostic Rule）。表單建立流程，生成時若 Phase 0 回 `clarify_needed` 則彈出 `ClarifyDialog` 補問 1~2 個商業邏輯問題 |
| `/admin/auto-patrols` | Auto-Patrols | 自動巡檢排程管理。同樣走表單建立 + 內嵌 clarification 中斷 |
| `/admin/skills` | Diagnostic Rules | 診斷規則管理（建立 / 編輯 / Try-Run / SSE 生成）。同樣走表單建立 + 內嵌 clarification 中斷 |

### 3.3 Admin

| Route | Page | 說明 |
|-------|------|------|
| `/system/skills` | Skills | 全 Skill 總覽 + detail review（Steps / Schema / Metadata） |
| `/admin/memories` | Agent Memory | 長期記憶管理（approve / reject） |
| `/system/data-sources` | Data Sources | System MCP 管理（endpoint_url / input_schema / sample fetch） |
| `/system/event-registry` | Event Registry | 事件登錄與 NATS 監控 |

## 4. 核心 Components

### 4.1 Shell & Layout

| Component | 說明 |
|-----------|------|
| `AppShell.tsx` | 頂層 layout — Topbar + Unified Sidebar (3 sections) + Main + AI Copilot |
| `Topbar.tsx` | 頂部導覽列 |
| `AnalysisPanel.tsx` | 中央分析結果面板（Contract 渲染，full-page overlay）。現在也渲染 Agent chat 中的 charts（contract flow 修正後，圖表從 Copilot 正確傳遞到 AnalysisPanel） |

### 4.2 AI Copilot（右側面板）

| Component | 說明 |
|-----------|------|
| `AICopilot.tsx` | Agent 對話主體 — SSE streaming、triggerMessage、contract state、handoff 處理 |
| `ChartIntentRenderer.tsx` | _chart DSL → Vega-Lite 動態生成 |
| `ContractCard.tsx` | Contract 摘要卡片 |

### 4.3 Contract 渲染

| Component | 說明 |
|-----------|------|
| `ContractRenderer.tsx` | AIOpsReportContract JSON → 結構化報告（summary + evidence + actions） |
| `EvidenceChain.tsx` | 證據鏈樹狀顯示 |
| `SuggestedActions.tsx` | 建議動作按鈕（agent / aiops_handoff / promote_analysis） |
| `VegaLiteChart.tsx` | Vega-Lite spec 渲染器 |
| `PlotlyVisualization.tsx` | Plotly 互動圖表 |
| `KpiCard.tsx` | KPI 指標卡片 |

### 4.4 Inline Clarification（表單建立中斷式補問）

2026-04-09：原本的 `SkillAuthoringChat`（多輪對話式 Skill 建立）已移除。改為在 3 個 admin 頁面既有的表單建立流程中，內嵌一次輕量的 clarification 中斷。

| Component | 說明 |
|-----------|------|
| `ClarifyDialog.tsx` | 520px 傳統 form modal（非 chat UI）— 顯示 1~2 個問題，每題 button options + optional freetext + 預設值。被 My Skills / Auto-Patrols / Diagnostic Rules 3 個頁面共用 |

**3 個 admin 頁面的 `handleGenerate` 拆分模式：**

```
handleGenerate(desc)              # 外層，使用者按「生成」按鈕
  → runGenerateStream(desc, skipClarify=false)
       ├─ SSE event "clarify_needed" → 停止 streaming → 開啟 ClarifyDialog
       └─ 正常 stream → 正常顯示

ClarifyDialog onConfirm(answers)
  → newDesc = desc + "\n\n" + answers 附加
  → runGenerateStream(newDesc, skipClarify=true)   # 第二次呼叫跳過 Phase 0
```

這個拆分讓生成流程可以在中途「暫停 / 補問 / 續跑」，不需要獨立的 authoring session。

### 4.5 Ontology 視覺化

| Component | 說明 |
|-----------|------|
| `TopologyCanvas.tsx` | 九類物件拓撲圖（D3/Canvas，node 顏色語意） |
| `EquipmentDetail.tsx` | 設備深潛面板（DC/SPC/Event/EC） |
| `OverviewDashboard.tsx` | 全廠概覽 dashboard |

## 5. API Routes（Proxy Layer）

aiops-app 的 API routes 全部是 **proxy** — 轉發到 `fastapi_backend_service`。

### 5.1 主要 Proxy

| Frontend API | Backend Target | 說明 |
|--------------|----------------|------|
| `POST /api/agent/chat` | `POST /api/v1/agent/chat/stream` | Agent SSE 對話（duplex streaming） |
| `GET /api/admin/skills` | `GET /api/v1/skill-definitions` | Skill 列表 |
| `POST /api/admin/rules/generate-steps/stream` | `POST /api/v1/diagnostic-rules/generate-steps/stream` | SSE Rule 生成 |
| `GET/POST /api/admin/auto-patrols` | `/api/v1/auto-patrols` | Auto-Patrol CRUD |
| `GET/POST /api/admin/alarms` | `/api/v1/alarms` | 告警管理 |
| `POST /api/admin/analysis/promote` | `POST /api/v1/analysis/promote` | 分析儲存為 My Skill |
| `GET/POST/PATCH/DELETE /api/admin/my-skills` | `/api/v1/my-skills` | My Skills CRUD |
| `POST /api/admin/my-skills/generate-steps/stream` | `POST /api/v1/my-skills/generate-steps/stream` | SSE My Skill 生成 |
| `POST /api/admin/my-skills/{id}/try-run` | `POST /api/v1/my-skills/{id}/try-run` | My Skill 試跑 |
| `POST /api/admin/my-skills/{id}/bind` | `POST /api/v1/my-skills/{id}/bind` | 升級 Skill binding_type |
| `GET /api/admin/automation/*` | `/api/v1/*` | Automation catch-all |
| `GET /api/ontology/*` | `/api/v1/ontology/*` | Ontology catch-all |
| `GET /api/mcp-catalog` | — | 回傳 MCP catalog（from store or catalog.ts） |

## 6. MCP Catalog（src/mcp/catalog.ts）

前端維護的完整 MCP 定義，注入到 Agent 的 system prompt：

| Category | Count | 範例 |
|----------|-------|------|
| Data MCPs | 8 | get_dc_timeseries, get_spc_data, get_lot_trace, query_object_parameter |
| Handoff MCPs | 3 | open_lot_trace, open_drill_down, open_topology |
| Automation MCPs | 8 | register_cron_job, test_run_skill, dispatch_action |
| **Total** | **19** | |

> 注意：Data MCPs 是「前端定義、供 Agent 參考」的 catalog，**實際的 System MCP 在 backend DB 中管理**。
> Catalog 的用途是讓 Agent 知道「有哪些工具可用 + 如何呼叫」。

## 7. State Management

### AppContext（唯一 Context Provider）

```typescript
{
  selectedEquipment: { equipment_id, name, status } | null
  triggerMessage: string | null           // 觸發 Agent 查詢
  contract: AIOpsReportContract | null    // 分析結果 → AnalysisPanel
  investigateMode: boolean                // 切換調查模式
}
```

## 8. 圖表渲染路徑

```
Agent tool result
  → render_card (backend adapter.py)
    → contract.visualization[] (Vega-Lite spec)
      → ContractRenderer → VegaLiteChart (中央 AnalysisPanel)

Agent text response
  → AICopilot (右側面板, markdown only, 不渲染圖表)
```

所有圖表 **只在中央 AnalysisPanel** 渲染，Copilot 只顯示文字。

## 9. 環境變數

| Variable | Default | 說明 |
|----------|---------|------|
| `NEXT_PUBLIC_FASTAPI_BASE` | `http://localhost:8000` | Backend API base URL |
| `AGENT_BASE_URL` | `http://localhost:8000` | Agent chat endpoint |
