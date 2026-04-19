# Phase 2 Test Report — Pipeline Builder MVP UI

**Report Date:** 2026-04-18
**Scope:** SPEC_pipeline_builder_phase2 §14 — 人工 UI，不含 Agent 整合
**Result:** 🟡 **Backend / Build 全綠；UI 類驗收待使用者人工實測**

---

## Executive Summary

| 指標 | 目標 | 實際 | 結論 |
|---|---|---|---|
| Backend 自動化測試 | 全綠 | **46 passed / 0 failed** | ✅ PASS |
| 新增 endpoint 可用 | 8 / 8 | 8 / 8 覆蓋 | ✅ PASS |
| 新增積木可執行 | 3 / 3 | 3 / 3 | ✅ PASS |
| Frontend 型別檢查 | 無錯誤 | `tsc --noEmit` clean | ✅ PASS |
| Frontend production build | 成功 | 3 pages + 9 proxies built | ✅ PASS |
| Coverage (Phase 1+2 模組) | ≥ 70% | **87%** | ✅ PASS |
| UI 人工驗收 | 45 項 | ⏳ 待使用者實測 | ⏳ PENDING |

---

## 1. 交付清單

### 1.1 Backend 新增 / 擴充
- `app/repositories/pipeline_repository.py` — 新增 `update`, `update_status` 方法
- `app/routers/pipeline_builder_router.py` — 擴充 8 個 endpoint
- `app/services/pipeline_builder/blocks/join.py` ★
- `app/services/pipeline_builder/blocks/groupby_agg.py` ★
- `app/services/pipeline_builder/blocks/chart.py` ★
- `app/services/pipeline_builder/seed.py` — seed 多了 3 個積木（共 8 個）
- `tests/pipeline_builder/test_phase2_crud.py` — 14 test cases

### 1.2 Frontend 新增
```
aiops-app/src/
├── app/
│   ├── admin/pipeline-builder/
│   │   ├── page.tsx                    # 列表頁
│   │   ├── new/page.tsx                # 新建
│   │   └── [id]/page.tsx               # 編輯器
│   └── api/pipeline-builder/           # 9 條 proxy routes
│       ├── _common.ts
│       ├── blocks/route.ts
│       ├── pipelines/route.ts
│       ├── pipelines/[id]/route.ts
│       ├── pipelines/[id]/promote/route.ts
│       ├── pipelines/[id]/fork/route.ts
│       ├── pipelines/[id]/deprecate/route.ts
│       ├── execute/route.ts
│       ├── validate/route.ts
│       └── preview/route.ts
├── components/pipeline-builder/
│   ├── BuilderLayout.tsx               # 四象限主佈局 + header 操作
│   ├── BlockLibrary.tsx                # 左側 accordion
│   ├── DagCanvas.tsx                   # React Flow + Dagre 自動排版
│   ├── CustomNode.tsx                  # 節點外觀 + port handles
│   ├── NodeInspector.tsx               # 右側面板
│   ├── SchemaForm.tsx                  # JSON-schema → form widgets
│   ├── DataPreviewPanel.tsx            # 底部資料預覽
│   ├── StatusBadge.tsx                 # 狀態徽章
│   └── ValidationDrawer.tsx            # 驗證結果抽屜
├── context/pipeline-builder/
│   └── BuilderContext.tsx              # Context + reducer + undo/redo (max 50)
└── lib/pipeline-builder/
    ├── api.ts                          # fetch wrappers
    ├── types.ts                        # 型別定義
    └── style.ts                        # category / status 色系
```

**檔案總計：** Backend 7 檔修改/新增、Frontend 22 檔新增

---

## 2. Backend 自動化驗收

### 2.1 測試執行結果
```
============================= test session starts ==============================
collected 46 items

tests/pipeline_builder/test_blocks.py ............        [26%]
tests/pipeline_builder/test_executor.py ....              [34%]
tests/pipeline_builder/test_phase2_crud.py ..............  [65%]
tests/pipeline_builder/test_smoke_e2e.py .....            [76%]
tests/pipeline_builder/test_validator.py ...........      [100%]

======================== 46 passed in 1.45s ========================
```

