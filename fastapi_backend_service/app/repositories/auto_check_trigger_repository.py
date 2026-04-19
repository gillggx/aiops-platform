"""Phase 5-UX-7: repo for pipeline_auto_check_triggers."""

from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline_auto_check_trigger import PipelineAutoCheckTriggerModel


class AutoCheckTriggerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_pipeline(self, pipeline_id: int) -> list[PipelineAutoCheckTriggerModel]:
        result = await self.db.execute(
            select(PipelineAutoCheckTriggerModel)
            .where(PipelineAutoCheckTriggerModel.pipeline_id == pipeline_id)
            .order_by(PipelineAutoCheckTriggerModel.event_type)
        )
        return list(result.scalars().all())

    async def list_by_event(self, event_type: str) -> list[PipelineAutoCheckTriggerModel]:
        """Used at runtime when an alarm fires — find all pipelines bound to event_type."""
        result = await self.db.execute(
            select(PipelineAutoCheckTriggerModel)
            .where(PipelineAutoCheckTriggerModel.event_type == event_type)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[PipelineAutoCheckTriggerModel]:
        result = await self.db.execute(
            select(PipelineAutoCheckTriggerModel)
            .order_by(PipelineAutoCheckTriggerModel.pipeline_id, PipelineAutoCheckTriggerModel.event_type)
        )
        return list(result.scalars().all())

    async def get(
        self, pipeline_id: int, event_type: str
    ) -> Optional[PipelineAutoCheckTriggerModel]:
        result = await self.db.execute(
            select(PipelineAutoCheckTriggerModel).where(
                PipelineAutoCheckTriggerModel.pipeline_id == pipeline_id,
                PipelineAutoCheckTriggerModel.event_type == event_type,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, pipeline_id: int, event_type: str) -> PipelineAutoCheckTriggerModel:
        row = PipelineAutoCheckTriggerModel(pipeline_id=pipeline_id, event_type=event_type)
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def remove(self, pipeline_id: int, event_type: str) -> bool:
        row = await self.get(pipeline_id, event_type)
        if row is None:
            return False
        await self.db.delete(row)
        await self.db.flush()
        return True

    async def replace_for_pipeline(
        self, pipeline_id: int, event_types: list[str]
    ) -> list[PipelineAutoCheckTriggerModel]:
        """Atomically set the trigger list for one pipeline (used by publish modal)."""
        await self.db.execute(
            delete(PipelineAutoCheckTriggerModel)
            .where(PipelineAutoCheckTriggerModel.pipeline_id == pipeline_id)
        )
        out: list[PipelineAutoCheckTriggerModel] = []
        for et in event_types:
            row = PipelineAutoCheckTriggerModel(pipeline_id=pipeline_id, event_type=et)
            self.db.add(row)
            out.append(row)
        await self.db.flush()
        for r in out:
            await self.db.refresh(r)
        return out
