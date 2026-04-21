"""LLM client façade — real Anthropic when ``LLM_PROVIDER=anthropic``.

Env contract:
    LLM_PROVIDER           stub | anthropic     (default stub)
    ANTHROPIC_API_KEY      sk-ant-...           required when provider=anthropic
    ANTHROPIC_MODEL        claude-*             default claude-sonnet-4-20250514

The ``llm_stream(system, user_msg)`` signature is stable; the backing client
is chosen at call time so a single env flip switches production from stub to
real Claude without a code change.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncIterator

log = logging.getLogger("python_ai_sidecar.llm")


def _stub_reply(user_msg: str) -> str:
    head = user_msg.strip().replace("\n", " ")
    if len(head) > 200:
        head = head[:200] + "…"
    return f"(stub LLM reply) received: {head}"


async def _stub_stream(user_msg: str) -> AsyncIterator[str]:
    reply = _stub_reply(user_msg)
    for token in reply.split(" "):
        await asyncio.sleep(0.02)
        yield token + " "


async def _anthropic_stream(system: str, user_msg: str) -> AsyncIterator[str]:
    # Lazy import so stub-only deployments don't need the SDK.
    from anthropic import AsyncAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        log.warning("ANTHROPIC_API_KEY missing — falling back to stub")
        async for tok in _stub_stream(user_msg):
            yield tok
        return

    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514").strip()
    max_tokens = int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024"))

    client = AsyncAnthropic(api_key=api_key)
    try:
        async with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            async for chunk in stream.text_stream:
                yield chunk
    except Exception as ex:  # noqa: BLE001 — fall back to stub so chat never dies
        log.warning("Anthropic call failed (%s) — falling back to stub", ex.__class__.__name__)
        async for tok in _stub_stream(user_msg):
            yield tok


async def llm_stream(system: str, user_msg: str) -> AsyncIterator[str]:
    """Yields tokens one at a time — shape-compatible with streaming LLM APIs."""
    provider = os.getenv("LLM_PROVIDER", "stub").lower()
    if provider == "anthropic":
        async for tok in _anthropic_stream(system, user_msg):
            yield tok
        return
    async for tok in _stub_stream(user_msg):
        yield tok


async def llm_complete(system: str, user_msg: str) -> str:
    chunks: list[str] = []
    async for tok in llm_stream(system, user_msg):
        chunks.append(tok)
    return "".join(chunks).strip()
