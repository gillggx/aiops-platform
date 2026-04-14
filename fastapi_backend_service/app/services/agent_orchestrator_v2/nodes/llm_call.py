"""llm_call node — invokes the LLM via the existing multi-provider client.

Uses the v1 BaseLLMClient.create() API, then converts the response into
LangChain AIMessage with tool_calls so the graph can route properly.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List
from langchain_core.runnables import RunnableConfig

from langchain_core.messages import AIMessage, ToolMessage

from app.services.agent_orchestrator_v2.state import MAX_ITERATIONS
from app.services.tool_dispatcher import TOOL_SCHEMAS

# Tools hidden from LLM — still available internally (e.g. skill code calls execute_mcp)
_LLM_HIDDEN_TOOLS = {"execute_mcp"}
LLM_TOOL_SCHEMAS = [t for t in TOOL_SCHEMAS if t["name"] not in _LLM_HIDDEN_TOOLS]

logger = logging.getLogger(__name__)


def _langchain_messages_to_v1(messages: list, system_text: str) -> tuple[str, list]:
    """Convert LangChain message list → v1 (system, messages) format.

    v1 client expects:
      system: str
      messages: [{"role": "user"|"assistant"|..., "content": str|list}]
    """
    v1_messages = []
    for msg in messages:
        if hasattr(msg, "type"):
            role = "user" if msg.type == "human" else "assistant" if msg.type == "ai" else msg.type
        else:
            role = msg.get("role", "user") if isinstance(msg, dict) else "user"

        content = msg.content if hasattr(msg, "content") else str(msg)

        # If it's an AIMessage with tool_calls, we need to include tool_use blocks
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            content_blocks = []
            if content:
                content_blocks.append({"type": "text", "text": content})
            for tc in msg.tool_calls:
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": tc.get("name", ""),
                    "input": tc.get("args", {}),
                })
            v1_messages.append({"role": "assistant", "content": content_blocks})
        elif isinstance(msg, ToolMessage):
            v1_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }
                ],
            })
        else:
            v1_messages.append({"role": role, "content": content})

    return system_text, v1_messages


def _v1_response_to_tool_calls(response) -> List[Dict[str, Any]]:
    """Extract tool_calls from v1 LLMResponse.content."""
    tool_calls = []
    for block in (response.content or []):
        if isinstance(block, dict) and block.get("type") == "tool_use":
            tool_calls.append({
                "id": block.get("id", ""),
                "name": block.get("name", ""),
                "args": block.get("input", {}),
            })
    return tool_calls


async def llm_call_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM and return an AIMessage (with or without tool_calls)."""
    from app.utils.llm_client import get_llm_client

    llm = get_llm_client()
    system_text = state.get("system_text") or config["configurable"].get("system_text", "")
    messages = state.get("messages", [])
    iteration = state.get("current_iteration", 0) + 1

    # Convert LangChain messages → v1 format
    system, v1_messages = _langchain_messages_to_v1(messages, system_text)

    try:
        response = await llm.create(
            system=system,
            messages=v1_messages,
            max_tokens=8192,
            tools=LLM_TOOL_SCHEMAS,
        )
    except Exception as exc:
        logger.exception("LLM call failed at iteration %d", iteration)
        # Return a synthetic error message so the graph can route to synthesis
        return {
            "messages": [AIMessage(content=f"LLM 呼叫失敗: {exc}")],
            "current_iteration": iteration,
            "force_synthesis": True,
        }

    # Build AIMessage from v1 response
    tool_calls = _v1_response_to_tool_calls(response)

    # Extract text content (strip thinking blocks same as v1)
    text = response.text or ""

    ai_msg = AIMessage(
        content=text,
        tool_calls=tool_calls if tool_calls else [],
        response_metadata={
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "stop_reason": response.stop_reason,
        },
    )

    return {
        "messages": [ai_msg],
        "current_iteration": iteration,
    }
