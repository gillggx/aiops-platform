# Skill → Pipeline Migration Report (Phase 4-A)

**Date:** 2026-04-18 (v2, after Phase 4-A+ block additions)
**Tool:** `app/services/pipeline_builder/skill_migrator.py`
**Scope:** 6 production skills in `skill_definitions` (3 DRs + 3 auto_patrol)

## Summary

| Status | v1 | v2 (目前) | Meaning |
|---|---|---|---|
| **full** | 2 | **4** ⬆ | 結構 + 參數完整，可直接 Run |
| **skeleton** | 4 | **2** ⬇ | 結構正確，需手動補 logic |
| **manual** | 0 | 0 | 無 MCP 無法自動 |

**v1 → v2 提升原因：** 新增 3 個積木 / 模式
- `block_count_rows` — row-count scalar output
- `block_threshold` 加 `operator / target` Mode B（generic comparison）
- `block_mcp_foreach` — 每 row call MCP 的 concurrent loop（asyncio.gather，預設並發 5）

## Per-skill Result (v2)

| ID | Skill | Source | Status | Pipeline |
|---|---|---|---|---|
| 3 | SPC chat's continue OOC check | auto_patrol | **full** | `process_history → rolling_window(500, sum) → threshold(≥2) → alert` |
| 4 | Tool 5-in-3-out check | auto_patrol | **full** | `process_history → rolling_window(5, sum) → threshold(≥4) → alert` |
| 5 | SPC OOC × APC trending | rule (DR) | skeleton | `process_history → mcp_foreach(get_process_context) → chart`（per-param rising 偵測需手補）|
| 6 | Same recipe check | rule (DR) | **full** ⬆ | `process_history → filter(OOC) → count_rows(groupby recipeID) → count_rows → threshold(>1) → alert` |
| 7 | Same APC check | rule (DR) | **full** ⬆ | `process_history → filter(OOC) → count_rows(groupby apcID) → count_rows → threshold(>1) → alert` |
| 10 | 機台 5-in-2-out stub | auto_patrol | skeleton | `process_history`（stub 本身無邏輯 — 這不是 migrator 的問題）|

## Migrator 新增能力（v2）

### Pattern: `same_group_check`
原：`filter → groupby_agg(count)` + 「count==1 需手調」
現：`filter → count_rows(group_by=field) → count_rows → threshold(operator='>', target=1)`
→ 全自動判定「OOC 事件是否都來自同一 recipe/APC」（若跨 2+ groups 即觸發）

### Pattern: multi-MCP for-loop
原：第 2 個 MCP 呼叫被當 "extra, needs manual"
現：偵測 `for ... in ...:` + `execute_mcp(...)` → 自動加 `block_mcp_foreach` 節點
→ `args_template` 自動從原 code 解析（e.g. `targetID: $lotID, step: $step`）

## 25 積木總覽（Phase 4-A 結束時）

| 類別 | 數量 | 新增（Phase 4-A） |
|---|---|---|
| Sources | 2 | — |
| Transforms | **13** | +`block_count_rows` / +`block_mcp_foreach` |
| Logic | 8 | `block_threshold` 加 Mode B（operator comparison）|
| Outputs | 2 | — |

## 仍為 skeleton 的原因

### Skill 5 — APC trending
- 主要 MCP foreach 已 wire ✅
- 缺：每 APC 參數**獨立**跑「連續 N 點上升」偵測（類似 skill 3 但 cross-parameter loop）
- 需要的是 `block_unpivot`（已有）+ `group_by=param_name` 的 tail-based check — migrator 尚未能自動辨識此複合 pattern
- 手動 5 分鐘可補：unpivot → delta(group_by=param) → consecutive_rule(group_by=param, flag=is_rising, count=2)

### Skill 10 — stub
- 原 code 就是 stub（`_findings = {"condition_met": False, "summary": "stub"}`）
- Migration 保留 source 節點已是極限；不建議強制補

## 測試
- `test_skill_migrator.py`：**14/14 passed**（含 6 skill fixtures + parser units + pattern cases）
- `test_phase_4a_blocks.py`：**11/11 passed**（count_rows + threshold.operator + mcp_foreach）
- 全套 backend：**215/215 passed**

## 使用

```bash
# 不變 — 所有 skill 都用同一 API
curl -X POST "http://localhost:8000/api/v1/pipeline-builder/migrate/skill/{id}?dry_run=true"
```

Skills 6/7 因為現在是 full，可直接 `dry_run=false` 寫進 `pb_pipelines`。
