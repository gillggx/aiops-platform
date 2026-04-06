"""synthesis node — extracts final_text and contract from the last AIMessage.

The LLM has already generated its final answer (stop_reason=end_turn).
This node:
  1. Extracts the text content
  2. Strips <contract> blocks, parses them via _resolve_contract
  3. Applies CHART RENDERED mode (strips visualization when chart_intents rendered)
  4. Strips <plan> tag if present
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)


async def synthesis_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """Extract final answer + contract from the conversation state."""
    from app.services.agent_orchestrator import _resolve_contract

    messages = state["messages"]
    last_msg = messages[-1] if messages else None
    text = ""
    if last_msg and hasattr(last_msg, "content"):
        text = last_msg.content or ""

    # Strip <plan> blocks (these were consumed by stage_update events earlier)
    text_clean = re.sub(r"<plan>[\s\S]*?</plan>", "", text).strip()

    # Build contract (applies CHART RENDERED mode + SPC auto-contract fallback)
    chart_rendered = state.get("chart_already_rendered", False)
    last_spc = state.get("last_spc_result")
    contract = _resolve_contract(text, last_spc, chart_rendered)

    # Strip <contract> block from user-visible text
    if chart_rendered:
        text_clean = re.sub(r"<contract>[\s\S]*?</contract>", "", text_clean).strip()

    return {
        "final_text": text_clean,
        "contract": contract,
    }
