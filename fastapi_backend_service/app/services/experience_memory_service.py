"""ExperienceMemoryService — reflective memory with health scoring + pgvector.

Phase 1 of the AIOps Agentic Memory System. Replaces the flat
agent_memories RAG store with a lifecycle-aware memory:

  Write  → LLM abstracts successful interactions into (intent, action)
  Read   → hybrid filter (cosine similarity + health score + freshness)
  Eval   → downstream task outcome updates confidence_score
  Decay  → confidence < 1 → STALE (hidden from retrieval)

See docs/memory_management.md for the full lifecycle spec.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_experience_memory import (
    AgentExperienceMemoryModel,
    EMBEDDING_DIM,
)
from app.utils.embedding_client import get_embedding_client, EmbeddingError

logger = logging.getLogger(__name__)


# ── Tuning constants ────────────────────────────────────────────────────

DEFAULT_CONFIDENCE = 5
MAX_CONFIDENCE = 10
MIN_ACTIVE_CONFIDENCE = 1    # below this → status STALE
SUCCESS_DELTA = 1
FAILURE_DELTA = -2            # failures penalised harder than successes rewarded

# Hybrid retrieve filters (used in context_loader)
# 0.45 calibrated for bge-m3 Chinese queries (English pairs tend to score higher)
MIN_COSINE_SIMILARITY = 0.45
MIN_RETRIEVE_CONFIDENCE = 1   # below this → not healthy enough to influence
DEFAULT_TOP_K = 5

# Dedup on write — if a near-duplicate exists, bump confidence instead
DEDUP_COSINE_THRESHOLD = 0.92


# ── Service ─────────────────────────────────────────────────────────────


class ExperienceMemoryService:
    """CRUD + lifecycle for AgentExperienceMemoryModel."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── WRITE PHASE ─────────────────────────────────────────────────────

    async def write(
        self,
        user_id: int,
        intent_summary: str,
        abstract_action: str,
        source: str = "auto",
        source_session_id: Optional[str] = None,
    ) -> AgentExperienceMemoryModel:
        """Write a new experience memory with embedding + dedup check.

        Dedup: if a near-duplicate (cosine > DEDUP_COSINE_THRESHOLD) exists
        for this user, increment its confidence_score instead of creating
        a new row. Returns the (new or bumped) memory.
        """
        if not intent_summary.strip() or not abstract_action.strip():
            raise ValueError("intent_summary and abstract_action must be non-empty")

        # Generate embedding of (intent + action) as one string
        embed_text = f"{intent_summary}\n{abstract_action}"
        try:
            client = get_embedding_client()
            embedding = await client.embed(embed_text)
        except EmbeddingError as exc:
            logger.warning(
                "Memory write: embedding failed, storing without vector — %s",
                exc,
            )
            embedding = None

        # Dedup check — only if embedding succeeded
        if embedding is not None:
            dup = await self._find_near_duplicate(user_id, embedding)
            if dup is not None:
                logger.info(
                    "Memory dedup: similar memory exists (id=%d, cos≈%.3f), "
                    "bumping confidence instead of inserting",
                    dup.id, self._last_similarity,
                )
                dup.confidence_score = min(
                    dup.confidence_score + 1, MAX_CONFIDENCE
                )
                dup.updated_at = datetime.now(tz=timezone.utc)
                await self._db.commit()
                await self._db.refresh(dup)
                return dup

        mem = AgentExperienceMemoryModel(
            user_id=user_id,
            intent_summary=intent_summary.strip()[:500],
            abstract_action=abstract_action.strip(),
            embedding=embedding,
            confidence_score=DEFAULT_CONFIDENCE,
            status="ACTIVE",
            source=source,
            source_session_id=source_session_id,
        )
        self._db.add(mem)
        await self._db.commit()
        await self._db.refresh(mem)
        logger.info(
            "Memory written: id=%d user=%d intent=%r",
            mem.id, user_id, intent_summary[:60],
        )
        return mem

    async def _find_near_duplicate(
        self,
        user_id: int,
        embedding: List[float],
    ) -> Optional[AgentExperienceMemoryModel]:
        """Return the closest existing memory if it exceeds the dedup threshold.

        Uses pgvector cosine distance (1 - cos_similarity).
        """
        # cosine distance = <-> operator on pgvector with vector_cosine_ops
        # similarity = 1 - distance
        stmt = (
            select(
                AgentExperienceMemoryModel,
                (1 - AgentExperienceMemoryModel.embedding.cosine_distance(embedding)).label("sim"),
            )
            .where(
                AgentExperienceMemoryModel.user_id == user_id,
                AgentExperienceMemoryModel.status == "ACTIVE",
                AgentExperienceMemoryModel.embedding.is_not(None),
            )
            .order_by(AgentExperienceMemoryModel.embedding.cosine_distance(embedding))
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            self._last_similarity = 0.0
            return None
        mem, sim = row
        self._last_similarity = float(sim)
        if sim >= DEDUP_COSINE_THRESHOLD:
            return mem
        return None

    # ── RETRIEVE PHASE (hybrid filter) ──────────────────────────────────

    async def retrieve(
        self,
        user_id: int,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        min_similarity: float = MIN_COSINE_SIMILARITY,
        min_confidence: int = MIN_RETRIEVE_CONFIDENCE,
    ) -> List[Tuple[AgentExperienceMemoryModel, float]]:
        """Retrieve top-k relevant, healthy memories for a query string.

        Returns list of (memory, similarity_score) tuples, sorted by
        semantic relevance. Only ACTIVE memories with confidence >=
        min_confidence are considered.

        Retrieval as a side effect records last_used_at (the feedback
        loop will decide success/fail later).
        """
        if not query.strip():
            return []

        try:
            client = get_embedding_client()
            query_vec = await client.embed(query)
        except EmbeddingError as exc:
            logger.warning("Memory retrieve: embedding failed — %s", exc)
            return []

        # Hybrid filter: ACTIVE status + healthy confidence + cosine distance
        # cosine_distance = 1 - cosine_similarity
        cos_dist = AgentExperienceMemoryModel.embedding.cosine_distance(query_vec)
        stmt = (
            select(AgentExperienceMemoryModel, (1 - cos_dist).label("sim"))
            .where(
                AgentExperienceMemoryModel.user_id == user_id,
                AgentExperienceMemoryModel.status == "ACTIVE",
                AgentExperienceMemoryModel.confidence_score >= min_confidence,
                AgentExperienceMemoryModel.embedding.is_not(None),
            )
            .order_by(cos_dist)
            .limit(top_k * 2)  # fetch more than needed, then filter by sim threshold
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        # Apply similarity threshold
        filtered: List[Tuple[AgentExperienceMemoryModel, float]] = []
        for mem, sim in rows:
            sim_float = float(sim)
            if sim_float >= min_similarity:
                filtered.append((mem, sim_float))
            if len(filtered) >= top_k:
                break

        # Bump last_used_at on retrieved memories (best-effort, non-blocking)
        if filtered:
            retrieved_ids = [m.id for m, _ in filtered]
            try:
                await self._db.execute(
                    update(AgentExperienceMemoryModel)
                    .where(AgentExperienceMemoryModel.id.in_(retrieved_ids))
                    .values(
                        last_used_at=datetime.now(tz=timezone.utc),
                        use_count=AgentExperienceMemoryModel.use_count + 1,
                    )
                )
                await self._db.commit()
            except Exception as exc:
                logger.warning("Memory retrieve: last_used_at update failed — %s", exc)
                await self._db.rollback()

        return filtered

    # ── FEEDBACK PHASE (confidence scoring) ─────────────────────────────

    async def record_feedback(
        self,
        memory_id: int,
        outcome: str,  # 'success' | 'failure' | 'env_error'
        reason: Optional[str] = None,
    ) -> Optional[AgentExperienceMemoryModel]:
        """Update confidence_score based on how a referenced memory played out.

          success     → +SUCCESS_DELTA, success_count += 1
          failure     → +FAILURE_DELTA (negative), fail_count += 1
          env_error   → no score change (external cause, not memory's fault)

        If confidence_score drops below MIN_ACTIVE_CONFIDENCE, status is
        flipped to STALE.
        """
        mem = await self._db.get(AgentExperienceMemoryModel, memory_id)
        if mem is None:
            return None

        if outcome == "success":
            mem.confidence_score = min(mem.confidence_score + SUCCESS_DELTA, MAX_CONFIDENCE)
            mem.success_count += 1
        elif outcome == "failure":
            mem.confidence_score = mem.confidence_score + FAILURE_DELTA
            mem.fail_count += 1
        elif outcome == "env_error":
            # External failure — don't punish the memory
            pass
        else:
            logger.warning("record_feedback: unknown outcome %r", outcome)
            return mem

        # Decay: mark STALE if below threshold
        if mem.confidence_score < MIN_ACTIVE_CONFIDENCE and mem.status == "ACTIVE":
            mem.status = "STALE"
            logger.info(
                "Memory decayed: id=%d now STALE (score=%d)",
                mem.id, mem.confidence_score,
            )

        mem.updated_at = datetime.now(tz=timezone.utc)
        await self._db.commit()
        await self._db.refresh(mem)
        return mem

    # ── ADMIN / MAINTENANCE ─────────────────────────────────────────────

    async def list_for_user(
        self,
        user_id: int,
        status_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[AgentExperienceMemoryModel]:
        """List memories for admin UI. Sorted by last_used_at DESC, then id DESC."""
        conditions = [AgentExperienceMemoryModel.user_id == user_id]
        if status_filter:
            conditions.append(AgentExperienceMemoryModel.status == status_filter)

        stmt = (
            select(AgentExperienceMemoryModel)
            .where(and_(*conditions))
            .order_by(
                AgentExperienceMemoryModel.last_used_at.desc().nullslast(),
                AgentExperienceMemoryModel.id.desc(),
            )
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def mark_rejected(self, memory_id: int) -> Optional[AgentExperienceMemoryModel]:
        """User explicitly marks a memory as wrong. Status → HUMAN_REJECTED.

        HUMAN_REJECTED is terminal — never retrieved, never reactivated.
        """
        mem = await self._db.get(AgentExperienceMemoryModel, memory_id)
        if mem is None:
            return None
        mem.status = "HUMAN_REJECTED"
        mem.updated_at = datetime.now(tz=timezone.utc)
        await self._db.commit()
        await self._db.refresh(mem)
        return mem

    async def delete(self, memory_id: int) -> bool:
        mem = await self._db.get(AgentExperienceMemoryModel, memory_id)
        if mem is None:
            return False
        await self._db.delete(mem)
        await self._db.commit()
        return True

    @staticmethod
    def to_dict(mem: AgentExperienceMemoryModel) -> Dict[str, Any]:
        """Serialise for API responses (excludes embedding vector)."""
        return {
            "id": mem.id,
            "user_id": mem.user_id,
            "intent_summary": mem.intent_summary,
            "abstract_action": mem.abstract_action,
            "confidence_score": mem.confidence_score,
            "use_count": mem.use_count,
            "success_count": mem.success_count,
            "fail_count": mem.fail_count,
            "status": mem.status,
            "source": mem.source,
            "source_session_id": mem.source_session_id,
            "last_used_at": mem.last_used_at.isoformat() if mem.last_used_at else None,
            "created_at": mem.created_at.isoformat(),
            "updated_at": mem.updated_at.isoformat(),
        }
