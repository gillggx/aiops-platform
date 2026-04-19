# Enhancement v1.1 Test Report — Pipeline Builder UX Upgrade

**Report Date:** 2026-04-18
**Scope:** `SPEC_pipeline_builder_enhancement_v1.md` v1.1 — Phase A + Phase B + Bonus C
**Result:** ✅ **All Automated Tests Green**

---

## Executive Summary

| 指標 | 目標 | 實際 | 結論 |
|---|---|---|---|
| Backend tests | all pass | **54 / 54** (1.76s) | ✅ |
| Playwright E2E tests | all pass | **20 / 20** (15s) | ✅ |
| Frontend type-check | clean | `tsc --noEmit` clean | ✅ |
| Phase A (P1–P5) | 5/5 項 | 5/5 | ✅ |
| Phase B (context-aware Inspector) | 6/6 檔案 | 6/6 | ✅ |
| Bonus C (click-to-fill) | 4 檔案 | 4/4 | ✅ |

---

## 1. 交付項目

### 1.1 Phase A — UX Polish（完成）

| # | 項目 | 實作檔案 |
|---|---|---|
| P1 | DataPreview 回底部（30vh，全寬） | `BuilderLayout.tsx`, `DataPreviewPanel.tsx` |
| P2 | 配色 Slate + 色條 + 1px border + 無 shadow + indigo selected | `style.ts`, `CustomNode.tsx`, `DagCanvas.tsx` |
| P3 | Node icon + Title + CAPTION（140px，預設英文） | `CustomNode.tsx`, `CategoryIcon.tsx`（★新增）, `BlockLibrary.tsx` |
| P4 | 拖拉閃爍修復（`onNodeDragStop` only persist） | `DagCanvas.tsx` |
| P5 | 頂部 Status Bar + 空畫布 pill | `BuilderLayout.tsx`, `DagCanvas.tsx` |

### 1.2 Phase B — Context-aware Inspector（完成）

| # | 項目 | 實作檔案 |
|---|---|---|
| B1 | Schema annotation `x-column-source` 標註於 7 個 block params | `seed.py` |
| B2 | TypeScript types 擴充 | `lib/pipeline-builder/types.ts` |
| B3 | `useUpstreamColumns` hook（含 pipeline hash cache） | `context/pipeline-builder/useUpstreamColumns.ts` ★新增 |
| B4 | SchemaForm 新 widget：`ColumnPicker`（select + fallback） | `components/pipeline-builder/SchemaForm.tsx` |
| B5 | NodeInspector 整合 upstream columns | `components/pipeline-builder/NodeInspector.tsx` |
| B6 | `block_join.key` 多 port intersect（`input.left+right`） | `SchemaForm.tsx` ColumnPicker |

### 1.3 Bonus C — Click-to-fill（完成）

| # | 項目 | 實作檔案 |
|---|---|---|
| C1 | `focusedColumnTarget` state + `setColumnTarget` action | `BuilderContext.tsx` |
| C2 | `ColumnPicker` 註冊 focus → 設 target | `SchemaForm.tsx` |
| C3 | DataPreview `onColumnClick` prop + header 可點擊 | `DataPreviewPanel.tsx` |
| C4 | BuilderLayout 在 Preview `onColumnClick` 時寫 Inspector 欄位 | `BuilderLayout.tsx` |

---

## 2. 測試結果詳細

### 2.1 Backend（pytest 54 tests）
```
tests/pipeline_builder/test_blocks.py           ............  [22%]
tests/pipeline_builder/test_executor.py         ....          [30%]
tests/pipeline_builder/test_phase2_crud.py      ..............  [56%]
tests/pipeline_builder/test_process_history.py  ........      [70%]
tests/pipeline_builder/test_smoke_e2e.py        .....         [79%]
tests/pipeline_builder/test_validator.py        ...........   [100%]

54 passed in 1.76s
```

### 2.2 Playwright E2E（20 tests）
```
 ✓ 1. List page loads and shows New button
 ✓ 2. Status filter buttons work
 ✓ 3. Editor renders all four panels + nodes + edges（v1.1 英文 labels + category captions）
 ✓ 4. Clicking a node populates inspector + enables preview
 ✓ 5. Run Preview on process_history node returns SPC-filtered columns
 ✓ 6. Run full pipeline sets success status dots
 ✓ 7. Validate button opens drawer with success state
 ✓ 8. Wide flatten + column controls（欄位搜尋 + group hide）
 ✓ 9. Single-source preview（單節點也能跑）
 ✓ 10. tool_id datalist populated from suggestions endpoint
 ✓ 11. object_name select shows "— 全部 —" + 6 dimensions

 v1.1 Phase A:
 ✓ 12. Status bar shows STATUS / ACTIVE NODES / SELECTED
 ✓ 13. Empty canvas shows "Drag blocks from library to begin" pill
 ✓ 14. Data Preview is at bottom (full width)
 ✓ 15. Drag performance: no position-change storm during drag

 v1.1 Phase B:
 ✓ 16. filter.column renders as dropdown populated from upstream columns
 ✓ 17. filter.column degrades to text input when upstream missing
 ✓ 18. threshold.column + consecutive_rule.flag_column all become pickers

 v1.1 Bonus C:
 ✓ 19. Focusing column picker + clicking preview header fills it

 ✓ 20. 3-of-3 runtime error surfacing

20 passed (15.0s)
```

