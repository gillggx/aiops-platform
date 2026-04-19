# SPEC Supplement — Phase 2：MVP UI for Pipeline Builder

**Version:** 1.0 (Draft)
**Date:** 2026-04-18
**Status:** Draft — 待討論，尚未啟動
**Prerequisites:**
- ✅ Phase 1 PoC 通過（見 `docs/phase_1_test_report.md`）
- ✅ 後端 Execution Engine + 5 積木 + REST API 已就緒
- ⏳ 本文件需使用者 review 並回答 §10 開放議題後才能動工

---

## 1. Context & Objective

### 1.1 接續 Phase 1
Phase 1 已完成後端 DAG 執行引擎與 5 個標準積木，但**使用者完全看不到**——目前只能透過 curl / Postman 操作。

### 1.2 Phase 2 目標
建立前端 Visual Pipeline Builder UI，讓 **PE 能不靠 Agent、也不靠工程師，獨立完成：**
1. 在畫布上拖拽組合 pipeline
2. 調整節點參數、預覽中間資料
3. 儲存為 Draft，管理生命週期（Draft → Pi-run → Production）
4. 執行並觀察結果

### 1.3 Go/No-Go 成功標準
- [ ] PE 可獨立完成「EQP-01 SPC 連續 OOC 巡檢」範例（不靠 Agent）
- [ ] 從開啟 Builder 到點 Deploy 成功 < 10 分鐘
- [ ] 5 個積木的 Inspector 表單能從 param_schema 自動生成，不需手刻 UI
- [ ] 節點執行結果（含錯誤）能在 UI 上即時顯示

### 1.4 非目標（Out of Scope — 延到後續 Phase）
- ❌ Agent 自動建圖 / Glass Box tool API（Phase 3）
- ❌ Custom Block 編輯器（Phase 4）
- ❌ 多人同步編輯（延後）
- ❌ 完整 Review / Approval workflow（先留 schema，實作晚點）
- ❌ 積木擴充到 14 個（先撐起 5 個 → 驗 UI → 再擴充）

---

## 2. Architecture & Design

### 2.1 前端技術棧

| 項目 | 選擇 | 理由 |
|---|---|---|
| Framework | Next.js (既有) | 沿用 aiops-app |
| DAG Library | **React Flow** (MIT) | 業界標準、API 穩定、社群活躍 |
| 表單生成 | **@rjsf/core** (React JSON Schema Form) | 從 param_schema 自動產表單，零手刻 |
| 狀態管理 | Zustand (輕量) 或 React Context | 目前專案未用 Redux；避免過度設計 |
| 樣式 | 沿用現有 inline style pattern | 符合 CLAUDE.md 規範 |
| HTTP client | 沿用 `/api/` proxy 模式 | 不直接打 backend |

### 2.2 四象限佈局（Layout）

