"""load_context node — wraps ContextLoader.build() for the LangGraph agent.

Produces: system_blocks, system_text, retrieved_memory_ids, context_meta,
          messages (seed with system message + history), history_turns.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from langchain_core.runnables import RunnableConfig

from langchain_core.messages import HumanMessage, SystemMessage

from app.services.context_loader import ContextLoader
from app.services.task_context_extractor import extract as extract_task_context

logger = logging.getLogger(__name__)


async def load_context_node(state: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
    """Stage 1: build system prompt, retrieve memories, load session history."""
    db = config["configurable"]["db"]
    user_id = state["user_id"]
    user_message = state["user_message"]
    canvas_overrides = state.get("canvas_overrides")

    # Task context extraction (same as v1)
    _tc_type, _tc_subject, _tc_tool = extract_task_context(user_message)
    task_context = {
        "task_type": _tc_type,
        "data_subject": _tc_subject,
        "tool_name": _tc_tool,
    }

    loader = ContextLoader(db)
    system_blocks, context_meta = await loader.build(
        user_id=user_id,
        query=user_message,
        top_k_memories=5,
        canvas_overrides=canvas_overrides,
        task_context=task_context,
    )

    # Flatten system blocks into a single text (for LLM providers that
    # take system as a string, not as content blocks)
    system_text = "\n".join(
        b.get("text", "") for b in system_blocks if isinstance(b, dict)
    )

    # Extract retrieved experience memory IDs for feedback loop
    retrieved_memory_ids = [
        int(h["id"])
        for h in context_meta.get("rag_hits", [])
        if h.get("_source") == "experience" and isinstance(h.get("id"), int)
    ]

    # Load session history
    from app.services.agent_orchestrator_v2.session import load_session
    session_id, history_messages, cumulative_tokens = await load_session(
        db, state.get("session_id"), user_id,
    )

    # Build initial messages: history + current user message
    messages = list(history_messages) + [HumanMessage(content=user_message)]

    context_meta["history_turns"] = len(history_messages) // 2
    context_meta["cumulative_tokens"] = cumulative_tokens

    return {
        "session_id": session_id,
        "system_blocks": system_blocks,
        "system_text": system_text,
        "retrieved_memory_ids": retrieved_memory_ids,
        "context_meta": context_meta,
        "messages": messages,
        "history_turns": context_meta["history_turns"],
    }
