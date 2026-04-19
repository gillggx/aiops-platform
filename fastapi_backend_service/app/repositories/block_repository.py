"""BlockRepository — CRUD for Pipeline Builder blocks."""

import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.block import BlockModel


class BlockRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, block_id: int) -> Optional[BlockModel]:
        result = await self.db.execute(select(BlockModel).where(BlockModel.id == block_id))
        return result.scalar_one_or_none()

    async def get_by_name_version(self, name: str, version: str) -> Optional[BlockModel]:
        result = await self.db.execute(
            select(BlockModel).where(BlockModel.name == name, BlockModel.version == version)
        )
        return result.scalar_one_or_none()

    async def list_active(self, category: Optional[str] = None) -> list[BlockModel]:
        """Return blocks in pi_run or production status."""
        stmt = select(BlockModel).where(BlockModel.status.in_(["pi_run", "production"]))
        if category:
            stmt = stmt.where(BlockModel.category == category)
        stmt = stmt.order_by(BlockModel.category, BlockModel.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_all(self) -> list[BlockModel]:
        result = await self.db.execute(select(BlockModel).order_by(BlockModel.category, BlockModel.name))
        return list(result.scalars().all())

    async def upsert(
        self,
        *,
        name: str,
        version: str,
        category: str,
        status: str,
        description: str,
        input_schema: list[dict[str, Any]],
        output_schema: list[dict[str, Any]],
        param_schema: dict[str, Any],
        implementation: dict[str, Any],
        is_custom: bool = False,
        examples: Optional[list[dict[str, Any]]] = None,
        output_columns_hint: Optional[list[dict[str, Any]]] = None,
    ) -> BlockModel:
        """Idempotent seed — create if not exists, otherwise update description/schemas."""
        examples_json = json.dumps(examples or [], ensure_ascii=False)
        out_cols_json = json.dumps(output_columns_hint or [], ensure_ascii=False)
        existing = await self.get_by_name_version(name, version)
        if existing is None:
            block = BlockModel(
                name=name,
                version=version,
                category=category,
                status=status,
                description=description,
                input_schema=json.dumps(input_schema, ensure_ascii=False),
                output_schema=json.dumps(output_schema, ensure_ascii=False),
                param_schema=json.dumps(param_schema, ensure_ascii=False),
                implementation=json.dumps(implementation, ensure_ascii=False),
                is_custom=is_custom,
                examples=examples_json,
                output_columns_hint=out_cols_json,
            )
            self.db.add(block)
            await self.db.flush()
            await self.db.refresh(block)
            return block
        # update mutable fields (description / schemas) — status/version 不動
        existing.description = description
        existing.input_schema = json.dumps(input_schema, ensure_ascii=False)
        existing.output_schema = json.dumps(output_schema, ensure_ascii=False)
        existing.param_schema = json.dumps(param_schema, ensure_ascii=False)
        existing.implementation = json.dumps(implementation, ensure_ascii=False)
        existing.category = category
        existing.is_custom = is_custom
        existing.examples = examples_json
        existing.output_columns_hint = out_cols_json
        await self.db.flush()
        await self.db.refresh(existing)
        return existing