```
┌───────────────────────────────────────────────────────────────────┐
│  Header: [Pipeline Name] [Status Badge] [Save] [Deploy] [Run]     │
├────────────┬─────────────────────────────────────┬────────────────┤
│            │                                     │                │
│  Block     │          DAG Canvas                 │  Node          │
│  Library   │          (React Flow)               │  Inspector     │
│  (left)    │                                     │  (right)       │
│            │                                     │                │
│  ≈ 220px   │          flex-1                     │  ≈ 320px       │
│            │                                     │                │
├────────────┴─────────────────────────────────────┴────────────────┤
│                                                                   │
│          Data Preview Panel (bottom, collapsible)                 │
│          Shows output of selected node                            │
│          ≈ 280px                                                  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 2.3 前後端接點（新增 API）

除了 Phase 1 已有的 4 個 endpoint，Phase 2 需新增：

| Method | Path | 用途 |
|---|---|---|
| GET | `/pipeline-builder/pipelines` | List 所有 pipelines（可按 status filter） |
| GET | `/pipeline-builder/pipelines/{id}` | Load 指定 pipeline（含 pipeline_json） |
| POST | `/pipeline-builder/pipelines` | Save new pipeline as Draft |
| PUT | `/pipeline-builder/pipelines/{id}` | Update pipeline（僅 Draft/Pi-run 可改） |
| POST | `/pipeline-builder/pipelines/{id}/promote` | 升級 status（Draft→Pi-run→Production） |
| POST | `/pipeline-builder/pipelines/{id}/fork` | Fork Production 成新 Draft |
| POST | `/pipeline-builder/pipelines/{id}/deprecate` | 標為 deprecated |
| POST | `/pipeline-builder/preview/{node_id}` | 只跑到指定 node，回傳該 node 的 preview（Data Preview 面板用） |

Frontend proxy routes：所有對應到 `aiops-app/app/api/pipeline-builder/...`。

### 2.4 Pipeline 儲存策略

- **Auto-save Draft**：編輯中每 5 秒或離開前自動存（防止丟失）
- **Explicit save**：Save 按鈕 → 明確版本（version bump）
- **Deploy 前 Pre-flight**：必須通過 Validator 才能 promote

### 2.5 Status 管理 UI

```
┌─ Status Badge (header 右側) ─┐
│  🟡 Draft  ─► [Promote to Pi-run]  
│  🔵 Pi-run  ─► [Promote to Production]  [Back to Draft ❌]
│  🟢 Production  ─► [Fork to new Draft]  [Deprecate]
│  ⚫ Deprecated (read-only)
└──────────────────────────────┘
```

Status 轉換規則（對應 SPEC §5.3）：
- 降級 (Production → Draft) **禁止**
- Production 修改 → fork 新 Draft
- Deprecate 為終態

---

## 3. 前端模組規劃

### 3.1 檔案結構

```
aiops-app/
├── app/
│   ├── pipeline-builder/                    ★ 新增頁面
│   │   ├── page.tsx                          # /pipeline-builder (list)
│   │   ├── [id]/page.tsx                     # /pipeline-builder/{id} (editor)
│   │   └── new/page.tsx                      # /pipeline-builder/new
│   └── api/
│       └── pipeline-builder/                ★ 新增 proxy routes
│           ├── blocks/route.ts
│           ├── pipelines/route.ts
│           ├── pipelines/[id]/route.ts
│           ├── pipelines/[id]/promote/route.ts
│           ├── execute/route.ts
│           ├── validate/route.ts
│           └── preview/[nodeId]/route.ts
│
├── components/
│   └── pipeline-builder/                    ★ 新增元件
│       ├── BuilderLayout.tsx                 # 四象限主佈局
│       ├── BlockLibrary.tsx                  # 左側積木庫
│       ├── DagCanvas.tsx                     # React Flow 包裝
│       ├── NodeInspector.tsx                 # 右側參數表單
│       ├── DataPreviewPanel.tsx              # 底部資料預覽
│       ├── StatusBadge.tsx                   # 狀態徽章
│       ├── DeployDialog.tsx                  # Deploy 確認對話框
│       ├── CustomNode.tsx                    # React Flow custom node 外觀
│       └── hooks/
│           ├── useBuilderState.ts            # Zustand store
│           ├── useAutoSave.ts
│           └── usePreview.ts
│
└── lib/
    └── pipeline-builder/
        ├── schema.ts                         # Pipeline JSON TS types
        ├── validators.ts                     # client-side quick validation
        └── block-style.ts                    # 積木顏色 / icon 對照