### 2.2 Coverage report
```
app/repositories/block_repository.py        64%
app/repositories/pipeline_repository.py     93%  ← Phase 2 新增方法全覆蓋
app/routers/pipeline_builder_router.py      91%  ← 8 個新 endpoint 高覆蓋
app/services/pipeline_builder/blocks/*      63%-100%
app/services/pipeline_builder/executor.py   84%
app/services/pipeline_builder/validator.py  92%
───────────────────────────────────────────────
TOTAL                                         87%
```

### 2.3 QA Section A — Backend API（8 / 8 ✅）

| # | 項目 | 結果 | 對應測試 |
|---|---|---|---|
| A1 | `GET /pipelines` 列表 | ✅ | `test_a1_list_pipelines_empty_initially` |
| A2 | `POST /pipelines` 建立 Draft | ✅ | `test_a2_create_pipeline` |
| A3 | `GET /pipelines/{id}` 讀 JSON | ✅ | `test_a3_get_pipeline_reads_json` |
| A4 | `PUT /pipelines/{id}` 更新 (Production 拒絕) | ✅ | `test_a4_update_pipeline_draft_ok`, `test_a5d_production_update_blocked` |
| A5 | `POST /promote` 正確切換 status（跳級禁止） | ✅ | `test_a5_promote_draft_to_pi_run`, `test_a5b_promote_to_production_requires_valid_pipeline`, `test_a5c_draft_to_production_blocked` |
| A6 | `POST /fork` 產生新 Draft + parent_id 正確 | ✅ | `test_a6_fork_production_to_draft` |
| A7 | `POST /deprecate` | ✅ | `test_a7_deprecate` |
| A8 | `POST /preview` 跑到指定節點 | ✅ | `test_a8_preview_up_to_node` |

### 2.4 QA Section B — 擴充積木（3 / 3 ✅）

| # | 項目 | 結果 | 對應測試 |
|---|---|---|---|
| B1 | `block_join` inner merge | ✅ | `test_b1_block_join` |
| B2 | `block_groupby_agg` mean 聚合 | ✅ | `test_b2_block_groupby_agg` |
| B3 | `block_chart` 產 vega-lite spec | ✅ | `test_b3_block_chart` |

---

## 3. Frontend 建置與型別驗收

### 3.1 Type check
```
> tsc --noEmit
(no errors)
```

### 3.2 Production build
所有目標頁面 / API routes 編譯成功：
```
├ ○ /admin/pipeline-builder              2.39 kB   107 kB
├ ƒ /admin/pipeline-builder/[id]         1.56 kB   103 kB
├ ○ /admin/pipeline-builder/new          1.32 kB   103 kB
├ ƒ /api/pipeline-builder/blocks            282 B
├ ƒ /api/pipeline-builder/execute           282 B
├ ƒ /api/pipeline-builder/pipelines         282 B
├ ƒ /api/pipeline-builder/pipelines/[id]    282 B
├ ƒ /api/pipeline-builder/pipelines/[id]/deprecate   282 B
├ ƒ /api/pipeline-builder/pipelines/[id]/fork        282 B
├ ƒ /api/pipeline-builder/pipelines/[id]/promote     282 B
├ ƒ /api/pipeline-builder/preview                    282 B
├ ƒ /api/pipeline-builder/validate                   282 B
```

---

## 4. UI QA Checklist — 待使用者實測（37 項）

以下項目需使用者啟動 dev server 並在瀏覽器逐一驗收。
建議操作流程：

### 4.1 啟動步驟

```bash
# Terminal 1 — backend
cd /Users/gill/metagpt_pure/workspace/fastapi_backend_refactored/fastapi_backend_service
python -m uvicorn main:app --port 8001 --reload

# Terminal 2 — frontend
cd /Users/gill/metagpt_pure/workspace/fastapi_backend_refactored/aiops-app
FASTAPI_BASE_URL=http://localhost:8001 npm run dev

# 瀏覽器
http://localhost:3000/admin/pipeline-builder
```

### 4.2 QA Section C — Pipeline List 頁（5 項）

