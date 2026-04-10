"""Render card builder — converts tool execution results into UI render cards.

Migrated from v1 agent_orchestrator.py. Each tool type produces a specific
card type that the frontend uses to render the result (chart_intents,
contract for AnalysisPanel, table, etc.).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from app.services.agent_orchestrator_v2.helpers import _notify_chart_rendered

logger = logging.getLogger(__name__)


def _build_render_card(
    tool_name: str,
    tool_input: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Build a render card dict for SSE tool_done events.

    Returns None for tools that don't need UI rendering (e.g. internal tools).
    """
    # ── execute_skill ──
    if tool_name == "execute_skill" and isinstance(result, dict) and "ui_render_payload" in result:
        lrd = result.get("llm_readable_data") or {}
        urp = result.get("ui_render_payload") or {}

        chart_intents = result.get("charts") or urp.get("chart_intents")
        if chart_intents:
            _notify_chart_rendered(result, chart_intents)

        card: Dict[str, Any] = {
            "type": "skill",
            "skill_name": result.get("skill_name", f"Skill #{tool_input.get('skill_id')}"),
            "status": lrd.get("status", "UNKNOWN"),
            "conclusion": lrd.get("summary", "") or lrd.get("diagnosis_message", ""),
            "summary": lrd.get("summary", ""),
            "problem_object": lrd.get("impacted_lots", []) or lrd.get("problematic_targets", []),
            "mcp_output": {
                "ui_render": {
                    "chart_data": urp.get("chart_data"),
                    "charts": [urp["chart_data"]] if urp.get("chart_data") else [],
                },
                "dataset": urp.get("dataset"),
                "_raw_dataset": urp.get("dataset"),
                "_call_params": tool_input.get("params", {}),
            },
        }
        if chart_intents:
            card["chart_intents"] = chart_intents
            # Build contract for AnalysisPanel rendering (no promote — already a Skill)
            from app.services.agent_orchestrator_v2.nodes.tool_execute import _chart_intent_to_vega_lite
            visualization = []
            for i, ci in enumerate(chart_intents):
                try:
                    vega_spec = _chart_intent_to_vega_lite(ci)
                    visualization.append({
                        "id": f"chart_{i}",
                        "type": "vega-lite",
                        "title": ci.get("title", ""),
                        "spec": vega_spec,
                    })
                except Exception:
                    pass
            if visualization:
                skill_name = result.get("skill_name", f"Skill #{tool_input.get('skill_id')}")
                card["contract"] = {
                    "$schema": "aiops-report/v1",
                    "summary": lrd.get("summary", f"{skill_name} 執行結果"),
                    "evidence_chain": [],
                    "visualization": visualization,
                    "suggested_actions": [],  # No promote — already a Skill
                }
        return card

    # ── execute_mcp ──
    if tool_name == "execute_mcp" and isinstance(result, dict) and result.get("status") == "success":
        od = result.get("output_data") or {}
        mcp_id = tool_input.get("mcp_id")
        mcp_name = result.get("mcp_name") or f"MCP #{mcp_id}"
        dataset = od.get("dataset")
        raw_dataset = od.get("_raw_dataset") or dataset

        return {
            "type": "mcp",
            "mcp_name": mcp_name,
            "mcp_output": {
                "ui_render": od.get("ui_render") or {},
                "dataset": dataset,
                "_raw_dataset": raw_dataset,
                "_call_params": tool_input.get("params", {}),
                "_is_processed": od.get("_is_processed", True),
            },
        }

    # ── draft_* tools ──
    _DRAFT_TOOL_TYPE_MAP = {
        "draft_skill": "skill",
        "draft_mcp": "mcp",
        "draft_routine_check": "routine_check",
        "draft_event_skill_link": "event_skill_link",
    }
    if tool_name in _DRAFT_TOOL_TYPE_MAP and isinstance(result, dict) and "draft_id" in result:
        draft_type = _DRAFT_TOOL_TYPE_MAP[tool_name]
        deep_link = result.get("deep_link_data") or {}
        return {
            "type": "draft",
            "draft_type": draft_type,
            "draft_id": result["draft_id"],
            "auto_fill": deep_link.get("auto_fill") or {},
        }

    # ── navigate ──
    if tool_name == "navigate" and isinstance(result, dict) and result.get("action") == "navigate":
        return {
            "type": "navigate",
            "target": result.get("target"),
            "id": result.get("id"),
            "message": result.get("message", ""),
        }

    # ── execute_utility ──
    if tool_name == "execute_utility" and isinstance(result, dict):
        tool_result = result.get("data") if "data" in result else result
        if isinstance(tool_result, dict) and tool_result.get("status") == "success":
            payload = tool_result.get("payload") or {}
            return {
                "type": "utility",
                "tool_name": tool_input.get("tool_name", "utility"),
                "summary": tool_result.get("summary", ""),
                "payload": payload,
            }

    # ── analyze_data ──
    if tool_name == "analyze_data" and isinstance(result, dict):
        if result.get("status") == "success":
            ad_data = result.get("data") or {}
            chart_json = ad_data.get("chart_json")
            payload: Dict[str, Any] = {}
            if chart_json:
                try:
                    payload["plotly"] = json.loads(chart_json) if isinstance(chart_json, str) else chart_json
                except Exception:
                    payload["chart_json"] = chart_json
            result_table = ad_data.get("result_table")
            if result_table and isinstance(result_table, list) and result_table:
                payload["rows"] = result_table
                payload["columns"] = list(result_table[0].keys())
            if not chart_json:
                stats = ad_data.get("stats") or {}
                if isinstance(stats, dict):
                    payload.update(stats)
            title = ad_data.get("title") or f"{ad_data.get('template', 'analyze_data')} 分析"

            contract = None
            if payload.get("plotly"):
                _notify_chart_rendered(result, [payload["plotly"]])
                contract = {
                    "$schema": "aiops-report/v1",
                    "summary": title,
                    "evidence_chain": [],
                    "visualization": [{
                        "id": "analyze_chart",
                        "type": "plotly",
                        "title": title,
                        "spec": payload["plotly"],
                    }],
                    "suggested_actions": [],
                }

            card: Dict[str, Any] = {
                "type": "utility",
                "tool_name": title,
                "summary": title,
                "payload": payload,
                "row_count": ad_data.get("row_count", 0),
                "jit_mcp_id": tool_input.get("mcp_id"),
                "jit_run_params": tool_input.get("run_params", {}),
                "jit_python_code": "",
                "jit_title": title,
                "analyze_template": tool_input.get("template"),
                "analyze_params": tool_input.get("params", {}),
                "analyze_stats": ad_data.get("stats") or {},
            }
            if contract:
                card["contract"] = contract
            return card

    # ── execute_analysis ──
    if tool_name == "execute_analysis" and isinstance(result, dict):
        if result.get("status") == "success":
            data = result.get("data") or {}
            charts = data.get("charts") or []
            findings = data.get("findings") or {}

            from app.services.agent_orchestrator_v2.nodes.tool_execute import _chart_intent_to_vega_lite
            visualization = []
            for i, chart in enumerate(charts):
                try:
                    vega_spec = _chart_intent_to_vega_lite(chart)
                    visualization.append({
                        "id": f"chart_{i}",
                        "type": "vega-lite",
                        "title": chart.get("title", f"Chart {i+1}"),
                        "spec": vega_spec,
                    })
                except Exception:
                    pass

            promote_payload = {
                "title": data.get("title", ""),
                "steps_mapping": data.get("steps_mapping", []),
                "input_schema": data.get("input_schema", []),
                "output_schema": data.get("output_schema", []),
            }

            contract = {
                "$schema": "aiops-report/v1",
                "summary": findings.get("summary", data.get("title", "")),
                "evidence_chain": [
                    {"step": i + 1, "tool": s.get("step_id", ""), "finding": s.get("nl_segment", "")}
                    for i, s in enumerate(data.get("steps_mapping", []))
                ],
                "visualization": visualization,
                "suggested_actions": [
                    {
                        "label": "⭐ 儲存為我的 Skill",
                        "trigger": "promote_analysis",
                        "payload": promote_payload,
                    },
                ],
            }

            if charts:
                _notify_chart_rendered(result, charts)

            return {
                "type": "analysis",
                "tool_name": data.get("title", "Ad-hoc 分析"),
                "summary": findings.get("summary", ""),
                "contract": contract,
            }

    # ── execute_jit (legacy) ──
    if tool_name == "execute_jit" and isinstance(result, dict):
        if result.get("status") == "success":
            jit_data = result.get("data") or {}
            chart_json = jit_data.get("chart_json")
            chart_intents = jit_data.get("chart_intents")
            jit_result = jit_data.get("jit_result") or {}
            payload: Dict[str, Any] = {}
            if chart_intents:
                payload["chart_intents"] = chart_intents
                _notify_chart_rendered(result, chart_intents)
            elif chart_json:
                try:
                    payload["plotly"] = json.loads(chart_json) if isinstance(chart_json, str) else chart_json
                except Exception:
                    payload["chart_json"] = chart_json
            else:
                payload = {k: v for k, v in jit_result.items()
                           if not isinstance(v, (list, dict)) or k == "summary"}
            return {
                "type": "utility",
                "tool_name": jit_data.get("title", "JIT 分析"),
                "summary": jit_data.get("title", "JIT 分析"),
                "payload": payload,
                "row_count": jit_data.get("row_count", 0),
                "jit_mcp_id": tool_input.get("mcp_id"),
                "jit_run_params": tool_input.get("run_params", {}),
                "jit_python_code": tool_input.get("python_code", ""),
                "jit_title": tool_input.get("title", "JIT 分析"),
            }

    return None