```

### 3.2 Block Library（左側）
- 依 category 分組：📥 Sources / ⚙️ Transforms / 🧠 Logic / 🚀 Outputs / 🔧 Custom
- 每個積木可拖曳到畫布
- 搜尋框（積木多時用）
- 積木上顯示 status badge（Pi-run 黃色、Production 綠色）

### 3.3 DAG Canvas（中央）
- React Flow default edge + custom node
- 節點顏色對應 category（對齊 SPEC wireframe）
- 支援：拖拽、連線、多選、刪除、鍵盤 shortcut（Ctrl+Z undo / Delete）
- 連線時即時檢查 port 型別，不相容標紅

### 3.4 Node Inspector（右側）
- 點選節點時顯示
- 表單 **從 block.param_schema 自動產生**（@rjsf）
- 支援 live validation（輸入錯即紅框提示）
- 參數修改後觸發 preview 重跑（debounced 800ms）

### 3.5 Data Preview（底部）
- 預設顯示選定節點的 output（table 呈現）
- 若節點尚未執行，顯示「點 Preview 按鈕跑到這裡」
- 資料量大時取樣（對齊 SPEC §6.2 `builder.preview` 的 sample_size=100）
- 錯誤時顯示紅色錯誤訊息 + hint

### 3.6 Header 操作區
- Pipeline 名稱（可重命名）
- Status Badge + promotion 按鈕
- [Save] — manual save
- [Validate] — 顯示驗證結果 drawer
- [Run] — 整條 pipeline 跑一次
- [Deploy] — 僅 Production status 可見（走 systemd / scheduler 掛載）

---

## 4. Step-by-Step Execution Plan

### Phase 2.0 — 後端 API 補齊（2 週，1 人）
- [ ] Pipeline CRUD endpoints（list / get / create / update）
- [ ] Status promotion / fork / deprecate endpoints
- [ ] `POST /preview/{node_id}` — 部分執行到指定節點回傳 preview
- [ ] 擴充 PipelineRepository / 新增 canvas_operations 紀錄（save 時寫 audit）
- [ ] 所有新 endpoint 加 unit test

### Phase 2.1 — Frontend 骨架（2 週，1 人）
- [ ] `/pipeline-builder` list 頁（簡單 table，可新建）
- [ ] `/pipeline-builder/{id}` editor 四象限骨架
- [ ] API proxy routes 建立
- [ ] Zustand store 定義 + 基本 state 管理
- [ ] Auto-save 機制（5s debounce）

### Phase 2.2 — Canvas + Inspector（3 週，1 人）
- [ ] React Flow 整合（custom node / edge / controls）
- [ ] 拖拽積木從 library → canvas
- [ ] 節點連線 + port 型別即時檢查
- [ ] Node Inspector：@rjsf + param_schema 自動表單
- [ ] 鍵盤 shortcut + undo/redo

### Phase 2.3 — Preview + Validate + Deploy（2 週，1 人）
- [ ] Data Preview Panel（點節點 → 跑 preview → 顯示 table）
- [ ] Validate drawer（顯示 7 條規則檢查結果）
- [ ] Status 管理 UI（Badge + promotion 按鈕 + fork 流程）
- [ ] Deploy 流程（確認對話框 + 成功/失敗 toast）

### Phase 2.4 — QA + 整合（1 週，1–2 人）
- [ ] E2E 手動測試：PE 完成 sample pipeline
- [ ] 跨瀏覽器測試（Chrome / Edge / Safari）
- [ ] 效能測試：20 節點 canvas 流暢度
- [ ] 撰寫 `docs/phase_2_test_report.md`

**Phase 2 合計：~10 週（2.5 個月）/ 1 人為主、末期 2 人**

---

## 5. 積木庫擴充策略

Phase 2 不強求把積木擴充到 14 個，建議分批：

### 5.1 立即擴充（Phase 2.2 前完成）— 3 個
為了讓 UI 有東西可組合，這 3 個高頻積木先做：
- `block_join` — 兩份 df by key 合併
- `block_groupby_agg` — 分組聚合
- `block_chart` — 取代現有 chart_middleware 做輸出

### 5.2 Phase 2.3 之後按需補充
- `block_rolling_window`
- `block_select_columns`
- `block_tool_status`（MCP）
- `block_isolation_forest`（ML — 複雜，建議晚做）
- `block_transfer_learning`（ML — 複雜，建議晚做）
- `block_save_to_mcp`

### 5.3 新增積木的 SOP
1. 在 `app/services/pipeline_builder/blocks/` 新增 executor class
2. 在 `seed.py` 加 block spec
3. `BUILTIN_EXECUTORS` 註冊
4. 寫對應 unit test
5. 驗證 Inspector 表單能自動產（如 param_schema 複雜可能需調整 @rjsf uiSchema）

---

## 6. UI/UX 設計原則（對齊既有 Design Guidelines）

依 `docs/SPEC_ui_guidelines.md`（2026-04 版）：

- **字級**：Canvas 標題 14px、節點 body 12–13px、Inspector label 12px
- **色系**：對齊 SPEC wireframe 的 4 類 category 色（Source 綠 / Transform 橘 / Logic 紫 / Output 紅 / Custom 紅框 + ⚠️）
- **緊湊度**：左側積木庫 220px、右側 Inspector 320px（與 Alarm Center 一致）
- **動畫**：React Flow 內建平滑動畫；節點新增/刪除 fade-in/out 200ms

---

## 7. 效能與可用性考量

| 項目 | 目標 | 對策 |
|---|---|---|
| Canvas 流暢度 | 20 節點無卡頓 | React Flow 本身效能夠；避免 Inspector rerender 全 canvas |
| Preview 反應時間 | < 2s（小資料） | Backend 已驗證 < 0.2s；UI 顯示 skeleton |
| Auto-save 失敗處理 | 不丟資料 | local storage backup + offline 佇列 |
| Pipeline JSON 大小 | 50 節點以內 | 目前無疑慮，未來可 lazy-load |
| Undo history 長度 | 最近 50 步 | 超過就裁剪 |

---

## 8. 測試策略

### 8.1 後端（延續 Phase 1 pattern）
- 新增 endpoint 全走 pytest + TestClient
- Pipeline CRUD 覆蓋率目標 ≥ 70%

### 8.2 前端
- **Component test**：Vitest + React Testing Library
  - BlockLibrary 渲染
  - DagCanvas drag-drop 邏輯
  - NodeInspector 表單 validation
- **E2E test**：Playwright（可選）
  - 完整建一條 pipeline → save → run → 看結果

### 8.3 手動驗收（QA Checklist 草案）
會在 Phase 2 啟動時展開，預計 40 項左右（UI 類驗收較多）。

---

## 9. Edge Cases & Risks

### 9.1 技術風險

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| R1 | @rjsf 產出的表單樣式不貼合 Design Guidelines | 高 | 中 | uiSchema 客製 + 必要時自刻 widget |
| R2 | React Flow 與 Next.js SSR 相容性（hydration 警告） | 中 | 中 | dynamic import with ssr: false |
| R3 | Auto-save 過於頻繁打後端 | 中 | 低 | 5s debounce + 只在有變更時送 |
| R4 | Preview 對大資料爆 memory | 低 | 高 | Backend sample_size 強制上限 1000 |
| R5 | Status 降級漏洞 | 中 | 高 | Backend 強制檢查 + Frontend 灰掉按鈕 |
| R6 | Pipeline JSON schema 變動影響舊資料 | 中 | 中 | version 欄位 + migration script |

### 9.2 UX 風險

| # | 風險 | 緩解 |
|---|---|---|
| UX1 | PE 看不懂 port 型別不相容 | 連線失敗時彈 tooltip 解釋 |
| UX2 | Inspector 表單太空/太擠 | 依 param_schema 複雜度用 collapse section |
| UX3 | Validator 錯誤列表嚇跑使用者 | 摺疊 + 分類 + 逐條點擊跳到對應節點 |
| UX4 | Deploy 誤觸 | 二次確認 dialog + 顯示 diff |

---

## 10. 開放議題（Phase 2 啟動前需決策）

- [ ] **Q1** — 前端 state 管理：**Zustand vs React Context**？（建議 Zustand：輕量、無 provider 地獄）
- [ ] **Q2** — Auto-save 是否預設開啟？還是使用者手動 save？
- [ ] **Q3** — Deploy 按鈕是否需要另一個 approver？（目前建議：PE admin 可自 approve，Phase 4 再上 workflow）
- [ ] **Q4** — Pipeline JSON 儲存格式要不要 gzip？（目前建議：否，DB Text 直接存可讀性高）
- [ ] **Q5** — 是否在這個 Phase 就處理 i18n？（建議：否，標籤先中文 hardcode）
- [ ] **Q6** — 積木 library 是否按 category 分 tab 還是 accordion？（建議：accordion，直覺）
- [ ] **Q7** — Pipeline 是否支援「複製一份我的 Production 到我自己 workspace 改」？（類似 fork 但是個人版）

---

## 11. Phase 2 → Phase 3 接軌點

Phase 2 完成後，下階段（Agent Glass Box）需具備：
- **Canvas Operation API**（Phase 2 已以「user 端觸發」實作）— Phase 3 改讓 Agent 呼叫同一套
- **WebSocket 通道** — Phase 2 可先不做（純 HTTP 也能動），但 Phase 3 必要
- **`canvas_operations` 紀錄表** — Phase 1 schema 已就位；Phase 2 save/edit 時開始寫；Phase 3 Agent 寫入變多

若 Phase 2 過程中發現這些接口設計有問題，應在此階段一併修正，**不留到 Phase 3 再改**（那時風險更高）。

---

## 12. 成本與 ROI

- **工時：** ~10 週 / 2.5 個月 / ~4 人月
- **累積到 Phase 2 底的投入：** Phase 1 (~1.7 人月) + Phase 2 (~4 人月) = **~5.7 人月**
- **關鍵里程碑：** Phase 2 結束時，**PE 可自助建規則**——這是本專案第一次達成「不需工程師介入」的目標，策略價值極高

---

## 13. 待討論

請使用者 review 以下三點後決定是否啟動：

1. **Scope 是否合意？** 本 Spec 提議 Phase 2 不做 Agent 整合（延後到 Phase 3），UI 先撐起「人工操作」。同意嗎？
2. **§10 開放議題 Q1–Q7** — 哪些現在就想定？哪些延後到啟動前？
3. **資源配置** — 目前預設 1 人為主、末期 2 人。若希望加速可討論 2 人平行的拆分方式（建議分工：一人後端 + API proxy，一人 React Flow canvas + Inspector）

**備註：** 本文件為 Phase 1 完成後自動產出的討論草稿。Phase 2 已於 2026-04-18 授權啟動。

---

## 14. Phase 2 實作子規格（MVP UI）

> **狀態：** Approved 2026-04-18，已啟動開發
> **範圍：** 人工 UI（不含 Agent 整合）
> **預估：** ~8–10 週 / 1 人為主

### 14.1 已決策議題（§10 開放問題的回答）

| # | 議題 | 決策 | 理由 |
|---|---|---|---|
| Q1 | 前端 state 管理 | **React Context + useReducer** | 專案既有 pattern（FlatDataContext / AppContext），避免引入新 dep；Zustand 的輕量紅利對單頁編輯器有限 |
| Q2 | Auto-save | ❌ 不自動存，**手動 Save 按鈕** | 使用者明確要求；降低後端寫入壓力與 race condition 風險 |
| Q3 | Deploy approval | PE admin 可自 approve | Review workflow 延到 Phase 4 |
| Q4 | Pipeline JSON gzip | ❌ 不壓縮 | 可讀性優先，50 節點內的 JSON 大小不是問題 |
| Q5 | i18n | ❌ 不做 | 標籤中文 hardcode，Phase 2 不涉 |
| Q6 | Block library UI | **Accordion** 分類 | 直覺、可摺疊 |
| Q7 | 個人版 fork | ✅ 支援 | 使用者可把 Production 複製到 personal workspace 改；不影響 Production |
| — | 資源 | **1 人開發** | 末期若排程緊可補第 2 人做手動 QA |

### 14.2 技術選型確認

| 項目 | 選擇 |
|---|---|
| DAG Library | `@xyflow/react` v12（專案已裝） |
| 自動佈局 | `@dagrejs/dagre`（專案已裝） |
| 表單生成 | **自刻輕量 schema-form 元件**（不引入 @rjsf，避免多 dep） |
| State | React Context + useReducer（含 undo stack） |
| 樣式 | inline style（對齊既有 admin 頁面） |
| 後端 API 前綴 | `/api/pipeline-builder/` (frontend proxy) → `http://backend/api/v1/pipeline-builder/` |