- [ ] C1：訪問 `/admin/pipeline-builder` 成功載入
- [ ] C2：列表顯示 pipelines（若無則顯示提示訊息）
- [ ] C3：Status filter 按鈕切換成功（all / draft / pi_run / production / deprecated）
- [ ] C4：點「新建 Pipeline」進入 `/admin/pipeline-builder/new`
- [ ] C5：點列表項進入編輯器 `/admin/pipeline-builder/{id}`

### 4.3 QA Section D — Editor 四象限佈局（4 項）

- [ ] D1：四個面板齊全（左側 BlockLibrary / 中央 Canvas / 右側 Inspector / 底部 DataPreview）
- [ ] D2：Header 顯示 pipeline 名稱（可編輯）+ StatusBadge
- [ ] D3：Canvas 有背景點、右下 MiniMap、左下 Controls（縮放 / fit）
- [ ] D4：未選節點時 Inspector 顯示「選取畫布上的節點...」placeholder

### 4.4 QA Section E — BlockLibrary（4 項）

- [ ] E1：5 個 category 以 accordion 呈現（Sources / Transforms / Logic / Outputs / Custom）
- [ ] E2：點 ▶/▼ 可展開摺疊
- [ ] E3：積木可拖到 canvas，節點出現在放開的位置
- [ ] E4：每個積木右側有 status badge（全部應為 Production 綠色）

### 4.5 QA Section F — DAG Canvas（9 項）

- [ ] F1：節點顏色對應 category（Source 綠 / Transform 橘 / Logic 紫 / Output 紅）
- [ ] F2：拖曳節點後位置會保留（切到別的 tab 再回來仍在該位置）
- [ ] F3：從節點右側 port 拉線到另一節點左側 port 成功建立 edge
- [ ] F4：Port 型別不相容（例如 dataframe → dict）連線失敗 + toast 紅色提示
- [ ] F5：刪除節點後相關 edges 一併消失
- [ ] F6：點節點顯示 active 藍框 + 右側 Inspector 載入對應表單 + 底部 DataPreview header 更新
- [ ] F7：選中節點按 Delete 鍵可刪除（在 input 內不應觸發）
- [ ] F8：Cmd/Ctrl+Z undo / Cmd/Ctrl+Shift+Z 或 Cmd/Ctrl+Y redo 正確
- [ ] F9：右上「自動排版」按鈕用 Dagre 重排，節點依 DAG 方向整齊排列

### 4.6 QA Section G — Node Inspector + SchemaForm（7 項）

- [ ] G1：點節點後自動顯示 param_schema 表單
- [ ] G2：string / number / integer / enum / boolean / array 欄位皆可輸入
- [ ] G3：未填 required 欄位時 label 變紅色、input 紅框
- [ ] G4：enum 欄位以下拉選單呈現
- [ ] G5：修改參數 → 底部 DataPreview 的「執行 Preview」按鈕可觸發重算（Phase 2 未做 debounced auto-preview，改為手動點）
- [ ] G6：在 A 節點改參數 → 切到 B 節點 → 再回 A → A 參數仍在
- [ ] G7：Inspector 頂部可編輯「顯示名稱」，失焦後更新節點 header

> 註：G5 調整為手動 Preview 按鈕（比 SPEC 原訂 debounce 更符合 Q2「不自動 save」精神 — 讓使用者明確決定何時耗費 backend 執行）。

### 4.7 QA Section H — Data Preview（5 項）

- [ ] H1：點選節點時預設顯示「點執行 Preview」按鈕
- [ ] H2：點執行 Preview 後 table 顯示 columns 與 rows（最多 30 欄、100 列）
- [ ] H3：大資料會顯示「顯示 N / 總數 M 筆」
- [ ] H4：節點輸出為 dict / scalar 時以 JSON pre-formatted 顯示
- [ ] H5：節點執行失敗時顯示紅色錯誤 panel + hint

### 4.8 QA Section I — Status 管理 UI（5 項）

