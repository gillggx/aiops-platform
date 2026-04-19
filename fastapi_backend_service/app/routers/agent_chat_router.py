"""Agent Chat Router — POST /agent/chat/stream (v13 Real Agentic Loop).

This is the main entry point for the v13 agentic platform.
Replaces /diagnose/copilot-chat for new clients (old endpoint preserved for compat).

SSE event types (in order):
  context_load → thinking → tool_start → tool_done → synthesis → memory_write → done/error
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select, delete

from app.database import get_db
from app.dependencies import get_current_user
from app.models.agent_session import AgentSessionModel
from app.models.user import UserModel
from app.services.agent_orchestrator_v2 import AgentOrchestratorV2

router = APIRouter(prefix="/agent", tags=["agent-v13"])


class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    # Optional overrides for testing
    context_overrides: Dict[str, Any] = {}


@router.post(
    "/chat/stream",
    summary="v13 真實 Agentic Loop — SSE 串流",
    response_class=StreamingResponse,
)
async def agent_chat_stream(
    body: AgentChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    """Run the v13 five-stage agentic loop and stream SSE events.

    Event format: `data: {JSON}\\n\\n`

    Event types:
    - `context_load`  — Context assembled (soul_preview, rag_hits, pref_summary)
    - `thinking`      — LLM thinking block text
    - `tool_start`    — About to execute a tool (tool, input, iteration)
    - `tool_done`     — Tool finished (tool, result_summary, iteration)
    - `synthesis`     — Final natural-language answer
    - `memory_write`  — Long-term memory auto-persisted (content, source)
    - `error`         — Error or MAX_ITERATIONS hit
    - `done`          — Stream complete (session_id)
    """
    # Internal loopback — tool_dispatcher calls self via HTTP.
    # Detect actual listening port from request, fallback to config or 8001.
    base_url = str(request.base_url).rstrip("/")
    if "aiops" in base_url or "443" in base_url or "https" in base_url:
        # Nginx proxied request — use loopback to actual backend port
        base_url = f"http://127.0.0.1:{request.scope.get('server', ('', 8001))[1]}"

    # Extract JWT token from Authorization header for internal API calls
    auth_header = request.headers.get("Authorization", "")
    auth_token = auth_header.removeprefix("Bearer ").strip()

    orchestrator = AgentOrchestratorV2(
        db=db,
        base_url=base_url,
        auth_token=auth_token,
        user_id=current_user.id,
        canvas_overrides=body.context_overrides or None,
    )

    async def event_stream():
        try:
            gen = orchestrator.run(
                message=body.message,
                session_id=body.session_id,
            )
            async for event in gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            err = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("/session/{session_id}", summary="清除指定 Session（開啟新對話）")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    await db.execute(
        delete(AgentSessionModel).where(
            AgentSessionModel.session_id == session_id,
            AgentSessionModel.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"status": "success", "cleared": session_id}


# ── Phase 5-UX-3b: session as first-class resource ─────────────────────────────

@router.post("/session", summary="建立新 Agent session")
async def create_session(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Create an empty Agent session. Used by /chat/new to issue a stable
    session_id before the user types their first message."""
    import uuid
    new_sid = str(uuid.uuid4())
    row = AgentSessionModel(
        session_id=new_sid,
        user_id=current_user.id,
        messages="[]",
        cumulative_tokens=0,
    )
    db.add(row)
    await db.commit()
    return {
        "session_id": new_sid,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/session/{session_id}", summary="讀取 session（含對話歷史 + 最近 pipeline）")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return session details for /chat/[id] page hydration.

    Includes:
      - messages: chronological [{role, content}]
      - last_pipeline_json: canvas snapshot from last build_pipeline call (or null)
      - last_pipeline_run_id: run id to look up result_summary
    """
    row = (await db.execute(
        select(AgentSessionModel).where(
            AgentSessionModel.session_id == session_id,
            AgentSessionModel.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    try:
        messages = json.loads(row.messages or "[]")
    except Exception:
        messages = []
    last_pipe = None
    if row.last_pipeline_json:
        try:
            last_pipe = json.loads(row.last_pipeline_json)
        except Exception:
            last_pipe = None

    return {
        "session_id": row.session_id,
        "title": row.title,
        "messages": messages,
        "cumulative_tokens": row.cumulative_tokens or 0,
        "last_pipeline_json": last_pipe,
        "last_pipeline_run_id": row.last_pipeline_run_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/sessions", summary="列出我的 sessions（近期優先）")
async def list_sessions(
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> list[Dict[str, Any]]:
    """Return recent sessions for the current user — for a 'My Chats' UI."""
    rows = (await db.execute(
        select(AgentSessionModel)
        .where(AgentSessionModel.user_id == current_user.id)
        .order_by(AgentSessionModel.updated_at.desc().nullslast(), AgentSessionModel.created_at.desc())
        .limit(max(1, min(100, limit)))
    )).scalars().all()

    out = []
    for r in rows:
        out.append({
            "session_id": r.session_id,
            "title": r.title or "(untitled)",
            "has_pipeline": bool(r.last_pipeline_json),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return out