### 14.3 檔案結構（新增）

```
fastapi_backend_service/app/
├── routers/pipeline_builder_router.py         ← 擴充：新增 Pipeline CRUD + promote/fork/preview
├── repositories/pipeline_repository.py        ← 擴充：更多查詢/更新方法
└── services/pipeline_builder/blocks/
    ├── join.py                                 ★ 新增
    ├── groupby_agg.py                          ★ 新增
    └── chart.py                                ★ 新增

aiops-app/src/
├── app/
│   └── admin/
│       └── pipeline-builder/                  ★ 新增
│           ├── page.tsx                        # list
│           ├── new/page.tsx                    # 新建（create → redirect）
│           └── [id]/page.tsx                   # editor 四象限
│   └── api/pipeline-builder/                  ★ 新增 proxy
│       ├── blocks/route.ts
│       ├── pipelines/route.ts
│       ├── pipelines/[id]/route.ts
│       ├── pipelines/[id]/promote/route.ts
│       ├── pipelines/[id]/fork/route.ts
│       ├── pipelines/[id]/deprecate/route.ts
│       ├── execute/route.ts
│       ├── validate/route.ts
│       └── preview/[nodeId]/route.ts
├── components/pipeline-builder/               ★ 新增
│   ├── BuilderLayout.tsx
│   ├── BlockLibrary.tsx
│   ├── DagCanvas.tsx
│   ├── CustomNode.tsx
│   ├── NodeInspector.tsx
│   ├── SchemaForm.tsx                           # 自刻 param_schema → form
│   ├── DataPreviewPanel.tsx
│   ├── StatusBadge.tsx
│   └── ValidationDrawer.tsx
├── context/pipeline-builder/                  ★ 新增
│   ├── BuilderContext.tsx                       # Context + reducer + actions
│   └── types.ts
└── lib/pipeline-builder/                      ★ 新增
    ├── api.ts                                   # fetch wrappers
    └── dag-layout.ts                            # Dagre 自動排版
```