- [ ] I1：Draft=灰 / Pi-run=黃 / Production=綠 / Deprecated=暗灰 徽章顏色正確
- [ ] I2：Draft 狀態顯示「→ Pi-run」按鈕，點擊成功升級
- [ ] I3：Pi-run → Production 會先跑 Validator；有錯誤時回 422、不升級並顯示錯誤
- [ ] I4：Production 狀態顯示「Fork」+「Deprecate」按鈕；Fork 成功跳轉到新 Draft 頁面
- [ ] I5：Deprecated 狀態所有編輯按鈕 disabled（Inspector 欄位 grey-out）

### 4.9 QA Section J — 儲存 / 執行 / 驗證（8 項）

- [ ] J1：Save 按鈕成功後顯示綠色 toast「已儲存」
- [ ] J2：Validate 按鈕打開抽屜顯示 7 條規則檢查結果（通過顯示 🎉）
- [ ] J3：驗證錯誤清單點選可跳到對應節點（selected 框變藍）
- [ ] J4：Run 按鈕跑整條 pipeline → 每個節點 header 右側出現綠/紅 status dot
- [ ] J5：Run 成功後 toast 顯示「執行成功（run_id=X）」
- [ ] J6：Dirty 狀態（未儲存）離開頁面會彈確認 dialog
- [ ] J7：Production / Deprecated pipeline 進入編輯器時整個 UI 變唯讀
- [ ] J8：Fork 後新 Pipeline 的 metadata.fork_of 記錄來源 ID（可在 backend DB 查到）

---

## 5. 已知限制 & 待跟進

| # | 項目 | Phase 對應 |
|---|---|---|
| L1 | DataPreview 改為手動觸發（原 SPEC 寫 debounce） | 符合 Q2「手動 save」設計哲學 |
| L2 | Playwright E2E 未自動化 | Phase 3 啟動前補上 |
| L3 | react-resizable-panels 未用 | 面板目前為固定寬度；使用者若覺得需要可快速加 |
| L4 | Inspector 不會自動重算 preview | 使用者需明確點「執行 Preview」 |
| L5 | Multi-user 同編輯 | 延到後續 Phase |
| L6 | Custom Block 建立 UI | Phase 4 |
| L7 | Agent 操作 Builder | Phase 3 |

---

## 6. 實測步驟建議

### 6.1 第一個測試場景：純手動建 SPC 巡檢規則

1. 進 `/admin/pipeline-builder` → 新建
2. 從左側拖 **MCP 歷史查詢** 到畫布 → Inspector 填 `tool_id=EQP-01`, `time_range=24h`
3. 拖 **條件過濾** → 連線 n1.data → n2.data → Inspector 填 `column=step`, `operator===`, `value=STEP_002`
4. 拖 **閾值檢查** → 連線 → 填 `column=spc_xbar_chart_value`, `bound_type=upper`, `upper_bound=150`
5. 拖 **連續規則** → 連線 data → data → 填 `flag_column=violates`, `count=3`
6. 拖 **發送告警** → 連線 triggers → records → 填 `severity=HIGH`
7. 點「自動排版」→ 確認畫布整齊
8. 點「驗證」→ 抽屜應顯示 🎉
9. 點「執行」→ 確認每個節點 header 亮綠點
10. 點某個節點 → 底部 DataPreview「執行 Preview」→ 看中間資料
11. 點「儲存」→ URL 變成 `/admin/pipeline-builder/1`
12. 點「→ Pi-run」→ status badge 變黃
13. 點「→ Production」→ status badge 變綠，按鈕換成 Fork / Deprecate
14. 點「Fork」→ 跳轉新 Draft，metadata.fork_of=1
15. 回列表 → 看到 2 筆 pipeline（1 Production + 1 Draft）

### 6.2 第二個測試場景：錯誤處理

1. 新建空 pipeline → 點「驗證」→ 應看到 C7（缺 source + output）
2. 加一個 MCP 節點 → 不填 tool_id → 驗證 → 應看到 C6 missing required
3. 加 block_join → 連 dataframe 到 block_alert 的 records（型別相容）/ 到 block_chart 的 data 應成功
4. 手動拉回線造成 cycle → 驗證應報 C5_CYCLE

---

## 7. 結論

**Backend 全自動綠燈、Frontend 建置成功、型別零錯誤。** Phase 2 MVP 已可交付使用者實測。

