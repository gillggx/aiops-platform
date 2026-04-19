"""Smoke-test migrated pipelines by running a full preview against each one
and reporting any runtime failures. Catches things validator can't:
  - column-not-found (params reference cols the data doesn't have)
  - upstream-node execution failures that cascade
  - empty-data errors
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
from app.services.pipeline_builder.executor import PipelineExecutor  # noqa: E402
from app.schemas.pipeline import PipelineJSON  # noqa: E402


async def main() -> None:
    await init_db()
    session_factory = _get_session_factory()

    async with session_factory() as db:
        registry = BlockRegistry()
        await registry.load_from_db(db)
        executor = PipelineExecutor(registry)

        res = await db.execute(
            select(PipelineModel)
            .where(PipelineModel.name.like("[migrated]%"))
            .order_by(PipelineModel.id)
        )
        pipes = list(res.scalars().all())

    print(f"→ executing {len(pipes)} migrated pipelines (full preview)")
    status_counter: Counter[str] = Counter()
    node_error_counter: Counter[str] = Counter()
    fails: list[tuple[int, str, str, dict]] = []

    for p in pipes:
        try:
            pj = PipelineJSON.model_validate(json.loads(p.pipeline_json))
        except Exception as e:  # noqa: BLE001
            fails.append((p.id, p.name, "parse_error", {"error": str(e)}))
            status_counter["parse_error"] += 1
            continue

        # Provide a sensible default $tool_id so variable-ref pipelines run
        inputs_map: dict[str, object] = {}
        for inp in (pj.inputs or []):
            if inp.required and inp.default is None and inp.example is None:
                inputs_map[inp.name] = "EQP-01" if inp.name == "tool_id" else ""
            elif inp.example is not None:
                inputs_map[inp.name] = inp.example
            elif inp.default is not None:
                inputs_map[inp.name] = inp.default

        try:
            result = await executor.execute(pj, inputs=inputs_map)
        except Exception as e:  # noqa: BLE001
            fails.append((p.id, p.name, "executor_crash", {"error": str(e)}))
            status_counter["executor_crash"] += 1
            continue

        status_counter[result["status"]] += 1
        if result["status"] != "success":
            # Find first failing node
            first_fail: dict | None = None
            for node_id, nr in result["node_results"].items():
                if nr.get("status") == "failed":
                    first_fail = {"node_id": node_id, "error": nr.get("error")}
                    node_error_counter[f"{node_id[:20]}: {str(nr.get('error'))[:60]}"] += 1
                    break
            fails.append((p.id, p.name, result["status"], first_fail or {"msg": result.get("error_message")}))

    print()
    print("=== Pipeline status distribution ===")
    for k, v in status_counter.most_common():
        print(f"  {k}: {v}")

    print()
    print("=== Failures ===")
    for pid, name, status, detail in fails:
        print(f"  #{pid} [{status}] {name}")
        print(f"      → {detail}")

    print()
    print(f"✓ Success: {status_counter.get('success', 0)} / {len(pipes)}")


if __name__ == "__main__":
    asyncio.run(main())