### 14.4 任務清單（T1–T12）

| # | 任務 | 預估 | 產出 |
|---|---|---|---|
| T1 | Backend：Pipeline CRUD + promote/fork/deprecate + preview endpoints | 2 days | 擴充 `pipeline_builder_router.py` + `pipeline_repository.py` |
| T2 | 3 積木擴充（join / groupby_agg / chart） | 1 day | `blocks/join.py`, `blocks/groupby_agg.py`, `blocks/chart.py` + seed 更新 |
| T3 | Frontend proxy routes（9 條路由） | 0.5 day | `app/api/pipeline-builder/*` |
| T4 | Pipeline list 頁 | 0.5 day | `app/admin/pipeline-builder/page.tsx` |
| T5 | Editor 骨架 + BuilderContext（含 undo stack） | 1 day | `context/pipeline-builder/*`, `app/admin/pipeline-builder/[id]/page.tsx` |
| T6 | BlockLibrary（accordion） | 1 day | `components/pipeline-builder/BlockLibrary.tsx` |
| T7 | DagCanvas（React Flow 整合 + CustomNode） | 2 days | `components/pipeline-builder/DagCanvas.tsx`, `CustomNode.tsx` |
| T8 | NodeInspector + SchemaForm | 2 days | `NodeInspector.tsx`, `SchemaForm.tsx` |
| T9 | DataPreviewPanel | 1 day | `DataPreviewPanel.tsx` |
| T10 | StatusBadge + promotion / fork / deprecate 按鈕流程 | 1 day | `StatusBadge.tsx` + dialog components |
| T11 | Backend tests + frontend smoke tests | 1 day | `tests/pipeline_builder/test_phase2_crud.py` + Playwright optional |
| T12 | `phase_2_test_report.md` | 0.5 day | 驗收報告 |
| — | 合計 | **~13 working days** | Phase 2 MVP 完成 |

