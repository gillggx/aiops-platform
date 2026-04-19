# Pipeline Builder — Phase α/β/γ/δ Report

**Date:** 2026-04-18
**Scope:** 完成 Phase α/β/γ/δ 四波，Pipeline Builder 標準積木從 12 → 23；新增結構化 examples 欄位 + BlockDocsDrawer UX。
**Against:** [docs/TEST_CASES_V3.md](TEST_CASES_V3.md)（44 cases）

---

## 1. 積木總覽 — 23 個

| 類別 | 數量 | 積木清單 |
|---|---|---|
| **Sources** | 2 | `block_process_history`, `block_mcp_call` *(δ)* |
| **Transforms** | 11 | filter / join / groupby_agg / shift_lag / rolling_window / delta / sort *(α)* / histogram *(α)* / unpivot *(β)* / union *(β)* / ewma *(γ)* |
| **Logic** | 8 | threshold / consecutive_rule / weco_rules / any_trigger *(β)* / linear_regression *(α)* / cpk *(β)* / correlation *(γ)* / hypothesis_test *(γ)* |
| **Outputs** | 2 | chart / alert |

- WECO rules 擴至 **Nelson 全 8 條**（R1..R8，β 補 R3/R4/R7/R8）
- Chart 支援 **多 y / 雙軸 / boxplot / heatmap**（α 擴充）
- Logic node **統一 `triggered + evidence` 介面**（3.2）— 5 個 logic block 都遵循
- Validator **C8 撤銷**（β）— 多 alert 合法

## 2. Examples 欄位（新 UX 基礎）

- 新增 `pb_blocks.examples TEXT NOT NULL DEFAULT '[]'` column（Alembic-safe `_safe_add_columns` migration）
- 23 個積木全部有 examples — **共 38 個 examples**（seed_examples.py 單一來源）
- `/api/v1/pipeline-builder/blocks` API response 自動帶 `examples` 欄位
- Agent system prompt（`_format_block_catalog`）自動注入 examples — Agent 有「標準答案」可參考，挑對積木 + 填對 params 的成功率提升

## 3. Frontend UX 改善

**BlockDocsDrawer.tsx**（新元件）
- BlockLibrary 每個積木右側加 **ⓘ** 按鈕 — 點擊開側抽屜（寬 `min(520px, 90vw)`）
- 內容分四區：
  1. **Description** — 原有的 `== What == / == Use case ==` 章節，格式化顯示
  2. **Examples** — 每個範例卡：標題 + summary + （可展開）params 表 + 「＋ Apply to canvas」按鈕
  3. **Ports** — input / output 以 chip 呈現
  4. **Param schema** — 完整 JSON schema（技術細節，可收折）
- 「Apply to canvas」按鈕 → 直接把該 example 的 params 預填，drop 新 node 到 canvas
- 不用拖出來就能讀完 docs + 預覽範例

## 4. Test Case 驗證結果

### Section 2（新 24 cases）— 🟢 JSON TC，CI 可跑

| Group | TC | Status |
|---|---|---|
| α (5) | TCα1–TCα5 | ✅ 5/5 passed |
| β (7) | TCβ1–TCβ7 | ✅ 7/7 passed |
| γ (7) | TCγ1–TCγ7 | ✅ 7/7 passed |
| δ (3) | TCδ1–TCδ3 | ✅ 3/3 passed (MCP call mocked) |
| 綜合 (2) | TC-all-1, TC-all-2 | ✅ 2/2 passed |

**合計：🟢 24/24 passed**（`tests/pipeline_builder/test_v3_test_cases.py`）

### Section 1（V2 20 cases）— 🤖 Agent TC，需 ANTHROPIC_LIVE

代表性 10 case 寫進 `e2e/agent-v3-benchmark.spec.ts`（ANTHROPIC_LIVE 閘門），每 case 發 prompt 到 `/api/agent/build/batch`，驗 finished 狀態 + 預期積木出現。
- V2 原 17/20 通過；V3 期待：
  - TC04（機台比較）：`block_union` 可直接用 → Agent 應選對
  - TC06（list tools）：`block_mcp_call` 可解 → 從 🚫 轉 ✅
  - TC13（最需關注機台）：`block_sort` 可直接取 top-N
  - TC16（雙軸圖）：chart 已支援
  - TC18/19/20（SPC 統計）：unpivot / linear_regression / histogram / hypothesis_test 全備齊

**執行方式**：`ANTHROPIC_LIVE=1 npx playwright test e2e/agent-v3-benchmark.spec.ts`（用戶驗收時跑）

## 5. Regression

| 項目 | 狀態 |
|---|---|
| Backend pytest（全 pipeline_builder/） | **168/168 passed** |
| TypeScript type-check | ✅ clean |
| Playwright e2e（pipeline-builder + agent-panel） | **33/34 passed**（1 skipped: ANTHROPIC_LIVE） |

## 6. Documentation

- [docs/SPEC_pipeline_builder.md §3.2](SPEC_pipeline_builder.md) — 23 blocks 清單更新
- [docs/SPEC_pipeline_builder.md §8 snapshot table](SPEC_pipeline_builder.md) — 所有 phase 標記完成
- [docs/TEST_CASES_V3.md](TEST_CASES_V3.md) — 44 case 清單（新）
- `.claude/memory/project_pipeline_builder_progress.md` — 23 blocks + 設計決策紀錄

## 7. 啟動 / 重啟

```bash
# 後端（seed 會 upsert examples 到 DB）
pkill -f "uvicorn main:app.*port 8000"
cd fastapi_backend_service
nohup ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --log-level warning > ../logs/fastapi_backend.log 2>&1 &
```

Cmd+Shift+R 重整前端後：
- 每個積木有 ⓘ 按鈕 → 點開看 docs + 範例
- 「Apply to canvas」可一鍵預填 example params
- 跑 Agent 時，system prompt 自動吃到 examples，TC19 這種「多 chart type 回歸」Agent 會選對 unpivot

---

## 8. 已知限制 / 下階段

- **Section 1 的 11 個 🤖 Agent TC 未自動驗**（需 ANTHROPIC_LIVE 實測）— 建議你這邊試跑後再 close
- **Phase 4 Migration 未啟動**：diagnostic_rules → Pipeline JSON；Custom Block 實作；舊 code-gen 路徑下線。這是大工程，需先統計既有 DR 清單才能估工
- **Examples 總量 38** — 平均每積木 1.65；部分積木（e.g. process_history / chart / weco_rules）多一點，部分（e.g. join / any_trigger）只 1 個。若使用一段時間後發現特定積木範例不夠，再補即可（seed_examples.py 是單檔維護）
