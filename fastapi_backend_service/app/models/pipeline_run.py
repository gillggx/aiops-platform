"""PipelineRunModel — pipeline 的一次執行紀錄。"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PipelineRunModel(Base):
    __tablename__ = "pb_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Ad-hoc run (Phase 1 測試)可為 NULL
    pipeline_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pb_pipelines.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pipeline_version: Mapped[str] = mapped_column(String(32), nullable=False, default="adhoc")

    # "user" | "agent" | "schedule" | "event"
    triggered_by: Mapped[str] = mapped_column(String(32), nullable=False, default="user")

    # "running" | "success" | "failed" | "validation_error"
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)

    # JSON: {node_id: {status, rows, duration_ms, error}}
    node_results: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 整體錯誤訊息（validation 失敗或 executor 失敗時）
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=timezone.utc), server_default=func.now(),
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"PipelineRunModel(id={self.id!r}, status={self.status!r})"
