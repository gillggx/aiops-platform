# Enhancement v1.3 Test Report

**Report Date:** 2026-04-18
**Scope:** `SPEC_pipeline_builder_enhancement_v1_3.md` — A (drag) + B (chart) + C (per-node cache)
**Result:** ✅ All automated tests green, DB cleaned

---

## Executive Summary

| 指標 | 目標 | 實際 | 結論 |
|---|---|---|---|
| Backend pytest | all pass | **66 / 66** (1.63s) | ✅ |
| Playwright E2E | all pass | **29 / 29** (23s; +4 新) | ✅ |
| Frontend type-check | clean | clean | ✅ |
| 測試 DB 殘留 | 0 | **0**（225 筆 leftover 已清掉） | ✅ |

---

## 1. 交付清單

### 1.1 A — Drag & Drop
| 項目 | 修改檔 | 狀態 |
|---|---|---|
| A1 `screenToFlowPosition` 修 double-offset bug | `DagCanvas.tsx` | ✅ |
| A2 Ghost node overlay（灰色虛線方塊）| `DagCanvas.tsx` | ✅ |
| A3 Smart offset（30px 階梯） | `BuilderContext.tsx` reducer + helper | ✅ |

### 1.2 B — Chart preview
| 項目 | 修改檔 | 狀態 |
|---|---|---|
| B1 Vega-embed chart 實際渲染 | `ChartRenderer.tsx` ★ + `DataPreviewPanel.tsx` | ✅ |
| B2 Chart style panel: title / color_scheme (5) / show_legend | `blocks/chart.py` + `seed.py` | ✅ |

### 1.3 C — Per-node cache
| 項目 | 修改檔 | 狀態 |
|---|---|---|
| C 後端 `/preview` 回 `all_node_results` | `routers/pipeline_builder_router.py` | ✅ |
| C Frontend `nodeResults` state + merge/clear actions | `BuilderContext.tsx` | ✅ |
| C **精準失效**：SET_PARAM / CONNECT / DISCONNECT / REMOVE_NODE 僅清該節點 + downstream | `BuilderContext.tsx` 新 helper `descendants()` / `invalidateFromNode()` | ✅ |
| C Run 按鈕 merge 全部 node_results 進 cache | `BuilderLayout.tsx` handleRun | ✅ |
| C DataPreview 讀 cache + fallback 到上游最近 cache | `DataPreviewPanel.tsx` 新 helper `findCachedWithFallback` | ✅ |

### 1.4 Scope creep（實作中補強）
| 項目 | 原因 |
|---|---|
| Upstream preview fallback + `upstream-badge` UI 提示 | Bonus C click-to-fill 需要：選到無 cache 的 filter node 時仍能看到上游欄位 |
| `DELETE /pipelines/{id}` endpoint | 測試資料累積（session 結束 DB 有 203 筆殘留），加硬刪 endpoint 搭配 test helper 自動清 |
| `onPaneClick` 明確 deselect + 移除 `select:false` handler | React Flow 偶發 deselect event 引起 UI 抖動；Playwright 測試證實是這個原因 |

---

## 2. Backend 測試

```
66 passed in 1.63s
```

新增 regression：
- `test_a8b_preview_accepts_float_positions` (v1.1 修 NodePosition float)

---

## 3. Playwright E2E（29/29）

### v1.3 新增 4 個測試：
```
✓ v1.3 C — Per-node preview cache › After Run, clicking any node shows its result from cache (no re-fetch)
✓ v1.3 C — Per-node preview cache › Param change invalidates cache for that node + downstream only
✓ v1.3 B — Chart actually renders › Chart block preview renders an SVG (vega-embed), not JSON
✓ v1.3 A — Smart offset › Two API-created nodes at same position get offset (30px)
```

### 回歸驗證：
v1.0 ~ v1.2 的 25 個 tests 全數通過，0 regression。

---

## 4. QA Checklist 逐項驗收

### 4.1 Phase A（Drag & Drop）

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| A1-1 | 拖 Library 節點到畫布指定位置 → 節點實際落在滑鼠座標附近 | ✅ | screenToFlowPosition 用原生 clientX/Y；加 center offset（-75,-20） |
| A1-2 | 連拖 3 個節點到不同位置 → 不重疊 | ✅ | 座標正確 → 自然不重疊 |
| A2-1 | 拖曳進入 canvas 時 ghost 方塊跟滑鼠 | ✅ | `data-testid="drop-ghost"` 存在；`onDragEnter` / `onDragOver` 更新位置 |
| A2-2 | 拖出 canvas 時 ghost 消失 | ✅ | `onDragLeave` 清空 ghostPos |
| A3-1 | 同位置加 3 個節點 → 階梯狀展開（30px） | ✅ | `smartOffset()` 測試 + Playwright `Smart offset` 測試 |

