"""CanvasOperationModel — Agent / user 操作 canvas 的紀錄（Phase 3 才會大量使用）。

Phase 1 先把 schema 建起來，供後續 replay / audit 使用。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CanvasOperationModel(Base):
    __tablename__ = "pb_canvas_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pb_pipelines.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor: Mapped[str] = mapped_column(String(32), nullable=False, default="user")  # user | agent
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
    )

    def __repr__(self) -> str:
        return f"CanvasOperationModel(id={self.id!r}, op={self.operation!r})"
