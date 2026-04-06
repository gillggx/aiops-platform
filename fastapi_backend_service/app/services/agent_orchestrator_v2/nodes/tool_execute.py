"""tool_execute node — runs tools via the existing ToolDispatcher.

Handles:
  - Preflight validation (MISSING_MCP_NAME, MISSING_PARAMS, etc.)
  - Tool execution via dispatcher.execute()
  - Programmatic data distillation
  - Render card building (for SSE tool_done events)
  - Chart rendered notification (sets chart_already_rendered flag)
  - Result trimming for LLM context (large results truncated)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List
from langchain_core.runnables import RunnableConfig

from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


async def tool_execute_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """Execute all tool_calls from the last AIMessage.

    Returns tool result messages + updated state (tools_used, render_cards, flags).
    """
    db = config["configurable"]["db"]
    base_url = config["configurable"]["base_url"]
    auth_token = config["configurable"]["auth_token"]
    user_id = config["configurable"]["user_id"]

    # Import here to avoid circular imports at module level
    from app.services.agent_orchestrator import (
        _preflight_validate,
        _build_render_card,
        _is_spc_result,
        _result_summary,
    )
    from app.services.data_distillation_service import DataDistillationService
    from app.services.tool_dispatcher import ToolDispatcher

    # Get the last AI message's tool_calls
    messages = state["messages"]
    last_msg = messages[-1] if messages else None
    if not last_msg or not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
        return {}

    dispatcher = ToolDispatcher(
        db=db,
        base_url=base_url,
        auth_token=auth_token,
        user_id=user_id,
    )
    distill_svc = DataDistillationService()

    tool_messages: List[ToolMessage] = []
    new_tools_used: List[Dict[str, Any]] = []
    new_render_cards: List[Dict[str, Any]] = []
    chart_rendered = state.get("chart_already_rendered", False)
    last_spc = state.get("last_spc_result")
    force_synth = False

    for tc in last_msg.tool_calls:
        tool_name = tc["name"]
        tool_input = tc.get("args", {})
        tc_id = tc.get("id", "")

        # Preflight validation
        preflight_err = await _preflight_validate(db, tool_name, tool_input)
        if preflight_err:
            result = preflight_err
        else:
            result = await dispatcher.execute(tool_name, tool_input)

        # Track SPC results for auto-contract fallback
        if (tool_name == "execute_mcp" and isinstance(result, dict)
                and _is_spc_result(result)):
            last_spc = (result.get("mcp_name", tool_name), result)

        # Distillation for execute_mcp results
        if tool_name == "execute_mcp" and isinstance(result, dict) and result.get("status") == "success":
            result = await distill_svc.distill_mcp_result(result)

        # Build render card (for SSE events)
        render_card = _build_render_card(tool_name, tool_input, result)
        if render_card:
            new_render_cards.append(render_card)

        # Check if chart was rendered (via _notify_chart_rendered side effect)
        if isinstance(result, dict) and result.get("_chart_rendered"):
            chart_rendered = True

        # Track successful tool uses (for memory lifecycle)
        if isinstance(result, dict) and result.get("status") == "success":
            try:
                result_text = json.dumps(result, ensure_ascii=False, default=str)[:20000]
            except Exception:
                result_text = str(result)[:20000]
            new_tools_used.append({
                "tool": tool_name,
                "mcp_name": tool_input.get("mcp_name", ""),
                "params": {k: v for k, v in tool_input.items()
                           if k not in ("mcp_id", "mcp_name", "python_code", "params")},
                "result_text": result_text,
            })

        # Force synthesis on unrecoverable MCP/skill errors
        if isinstance(result, dict) and result.get("status") == "error":
            if tool_name in ("execute_mcp", "execute_skill"):
                if result.get("code") != "MISSING_PARAMS":
                    force_synth = True

        # Convert result to ToolMessage (trimmed for LLM context)
        result_content = _trim_result_for_llm(result)
        tool_messages.append(ToolMessage(
            content=result_content,
            tool_call_id=tc_id,
            name=tool_name,
        ))

    return {
        "messages": tool_messages,
        # _extend_list reducer will append these to the existing lists
        "tools_used": new_tools_used,
        "render_cards": new_render_cards,
        "chart_already_rendered": chart_rendered,
        "last_spc_result": last_spc,
        "force_synthesis": force_synth or state.get("force_synthesis", False),
    }


def _trim_result_for_llm(result: Any, max_chars: int = 4000) -> str:
    """Trim tool result for LLM context — keep llm_readable_data, drop heavy payloads."""
    if not isinstance(result, dict):
        return str(result)[:max_chars]

    # Prefer llm_readable_data (designed for LLM consumption)
    lrd = result.get("llm_readable_data")
    if lrd:
        if isinstance(lrd, str):
            return lrd[:max_chars]
        try:
            return json.dumps(lrd, ensure_ascii=False, default=str)[:max_chars]
        except Exception:
            pass

    # Fallback: strip heavy keys, serialize the rest
    trimmed = dict(result)
    for key in ("output_data", "ui_render_payload", "_raw_dataset", "dataset", "_data_profile"):
        trimmed.pop(key, None)
    try:
        text = json.dumps(trimmed, ensure_ascii=False, default=str)
        return text[:max_chars]
    except Exception:
        return str(result)[:max_chars]
