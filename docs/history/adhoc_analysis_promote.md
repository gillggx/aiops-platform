# Spec: Ad-hoc Analysis → Promote to Diagnostic Rule

**Status**: Draft — awaiting approval
**Depends on**: Phase 1 (memory), Phase 2 (LangGraph v2), object-info API

---

## 1. Concept

Agent 可以動態生成 python code 並執行一次性分析，結果顯示在**中間分析面板**。
如果 user 覺得這個分析有用，可以一鍵「儲存為常用工具」→ 變成正式的 Diagnostic Rule。

```
User 問問題
  ↓
Agent 規劃 MCP + 生成 python code
  ↓
execute_analysis（一次性 Skill 執行）
  ↓
中間分析面板顯示結果 + charts
  ↓
[⭐ 儲存為 Diagnostic Rule]  ← user 決定
  ↓
永久 Skill（出現在 skill_catalog + /admin/skills）
  ↓
下次 Agent 直接 execute_skill（不用再生成 code）
```

---

## 2. Core Design Decisions

| 決策 | 結論 |
|---|---|
| execute_analysis vs execute_jit | **取代** execute_jit，所有一次性分析都走 execute_analysis |
| Promote 產物 | **Diagnostic Rule**（跟 admin/skills 裡的一樣，source='rule'），只差還沒綁 alarm |
| Chart 渲染位置 | **中間分析面板**（不是 copilot 右邊） |
| Chart 渲染元件 | **現有 ChartIntentRenderer**（Vega-Lite），只是改在分析面板渲染 |

---

## 3. Architecture

### 3.1 execute_analysis Tool

取代 execute_jit。Agent 傳入完整的 steps_mapping（跟 Diagnostic Rule 格式一致）。

```json
{
  "name": "execute_analysis",
  "description": "執行一次性分析：Agent 生成 python code，AIOps sandbox 執行，結果顯示在分析面板。可 promote 為常用 Diagnostic Rule。",
  "input_schema": {
    "type": "object",
    "properties": {
      "title": {
        "type": "string",
        "description": "分析標題（顯示在分析面板頂部）"
      },
      "steps": {
        "type": "array",
        "description": "步驟清單，每步含 step_id + nl_segment + python_code",
        "items": {
          "type": "object",
          "properties": {
            "step_id": {"type": "string"},
            "nl_segment": {"type": "string"},
            "python_code": {"type": "string"}
          }
        }
      },
      "input_params": {
        "type": "object",
        "description": "執行參數（例如 {step: 'STEP_013'}）"
      }
    },
    "required": ["title", "steps", "input_params"]
  }
}
```

### 3.2 Backend 執行流程

```
execute_analysis tool call
  │
  ▼
ToolDispatcher._execute_inner("execute_analysis", ...)
  │
  ▼
POST /api/v1/analysis/run  (新 endpoint)
  │
  ▼
SkillExecutorService._run_script(steps, input_params)
  │ 同 try-run-draft 的 sandbox
  │ 捕獲 _findings + _charts
  │
  ▼
回傳：
{
  "status": "success",
  "title": "...",
  "findings": { condition_met, summary, outputs, impacted_lots },
  "charts": [ _chart DSL objects ],
  "steps_mapping": [...],      // 原始 steps（promote 時用）
  "input_params": {...},       // 原始參數（promote 時用）
  "input_schema_inferred": [...], // 從 input_params 推斷的 schema
}
```

### 3.3 render_card → contract（分析面板）

`_build_render_card` 的 execute_analysis 分支：

```python
if tool_name == "execute_analysis" and result.get("status") == "success":
    charts = result.get("charts") or []
    findings = result.get("findings") or {}
    
    # 轉成 contract 讓分析面板渲染
    visualization = []
    for i, chart in enumerate(charts):
        viz_spec = _chart_intent_to_vega_lite(chart)  # 用 ChartIntentRenderer 的邏輯
        visualization.append({
            "id": f"chart_{i}",
            "type": "vega-lite",
            "spec": viz_spec,
        })
    
    contract = {
        "$schema": "aiops-report/v1",
        "summary": findings.get("summary", ""),
        "evidence_chain": [...],
        "visualization": visualization,
        "suggested_actions": [
            {
                "label": "⭐ 儲存為 Diagnostic Rule",
                "trigger": "promote_analysis",
                "payload": {
                    "title": result["title"],
                    "steps_mapping": result["steps_mapping"],
                    "input_schema": result["input_schema_inferred"],
                    "output_schema": [...],
                }
            }
        ],
    }
    
    return {
        "type": "analysis",
        "contract": contract,
        ...
    }
```

**關鍵**：chart_intents 不再走 copilot 右邊，而是**轉成 Vega-Lite 嵌進 contract.visualization**，走分析面板。

### 3.4 Promote API

```
POST /api/v1/diagnostic-rules/promote
Body:
{
  "name": "SPC 全圖分析",
  "description": "查看指定 step 的所有 SPC charts",
  "auto_check_description": "...",
  "steps_mapping": [...],      // 從 execute_analysis 結果帶過來
  "input_schema": [...],
  "output_schema": [...],
}

Response:
{
  "id": 10,
  "name": "SPC 全圖分析",
  "source": "rule",
  ...
}
```

本質就是 `POST /api/v1/diagnostic-rules`（已有的 CRUD），只是 pre-fill 了所有欄位。

### 3.5 前端 Promote Flow

分析面板 `ContractRenderer` 已經有 `suggested_actions` 渲染。
當 user 點「⭐ 儲存為 Diagnostic Rule」：

1. 前端彈一個 modal：
   - 名稱（pre-fill from title）
   - 描述（pre-fill）
   - 輸入參數（pre-fill from input_schema_inferred，可編輯）
   - [確認儲存]