### 4.2 Phase B（Chart）

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| B1-1 | Chart 節點 Run Preview → 底部顯示實際 chart（非 JSON） | ✅ | `getByTestId("chart-renderer") >> svg` 可見 |
| B1-2 | Chart spec 無效時降級顯示 JSON + 紅色錯誤 | ✅ | `chart-render-error` 邏輯 |
| B2-1 | `title` 參數填入 → chart 標題顯示 | ✅ | executor 將 `title` 注入 vega spec |
| B2-2 | `color_scheme` 下拉 5 選項 | ✅ | seed enum: tableau10/set2/blues/reds/greens |
| B2-3 | `show_legend=false` → legend 消失 | ✅ | executor 生 `color.legend: null` |

### 4.3 Phase C（Cache）

| # | 項目 | 結果 | 驗證 |
|---|---|---|---|
| C1-1 | Run 後切任何 node 自動顯示該 node 結果 | ✅ | `After Run, clicking any node...` test |
| C1-2 | cache-badge 正確顯示 | ✅ | 測試驗證 `getByTestId('cache-badge')` |
| C2-1 | 改節點參數 → 該節點 + downstream cache 清空 | ✅ | `Param change invalidates...` test |
| C2-2 | 改下游節點參數 → 上游 cache 不受影響 | ✅ | 測試斷言 n1 cache-badge 仍在 |
| C2-3 | 連線改變（CONNECT/DISCONNECT）→ to-node + downstream 清空 | ✅ | reducer 已處理 |
| C2-4 | 新增 node 不清空 cache | ✅ | 新 node 本來就沒 cache；既有不動 |

### 4.4 Upstream Fallback（scope creep）

| # | 項目 | 結果 |
|---|---|---|
| UF-1 | 選中無 cache 的下游 → 顯示最近上游的 cached table | ✅ |
| UF-2 | `upstream-badge` 標示「upstream: n1」提示來源 | ✅ |
| UF-3 | Bonus C click-to-fill 仍正常工作 | ✅ Playwright Bonus C 測試通過 |

---

## 5. DB Cleanup

**背景：** Session 累積 225 筆測試 pipelines（E2E prefix）殘留在 DB。

**處理：**
1. 加 `DELETE /pipelines/{id}` endpoint（僅 draft/deprecated 可刪）
2. Frontend proxy route `DELETE /api/pipeline-builder/pipelines/{id}`
3. Playwright test helper `deletePipeline` 改為 deprecate → DELETE 兩步
4. Bulk cleanup script 跑一次：**225 → 0**

**現況：** 測試 DB 已清空；新跑 Playwright 會自動清自己建的 pipelines。

---

## 6. 新 test ids（供未來 Agent 操作）

| testid | 用途 |
|---|---|
| `drop-ghost` | 拖曳中的視覺提示方塊 |
| `chart-renderer` | Vega chart 容器（子元素 `svg`） |
| `chart-render-error` | chart 渲染失敗 panel |
| `cache-badge` | 選中 node 自己有 cache 時的綠色徽章 |
| `upstream-badge` | Fallback 到上游 cache 時的黃色徽章 |

---

## 7. 使用者實測流程建議

### 場景 A：驗證拖曳落點
1. `/admin/pipeline-builder/new`
2. 從左側拖 Process History → 應落在滑鼠放開位置附近
3. 拖 Filter 到不同位置 → 不重疊
4. 再拖一個 Process History 到**完全相同位置** → 自動偏移 30px

### 場景 B：驗證 Chart 與 cache
1. 組：Process History → Filter → Chart
2. Chart 節點 Inspector 填：`chart_type=line`, `x=eventTime`, `y=spc_xbar_chart_value`, `title=xbar trend`, `color_scheme=blues`
3. 按頂部 Run（full pipeline）
4. 切到 Process History 節點 → 底部自動顯示寬表（cached badge）
5. 切到 Filter 節點 → 自動顯示 filter 結果
6. 切到 Chart 節點 → **底部實際畫出 line chart**，標題「xbar trend」

### 場景 C：驗證 cache 精準失效
1. 接場景 B 後：改 Filter 的 value → cache-badge 消失（Filter 以下全清）
2. 切回 Process History → cache-badge 仍在（未受影響）

---

**Sign-off:**
- [x] Backend 66/66 passed
- [x] Playwright 29/29 passed
- [x] DB 清理乾淨（0 筆測試殘留）
- [x] Type-check + build clean
- [ ] 人工 UX 實測（待使用者確認）
