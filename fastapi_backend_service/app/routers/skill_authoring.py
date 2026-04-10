"""Skill Authoring router — interactive multi-turn Skill creation.

Endpoints:
  POST   /skill-authoring/sessions               — create new session
  GET    /skill-authoring/sessions               — list user's sessions
  GET    /skill-authoring/sessions/{id}          — get full session detail
  POST   /skill-authoring/sessions/{id}/clarify  — SSE: Agent produces understanding + questions
  POST   /skill-authoring/sessions/{id}/respond  — user replies to clarification
  POST   /skill-authoring/sessions/{id}/generate — SSE: Phase 1-3 generation
  POST   /skill-authoring/sessions/{id}/try-run  — execute current steps
  POST   /skill-authoring/sessions/{id}/feedback — record user rating + comment
  POST   /skill-authoring/sessions/{id}/revise   — SSE: regenerate from feedback
  POST   /skill-authoring/sessions/{id}/save     — promote to skill_definitions
  DELETE /skill-authoring/sessions/{id}          — delete session
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import StandardResponse
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import UserModel
from app.services.skill_authoring_service import SkillAuthoringService
from app.utils.llm_client import get_llm_client

router = APIRouter(prefix="/skill-authoring", tags=["skill-authoring"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _get_svc(db: AsyncSession = Depends(get_db)) -> SkillAuthoringService:
    return SkillAuthoringService(db=db, llm=get_llm_client())


def _serialize_session(s) -> Dict[str, Any]:
    """Convert session model to API response dict."""
    def _j(text):
        if not text:
            return []
        try:
            return json.loads(text) if isinstance(text, str) else text
        except Exception:
            return []

    return {
        "id": s.id,
        "user_id": s.user_id,
        "target_type": s.target_type,
        "state": s.state,
        "initial_prompt": s.initial_prompt,
        "target_context": _j(s.target_context),
        "turns": _j(s.turns),
        "current_understanding": s.current_understanding,
        "current_steps_mapping": _j(s.current_steps_mapping),
        "current_input_schema": _j(s.current_input_schema),
        "current_output_schema": _j(s.current_output_schema),
        "last_test_result": _j(s.last_test_result) if isinstance(s.last_test_result, str) else s.last_test_result,
        "promoted_skill_id": s.promoted_skill_id,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


# ── Schemas ──────────────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    target_type: str = Field(..., pattern="^(my_skill|auto_patrol|diagnostic_rule)$")
    initial_prompt: str = Field(..., min_length=5)
    target_context: Optional[Dict[str, Any]] = None


class RespondRequest(BaseModel):
    content: str = Field(..., min_length=1)


class TryRunRequest(BaseModel):
    mock_payload: Optional[Dict[str, Any]] = None


class FeedbackRequest(BaseModel):
    rating: str = Field(..., pattern="^(correct|wrong|partial)$")
    comment: str = ""


class SaveRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.post("", response_model=StandardResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    svc: SkillAuthoringService = Depends(_get_svc),
    current_user: UserModel = Depends(get_current_user),
):
    session = await svc.create_session(
        user_id=current_user.id,
        target_type=body.target_type,
        initial_prompt=body.initial_prompt,
        target_context=body.target_context,
    )
    return StandardResponse.success(data=_serialize_session(session), message="Session 已建立")


@router.get("", response_model=StandardResponse)
async def list_sessions(
    svc: SkillAuthoringService = Depends(_get_svc),
    current_user: UserModel = Depends(get_current_user),
):
    sessions = await svc.list_sessions(user_id=current_user.id)
    return StandardResponse.success(data=[_serialize_session(s) for s in sessions])


@router.get("/{session_id}", response_model=StandardResponse)
async def get_session(
    session_id: int,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message=f"Session #{session_id} 不存在", status_code=404)
    return StandardResponse.success(data=_serialize_session(session))


@router.delete("/{session_id}", response_model=StandardResponse)
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    _: UserModel = Depends(get_current_user),
):
    from app.models.skill_authoring_session import SkillAuthoringSessionModel
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(SkillAuthoringSessionModel).where(SkillAuthoringSessionModel.id == session_id))
    await db.commit()
    return StandardResponse.success(message="Session 已刪除")


# ── State transition endpoints ───────────────────────────────────────────────

@router.post("/{session_id}/clarify")
async def clarify_intent(
    session_id: int,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)

    return StreamingResponse(
        svc.clarify(session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/respond", response_model=StandardResponse)
async def respond_to_clarification(
    session_id: int,
    body: RespondRequest,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)
    await svc.respond(session, body.content)
    return StandardResponse.success(data=_serialize_session(session), message="已記錄")


@router.post("/{session_id}/generate")
async def generate_steps(
    session_id: int,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)

    return StreamingResponse(
        svc.generate(session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/try-run", response_model=StandardResponse)
async def try_run(
    session_id: int,
    body: TryRunRequest = TryRunRequest(),
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)
    result = await svc.try_run(session, mock_payload=body.mock_payload)
    return StandardResponse.success(data=result, message="試跑完成")


@router.post("/{session_id}/feedback", response_model=StandardResponse)
async def submit_feedback(
    session_id: int,
    body: FeedbackRequest,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)
    await svc.feedback(session, body.rating, body.comment)
    return StandardResponse.success(data=_serialize_session(session), message="Feedback 已記錄")


@router.post("/{session_id}/revise")
async def revise(
    session_id: int,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)

    return StreamingResponse(
        svc.revise(session),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{session_id}/save", response_model=StandardResponse)
async def save_session(
    session_id: int,
    body: SaveRequest,
    svc: SkillAuthoringService = Depends(_get_svc),
    _: UserModel = Depends(get_current_user),
):
    session = await svc.get_session(session_id)
    if not session:
        return StandardResponse.error(message="Session 不存在", status_code=404)
    try:
        skill_id = await svc.save(session, name=body.name, description=body.description)
        return StandardResponse.success(
            data={"skill_id": skill_id, "session": _serialize_session(session)},
            message=f"已儲存為 Skill #{skill_id}",
        )
    except ValueError as e:
        return StandardResponse.error(message=str(e))
