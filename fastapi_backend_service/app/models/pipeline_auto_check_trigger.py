"""Phase 5-UX-7: alarm-event → pipeline binding for auto_check kind.

Each row: "when event_type fires, run pipeline_id with inputs sourced from the
alarm payload by name-match (pipeline input names == alarm payload keys)".

No inputs_mapping column — by convention the pipeline's declared inputs
describe exactly what it needs from the alarm; alarm service resolves each
input by name, falling back to the input's default if the alarm payload
doesn't carry that field.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PipelineAutoCheckTriggerModel(Base):
    __tablename__ = "pipeline_auto_check_triggers"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "event_type", name="uq_pacheck_pipeline_event"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("pb_pipelines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"PipelineAutoCheckTriggerModel(id={self.id!r}, "
            f"pipeline_id={self.pipeline_id!r}, event_type={self.event_type!r})"
        )