### 14.5 Phase 2 QA Checklist（45 項驗收）

開發完成後在 `docs/phase_2_test_report.md` 逐項勾選。

#### A. Backend API（8 項）
- [ ] A1：`GET /pipeline-builder/pipelines` 列表回傳正確
- [ ] A2：`POST /pipeline-builder/pipelines` 建立 Draft 成功
- [ ] A3：`GET /pipeline-builder/pipelines/{id}` 可讀回 pipeline_json
- [ ] A4：`PUT /pipeline-builder/pipelines/{id}` 可更新 Draft/Pi-run（Production 拒絕）
- [ ] A5：`POST /pipelines/{id}/promote` 正確切換 status
- [ ] A6：`POST /pipelines/{id}/fork` 從 Production 產生新 Draft（parent_id 正確）
- [ ] A7：`POST /pipelines/{id}/deprecate` 標為 deprecated
- [ ] A8：`POST /preview/{node_id}` 跑到指定節點並回傳資料

#### B. 擴充積木（3 項）
- [ ] B1：`block_join` 兩表 by key inner/left 合併成功
- [ ] B2：`block_groupby_agg` mean/sum/count/max/min 聚合正確
- [ ] B3：`block_chart` 輸出 chart spec（Phase 2 輸出 vega-lite spec 字串，無需 render）

#### C. Pipeline List 頁（5 項）
- [ ] C1：頁面路徑 `/admin/pipeline-builder` 可訪問
- [ ] C2：列表顯示所有 pipeline（名稱、狀態、建立時間）
- [ ] C3：可用 Status filter
- [ ] C4：「新建」按鈕導至 editor（`/admin/pipeline-builder/new`）
- [ ] C5：點列項導至 editor（`/admin/pipeline-builder/{id}`）

