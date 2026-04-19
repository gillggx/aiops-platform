"""PipelineRepository + PipelineRunRepository."""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import PipelineModel
from app.models.pipeline_run import PipelineRunModel


class PipelineRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, pipeline_id: int) -> Optional[PipelineModel]:
        result = await self.db.execute(select(PipelineModel).where(PipelineModel.id == pipeline_id))
        return result.scalar_one_or_none()

    async def list_all(self, status: Optional[str] = None) -> list[PipelineModel]:
        stmt = select(PipelineModel)
        if status:
            stmt = stmt.where(PipelineModel.status == status)
        stmt = stmt.order_by(PipelineModel.updated_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        *,
        name: str,
        description: str,
        status: str,
        pipeline_json: dict[str, Any],
        created_by: Optional[int] = None,
        parent_id: Optional[int] = None,
    ) -> PipelineModel:
        pipe = PipelineModel(
            name=name,
            description=description,
            status=status,
            pipeline_json=json.dumps(pipeline_json, ensure_ascii=False),
            created_by=created_by,
            parent_id=parent_id,
        )
        self.db.add(pipe)
        await self.db.flush()
        await self.db.refresh(pipe)
        return pipe

    async def update(
        self,
        pipeline_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        pipeline_json: Optional[dict[str, Any]] = None,
        pipeline_kind: Optional[str] = None,
    ) -> Optional[PipelineModel]:
        pipe = await self.get_by_id(pipeline_id)
        if pipe is None:
            return None
        if name is not None:
            pipe.name = name
        if description is not None:
            pipe.description = description
        if pipeline_json is not None:
            pipe.pipeline_json = json.dumps(pipeline_json, ensure_ascii=False)
        if pipeline_kind is not None:
            pipe.pipeline_kind = pipeline_kind
        await self.db.flush()
        await self.db.refresh(pipe)
        return pipe

    async def delete(self, pipeline_id: int) -> bool:
        pipe = await self.get_by_id(pipeline_id)
        if pipe is None:
            return False
        await self.db.delete(pipe)
        await self.db.flush()
        return True

    async def update_status(
        self,
        pipeline_id: int,
        *,
        new_status: str,
        approved_by: Optional[int] = None,
    ) -> Optional[PipelineModel]:
        from datetime import datetime, timezone
        pipe = await self.get_by_id(pipeline_id)
        if pipe is None:
            return None
        pipe.status = new_status
        # PR-B: active replaced production as "approved/live" state
        if new_status in {"production", "active"}:
            pipe.approved_by = approved_by
            pipe.approved_at = datetime.now(tz=timezone.utc)
        await self.db.flush()
        await self.db.refresh(pipe)
        return pipe

    async def bump_usage_stats(
        self, pipeline_id: int, *, triggered: bool = False
    ) -> Optional[PipelineModel]:
        """PR-C telemetry — increment invoke_count + update timestamps.

        Idempotent in the sense that missed writes simply under-count; never
        raises. Caller typically schedules this via asyncio.create_task and
        doesn't await (fire-and-forget).
        """
        pipe = await self.get_by_id(pipeline_id)
        if pipe is None:
            return None
        try:
            stats = json.loads(pipe.usage_stats or "{}")
        except Exception:
            stats = {}
        stats["invoke_count"] = int(stats.get("invoke_count") or 0) + 1
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        stats["last_invoked_at"] = now_iso
        if triggered:
            stats["last_triggered_at"] = now_iso
        pipe.usage_stats = json.dumps(stats, ensure_ascii=False)
        await self.db.flush()
        return pipe


class PipelineRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_run(
        self,
        *,
        pipeline_id: Optional[int],
        pipeline_version: str,
        triggered_by: str,
        status: str = "running",
    ) -> PipelineRunModel:
        run = PipelineRunModel(
            pipeline_id=pipeline_id,
            pipeline_version=pipeline_version,
            triggered_by=triggered_by,
            status=status,
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def finish_run(
        self,
        *,
        run_id: int,
        status: str,
        node_results: dict[str, Any],
        error_message: Optional[str] = None,
    ) -> PipelineRunModel:
        run = await self.get_by_id(run_id)
        if run is None:
            raise ValueError(f"PipelineRun {run_id} not found")
        run.status = status
        run.node_results = json.dumps(node_results, ensure_ascii=False, default=str)
        run.error_message = error_message
        run.finished_at = datetime.now(tz=timezone.utc)
        await self.db.flush()
        await self.db.refresh(run)
        return run

    async def get_by_id(self, run_id: int) -> Optional[PipelineRunModel]:
        result = await self.db.execute(select(PipelineRunModel).where(PipelineRunModel.id == run_id))
        return result.scalar_one_or_none()