---

## 3. QA Checklist 逐項驗收

### 3.1 Phase A QA（UXA1–UXA5 + P1–P4）

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| UXA1 | 移除所有 node box-shadow，選中用 indigo border | ✅ | `CustomNode.tsx` selected `2px outline rgba(79,70,229,0.12)` |
| UXA2 | Node icon + title + SOURCE/TRANSFORM caption | ✅ | Playwright test `editor renders all four panels + nodes + edges` 驗證 |
| UXA3 | Status bar 3 欄位會根據 state 更新 | ✅ | Playwright test `Status bar shows STATUS / ACTIVE NODES / SELECTED` |
| UXA4 | 空畫布 pill | ✅ | Playwright test `empty canvas shows pill` |
| UXA5 | 拖拉 onNodeDragStop 驗證 | ✅ | Playwright test `Drag performance: no position-change storm`（視覺移動 100+px 而 state 穩定）|
| P1 | Preview 回底部 30vh | ✅ | Playwright test `Data Preview is at bottom (full width)`（寬度 ≈ viewport、y > 0.55 vh）|
| P2 | 配色 Slate（無 box-shadow） | ✅ | `style.ts` 定義 + CustomNode 無 shadow |
| P3 | Node 縮小 + 英文 | ✅ | `minWidth: 140`、`CATEGORY_CAPTIONS` 全大寫 |
| P4 | `onNodeDragStop` event | ✅ | `DagCanvas.tsx` `onNodesChangeFiltered` 略過 position，`handleNodeDragStop` 單次寫入 |

### 3.2 Phase B QA（CAI1–CAI5）

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| CAI1 | Filter node column 變下拉，列上游 columns | ✅ | `filter.column renders as dropdown populated from upstream columns` |
| CAI2 | 上游 preview 失敗時降級 text input | ✅ | `filter.column degrades to text input when upstream missing` |
| CAI3 | 多層 pipeline n1→n2→n3 | ✅ | `threshold.column + consecutive_rule.flag_column all become pickers`（n3 自 n2 拿 cols）|
| CAI4 | block_join 能從 left / right 取 | ✅ | Schema seed `key: x-column-source: "input.left+right"`（intersect） |
| CAI5 | Cache 生效 | ✅ | `useUpstreamColumns` 用 pipeline hash 為 key；重複選相同 node 不再 network |

### 3.3 Bonus C QA

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| BC1 | Focus picker → 設 target | ✅ | `SchemaForm.tsx` `onFocus={registerFocus}` |
| BC2 | Preview header 可點（有 hover 游標） | ✅ | `DataPreviewPanel.tsx` `cursor: pointer` + `onClick` |
| BC3 | 點 header 填 Inspector | ✅ | Playwright test `focusing column picker then clicking a preview header fills it`（toast 出現 + picker value=`toolID`）|
| BC4 | 切換 node Preview 資料保留（使 C3 順暢） | ✅ | `DataPreviewPanel.tsx` useEffect 只 reset 欄位篩選，不 reset preview data |

---

## 4. 架構里程碑

### 4.1 核心平台能力
v1.1 完成後，Pipeline Builder 已具備：

1. **專業視覺**：Palantir / Databricks 風格，無玩具感
2. **資料感知 Inspector**：欄位參數不再盲打，從上游 schema 動態選單（Foundry 核心差異化）
3. **直觀互動**：點 preview 欄位 → 自動填 Inspector（Palantir 招牌手勢）
4. **穩定效能**：拖拉平滑，無無效 re-render

### 4.2 為 Phase 3 Agent 鋪路

Schema annotation 路線的 Agent 友善度驗證：
- ✅ `x-column-source` 是 **宣告式** — Agent 讀 schema 即知參數來源
- ✅ `useUpstreamColumns` 拿 columns 的邏輯 = Agent 要用 `builder.preview(n-1)` 決定 `set_param(n, column=?)` 的邏輯
- ✅ Click-to-fill 的 UX = Agent 的 `explain("I'm filling column=toolID because upstream has this col")` 的視覺化對應

這些都是 Phase 3 Glass Box Agent 可以直接複用的基礎設施。

---

## 5. 檔案變更一覽

### Backend（1 檔）
- `app/services/pipeline_builder/seed.py` — 加入 `x-column-source` 標註於 7 處欄位

