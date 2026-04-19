"""Validate all `[migrated]` pipelines in local DB. Prints a per-rule tally
so we can categorize systemic migrator bugs.

Usage:
    python -m scripts.validate_migrated_pipelines
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import init_db, _get_session_factory  # noqa: E402
from app.models.pipeline import PipelineModel  # noqa: E402
from app.services.pipeline_builder.block_registry import BlockRegistry  # noqa: E402
from app.services.pipeline_builder.validator import PipelineValidator  # noqa: E402


async def main() -> None:
    await init_db()
    session_factory = _get_session_factory()
    async with session_factory() as db:
        # Load block catalog from DB (same path as the registry warmup)
        registry = BlockRegistry()
        await registry.load_from_db(db)
        validator = PipelineValidator(registry.catalog)

        # Fetch all migrated pipelines
        res = await db.execute(
            select(PipelineModel).where(PipelineModel.name.like("[migrated]%")).order_by(PipelineModel.id)
        )
        pipes = list(res.scalars().all())

    print(f"→ validating {len(pipes)} migrated pipelines")
    rule_counter: Counter[str] = Counter()
    sample_per_rule: dict[str, list[str]] = {}
    failures: list[tuple[PipelineModel, list[dict]]] = []

    for p in pipes:
        try:
            pj = json.loads(p.pipeline_json)
        except Exception as e:  # noqa: BLE001
            print(f"  #{p.id} JSON parse fail: {e}")
            continue
        errors = validator.validate(pj)
        if errors:
            failures.append((p, errors))
            for e in errors:
                rule = e.get("rule", "UNKNOWN")
                rule_counter[rule] += 1
                samples = sample_per_rule.setdefault(rule, [])
                if len(samples) < 3:
                    samples.append(f"#{p.id}: {e.get('message', '')}")

    print()
    print(f"✓ PASS: {len(pipes) - len(failures)} / {len(pipes)}")
    print(f"✗ FAIL: {len(failures)}")
    print()
    print("=== Errors by rule ===")
    for rule, n in rule_counter.most_common():
        print(f"  {rule}: {n}")
        for s in sample_per_rule.get(rule, [])[:2]:
            print(f"    — {s}")

    print()
    print("=== Per-pipeline first error ===")
    for p, errs in failures:
        first = errs[0]
        print(f"  #{p.id} [{p.pipeline_kind}] {p.name}")
        for e in errs[:3]:
            node_suffix = f" (node={e.get('node_id')})" if e.get("node_id") else ""
            print(f"    · {e.get('rule')}: {e.get('message')}{node_suffix}")


if __name__ == "__main__":
    asyncio.run(main())
