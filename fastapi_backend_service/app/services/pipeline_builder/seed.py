"""Seed 5 standard Phase-1 blocks into DB (idempotent).

Called from main.py lifespan. Uses BlockRepository.upsert to keep
(name, version) as the natural key.

All Phase-1 blocks are status='production' so Phase 1 pipelines can use them.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.block_repository import BlockRepository

logger = logging.getLogger(__name__)


def _blocks() -> list[dict[str, Any]]:
    return [
        {
            "name": "block_process_history",
            "version": "1.0.0",
            "category": "source",
            "status": "production",
            "description": (
                "== What ==\n"
                "拉取指定條件（機台 / 批次 / 站點）在時間區間內的製程歷史資料。\n"
                "底層 MCP: get_process_info。每列一筆 process event，所有維度 (SPC/APC/DC/RECIPE/FDC/EC) 被 flatten 成寬表。\n"
                "\n"
                "== Input options ==\n"
                "tool_id / lot_id / step — **三擇一必填**，可同時指定多個提升精度\n"
                "object_name (選填) — 指定後只回該維度欄位；不帶則回所有維度寬表\n"
                "time_range — 1h / 24h / 7d / 30d（預設 24h）\n"
                "\n"
                "== Output columns ==\n"
                "基礎：eventTime, toolID, lotID, step, spc_status, fdc_classification\n"
                "SPC:   spc_<chart>_value / _ucl / _lcl / _is_ooc （chart: xbar/r/s/p/c）\n"
                "APC:   apc_<param_name> （~20 個 parameter）\n"
                "DC:    dc_<sensor_name>（~30 個 sensor）\n"
                "RECIPE:recipe_version + recipe_<param_name>\n"
                "FDC:   fdc_classification, fdc_fault_code, fdc_confidence, fdc_description\n"
                "EC:    ec_<const>_value / _nominal / _deviation_pct / _status\n"
            ),
            "input_schema": [],
            "output_schema": [
                {"port": "data", "type": "dataframe", "columns": ["eventTime", "toolID", "lotID", "step", "spc_status"]},
            ],
            "param_schema": {
                "type": "object",
                "properties": {
                    "tool_id":    {"type": "string", "title": "機台 ID (三擇一)", "x-suggestions": "tool_id"},
                    "lot_id":     {"type": "string", "title": "批次 ID (三擇一)"},
                    "step":       {"type": "string", "title": "站點 Step (三擇一)", "x-suggestions": "step"},
                    "object_name": {
                        "type": "string",
                        "title": "資料維度 (選填，留空=全部)",
                        "enum": ["", "SPC", "APC", "DC", "RECIPE", "FDC", "EC"],
                    },
                    "time_range": {"type": "string", "enum": ["1h", "24h", "7d", "30d"], "default": "24h", "title": "時間窗"},
                    "event_time": {"type": "string", "title": "精確時間 (ISO8601，選填)"},
                    "limit":      {"type": "integer", "default": 100, "minimum": 1, "maximum": 200, "title": "筆數上限"},
                },
            },
            "implementation": {
                "type": "python",
                "ref": "app.services.pipeline_builder.blocks.process_history:ProcessHistoryBlockExecutor",
            },
            "output_columns_hint": [
                # Base columns — always present
                {"name": "eventTime", "type": "datetime", "description": "事件時間 (ISO8601 字串，block_sort/block_linear_regression 會自動轉 epoch)"},
                {"name": "toolID", "type": "string", "description": "機台 ID，e.g. EQP-01"},
                {"name": "lotID", "type": "string", "description": "批次 ID"},
                {"name": "step", "type": "string", "description": "製程站點，e.g. STEP_013"},
                {"name": "spc_status", "type": "string", "description": "'PASS' | 'OOC' — SPC 總體判定（注意不是 status）"},
                {"name": "fdc_classification", "type": "string", "description": "FDC 分類，e.g. 'anomaly_detected'"},
                # SPC family — flat per chart_type
                {"name": "spc_xbar_chart_value", "type": "number", "when_present": "object_name=SPC + chart_type=xbar_chart"},
                {"name": "spc_xbar_chart_ucl", "type": "number", "when_present": "object_name=SPC + chart_type=xbar_chart"},
                {"name": "spc_xbar_chart_lcl", "type": "number", "when_present": "object_name=SPC + chart_type=xbar_chart"},
                {"name": "spc_xbar_chart_is_ooc", "type": "boolean", "when_present": "object_name=SPC + chart_type=xbar_chart"},
                {"name": "spc_r_chart_value", "type": "number", "when_present": "SPC + chart_type=r_chart"},
                {"name": "spc_r_chart_ucl", "type": "number", "when_present": "SPC + chart_type=r_chart"},
                {"name": "spc_r_chart_lcl", "type": "number", "when_present": "SPC + chart_type=r_chart"},
                {"name": "spc_s_chart_value", "type": "number", "when_present": "SPC + chart_type=s_chart"},
                {"name": "spc_p_chart_value", "type": "number", "when_present": "SPC + chart_type=p_chart"},
                {"name": "spc_c_chart_value", "type": "number", "when_present": "SPC + chart_type=c_chart"},
                # APC — dynamic per param_name
                {"name": "apc_<param_name>", "type": "number", "description": "APC 參數值，<param_name> 會展開，e.g. apc_etch_time_offset / apc_rf_power_bias / apc_chamber_pressure", "when_present": "object_name=APC"},
                # DC — dynamic per sensor
                {"name": "dc_<sensor_name>", "type": "number", "description": "DC sensor 讀值，e.g. dc_temperature / dc_gas_flow", "when_present": "object_name=DC"},
                # RECIPE
                {"name": "recipe_version", "type": "string", "when_present": "object_name=RECIPE"},
                {"name": "recipe_<param_name>", "type": "number", "description": "Recipe 參數設定值", "when_present": "object_name=RECIPE"},
                # FDC
                {"name": "fdc_fault_code", "type": "string", "when_present": "object_name=FDC"},
                {"name": "fdc_confidence", "type": "number", "when_present": "object_name=FDC"},
                {"name": "fdc_description", "type": "string", "when_present": "object_name=FDC"},
                # EC
                {"name": "ec_<const>_value", "type": "number", "when_present": "object_name=EC"},
                {"name": "ec_<const>_deviation_pct", "type": "number", "when_present": "object_name=EC"},
            ],
        },
        {
            "name": "block_filter",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "根據 column/operator/value 過濾 DataFrame 列。\n"
                "支援 operator: ==, !=, >, <, >=, <=, contains, in。\n"
                "'in' 的 value 必須是 list。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["column", "operator"],
                "properties": {
                    "column":   {"type": "string", "x-column-source": "input.data"},
                    "operator": {
                        "type": "string",
                        "enum": ["==", "!=", ">", "<", ">=", "<=", "contains", "in"],
                    },
                    "value":    {},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.filter:FilterBlockExecutor"},
        },
        {
            "name": "block_threshold",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "對 column 做閾值判斷，為 Logic Node（統一 triggered+evidence schema）。\n"
                "\n"
                "== Two modes ==\n"
                "  Mode A — UCL/LCL bound（傳統 SPC 用法）\n"
                "    bound_type='upper' → violates if value > upper_bound\n"
                "    bound_type='lower' → violates if value < lower_bound\n"
                "    bound_type='both'  → upper or lower\n"
                "\n"
                "  Mode B — generic operator comparison（Phase 4-A+）\n"
                "    operator ∈ {==, !=, >=, <=, >, <} + target\n"
                "    numeric column 數值比較；非數值 column 僅支援 ==/!=\n"
                "    常用場景：搭配 block_count_rows 做「row count == 1」等檢查\n"
                "\n"
                "== Output (PR-A evidence semantics) ==\n"
                "  triggered (bool)      — 是否有任一 row 違反\n"
                "  evidence  (dataframe) — **全部被評估的 rows**（不是篩選子集），加欄：\n"
                "                           triggered_row (bool)  — 該筆是否違規\n"
                "                           violation_side(str)   — 'above' / 'below' / None\n"
                "                           violated_bound(float) — 比較的 bound 值\n"
                "                           explanation(str)      — 違規描述\n"
                "  👉 要顯示 raw 資料（5 筆 process）→ chart 接 evidence 就能看全部，加\n"
                "     highlight_column='triggered_row' 可紅圈標記違規點。\n"
                "  👉 要只看違規列 → chart 先 filter(triggered_row==true) 再接 chart。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [
                {"port": "triggered", "type": "bool"},
                {"port": "evidence", "type": "dataframe"},
            ],
            "param_schema": {
                "type": "object",
                "required": ["column"],
                "properties": {
                    "column":      {"type": "string", "x-column-source": "input.data"},
                    # Mode A (legacy)
                    "bound_type":  {"type": "string", "enum": ["upper", "lower", "both"], "title": "Mode A: UCL/LCL 模式"},
                    "upper_bound": {"type": "number"},
                    "lower_bound": {"type": "number"},
                    # Mode B (generic)
                    "operator":    {"type": "string", "enum": ["==", "!=", ">=", "<=", ">", "<"], "title": "Mode B: 通用比較運算子"},
                    "target":      {"title": "Mode B: 目標值（數字或字串）"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.threshold:ThresholdBlockExecutor"},
        },
        {
            "name": "block_count_rows",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "算上游 DataFrame 有幾 row，輸出 1-row DF with `count` 欄位。\n"
                "若 `group_by` 有給，按該欄位分組，每組一 row。\n"
                "\n"
                "== Use case ==\n"
                "  「OOC events 是不是都來自同一個 recipe?」\n"
                "  → filter(OOC) → groupby_agg(recipeID, count) → **count_rows** → threshold(operator='==', target=1)\n"
                "  count_rows 把「有幾個 unique recipe」變成單一 count 值，threshold 就能比「==1」判定。\n"
                "\n"
                "== Params ==\n"
                "  group_by (opt) — 有給時按欄位分組 count\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe) — 1 row (無 group_by) 或 N rows (含 group_by + count)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "properties": {
                    "group_by": {"type": "string", "x-column-source": "input.data", "title": "Group by (選填)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.count_rows:CountRowsBlockExecutor"},
        },
        {
            "name": "block_mcp_foreach",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "對上游 DataFrame 每一 row 呼叫指定 MCP，把 response 合併成新欄位。\n"
                "Async concurrent — `max_concurrency` 限制同時 in-flight 的 HTTP 請求數（預設 5）。\n"
                "\n"
                "== Use case ==\n"
                "  「每筆 process 取 APC context 做趨勢分析」：\n"
                "  process_history(limit=10) → mcp_foreach(mcp_name='get_process_context',\n"
                "    args_template={'targetID':'$lotID', 'step':'$step'},\n"
                "    result_prefix='apc_') → 下游 delta / consecutive_rule\n"
                "\n"
                "== Params ==\n"
                "  mcp_name        (required) — MCP 名稱（必須註冊在 mcp_definitions 表）\n"
                "  args_template   (required, object) — 傳給 MCP 的 args；值可用 `$col_name` 引用當前 row 欄位\n"
                "  result_prefix   (opt)      — 合併時的欄位前綴（避免名稱衝突；e.g. 'apc_'）\n"
                "  max_concurrency (opt, default 5) — 同時 in-flight 的請求數\n"
                "\n"
                "== Result merging ==\n"
                "  dict 回傳 → 每 key 轉成欄位（加 prefix）\n"
                "  list[dict] → 取第 1 筆（1:1 展開）\n"
                "  其他 → 存成 `<prefix>raw` JSON 欄位\n"
                "\n"
                "== Limits ==\n"
                "  上游最多 500 rows（超過 raise TOO_MANY_ROWS；先 filter/limit）\n"
                "  單一 call 失敗會讓整個 block fail（fail-fast）"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["mcp_name", "args_template"],
                "properties": {
                    "mcp_name":        {"type": "string"},
                    "args_template":   {"type": "object", "title": "MCP args (可用 $col 引用 row 欄位)"},
                    "result_prefix":   {"type": "string", "default": "", "title": "結果欄位前綴"},
                    "max_concurrency": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.mcp_foreach:McpForeachBlockExecutor"},
        },
        {
            "name": "block_consecutive_rule",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "Tail-based 連續 N 次 True 偵測（Logic Node）。\n"
                "\n"
                "== Semantics ==\n"
                "  反映 **當下狀態**：按 sort_by 排序後，每個 group 檢查**最後 N 筆**是否全為 True。\n"
                "  - 是：該 group 觸發，其 tail N rows `triggered_row=True`\n"
                "  - 否：不觸發（即使歷史上曾有 run >= N）\n"
                "  用於即時告警。需要歷史掃描時另外用 transform + groupby 組合。\n"
                "\n"
                "== Params ==\n"
                "  flag_column (required) — bool column；通常上游是 block_threshold.evidence.triggered_row 或 block_delta 的 is_rising\n"
                "  count       (required) — N（>= 2）\n"
                "  sort_by     (required) — 排序欄位（e.g. 'eventTime'）；**不會預設**，必填\n"
                "  group_by    (optional) — 每組獨立評估（e.g. toolID）\n"
                "\n"
                "== Output (PR-A evidence semantics) ==\n"
                "  triggered (bool)      — 任一 group 的最後 N 筆全為 True\n"
                "  evidence  (dataframe) — **全部輸入 rows（按 group+sort_by 排序）**；加欄：\n"
                "      triggered_row (bool) — 該筆是否屬於觸發 tail\n"
                "      group, trigger_id, run_position, run_length（僅觸發列填值）"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [
                {"port": "triggered", "type": "bool"},
                {"port": "evidence", "type": "dataframe"},
            ],
            "param_schema": {
                "type": "object",
                "required": ["flag_column", "count", "sort_by"],
                "properties": {
                    "flag_column": {"type": "string", "x-column-source": "input.data"},
                    "count":       {"type": "integer", "minimum": 2},
                    "sort_by":     {"type": "string", "x-column-source": "input.data", "title": "Sort by (必填)"},
                    "group_by":    {"type": "string", "x-column-source": "input.data", "title": "Group by (選填)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.consecutive_rule:ConsecutiveRuleBlockExecutor"},
        },
        {
            "name": "block_delta",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "計算相鄰點的差值與 trend 旗標（rising / falling）。\n"
                "\n"
                "== Use case ==\n"
                "  偵測「連續 3 點上升」這類 trend rule → 先用 block_delta 產生 is_rising，\n"
                "  再接 block_consecutive_rule(flag_column=<value>_is_rising, count=3)。\n"
                "\n"
                "== Params ==\n"
                "  value_column (required) — 監控欄位（numeric）\n"
                "  sort_by      (required) — 排序欄位（e.g. eventTime）；**不預設**\n"
                "  group_by     (optional) — 各組獨立算 delta（第一筆 NaN）\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe) — 輸入 df 外加 3 欄：\n"
                "    <value_column>_delta      (number)\n"
                "    <value_column>_is_rising  (bool, delta > 0)\n"
                "    <value_column>_is_falling (bool, delta < 0)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["value_column", "sort_by"],
                "properties": {
                    "value_column": {"type": "string", "x-column-source": "input.data"},
                    "sort_by":      {"type": "string", "x-column-source": "input.data", "title": "Sort by (必填)"},
                    "group_by":     {"type": "string", "x-column-source": "input.data", "title": "Group by (選填)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.delta:DeltaBlockExecutor"},
        },
        {
            "name": "block_join",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "兩個 DataFrame by key 合併。\n"
                "key 可為單一 column name 或 list；how 支援 inner / left / right / outer。\n"
                "右表同名 column 自動加 '_r' 後綴。"
            ),
            "input_schema": [
                {"port": "left", "type": "dataframe"},
                {"port": "right", "type": "dataframe"},
            ],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["key"],
                "properties": {
                    # Show the set of columns common to both left and right ports
                    "key": {
                        "type": "string",
                        "title": "Join key(s); 逗號分隔多欄",
                        "x-column-source": "input.left+right",
                    },
                    "how": {"type": "string", "enum": ["inner", "left", "right", "outer"], "default": "inner"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.join:JoinBlockExecutor"},
        },
        {
            "name": "block_groupby_agg",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "Group by + 聚合（mean / sum / count / min / max / median / std）。\n"
                "輸出欄位名為 {agg_column}_{agg_func}，e.g. value_mean。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["group_by", "agg_column", "agg_func"],
                "properties": {
                    "group_by":   {"type": "string", "title": "Group by column (逗號分隔多欄)", "x-column-source": "input.data"},
                    "agg_column": {"type": "string", "x-column-source": "input.data"},
                    "agg_func": {
                        "type": "string",
                        "enum": ["mean", "sum", "count", "min", "max", "median", "std"],
                    },
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.groupby_agg:GroupByAggBlockExecutor"},
        },
        {
            "name": "block_chart",
            "version": "1.0.0",
            "category": "output",
            "status": "production",
            "description": (
                "== What ==\n"
                "產生圖表 spec（chart_spec）。預設 Vega-Lite（單 y 簡單圖）；符合下列條件會自動切\n"
                "到 ChartDSL (Plotly) 模式：\n"
                "  - 任一 SPC 控制欄位有給（ucl/lcl/center/highlight）\n"
                "  - y 是 array（多條線）\n"
                "  - y_secondary 有給（雙 Y 軸）\n"
                "  - chart_type='boxplot' 或 'heatmap'\n"
                "\n"
                "== chart_type ==\n"
                "  line / bar / scatter / area — 標準\n"
                "  boxplot                     — 箱型圖，x=group_by 欄位、y=value column\n"
                "  heatmap                     — 熱圖，x/y 為類別欄位、value_column 為 cell 值\n"
                "  distribution                — 直方圖 + 常態 PDF 曲線 + μ/±σ 線 + USL/LSL；value_column 給 raw 欄位即可（不需先跑 histogram）\n"
                "  table                       — 以表格呈現 data（不需 x/y）。可選 `columns` 限制欄位、`max_rows` 限制列數（預設 500）\n"
                "\n"
                "== SPC sigma_zones (line chart only) ==\n"
                "  sigma_zones=[1, 2] → 除 UCL/LCL 外加畫 ±1σ / ±2σ 細線（顏色綠→紅逐級深），\n"
                "  σ = (UCL - Center) / 3 自動推算；用於 Nelson A/B/C zone 視覺化。\n"
                "\n"
                "== y params ==\n"
                "  y: string | string[]  — 單值或多值（多值時自動畫多條線）\n"
                "  y_secondary: string[] — 右側 Y 軸系列（雙軸，e.g. TC16 SPC xbar + APC rf_power）\n"
                "\n"
                "== SPC 場景建議搭配 ==\n"
                "  chart_type='line', x='eventTime', y='spc_xbar_chart_value',\n"
                "  ucl_column='spc_xbar_chart_ucl', lcl_column='spc_xbar_chart_lcl',\n"
                "  highlight_column='spc_xbar_chart_is_ooc'\n"
                "→ 標準 xbar 控制圖：值折線 + UCL/LCL 紅虛線 + OOC 紅圈\n"
                "\n"
                "== Boxplot 用法 ==\n"
                "  chart_type='boxplot', y='spc_xbar_chart_value', group_by='toolID'\n"
                "\n"
                "== Heatmap 用法 ==\n"
                "  chart_type='heatmap', x='col_a', y='col_b', value_column='correlation'\n"
                "  常搭配 block_correlation 的 long-format 輸出。\n"
                "\n"
                "== sequence ==\n"
                "多張 chart 在 Pipeline Results 面板的顯示順序；新增時前端自動配 max+1。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "chart_spec", "type": "dict"}],
            "param_schema": {
                "type": "object",
                "required": ["chart_type"],
                "properties": {
                    "chart_type": {"type": "string", "enum": ["line", "bar", "scatter", "area", "boxplot", "heatmap", "distribution", "table"]},
                    "x":     {"type": "string", "x-column-source": "input.data"},
                    # y: string OR array of strings (multi-line / dual-axis)
                    "y":     {"type": ["string", "array"], "items": {"type": "string"}, "x-column-source": "input.data", "title": "y (string or array)"},
                    "y_secondary": {"type": ["string", "array"], "items": {"type": "string"}, "title": "右側 Y 軸欄位 (選填，string/array)", "x-column-source": "input.data"},
                    "value_column": {"type": "string", "title": "heatmap/distribution value 欄位", "x-column-source": "input.data"},
                    "group_by": {"type": "string", "title": "boxplot group_by (boxplot 專用)", "x-column-source": "input.data"},
                    # v3.5 distribution mode params
                    "bins":             {"type": "integer", "minimum": 2, "default": 20, "title": "直方圖 bins (distribution)"},
                    "usl":              {"type": "number", "title": "USL (distribution / SPC)"},
                    "lsl":              {"type": "number", "title": "LSL (distribution / SPC)"},
                    "show_sigma_lines": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 6}, "default": [1, 2, 3], "title": "Distribution σ 線 (1..6)"},
                    # v3.5 SPC line chart extra
                    "sigma_zones":      {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 6}, "title": "SPC ±σ zones 線 (e.g. [1, 2])"},
                    "color": {"type": "string", "x-column-source": "input.data"},
                    # v1.3 B2 style panel
                    "title": {"type": "string", "title": "標題"},
                    "color_scheme": {
                        "type": "string",
                        "enum": ["", "tableau10", "set2", "blues", "reds", "greens"],
                        "default": "",
                        "title": "Color scheme",
                    },
                    "show_legend": {"type": "boolean", "default": True, "title": "顯示圖例"},
                    "width":  {"type": "integer", "default": 600},
                    "height": {"type": "integer", "default": 300},
                    # v3.2 SPC extensions — 任一給值就走 SPC 模式（Plotly）
                    "ucl_column":       {"type": "string", "title": "UCL 欄位 (SPC)", "x-column-source": "input.data"},
                    "lcl_column":       {"type": "string", "title": "LCL 欄位 (SPC)", "x-column-source": "input.data"},
                    "center_column":    {"type": "string", "title": "Center 欄位 (SPC，選填)", "x-column-source": "input.data"},
                    "highlight_column": {"type": "string", "title": "OOC highlight 欄位 (bool)", "x-column-source": "input.data"},
                    # v3.2: 多圖顯示用流水號（1..N）；pipeline 結果面板按此排序
                    "sequence": {
                        "type": "integer",
                        "minimum": 1,
                        "title": "顯示順序（流水號）",
                        "description": "Canvas Pipeline Results 面板按此遞增排序展示多張 charts。新增時前端自動指派 max+1。",
                    },
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.chart:ChartBlockExecutor"},
        },
        {
            "name": "block_shift_lag",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "將指定 column 平移 N 列（pandas .shift(N)）→ 輸出 <column>_lag<N> 欄位；\n"
                "若 compute_delta=true，也輸出 <column>_delta = current - previous。\n"
                "適合計算批次之間的 drift（e.g. APC rf_power_bias 本批 vs 上批）。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["column", "offset"],
                "properties": {
                    "column":   {"type": "string", "title": "目標欄位", "x-column-source": "input.data"},
                    "offset":   {"type": "integer", "default": 1, "title": "Offset（正=過去、負=未來）"},
                    "group_by": {"type": "string", "title": "Group by（選填；各組內獨立 shift）", "x-column-source": "input.data"},
                    "sort_by":  {"type": "string", "title": "Sort by（選填，預設 eventTime）", "x-column-source": "input.data"},
                    "compute_delta": {"type": "boolean", "default": True, "title": "同時輸出 delta 欄位"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.shift_lag:ShiftLagBlockExecutor"},
        },
        {
            "name": "block_rolling_window",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "滑動視窗統計（pandas .rolling(window)）。\n"
                "func 支援 mean / std / min / max / sum / median；輸出 <column>_rolling_<func> 欄位。\n"
                "常用情境：近 5 筆移動平均；近 10 筆標準差作為 volatility 指標。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["column", "window", "func"],
                "properties": {
                    "column":  {"type": "string", "title": "目標欄位", "x-column-source": "input.data"},
                    "window":  {"type": "integer", "minimum": 1, "default": 5, "title": "Window size"},
                    "func":    {"type": "string", "enum": ["mean", "std", "min", "max", "sum", "median"], "default": "mean"},
                    "min_periods": {"type": "integer", "minimum": 1, "default": 1, "title": "min_periods"},
                    "group_by": {"type": "string", "title": "Group by（選填）", "x-column-source": "input.data"},
                    "sort_by":  {"type": "string", "title": "Sort by（選填，預設 eventTime）", "x-column-source": "input.data"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.rolling_window:RollingWindowBlockExecutor"},
        },
        {
            "name": "block_weco_rules",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "Western Electric / Nelson 控制圖規則（SPC）— Logic Node（triggered + evidence schema）。\n"
                "\n"
                "支援 8 條 Nelson 完整規則：\n"
                "  R1 = 1 點 > 3σ（OOC）\n"
                "  R2 = 連續 9 點同側（mean shift）\n"
                "  R3 = 連續 6 點嚴格上升或下降（systematic trend）\n"
                "  R4 = 連續 14 點 up/down 交替（over-adjustment）\n"
                "  R5 = 3 點中 2 點 > 2σ 同側（early warning）\n"
                "  R6 = 5 點中 4 點 > 1σ 同側（gradual drift）\n"
                "  R7 = 連續 15 點在 ±1σ 內（stratification / sensor stuck）\n"
                "  R8 = 連續 8 點在 ±1σ 外（bimodal distribution）\n"
                "\n"
                "σ 來源（sigma_source）：\n"
                "  from_ucl_lcl — 預設；σ = (ucl_column 平均 - center) / 3\n"
                "  from_value   — σ = 該欄位自身的 std\n"
                "  manual       — 使用者給 manual_sigma 數字\n"
                "\n"
                "center_column 有給則用該欄位平均；否則用 value_column 平均。\n"
                "\n"
                "Output (PR-A evidence semantics):\n"
                "  triggered (bool)      — 是否有任一 rule 被觸發\n"
                "  evidence  (dataframe) — **全部輸入 rows（按 group+sort_by 排序）**，加欄：\n"
                "                          triggered_row(bool)     — 該筆是否觸發任一 rule\n"
                "                          triggered_rules(str)    — 觸發的 rule ids（CSV，e.g. 'R1,R5'）\n"
                "                          violation_side(str|None)— 'above'/'below'/None\n"
                "                          center, sigma           — SPC 基線（每 group 一致）"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [
                {"port": "triggered", "type": "bool"},
                {"port": "evidence", "type": "dataframe"},
            ],
            "param_schema": {
                "type": "object",
                "required": ["value_column"],
                "properties": {
                    "value_column":  {"type": "string", "title": "監控指標欄位", "x-column-source": "input.data"},
                    "center_column": {"type": "string", "title": "Center Line 欄位（選填）", "x-column-source": "input.data"},
                    "sigma_source":  {
                        "type": "string",
                        "enum": ["from_ucl_lcl", "from_value", "manual"],
                        "default": "from_ucl_lcl",
                        "title": "σ 來源",
                    },
                    "ucl_column":    {"type": "string", "title": "UCL 欄位（sigma_source=from_ucl_lcl 時用）", "x-column-source": "input.data"},
                    "manual_sigma":  {"type": "number", "title": "σ 數字（sigma_source=manual 時用）"},
                    "rules": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8"]},
                        "default": ["R1", "R2", "R5", "R6"],
                        "title": "啟用規則 (Nelson R1..R8；預設 4 條常用)",
                    },
                    "group_by": {"type": "string", "title": "Group by（選填，每組獨立評估）", "x-column-source": "input.data"},
                    "sort_by":  {"type": "string", "title": "Sort by（選填，預設 eventTime）", "x-column-source": "input.data"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.weco_rules:WecoRulesBlockExecutor"},
        },
        {
            "name": "block_unpivot",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "Wide → long 轉換（pandas melt）。把多欄位「攤平」成一個分類欄 + 一個值欄。\n"
                "\n"
                "== Use case ==\n"
                "  SPC 寬表有 spc_xbar_chart_value / spc_r_chart_value / spc_s_chart_value / ...\n"
                "  要「對每個 chart_type 各做一次 regression / capability」→ 先 unpivot 成 long，\n"
                "  下游用 group_by=chart_type 一次處理所有 type。\n"
                "\n"
                "== Params ==\n"
                "  id_columns    (required, array) — 保留的識別欄 (eventTime/toolID/...)\n"
                "  value_columns (required, array) — 要 melt 的欄位清單\n"
                "  variable_name (default 'variable') — 新增「原欄位名」欄名，e.g. 'chart_type'\n"
                "  value_name    (default 'value')    — 新增「原欄位值」欄名\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe, long format)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["id_columns", "value_columns"],
                "properties": {
                    "id_columns":    {"type": "array", "items": {"type": "string"}, "title": "保留欄位"},
                    "value_columns": {"type": "array", "items": {"type": "string"}, "title": "要 melt 的欄位"},
                    "variable_name": {"type": "string", "default": "variable", "title": "分類欄名"},
                    "value_name":    {"type": "string", "default": "value", "title": "值欄名"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.unpivot:UnpivotBlockExecutor"},
        },
        {
            "name": "block_union",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "兩個 DataFrame 的縱向合併（row-wise concat）。\n"
                "\n"
                "== Use case ==\n"
                "  分別拉 EQP-01, EQP-02 的 process_history 後合併成一張 → 下游 overlay 比較。\n"
                "\n"
                "== Input ports ==\n"
                "  primary   (dataframe)\n"
                "  secondary (dataframe)\n"
                "\n"
                "== Params ==\n"
                "  on_schema_mismatch: 'outer' (預設，聯集欄位，缺值填 null) | 'intersect' (僅共同欄位)\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe) — primary rows 在前，secondary 在後"
            ),
            "input_schema": [
                {"port": "primary", "type": "dataframe"},
                {"port": "secondary", "type": "dataframe"},
            ],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "properties": {
                    "on_schema_mismatch": {
                        "type": "string",
                        "enum": ["outer", "intersect"],
                        "default": "outer",
                        "title": "欄位不符時",
                    },
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.union:UnionBlockExecutor"},
        },
        {
            "name": "block_cpk",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "Process capability 指標：Cp / Cpu / Cpl / Cpk / Pp / Ppk。\n"
                "\n"
                "== Formulas ==\n"
                "  Cp  = (USL - LSL) / (6σ)\n"
                "  Cpu = (USL - μ) / (3σ)\n"
                "  Cpl = (μ - LSL) / (3σ)\n"
                "  Cpk = min(Cpu, Cpl)\n"
                "  Pp/Ppk 在 MVP 等於 Cp/Cpk（短期=長期）\n"
                "\n"
                "== Params ==\n"
                "  value_column (required)\n"
                "  usl / lsl    — 至少給一個（單邊也可）\n"
                "  group_by     — 各組獨立算 Cpk (optional)\n"
                "\n"
                "== Output ==\n"
                "  stats (dataframe) — per group: n / mu / sigma / cp / cpu / cpl / cpk / pp / ppk / usl / lsl / group"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "stats", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["value_column"],
                "properties": {
                    "value_column": {"type": "string", "x-column-source": "input.data"},
                    "usl":          {"type": "number", "title": "USL (upper spec limit)"},
                    "lsl":          {"type": "number", "title": "LSL (lower spec limit)"},
                    "group_by":     {"type": "string", "title": "Group by (選填)", "x-column-source": "input.data"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.cpk:CpkBlockExecutor"},
        },
        {
            "name": "block_any_trigger",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "OR 多個 logic node 的 triggered 值 + 合併所有 evidence。\n"
                "用於「任一 rule 觸發 → 發單一聚合告警」的場景，避免 alarm fatigue。\n"
                "\n"
                "== Use case ==\n"
                "  監控 5 張 SPC charts（Xbar/R/S/P/C）各自用 block_weco_rules 判斷 → 串進\n"
                "  block_any_trigger 合併 → 接 block_alert → 任一 chart 觸發就發一封告警，\n"
                "  evidence 會自動加 source_port 欄位標註是誰觸發的。\n"
                "\n"
                "== Input ports ==\n"
                "  trigger_1 .. trigger_4 (bool, 最少連一個)\n"
                "  evidence_1 .. evidence_4 (dataframe, 選填；與 trigger_N 配對使用)\n"
                "\n"
                "== Output (PR-A evidence semantics) ==\n"
                "  triggered (bool)      — 任一 trigger_* 為 true\n"
                "  evidence  (dataframe) — **所有連接 port 的 evidence concat**（不只觸發的，\n"
                "                          保留完整 audit trail），加欄：\n"
                "                           source_port(str)   — 來自哪個 trigger_N\n"
                "                           triggered_row(bool)— 該列是否觸發（沿用上游或 port-level bool）"
            ),
            "input_schema": [
                {"port": "trigger_1", "type": "bool"},
                {"port": "trigger_2", "type": "bool"},
                {"port": "trigger_3", "type": "bool"},
                {"port": "trigger_4", "type": "bool"},
                {"port": "evidence_1", "type": "dataframe"},
                {"port": "evidence_2", "type": "dataframe"},
                {"port": "evidence_3", "type": "dataframe"},
                {"port": "evidence_4", "type": "dataframe"},
            ],
            "output_schema": [
                {"port": "triggered", "type": "bool"},
                {"port": "evidence", "type": "dataframe"},
            ],
            "param_schema": {"type": "object", "properties": {}},
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.any_trigger:AnyTriggerBlockExecutor"},
        },
        {
            "name": "block_correlation",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "計算多欄位 pairwise correlation matrix（long format）。可直接餵 block_chart(heatmap)。\n"
                "\n"
                "== Params ==\n"
                "  columns (required, array) — 要納入的數值欄位（>= 2）\n"
                "  method  (default 'pearson') — 'pearson' | 'spearman' | 'kendall'\n"
                "\n"
                "== Output ==\n"
                "  matrix (dataframe, long) — col_a / col_b / correlation / p_value / n\n"
                "  搭配 block_chart(chart_type=heatmap, x=col_a, y=col_b, value_column=correlation)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "matrix", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["columns"],
                "properties": {
                    "columns": {"type": "array", "items": {"type": "string"}, "title": "納入欄位"},
                    "method":  {"type": "string", "enum": ["pearson", "spearman", "kendall"], "default": "pearson"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.correlation:CorrelationBlockExecutor"},
        },
        {
            "name": "block_hypothesis_test",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "常用統計假設檢定：Welch t-test / one-way ANOVA / chi-square independence。\n"
                "\n"
                "== Params ==\n"
                "  test_type (required) — 't_test' (2 組均值) / 'anova' (3+ 組均值) / 'chi_square' (類別獨立性)\n"
                "  value_column   — required for t_test / anova\n"
                "  group_column   — required (分組欄位)\n"
                "  target_column  — required for chi_square（與 group_column 做列聯）\n"
                "  alpha (default 0.05) — 顯著水準\n"
                "\n"
                "== Output ==\n"
                "  stats (dataframe, 1 row) — test / statistic / p_value / significant(bool) + test-specific fields\n"
                "\n"
                "Errors: INSUFFICIENT_DATA (n<2 per group), INVALID_INPUT (wrong group count)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "stats", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["test_type", "group_column"],
                "properties": {
                    "test_type":     {"type": "string", "enum": ["t_test", "anova", "chi_square"]},
                    "value_column":  {"type": "string", "x-column-source": "input.data", "title": "數值欄位 (t_test/anova)"},
                    "group_column":  {"type": "string", "x-column-source": "input.data"},
                    "target_column": {"type": "string", "x-column-source": "input.data", "title": "類別欄位 (chi_square)"},
                    "alpha":         {"type": "number", "minimum": 0.001, "maximum": 0.5, "default": 0.05},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.hypothesis_test:HypothesisTestBlockExecutor"},
        },
        {
            "name": "block_ewma",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "Exponentially Weighted Moving Average（指數加權移動平均）。\n"
                "相較 block_rolling_window（固定長度 SMA），EWMA 權重遞減，對近期更敏感。\n"
                "\n"
                "== Params ==\n"
                "  value_column (required)\n"
                "  alpha        (required, 0 < α < 1) — 平滑係數；越大越響應近期\n"
                "  sort_by      (required)\n"
                "  group_by     (opt) — 各組獨立 EWMA\n"
                "  adjust       (default False) — 傳給 pandas .ewm(adjust=)\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe) + <value_column>_ewma 欄位"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["value_column", "alpha", "sort_by"],
                "properties": {
                    "value_column": {"type": "string", "x-column-source": "input.data"},
                    "alpha":        {"type": "number", "minimum": 0.001, "maximum": 0.999, "default": 0.2, "title": "平滑係數 α"},
                    "sort_by":      {"type": "string", "x-column-source": "input.data"},
                    "group_by":     {"type": "string", "title": "Group by (選填)", "x-column-source": "input.data"},
                    "adjust":       {"type": "boolean", "default": False},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.ewma:EwmaBlockExecutor"},
        },
        {
            "name": "block_mcp_call",
            "version": "1.0.0",
            "category": "source",
            "status": "production",
            "description": (
                "== What ==\n"
                "通用 MCP 呼叫器。從 mcp_definitions 表讀 MCP 的 api_config（endpoint_url / method /\n"
                "headers），帶 params.args 去 GET 或 POST，回傳 DataFrame。\n"
                "\n"
                "== When to use ==\n"
                "  呼叫**沒有專用 block** 的 MCP（e.g. list_tools / get_alarm_list / get_tool_status）。\n"
                "  已有 specialized block 的 MCP（e.g. get_process_info → block_process_history）優先用\n"
                "  specialized block — 它懂特定回傳的 flatten 邏輯（如 SPC 展開）。\n"
                "\n"
                "== Params ==\n"
                "  mcp_name (required) — MCP 名字（必須在 mcp_definitions 註冊）\n"
                "  args     (optional object) — 丟給 MCP 的 query params / body\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe) — 自動從回傳 JSON 抽 list：events / dataset / items / data / records / rows；\n"
                "                     都沒有則把整個回傳當單筆 row\n"
                "\n"
                "Errors: MCP_NOT_FOUND / INVALID_MCP_CONFIG / MCP_HTTP_ERROR / MCP_UNREACHABLE"
            ),
            "input_schema": [],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["mcp_name"],
                "properties": {
                    "mcp_name": {"type": "string", "title": "MCP 名稱"},
                    "args":     {"type": "object", "title": "呼叫參數 (object)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.mcp_call:McpCallBlockExecutor"},
            "output_columns_hint": [
                {"name": "<dynamic>", "type": "object", "description": "欄位取決於 MCP 的回傳結構；若要查 process 資料優先用 block_process_history（已 flatten）。對於 list_tools / get_alarm_list 等簡單回傳，每個回傳 object 的 key 會成為一個 column"},
            ],
        },
        {
            "name": "block_linear_regression",
            "version": "1.0.0",
            "category": "logic",
            "status": "production",
            "description": (
                "== What ==\n"
                "OLS 線性回歸 y = slope * x + intercept，支援 group_by 分組。\n"
                "\n"
                "== Use case ==\n"
                "  SPC vs APC 關係（e.g. spc_xbar vs apc_rf_power_bias）→ R²、殘差、CI band\n"
                "\n"
                "== Output ports ==\n"
                "  stats (dataframe) — per-group row: slope / intercept / r_squared / p_value / n / stderr / group\n"
                "  data  (dataframe) — 原 df + <y>_pred + <y>_residual + group（可餵 chart(scatter)）\n"
                "  ci    (dataframe) — 密集網格：x / pred / ci_lower / ci_upper / group（畫信賴區間帶）\n"
                "\n"
                "Errors: INSUFFICIENT_DATA when n<3 or x variance=0"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [
                {"port": "stats", "type": "dataframe"},
                {"port": "data", "type": "dataframe"},
                {"port": "ci", "type": "dataframe"},
            ],
            "param_schema": {
                "type": "object",
                "required": ["x_column", "y_column"],
                "properties": {
                    "x_column":   {"type": "string", "x-column-source": "input.data"},
                    "y_column":   {"type": "string", "x-column-source": "input.data"},
                    "group_by":   {"type": "string", "title": "Group by (選填)", "x-column-source": "input.data"},
                    "confidence": {"type": "number", "minimum": 0.5, "maximum": 0.999, "default": 0.95, "title": "CI 水準 (0–1)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.linear_regression:LinearRegressionBlockExecutor"},
        },
        {
            "name": "block_histogram",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "計算數值欄位的 histogram（直方圖分布）+ 基本統計。\n"
                "若想畫「常態分佈圖（含鐘形曲線 + σ 線）」，**直接用 block_chart(chart_type='distribution')** 更方便；\n"
                "block_histogram 適合單純拿 bin 資料做自訂下游處理。\n"
                "\n"
                "== Params ==\n"
                "  value_column (required)\n"
                "  bins         — 整數（等寬 bin 數；預設 20）\n"
                "  group_by     — 各組獨立計算\n"
                "\n"
                "== Output ports ==\n"
                "  data  (dataframe) — group / bin_left / bin_right / bin_center / count / density\n"
                "  stats (dataframe) — group / n / mu / sigma / skewness（per-group summary；供下游讀 μ/σ）"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [
                {"port": "data", "type": "dataframe"},
                {"port": "stats", "type": "dataframe"},
            ],
            "param_schema": {
                "type": "object",
                "required": ["value_column"],
                "properties": {
                    "value_column": {"type": "string", "x-column-source": "input.data"},
                    "bins":         {"type": "integer", "minimum": 2, "default": 20, "title": "Bin 數"},
                    "group_by":     {"type": "string", "title": "Group by (選填)", "x-column-source": "input.data"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.histogram:HistogramBlockExecutor"},
        },
        {
            "name": "block_sort",
            "version": "1.0.0",
            "category": "transform",
            "status": "production",
            "description": (
                "== What ==\n"
                "多欄排序 + optional top-N cap。用於「OOC 最多的 3 台機台」這類 ranking 場景。\n"
                "\n"
                "== Params ==\n"
                "  columns (required, array) — e.g. [{\"column\":\"ooc_count\",\"order\":\"desc\"}]\n"
                "  limit   (optional, int)   — 保留前 N 列\n"
                "\n"
                "== Output ==\n"
                "  data (dataframe)"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["columns"],
                "properties": {
                    "columns": {
                        "type": "array",
                        "title": "排序欄位 (list of {column, order})",
                        "items": {
                            "type": "object",
                            "properties": {
                                "column": {"type": "string"},
                                "order":  {"type": "string", "enum": ["asc", "desc"], "default": "asc"},
                            },
                        },
                    },
                    "limit":   {"type": "integer", "minimum": 1, "title": "Top-N (選填)"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.sort:SortBlockExecutor"},
        },
        {
            "name": "block_alert",
            "version": "1.0.0",
            "category": "output",
            "status": "production",
            "description": (
                "== What ==\n"
                "當上游 Logic Node 觸發時，包裝成一筆告警 record；**不負責呈現 evidence**。\n"
                "Evidence 呈現由 Canvas 從 Logic Node 的 evidence port 直接展示。\n"
                "\n"
                "== Connect ==\n"
                "  input.triggered ← upstream logic_node.triggered   (bool)\n"
                "  input.evidence  ← upstream logic_node.evidence    (dataframe)\n"
                "  上游必須是 Logic Node（block_threshold / block_consecutive_rule / block_weco_rules）。\n"
                "\n"
                "== Behaviour ==\n"
                "  triggered=False → output.alert 為空 DF（不做事）\n"
                "  triggered=True  → output.alert 一筆 row：severity / title / message /\n"
                "                    evidence_count / first_event_time / last_event_time / emitted_at\n"
                "\n"
                "  title_template / message_template 支援 {column_name}（從 evidence 第一筆取）\n"
                "                                    及 {evidence_count}"
            ),
            "input_schema": [
                {"port": "triggered", "type": "bool"},
                {"port": "evidence", "type": "dataframe"},
            ],
            "output_schema": [{"port": "alert", "type": "dataframe"}],
            "param_schema": {
                "type": "object",
                "required": ["severity"],
                "properties": {
                    "severity": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"]},
                    "title_template": {"type": "string"},
                    "message_template": {"type": "string"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.alert:AlertBlockExecutor"},
        },
        {
            "name": "block_data_view",
            "version": "1.0.0",
            "category": "output",
            "status": "production",
            "description": (
                "== What ==\n"
                "把上游 DataFrame **釘在 Pipeline Results 的資料視圖區**，讓人類可以在執行結果\n"
                "面板看到任何中間步驟的資料，不需要配置 chart_type/x/y 等圖表參數。\n"
                "\n"
                "== When to use ==\n"
                "  - Diagnostic Rule 要把「最近 N 筆 process 資料」當輸出秀給工程師\n"
                "  - 想 audit 某個中間 node 的輸出（接一條邊過去即可，純顯示用）\n"
                "  - 比 block_chart(chart_type='table') **更輕量**：沒有 chart schema 的包袱\n"
                "\n"
                "== Multiple views ==\n"
                "  同一 pipeline 可以放多個 block_data_view（例如一個秀原始 5 筆 + 一個秀 Filter 後的 3 筆）。\n"
                "  用 `sequence` 參數控制呈現順序（ascending；未指定則以 canvas position.x 為 tiebreak）。\n"
                "\n"
                "== Output ==\n"
                "  data_view (dict) — Pipeline Results 自動收集到 result_summary.data_views；\n"
                "                      前端以表格呈現（含 title + description + columns + rows）。"
            ),
            "input_schema": [{"port": "data", "type": "dataframe"}],
            "output_schema": [{"port": "data_view", "type": "dict"}],
            "param_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "title": "標題（預設 'Data View'）"},
                    "description": {"type": "string", "title": "副標（選填）"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "string"},
                        "title": "要顯示的欄位（未指定則全部）",
                    },
                    "max_rows": {"type": "integer", "minimum": 1, "default": 200, "title": "最多顯示列數（預設 200）"},
                    "sequence": {"type": "integer", "title": "多視圖時的排序（ascending）"},
                },
            },
            "implementation": {"type": "python", "ref": "app.services.pipeline_builder.blocks.data_view:DataViewBlockExecutor"},
        },
    ]


async def _deprecate_renamed_blocks(db: AsyncSession) -> None:
    """Mark legacy-named blocks as deprecated so they stop appearing in the catalog."""
    renamed = [("block_mcp_fetch", "1.0.0")]  # renamed to block_process_history
    repo = BlockRepository(db)
    for name, version in renamed:
        existing = await repo.get_by_name_version(name, version)
        if existing is not None and existing.status != "deprecated":
            existing.status = "deprecated"
            await db.flush()
            logger.info("Pipeline Builder: deprecated legacy block %s@%s", name, version)


async def seed_phase1_blocks(db: AsyncSession) -> int:
    """Upsert Phase-1 standard blocks. Returns count of blocks seeded."""
    await _deprecate_renamed_blocks(db)
    from app.services.pipeline_builder.seed_examples import examples_by_name
    repo = BlockRepository(db)
    specs = _blocks()
    examples_map = examples_by_name()
    for spec in specs:
        examples = examples_map.get(spec["name"], [])
        # Split optional field out of spec to avoid duplicate kwargs in upsert
        out_cols_hint = spec.pop("output_columns_hint", None)
        await repo.upsert(**spec, examples=examples, output_columns_hint=out_cols_hint)
    await db.commit()
    logger.info("Pipeline Builder: seeded %d standard blocks", len(specs))
    return len(specs)