### Frontend（14 檔）
**新增 (3)：**
- `components/pipeline-builder/CategoryIcon.tsx` — 5 個 inline SVG
- `context/pipeline-builder/useUpstreamColumns.ts` — hook + cache
- `lib/pipeline-builder/style.ts` — palette + `blockDisplayName()`（大幅重寫）

**修改 (11)：**
- `components/pipeline-builder/CustomNode.tsx` — 全新視覺
- `components/pipeline-builder/BlockLibrary.tsx` — accordion + icon + 英文 label
- `components/pipeline-builder/DagCanvas.tsx` — onNodeDragStop + empty pill + palette
- `components/pipeline-builder/NodeInspector.tsx` — wire upstream columns
- `components/pipeline-builder/SchemaForm.tsx` — 新 ColumnPicker widget
- `components/pipeline-builder/DataPreviewPanel.tsx` — bottom layout + onColumnClick
- `components/pipeline-builder/BuilderLayout.tsx` — 布局重排 + Status bar + bonus C wiring
- `context/pipeline-builder/BuilderContext.tsx` — 加 `focusedColumnTarget` + `setColumnTarget`
- `lib/pipeline-builder/types.ts` — `x-column-source` 欄位
- `e2e/pipeline-builder.spec.ts` — 新增 8 個測試

---

## 6. 已知限制 / Future work

| # | 項目 | 後續 |
|---|---|---|
| L1 | `block_join` key 只做 **intersection**（兩側同名）；若需跨名 join（left_on / right_on）需另開 spec | 待需求驅動 |
| L2 | `useUpstreamColumns` cache 用 module-level Map；多頁面切換不清除（可能占少量記憶體） | 可接受；若介入 observability，可加 LRU 上限 |
| L3 | ColumnPicker 對 array 型 value（如 `block_join.key`）僅支援單欄；多欄需逗號分隔輸入 | Phase 3 視需求做 multi-select UI |
| L4 | Click-to-fill 的 toast 目前中文 hardcode | i18n 一併 Phase 3 處理 |
| L5 | Drag perf test 驗證視覺移動但不直接驗證 `actions.moveNode` 呼叫次數 | 可加 React DevTools Profiler 驗；目前以視覺代驗 |

---

## 7. 使用者實測建議流程

以下場景驗證 Phase A + B + Bonus 的完整流程：

**場景：SPC 連續 OOC 巡檢（context-aware 建置）**

1. 開 `http://localhost:3000/admin/pipeline-builder/new`
2. 拖 **Process History** 到畫布；Inspector 填 `tool_id=EQP-01`, `object_name=SPC`
3. 選中 Process History 節點 → 點底部「Run Preview」→ 看到 SPC 寬表（~15 欄）
4. 拖 **Filter** 到畫布，連線 `Process History.data` → `Filter.data`
5. **點 Filter 節點** → Inspector 的 `column` 欄位自動變下拉選單（列出 n1 的 15 個 SPC 欄位）
6. **聚焦 column 欄位** → 底部 table 的欄位名（如 `spc_xbar_chart_value`）滑鼠 hover 變游標
7. **點 `spc_xbar_chart_value` 欄位 header** → Inspector 自動填入該值 + toast「已填入 column = spc_xbar_chart_value」
8. 設 `operator= >`, `value=150`
9. 拖 **Consecutive Rule** → 連線；Inspector 的 `flag_column` 也是下拉（列出 filter 的 output 欄位）
10. 拖 **Alert** → 連線；填 `severity=HIGH`
11. 按「Validate」→ 抽屜顯示綠色通過
12. 按「Run」→ 看到節點亮綠燈 + 成功 toast
13. 按「Save」→ toast「已儲存」
14. 試按「→ Pi-run」→ Status Bar 的 STATUS 變黃
15. 試按「→ Production」→ Status Bar 變綠，按鈕換成 Fork / Deprecate
16. 點畫布空白處取消選取 → Inspector 顯示 "Select a node to edit parameters"；Status Bar 的 SELECTED 變 —

---

## 8. 下一步建議

- [ ] **人工 UX 審閱**：依 §7 步驟走一遍，確認視覺與互動符合企業平台期待
- [ ] **若審閱通過**：提交 commit，開始準備 **Phase 3 (Agent Glass Box) 補充 spec**
- [ ] Phase 3 會把這個 Schema annotation + useUpstreamColumns 機制進一步抽出為 Agent 可呼叫的 tools（`builder.preview(node_id)` / `builder.set_param(node_id, key, value)` / ...）

---

**Sign-off:**
- [x] Backend 54/54 passed
- [x] Playwright E2E 20/20 passed
- [x] Frontend type-check clean
- [x] 實機測試指令：`./start.sh`（已在執行）
- [ ] 人工視覺 / 互動審閱（使用者）
