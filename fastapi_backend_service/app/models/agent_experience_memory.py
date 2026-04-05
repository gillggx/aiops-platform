"""AgentExperienceMemory — reflective memory with lifecycle + pgvector.

Phase 1 of the AIOps Agentic Memory System (see docs/memory_management.md).

Replaces the legacy flat ``agent_memories`` table with:
  - Abstracted intent + action (no raw tool-chain strings)
  - pgvector embedding for semantic search
  - Health scoring: confidence_score, use/success/fail counts
  - Status machine: ACTIVE → STALE or HUMAN_REJECTED
  - last_used_at tracking for freshness decay
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from pgvector.sqlalchemy import Vector

from app.database import Base


# bge-m3 embedding dimension
EMBEDDING_DIM = 1024


class AgentExperienceMemoryModel(Base):
    """A single reflective experience memory with health scoring.

    Lifecycle:
      Write  → created via background worker after successful task, with
               LLM-abstracted intent + action (no raw tool chains).
      Read   → retrieved via hybrid search (semantic + health filter).
      Eval   → confidence_score updated based on downstream task outcome.
      Decay  → status=STALE when confidence_score < 1 or health conditions
               met. status=HUMAN_REJECTED when user explicitly marks wrong.
    """

    __tablename__ = "agent_experience_memory"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Core content (abstracted by LLM at write time) ──────────────────
    intent_summary: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="記憶意圖（例如：「當 EQP 發生連續 OOC 時」）",
    )
    abstract_action: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="抽象策略（例如：「優先撈最近 5 筆並檢查 trend」）",
    )
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(EMBEDDING_DIM), nullable=True,
        comment="bge-m3 1024-dim vector of (intent_summary + abstract_action)",
    )

    # ── Lifecycle / scoring (core feature of reflective memory) ─────────
    confidence_score: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5",
        comment="Health score; starts at 5, ±1 on success, -2 on failure, < 1 → STALE",
    )
    use_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="How many times this memory was retrieved and referenced by Agent",
    )
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    fail_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )

    # ── State machine ────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE", server_default="ACTIVE",
        index=True,
        comment="ACTIVE | STALE | HUMAN_REJECTED",
    )

    # ── Provenance (what triggered the write) ───────────────────────────
    source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="auto", server_default="auto",
        comment="auto | user_explicit | system",
    )
    source_session_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True,
        comment="Optional: agent session that created this memory",
    )

    # ── Timestamps ──────────────────────────────────────────────────────
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Updated every time the memory is retrieved",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
        onupdate=lambda: datetime.now(tz=timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"AgentExperienceMemoryModel(id={self.id}, "
            f"user={self.user_id}, status={self.status!r}, "
            f"score={self.confidence_score}, use={self.use_count}, "
            f"intent={self.intent_summary[:40]!r})"
        )