#### D. Editor 四象限佈局（4 項）
- [ ] D1：左側 BlockLibrary、中央 Canvas、右側 Inspector、底部 DataPreview 全顯示
- [ ] D2：分隔線可拖拽調整（react-resizable-panels）
- [ ] D3：Header 顯示 pipeline name + status badge
- [ ] D4：右側 Inspector 在未選節點時顯示 placeholder

#### E. BlockLibrary（4 項）
- [ ] E1：依 category accordion 分組（Sources / Transforms / Logic / Outputs / Custom）
- [ ] E2：每個 category 預設展開；可點擊摺疊
- [ ] E3：積木可拖拽至畫布生成新節點
- [ ] E4：積木顯示 status badge（Production / Pi-run）

#### F. DAG Canvas（9 項）
- [ ] F1：節點顯示正確顏色（依 category）
- [ ] F2：節點可拖曳、位置會持久化到 pipeline_json
- [ ] F3：節點之間可連線（拖拽 port）
- [ ] F4：Port 型別不相容時連線失敗 + tooltip 提示
- [ ] F5：刪除節點移除相關 edges
- [ ] F6：點選節點顯示 active border + 同步右側 Inspector + 底部 Preview
- [ ] F7：鍵盤 Delete 刪除選中節點/邊
- [ ] F8：Ctrl+Z / Ctrl+Y undo / redo 正確
- [ ] F9：「自動排版」按鈕用 Dagre 重排

#### G. Node Inspector + SchemaForm（7 項）
- [ ] G1：點選節點後自動載入 param_schema
- [ ] G2：支援 string / number / integer / boolean / enum / array 欄位
- [ ] G3：Required 欄位未填時紅框提示
- [ ] G4：Enum 欄位以下拉選單呈現
- [ ] G5：修改後 debounce 800ms 觸發 preview 重跑
- [ ] G6：不同節點切換時表單狀態不互相污染
- [ ] G7：節點顯示名稱可編輯（修改節點 display label）

#### H. Data Preview Panel（5 項）
- [ ] H1：點節點時預設顯示該節點 output
- [ ] H2：Table 分欄顯示（最多 30 欄，超過顯示「...」）
- [ ] H3：大資料量取樣至前 100 筆 + 顯示 total 計數
- [ ] H4：節點未執行時顯示「點 Preview」按鈕觸發
- [ ] H5：節點執行失敗時顯示紅色錯誤訊息 + hint

#### I. Status 管理 UI（5 項）
- [ ] I1：Status Badge 顏色正確（Draft 灰 / Pi-run 黃 / Production 綠 / Deprecated 暗）
- [ ] I2：Draft → Pi-run promotion 按鈕可點
- [ ] I3：Pi-run → Production 前強制走 Validator，失敗時不允許
- [ ] I4：Production 的 Fork 按鈕可產生新 Draft（parent 關係正確）
- [ ] I5：Deprecate 後 Editor 進入唯讀模式

#### J. 儲存 / 執行 / 驗證（8 項）
- [ ] J1：Save 按鈕成功寫入後端 + toast 提示
- [ ] J2：Validate 按鈕打開 drawer 顯示 7 條規則結果
- [ ] J3：驗證錯誤可點擊跳到對應節點
- [ ] J4：Run 按鈕跑整條 pipeline + 節點顯示 success/failed 狀態
- [ ] J5：Run 結果寫入 pipeline_runs + 可在右側看到最新 run 摘要
- [ ] J6：離開頁面時若有未儲存變更彈出確認 dialog
- [ ] J7：只讀模式（Deprecated / 非擁有者 Production）所有編輯操作 disabled
- [ ] J8：Fork 支援 personal workspace 概念（pipeline.metadata.fork_of 紀錄來源）

### 14.6 完成後產出

1. **`docs/phase_2_test_report.md`** — 逐項 QA + screenshots
2. **啟動 dev server 讓使用者實測** — `npm run dev` in `aiops-app/`
3. **若全綠：自動產出 Phase 3（Agent Glass Box）補充 spec**

---

**END OF PHASE 2 SUPPLEMENT**
