"""Admin router for the reflective experience memory system.

Endpoints (all under /api/v1/experience-memory):
  GET    /                List current user's memories (optional ?status filter)
  GET    /{memory_id}     Get single memory (including embedding metadata)
  POST   /{memory_id}/reject  Mark as HUMAN_REJECTED (terminal)
  DELETE /{memory_id}     Hard delete
  POST   /retrieve        Manual semantic search (debug / inspection tool)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import StandardResponse
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import UserModel
from app.services.experience_memory_service import ExperienceMemoryService

router = APIRouter(prefix="/experience-memory", tags=["experience-memory"])


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


@router.get("", response_model=StandardResponse)
async def list_memories(
    status: Optional[str] = Query(None, description="ACTIVE / STALE / HUMAN_REJECTED"),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """List experience memories for the current user, newest first."""
    svc = ExperienceMemoryService(db)
    memories = await svc.list_for_user(
        user_id=current_user.id,
        status_filter=status,
        limit=limit,
    )
    return StandardResponse.success(
        data=[ExperienceMemoryService.to_dict(m) for m in memories]
    )


@router.get("/{memory_id}", response_model=StandardResponse)
async def get_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    from app.models.agent_experience_memory import AgentExperienceMemoryModel
    mem = await db.get(AgentExperienceMemoryModel, memory_id)
    if mem is None or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="memory not found")
    return StandardResponse.success(data=ExperienceMemoryService.to_dict(mem))


@router.post("/{memory_id}/reject", response_model=StandardResponse)
async def reject_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """User explicitly marks a memory as wrong. Status → HUMAN_REJECTED (terminal).

    Rejected memories are never retrieved again — safer than delete, because
    it preserves the audit trail.
    """
    from app.models.agent_experience_memory import AgentExperienceMemoryModel
    mem = await db.get(AgentExperienceMemoryModel, memory_id)
    if mem is None or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="memory not found")

    svc = ExperienceMemoryService(db)
    updated = await svc.mark_rejected(memory_id)
    return StandardResponse.success(data=ExperienceMemoryService.to_dict(updated))


@router.delete("/{memory_id}", response_model=StandardResponse)
async def delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """Hard delete (rare — normally use /reject instead)."""
    from app.models.agent_experience_memory import AgentExperienceMemoryModel
    mem = await db.get(AgentExperienceMemoryModel, memory_id)
    if mem is None or mem.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="memory not found")

    svc = ExperienceMemoryService(db)
    ok = await svc.delete(memory_id)
    return StandardResponse.success(data={"deleted": ok})


@router.post("/retrieve", response_model=StandardResponse)
async def retrieve_memories(
    body: RetrieveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """Debug endpoint: run a semantic search as the agent would.

    Useful for the admin UI to preview which memories a given query
    would hit, with similarity scores. **Does** bump last_used_at /
    use_count (same as agent retrieval) — use sparingly in tooling.
    """
    svc = ExperienceMemoryService(db)
    results = await svc.retrieve(
        user_id=current_user.id,
        query=body.query,
        top_k=body.top_k,
    )
    return StandardResponse.success(data=[
        {**ExperienceMemoryService.to_dict(mem), "similarity": round(sim, 3)}
        for mem, sim in results
    ])
