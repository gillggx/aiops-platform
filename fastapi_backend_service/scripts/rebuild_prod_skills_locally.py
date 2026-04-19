"""PR-Final Track B — rebuild production skill_definitions as local pipelines.

Reads a pg_dump JSON of prod's `skill_definitions` and for each row:
  1. Upserts the legacy skill row into LOCAL `skill_definitions` (idempotent by name).
  2. Runs `skill_migrator.migrate_skill` to produce a Pipeline JSON.
  3. Creates (or updates) a `pb_pipelines` row as a draft, with
     `pipeline_kind` inferred (auto_patrol if source=auto_patrol, else diagnostic)
     and `metadata.source_skill_id` for idempotent re-runs.
  4. Writes a Markdown report summarising successes + skeletons.

Usage:
    # From fastapi_backend_service/
    python -m scripts.rebuild_prod_skills_locally \\
        --input ~/aiops_prod_backup/prod_skills.json \\
        --report ../docs/PROD_REBUILD_REPORT.md

Safe to re-run — rows keyed by (skill name) + (pipeline metadata.source_skill_id).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select

# Allow running via `python -m scripts.xxx` or plain `python scripts/xxx.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import init_db, _get_session_factory  # noqa: E402
from app.models.skill_definition import SkillDefinitionModel  # noqa: E402
from app.models.pipeline import PipelineModel  # noqa: E402
from app.repositories.pipeline_repository import PipelineRepository  # noqa: E402
from app.services.pipeline_builder.skill_migrator import migrate_skill  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _infer_pipeline_kind(skill: dict[str, Any], pipeline_json: dict[str, Any]) -> str:
    """Rule of thumb:
       - source=auto_patrol  → auto_patrol
       - has block_alert node → auto_patrol
       - else                → diagnostic
    """
    if skill.get("source") == "auto_patrol":
        return "auto_patrol"
    nodes = pipeline_json.get("nodes") or []
    if any(n.get("block_id") == "block_alert" for n in nodes):
        return "auto_patrol"
    return "diagnostic"


def _normalize_skill_payload(skill: dict[str, Any]) -> dict[str, Any]:
    """pg_dump `row_to_json + json_agg` returns nested objects as already-parsed
    dict/list (not strings). migrate_skill expects JSON strings, so we re-dump."""
    out = dict(skill)
    for key in ("steps_mapping", "input_schema", "output_schema"):
        v = out.get(key)
        if v is not None and not isinstance(v, str):
            out[key] = json.dumps(v, ensure_ascii=False)
    return out


async def _upsert_legacy_skill(db, skill: dict[str, Any]) -> SkillDefinitionModel:
    """Idempotent by name — update in place if exists, else insert."""
    name = skill["name"]
    res = await db.execute(select(SkillDefinitionModel).where(SkillDefinitionModel.name == name))
    existing = res.scalar_one_or_none()
    payload = {
        "name": name,
        "description": skill.get("description") or "",
        "trigger_mode": skill.get("trigger_mode") or "event",
        "steps_mapping": skill.get("steps_mapping"),
        "input_schema": skill.get("input_schema") or "[]",
        "output_schema": skill.get("output_schema") or "[]",
        "source": skill.get("source") or "rule",
        "auto_check_description": skill.get("auto_check_description") or "",
        "visibility": skill.get("visibility") or "private",
        "is_active": skill.get("is_active", True),
        "binding_type": skill.get("binding_type") or "none",
    }
    if existing is None:
        obj = SkillDefinitionModel(**payload)
        db.add(obj)
        await db.flush()
        return obj
    for k, v in payload.items():
        setattr(existing, k, v)
    await db.flush()
    return existing


async def _find_existing_pipeline_for_skill(db, skill_id: int) -> Optional[PipelineModel]:
    """Find pipeline whose pipeline_json.metadata.source_skill_id == skill_id.

    Uses two LIKE patterns to avoid false positives (e.g. id 3 matching 31, 32, ...):
    matching the value followed by a JSON field boundary (`,` or `}`).
    """
    # pipeline_json is TEXT; filter via SQL LIKE (sqlite + postgres both support).
    like_comma = f'%"source_skill_id": {skill_id},%'
    like_brace = f'%"source_skill_id": {skill_id}}}%'
    res = await db.execute(
        select(PipelineModel).where(
            PipelineModel.pipeline_json.like(like_comma)
            | PipelineModel.pipeline_json.like(like_brace)
        )
    )
    # Secondary guard: filter again in Python for safety (belt + suspenders).
    for pipe in res.scalars().all():
        try:
            meta = json.loads(pipe.pipeline_json).get("metadata", {}) or {}
            if meta.get("source_skill_id") == skill_id:
                return pipe
        except Exception:  # noqa: BLE001
            continue
    return None


# ---------------------------------------------------------------------------
# Per-skill work
# ---------------------------------------------------------------------------

async def _rebuild_one(
    db,
    raw_skill: dict[str, Any],
) -> dict[str, Any]:
    """Process one prod skill row → upsert legacy + (re)create pipeline."""
    skill = _normalize_skill_payload(raw_skill)
    prod_skill_id = skill["id"]

    # 1. Upsert legacy skill (to preserve "migrate from skill" UX hooks)
    local_skill = await _upsert_legacy_skill(db, skill)

    # 2. Run migrator using the prod's skill id (so metadata preserves prod's id)
    skill_for_migrator = dict(skill)
    result = migrate_skill(skill_for_migrator)

    kind = _infer_pipeline_kind(skill, result.pipeline_json)

    # 3. Upsert pipeline — idempotent by metadata.source_skill_id
    repo = PipelineRepository(db)
    existing = await _find_existing_pipeline_for_skill(db, prod_skill_id)
    pipeline_name = f"[migrated] {skill['name']}"
    pipeline_json_with_meta = {
        **result.pipeline_json,
        "metadata": {
            **(result.pipeline_json.get("metadata") or {}),
            "source_skill_id": prod_skill_id,
            "migration_status": result.status,
            "original_source": skill.get("source"),
        },
        "name": pipeline_name,
    }
    description = f"Migrated from skill #{prod_skill_id} ({(skill.get('description') or '')[:80]})"

    if existing is None:
        pipe = await repo.create(
            name=pipeline_name,
            description=description,
            status="draft",
            pipeline_json=pipeline_json_with_meta,
        )
        pipe.pipeline_kind = kind
        action = "created"
    else:
        pipe = await repo.update(
            existing.id,
            name=pipeline_name,
            description=description,
            pipeline_json=pipeline_json_with_meta,
        )
        pipe.pipeline_kind = kind
        action = "updated"

    return {
        "prod_skill_id": prod_skill_id,
        "skill_name": skill["name"],
        "local_skill_id": local_skill.id,
        "local_pipeline_id": pipe.id,
        "status": result.status,
        "kind": kind,
        "action": action,
        "notes": result.notes,
        "detected_mcps": result.detected_mcps,
        "n_nodes": len(result.pipeline_json.get("nodes") or []),
        "n_edges": len(result.pipeline_json.get("edges") or []),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

async def main(input_path: Path, report_path: Optional[Path]) -> None:
    skills = json.loads(input_path.read_text())
    print(f"→ loaded {len(skills)} prod skills from {input_path}", flush=True)

    await init_db()
    session_factory = _get_session_factory()
    results: list[dict[str, Any]] = []

    async with session_factory() as db:
        for s in skills:
            try:
                r = await _rebuild_one(db, s)
                results.append(r)
                icon = {"full": "✓", "skeleton": "◐", "manual": "✗"}.get(r["status"], "?")
                print(
                    f"  {icon} #{r['prod_skill_id']:3d} [{r['status']:8}][{r['kind']:11}] "
                    f"[{r['action']:7}] pipe={r['local_pipeline_id']} — {r['skill_name']}"
                )
            except Exception as e:  # noqa: BLE001
                results.append({
                    "prod_skill_id": s.get("id"),
                    "skill_name": s.get("name"),
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                })
                print(f"  ✗ #{s.get('id')} — ERROR: {e}")
        await db.commit()

    # summary
    counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if "kind" in r:
            kind_counts[r["kind"]] = kind_counts.get(r["kind"], 0) + 1
    print("")
    print(f"Totals: {counts}")
    print(f"Kinds:  {kind_counts}")

    if report_path is not None:
        _write_report(report_path, results, counts, kind_counts)
        print(f"\n→ wrote report to {report_path}")


def _write_report(
    path: Path,
    results: list[dict[str, Any]],
    counts: dict[str, int],
    kind_counts: dict[str, int],
) -> None:
    total = len(results)
    full = counts.get("full", 0)
    skeleton = counts.get("skeleton", 0)
    manual = counts.get("manual", 0)
    error = counts.get("error", 0)

    lines = [
        "# Production Skills Rebuild Report",
        "",
        "Auto-generated by `scripts/rebuild_prod_skills_locally.py`. Reflects the latest "
        "run against `~/aiops_prod_backup/prod_skills.json`.",
        "",
        "## Summary",
        "",
        f"- Total: **{total}**",
        f"- Full auto-migrate: **{full}** ({100*full//total if total else 0}%)",
        f"- Skeleton (needs manual): **{skeleton}**",
        f"- Manual only: **{manual}**",
        f"- Errors: **{error}**",
        "",
        f"- By pipeline_kind: {', '.join(f'{k}={v}' for k, v in sorted(kind_counts.items()))}",
        "",
        "## Per-skill detail",
        "",
        "| Status | Prod ID | Kind | Pipeline | Nodes/Edges | Skill Name |",
        "|:------:|:-------:|:-----|:--------:|:-----------:|:-----------|",
    ]
    for r in sorted(results, key=lambda x: (x.get("status") != "full", x.get("prod_skill_id") or 0)):
        icon = {"full": "✓", "skeleton": "◐", "manual": "✗", "error": "⚠"}.get(r.get("status"), "?")
        lines.append(
            f"| {icon} | #{r.get('prod_skill_id')} | {r.get('kind','?')} | "
            f"`#{r.get('local_pipeline_id','?')}` | {r.get('n_nodes','?')}/{r.get('n_edges','?')} | "
            f"{r.get('skill_name','?')} |"
        )

    # Skeleton + error details
    non_full = [r for r in results if r.get("status") != "full"]
    if non_full:
        lines += ["", "## Items needing manual review", ""]
        for r in non_full:
            lines.append(f"### #{r.get('prod_skill_id')} — {r.get('skill_name')}")
            lines.append("")
            if r.get("error"):
                lines.append(f"- **Error**: {r['error']}")
            lines.append(f"- Status: `{r.get('status')}`")
            lines.append(f"- Local pipeline: `#{r.get('local_pipeline_id', '-')}`")
            if r.get("notes"):
                lines.append("- Notes:")
                for n in r["notes"]:
                    lines.append(f"  - {n}")
            lines.append("")

    lines += [
        "",
        "## Next steps",
        "",
        "1. Open each `[migrated]` pipeline in Pipeline Builder (local) and verify params.",
        "2. For skeleton rows, edit the canvas manually using Inspector + Run Preview.",
        "3. When a pipeline looks correct: promote draft → validating → locked → active.",
        "4. When ALL 27 full-auto pipelines pass structural validation, proceed with the",
        "   PROD_DEPLOY_READINESS.md checklist to roll Phase 4 to production.",
        "",
    ]
    path.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(Path.home() / "aiops_prod_backup" / "prod_skills.json"))
    parser.add_argument("--report", default=None, help="Markdown report path (optional)")
    args = parser.parse_args()
    asyncio.run(main(Path(args.input), Path(args.report) if args.report else None))
