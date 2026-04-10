"""SkillAuthoringSessionModel — stateful Skill creation session.

Captures the multi-turn dialog between user and Agent during Skill authoring:
clarification → planning → generation → testing → feedback → revision → save.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SkillAuthoringSessionModel(Base):
    """A multi-turn Skill authoring session.

    State machine:
        drafting → clarifying → planned → tested → reviewed → saved
                                                  ↓ (feedback=wrong)
                                              revising → planned (loop)
    """

    __tablename__ = "skill_authoring_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 'my_skill' | 'auto_patrol' | 'diagnostic_rule'
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # State machine
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="drafting", server_default="drafting", index=True
    )

    # Original user input
    initial_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Conversation history — list of {role, type, content, timestamp, ...}
    turns: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Current snapshot (gets overwritten on each revision)
    current_understanding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    current_steps_mapping: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    current_input_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    current_output_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Last try-run result
    last_test_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON

    # Final promote target
    promoted_skill_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("skill_definitions.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
        onupdate=lambda: datetime.now(tz=timezone.utc),
    )

    def __repr__(self) -> str:
        return f"SkillAuthoringSessionModel(id={self.id!r}, state={self.state!r}, target_type={self.target_type!r})"