- ✅ 自動化可驗收的（Section A, B, 以及建置相關）：全通過
- ⏳ 需人工實測的（Section C–J，共 37 項）：請使用者按 §6 步驟逐項勾選並回報
- 📋 全綠後自動產出 Phase 3（Agent Glass Box）補充 spec

---

**Sign-off：**
- [x] Backend 自動化 46/46 passed
- [x] Coverage 87%（> 70% 目標）
- [x] Frontend type-check + build 成功
- [ ] UI QA 37 項（使用者人工勾選）

---

## 8. 2026-04-18 補充：MCP block 重構 + Playwright E2E

### 8.1 變更摘要

依使用者回饋調整 `block_mcp_fetch` 設計：

| 變更 | 說明 |
|---|---|
| 🔀 重命名 | `block_mcp_fetch` → `block_process_history`（name 更直觀；舊名自動標 deprecated） |
| 🎯 三擇一 | `tool_id / lot_id / step` 皆 optional，但至少要給一個（runtime check） |
| 📊 寬 flatten | `object_name` 不帶時輸出全維度展開寬表（browse 場景一次看完） |
| 🔎 欄位前綴 | `spc_* / apc_* / dc_* / recipe_* / fdc_* / ec_*` 明確分群 |
| 🖥️ 預覽升級 | DataPreview 新增：欄位搜尋框、分組 badge 一鍵隱藏/顯示、欄位數量指示器 |

### 8.2 端到端自動化驗證結果

| 層級 | 測試 | 結果 |
|---|---|---|
| Backend unit + integration | 54 passed (含 8 個新 process_history 測試) | ✅ |
| Backend coverage | 87% | ✅ |
| Frontend type-check | clean | ✅ |
| **Playwright E2E** | **9 / 9 passed (6.3s)** | ✅ **新增** |

### 8.3 Playwright 覆蓋場景

檔案：[aiops-app/e2e/pipeline-builder.spec.ts](../aiops-app/e2e/pipeline-builder.spec.ts)

| # | 場景 | 驗證重點 |
|---|---|---|
| 1 | List 頁載入 | heading + New 按鈕 |
| 2 | Status filter 按鈕 | 全部 / draft / pi_run / production / deprecated 5 個 |
| 3 | Editor 四象限 | 3 nodes + 2 edges 正確渲染 + Chinese labels + header buttons |
| 4 | Node inspector | 點 node → Inspector 顯示 param (tool_id=EQP-01) + Preview 按鈕 enabled |
| 5 | SPC-filtered preview | `object_name=SPC` → 表格只有 spc_* 欄位 + toolID，**沒有** apc_* 欄位 |
| 6 | 全 pipeline 執行 | 「執行成功」toast 出現 |
| 7 | Validate drawer | 「通過所有 7 條驗證規則」顯示 |
| 8 | Wide flatten + 欄位控制 | 寬表（>8 cols）顯示 controls；hide SPC group → spc_* 消失；search "xbar" → 剩 xbar 欄 |
| 9 | 3-of-3 runtime 錯誤 | `params:{}` → 按執行 → 「執行失敗」toast |

### 8.4 Phase 3 (Agent Glass Box) 鋪路

這組 Playwright 測試**證明了以下能力**，Phase 3 Agent 可直接沿用：

1. ✅ **Agent 可透過 REST API 建立 pipeline**（已實測：`POST /pipelines` + 8 種 block）
2. ✅ **前端以 data-testid 提供穩定 hooks**（Agent 若需透過 UI 也有穩定定位器）
3. ✅ **Preview API 可針對單節點切片執行**，Agent 取中間資料後決定下一步
4. ✅ **3-of-3 / schema 驗證錯誤可結構化回傳**，Agent 能自動修正重試

### 8.5 Dev server 實測指令（人工複測用）

```bash
cd /Users/gill/metagpt_pure/workspace/fastapi_backend_refactored
./start.sh
# 開瀏覽器 → http://localhost:3000/admin/pipeline-builder
```

**Playwright 重跑：**
```bash
cd aiops-app
npx playwright test --config=e2e/playwright.config.ts e2e/pipeline-builder.spec.ts --project=desktop-1920
```
