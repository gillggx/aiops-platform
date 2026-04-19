"""BlockModel — Pipeline Builder 積木定義。

每一筆對應一個可組合積木（資料源 / 處理 / 邏輯 / 輸出 / custom）。
Description 為 LLM 讀取 catalog 的唯一文件來源（符合 CLAUDE.md 原則）。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BlockModel(Base):
    __tablename__ = "pb_blocks"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_pb_blocks_name_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft", server_default="draft")

    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    output_schema: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    param_schema: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    implementation: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # v3.4: concrete usage examples shown in BlockDocsDrawer + injected into Agent
    # prompt; each entry is {name, summary, params: {...}, [upstream_hint]}.
    examples: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    # Phase 5-UX-3b: structured hint for LLM — actual flat columns this block's
    # output carries. Distinct from output_schema.columns (which is ports' static
    # type hint). Shape: [{name, type, description, when_present?}].
    output_columns_hint: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")

    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")

    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        return f"BlockModel(id={self.id!r}, name={self.name!r}, version={self.version!r})"
