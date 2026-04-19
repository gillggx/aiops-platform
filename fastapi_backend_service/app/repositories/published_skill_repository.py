"""PublishedSkillRepository — CRUD + simple ILIKE search for PR-C registry."""

from __future__ import annotations

import json
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pb_published_skill import PublishedSkillModel


class PublishedSkillRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, data: dict[str, Any]) -> PublishedSkillModel:
        row = PublishedSkillModel(
            pipeline_id=data["pipeline_id"],
            pipeline_version=str(data["pipeline_version"]),
            slug=data["slug"],
            name=data["name"],
            use_case=data.get("use_case", ""),
            when_to_use=json.dumps(data.get("when_to_use") or [], ensure_ascii=False),
            inputs_schema=json.dumps(data.get("inputs_schema") or [], ensure_ascii=False),
            outputs_schema=json.dumps(data.get("outputs_schema") or {}, ensure_ascii=False),
            example_invocation=(
                json.dumps(data.get("example_invocation"), ensure_ascii=False)
                if data.get("example_invocation") is not None
                else None
            ),
            tags=json.dumps(data.get("tags") or [], ensure_ascii=False),
            status=data.get("status", "active"),
            published_by=data.get("published_by"),
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def list_all(self, *, include_retired: bool = False) -> list[PublishedSkillModel]:
        stmt = select(PublishedSkillModel)
        if not include_retired:
            stmt = stmt.where(PublishedSkillModel.status == "active")
        stmt = stmt.order_by(PublishedSkillModel.published_at.desc())
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def get_by_slug(self, slug: str) -> Optional[PublishedSkillModel]:
        stmt = select(PublishedSkillModel).where(PublishedSkillModel.slug == slug)
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def get_by_id(self, skill_id: int) -> Optional[PublishedSkillModel]:
        stmt = select(PublishedSkillModel).where(PublishedSkillModel.id == skill_id)
        res = await self._db.execute(stmt)
        return res.scalar_one_or_none()

    async def search(self, query: str, *, top_k: int = 10) -> list[PublishedSkillModel]:
        """Simple ILIKE search until pgvector is wired. Scans use_case + name + tags."""
        q = f"%{query.lower()}%"
        stmt = select(PublishedSkillModel).where(
            PublishedSkillModel.status == "active",
        ).where(
            or_(
                PublishedSkillModel.use_case.ilike(q),
                PublishedSkillModel.name.ilike(q),
                PublishedSkillModel.tags.ilike(q),
            )
        ).limit(top_k)
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def retire(self, skill_id: int) -> Optional[PublishedSkillModel]:
        from datetime import datetime, timezone
        row = await self.get_by_id(skill_id)
        if row is None:
            return None
        row.status = "retired"
        row.retired_at = datetime.now(tz=timezone.utc)
        await self._db.flush()
        return row

    def to_dict(self, row: PublishedSkillModel) -> dict[str, Any]:
        def _loads(v: Optional[str], default: Any) -> Any:
            if v is None or v == "":
                return default
            try:
                return json.loads(v)
            except Exception:
                return default
        return {
            "id": row.id,
            "pipeline_id": row.pipeline_id,
            "pipeline_version": row.pipeline_version,
            "slug": row.slug,
            "name": row.name,
            "use_case": row.use_case,
            "when_to_use": _loads(row.when_to_use, []),
            "inputs_schema": _loads(row.inputs_schema, []),
            "outputs_schema": _loads(row.outputs_schema, {}),
            "example_invocation": _loads(row.example_invocation, None),
            "tags": _loads(row.tags, []),
            "status": row.status,
            "published_by": row.published_by,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "retired_at": row.retired_at.isoformat() if row.retired_at else None,
        }