2. `POST /api/v1/diagnostic-rules`（或 `/promote`）
3. 成功 → toast 提示「已儲存！前往 Diagnostic Rules 查看」
4. 新的 Skill 出現在 `skill_catalog` → 下次 Agent 直接 execute_skill

---

## 4. 改動清單

### Phase A — execute_analysis 取代 execute_jit（Backend）

| # | 檔案 | 改動 |
|---|---|---|
| A1 | `tool_dispatcher.py` | 把 `execute_jit` tool schema 改名為 `execute_analysis`，更新 description |
| A2 | `tool_dispatcher.py` | `_execute_inner` 的 execute_jit case 改為 execute_analysis，路由到新 endpoint |
| A3 | 新增 `routers/analysis.py` | `POST /api/v1/analysis/run` — 呼叫 SkillExecutorService._run_script |
| A4 | `agent_orchestrator_v2/nodes/tool_execute.py` | execute_analysis 結果 → 組 contract（含 visualization + promote action） |
| A5 | `agent_orchestrator_v2/adapter.py` | execute_analysis 的 render_card → synthesis event 帶 contract |
| A6 | `context_loader.py` soul prompt | 更新工具說明：execute_analysis 取代 execute_jit |

### Phase B — Chart 渲染在分析面板（Frontend）

| # | 檔案 | 改動 |
|---|---|---|
| B1 | `ContractRenderer.tsx` | 確保 visualization 裡的 Vega-Lite spec 能正確渲染（已有） |
| B2 | `AICopilot.tsx` | execute_analysis 的 render_card 帶 contract → 走分析面板（左邊），不走 copilot chart_intents |
| B3 | `ChartIntentRenderer.tsx` | 新增 `intentToVegaLite()` export（讓 backend 也能用同樣的轉換邏輯），或在 backend 做轉換 |

### Phase C — Promote to Diagnostic Rule（Backend + Frontend）

| # | 檔案 | 改動 |
|---|---|---|
| C1 | `routers/diagnostic_rules.py` 或新 endpoint | `POST /promote` — 接收 steps_mapping + schemas → 建 Skill record |
| C2 | `ContractRenderer.tsx` / `SuggestedActions.tsx` | 處理 `trigger: "promote_analysis"` action → 彈 promote modal |
| C3 | 新增 `PromoteModal.tsx` | 名稱 + 描述 + input_schema 編輯 + 確認 |
| C4 | `/api/admin/rules/promote/route.ts` | Next.js proxy |

---

## 5. 遷移策略

### execute_jit → execute_analysis

| 面向 | 做法 |
|---|---|
| Tool schema | 直接 rename + 更新 description |
| Agent prompt | soul prompt 裡的 execute_jit 引用全改為 execute_analysis |
| 舊的 execute_jit API (`/agent/jit-analyze`) | 保留為 backward compat alias，內部 redirect 到新 endpoint |
| 記憶體 | 有引用 execute_jit 的 experience memory 不影響（abstracted 後不記 tool name） |
| 前端 copilot | chart_intents 路徑保留但不再是主路徑（分析面板 contract 是主路徑） |

---

## 6. 前後對比

### Before（現在）

```
User: "看 STEP_013 的 SPC charts"
  ↓
Agent → execute_skill(#8) × 5（或 execute_jit 寫 python）
  ↓
chart_intents → copilot 右邊面板（小、擠）
  ↓
用完就沒了（不能 reuse）
```

### After

```
User: "看 STEP_013 的 SPC charts"
  ↓
Agent → execute_analysis({
  title: "STEP_013 SPC 全圖分析",
  steps: [{python_code: "...撈資料 + 組 _charts..."}],
  input_params: {step: "STEP_013"}
})
  ↓
中間分析面板：5 張大圖 + findings 摘要
  ↓
底部按鈕：[⭐ 儲存為 Diagnostic Rule]
  ↓
User 點了 → 永久 Skill → 下次 Agent 直接 execute_skill
```

---

## 7. Edge Cases

| 情況 | 處理 |
|---|---|
| execute_analysis 的 python code 有 bug | sandbox 回 error，分析面板顯示錯誤訊息，不影響 promote |
| User promote 後又想改 code | 去 /admin/skills 編輯（已有的 UI） |
| Agent 不知道該 execute_skill 還是 execute_analysis | skill_catalog 有就用 execute_skill；沒有才用 execute_analysis。soul prompt 引導 |
| 同樣的分析被 promote 兩次 | Skill name unique constraint → 第二次失敗，提示 user 改名 |
| charts 太多（> 10 張）| 分析面板 scroll，不限制 |

---

## 8. Success Criteria

1. ✅ User 問「看 STEP_013 的 SPC charts」→ 5 張圖顯示在**中間分析面板**
2. ✅ 底部有「⭐ 儲存為 Diagnostic Rule」按鈕
3. ✅ 點按鈕 → modal pre-fill → 確認 → Skill 建立成功
4. ✅ 下次問同樣問題 → Agent 直接 execute_skill（不再重新生成 code）
5. ✅ 新 Skill 出現在 /admin/skills 頁面（source=rule）
6. ✅ execute_jit 被完全取代，前端 copilot 不再重複渲染 charts

---

## 9. 不做的事

- 不做自動 promote（User 明確決定才儲存）
- 不做 Skill 版本管理（promote 就是 v1，想改去 admin/skills 手動）
- 不做 input_schema 的自動推斷優化（先用 input_params 的 keys 推斷，不 parse python code）
- 不改 Auto-Patrol / Alarm 觸發邏輯（promote 出來的 Skill 需要 user 手動綁 alarm）

---

請問這份 Spec 是否符合預期？若確認無誤，請回覆「開始開發」。
