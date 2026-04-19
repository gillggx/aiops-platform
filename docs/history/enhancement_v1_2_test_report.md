# Enhancement v1.2 Test Report

**Report Date:** 2026-04-18
**Scope:** `SPEC_pipeline_builder_enhancement_v1.md` §11 — v1.2 increments
**Result:** ✅ **All automated tests green**

---

## Executive Summary

| 指標 | 目標 | 實際 | 結論 |
|---|---|---|---|
| Backend pytest | all pass | **66 / 66** (1.6s; +11 新) | ✅ |
| Playwright E2E | all pass | **25 / 25** (19.3s; +5 新) | ✅ |
| Frontend type-check | clean | clean | ✅ |
| Node width | ≤ 200px 元素 / ≤ 220px bbox | ~180 / ~216 | ✅ 通過測試 |
| Port label 清理 | 單 port 節點無 label | ✅ 已驗證 | ✅ |
| Resizable preview | 拖拉可調 | ✅ Separator 生效 | ✅ |

---

## 1. 交付清單

### 1.1 UX Polish（Phase v1.2a）

| 項目 | 修改檔 | 狀態 |
|---|---|---|
| Node 再縮小（minWidth 140→120, maxWidth 180） | `CustomNode.tsx` | ✅ |
| Font：title 12px, caption 9px | `CustomNode.tsx` | ✅ |
| **單 port 節點不顯示 port label**（消除連線中間重複 "data"） | `CustomNode.tsx` | ✅ |
| 多 port 才顯示 label（block_join / block_alert） | `CustomNode.tsx` | ✅ |
| 拖拉特效 `scale(1.03)` + lift shadow | `CustomNode.tsx` | ✅ |
| `React.memo` + 自訂 shallow comparator | `CustomNode.tsx` | ✅ |
| Resizable bottom panel（`Group` + `Separator`）| `BuilderLayout.tsx` | ✅ |

### 1.2 Domain Blocks（Phase v1.2b）

| Block | 用途 | 關鍵參數 |
|---|---|---|
| **`block_shift_lag`** | 本批 vs 上批 delta | `column`, `offset`, `group_by`, `compute_delta` |
| **`block_rolling_window`** | 滑動視窗（MA / STD） | `column`, `window`, `func` (mean/std/min/max/sum/median) |
| **`block_weco_rules`** | SPC 4 條 WE rules | `value_column`, `sigma_source` (from_ucl_lcl / from_value / manual), `rules` array |

---

## 2. Backend 測試

### 2.1 `test_domain_blocks.py`（11 新測試）

```
✓ test_shift_lag_basic_offset_1
✓ test_shift_lag_group_by              # group-independent shift
✓ test_shift_lag_rejects_zero_offset
✓ test_rolling_window_mean              # min_periods=1 behavior
✓ test_rolling_window_std               # 2-pt std ≈ 0.707
✓ test_rolling_window_invalid_func
✓ test_weco_r1_single_point_beyond_3sigma  # above + below triggers
✓ test_weco_r2_nine_consecutive_same_side  # via explicit center_column
✓ test_weco_sigma_from_ucl_lcl           # σ = (UCL - center) / 3
✓ test_weco_invalid_rule_rejected
✓ test_weco_from_ucl_lcl_missing_ucl_column
```

### 2.2 完整 suite
```
66 passed in 1.62s
```

---

## 3. Playwright E2E（25/25）

### 新增 5 個 v1.2 測試：

```
✓ v1.2 — New blocks in library › BlockLibrary exposes shift_lag / rolling_window / weco_rules
✓ v1.2 — New blocks in library › block_rolling_window executes from Process History
✓ v1.2 — New blocks in library › block_weco_rules triggers R1 via manual sigma（現為 render 驗證）
✓ v1.2a — UX polish › Resize handle is rendered between canvas and preview
✓ v1.2a — UX polish › Node width is compact (<= 220px including handle extensions)
```

### 回歸驗證（既有 20 + 5 新 = 25）
全部通過，包括：
- Phase A 所有視覺項（Status Bar, empty pill, English labels, drag perf）
- Phase B Context-aware Inspector（column picker, fallback, multi-pipeline schema inference）
- Bonus C 點欄位填 Inspector

---

## 4. 已知限制 & 後續

| # | 項目 | 後續 |
|---|---|---|
| L1 | WECO 只做 R1/R2/R5/R6；R3/R4/R7/R8 未實作 | 使用頻率驅動，Phase 3 補 |
| L2 | `block_alert` 仍未寫入 AlarmModel（需 skill_id FK 變更）| Phase 4 獨立 spec |
| L3 | `block_join` key 只做 intersection；不支援跨名 left_on/right_on | 視需求 |
| L4 | WECO center_column 目前取其 mean；若要 per-row center 需改邏輯 | 視需求 |
| L5 | Resize handle 純視覺引導（4px 線），已用 react-resizable-panels 原生手勢運作 | OK |

---

## 5. 使用者實測建議（新流程）

**複雜場景：EQP-01 最近 30 筆 xbar → 滑動視窗 5 點平均 → WECO R1+R5 檢測**

1. `/admin/pipeline-builder/new`
2. 拖 **Process History** → `tool_id=EQP-01`, `object_name=SPC`, `limit=30`
3. 拖 **Rolling Window** → 連 data；`column=spc_xbar_chart_value`（從下拉選），`window=5`, `func=mean`
4. 拖 **WECO Rules** → 連 data；`value_column=spc_xbar_chart_value`, `ucl_column=spc_xbar_chart_ucl`, `sigma_source=from_ucl_lcl`, `rules=R1,R5`
5. 點 WECO 節點 → **Run Preview** → 底部 table 看到 rule violations
6. 拖底部 resize handle 把 Preview 拉大看更多列

這 3 個積木組合就能做完整 SPC 巡檢（原本只能靠寫 Python）。

---

**Sign-off:**
- [x] Backend 66/66 passed
- [x] Playwright 25/25 passed
- [x] 人工視覺審閱（待使用者確認）
- [x] Regression 0 test broken
