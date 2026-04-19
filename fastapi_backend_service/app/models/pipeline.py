"""PipelineModel — 一條儲存的 DAG pipeline。"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PipelineModel(Base):
    __tablename__ = "pb_pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # PR-B lifecycle: draft | validating | locked | active | archived (widened to 20)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft", server_default="draft")
    # Phase 5-UX-3b: pipeline_kind now nullable; only required at lock/publish time.
    # Session/ad-hoc pipelines (/chat/*) don't need a kind until user chooses to publish.
    # Legacy values: auto_patrol | diagnostic.
    pipeline_kind: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, default=None
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")

    pipeline_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # PR-C telemetry + lifecycle timestamps + auto-doc draft
    usage_stats: Mapped[str] = mapped_column(
        Text, nullable=False,
        default='{"invoke_count":0,"last_invoked_at":null,"last_triggered_at":null}',
        server_default='{"invoke_count":0,"last_invoked_at":null,"last_triggered_at":null}',
    )
    auto_doc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("pb_pipelines.id", ondelete="SET NULL"), nullable=True
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
        return f"PipelineModel(id={self.id!r}, name={self.name!r}, status={self.status!r})"
