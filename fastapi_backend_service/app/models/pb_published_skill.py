"""PublishedSkillModel — PR-C Phase 4-D skill registry.

When a diagnostic pipeline is published, a row is written here with LLM-generated
documentation, inputs schema, and discovery metadata. Agent's search_published_skills
tool reads from this table.

Pgvector embedding column left out of this initial cut; search falls back to ILIKE
on use_case + tags until vector extension is wired in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PublishedSkillModel(Base):
    __tablename__ = "pb_published_skills"
    __table_args__ = (UniqueConstraint("pipeline_id", "pipeline_version", name="uq_pbps_pipeline_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pb_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    # LLM-generated (or template-generated) doc fields, stored as JSON text for SQLite parity
    use_case: Mapped[str] = mapped_column(Text, nullable=False, default="")
    when_to_use: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    inputs_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    outputs_schema: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    example_invocation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    published_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
    )
    retired_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"PublishedSkillModel(slug={self.slug!r}, status={self.status!r})"
