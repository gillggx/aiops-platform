"""Pipeline Builder Router — Phase 1 + Phase 2 endpoints.

Phase 1:
  GET  /pipeline-builder/blocks           — list block catalog
  POST /pipeline-builder/validate         — validate a Pipeline JSON
  POST /pipeline-builder/execute          — validate + execute a Pipeline JSON
  GET  /pipeline-builder/runs/{run_id}    — fetch run record

Phase 2 (CRUD + lifecycle):
  GET   /pipeline-builder/pipelines                       — list pipelines
  POST  /pipeline-builder/pipelines                       — create Draft
  GET   /pipeline-builder/pipelines/{id}                  — read
  PUT   /pipeline-builder/pipelines/{id}                  — update (Draft/Pi-run only)
  POST  /pipeline-builder/pipelines/{id}/promote          — Draft→Pi-run→Production
  POST  /pipeline-builder/pipelines/{id}/fork             — Production→new Draft
  POST  /pipeline-builder/pipelines/{id}/deprecate        — mark deprecated
  POST  /pipeline-builder/preview                         — partial execute up to a node
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.block_repository import BlockRepository
from app.repositories.pipeline_repository import PipelineRepository, PipelineRunRepository
from app.repositories.published_skill_repository import PublishedSkillRepository
from app.services.pipeline_builder.doc_generator import generate_draft_doc
from app.schemas.pipeline import (
    ExecuteRequest,
    ExecuteResponse,
    NodeResult,
    PipelineJSON,
    ValidationError,
)
from app.services.pipeline_builder.block_registry import BlockRegistry
from app.services.pipeline_builder.executor import PipelineExecutor
from app.services.pipeline_builder.validator import PipelineValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipeline-builder", tags=["pipeline-builder"])


# ---------------------------------------------------------------------------
# Phase 2 — request/response models
# ---------------------------------------------------------------------------


class PipelineCreateBody(BaseModel):
    name: str
    description: str = ""
    # Phase 5-UX-3b: optional. Required only when transitioning → locked.
    pipeline_kind: Optional[Literal["auto_patrol", "auto_check", "skill"]] = None
    pipeline_json: PipelineJSON


class PipelineUpdateBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    pipeline_json: Optional[PipelineJSON] = None
    # Phase 5-UX-3b: allow setting kind after creation (at publish time)
    pipeline_kind: Optional[Literal["auto_patrol", "auto_check", "skill"]] = None


class PromoteBody(BaseModel):
    # Legacy — accepts old names for backward compat; router maps them to new enum.
    target_status: Literal["pi_run", "production", "validating", "locked", "active"]


class TransitionBody(BaseModel):
    """PR-B: unified state transition. `to` must be one of the 5 lifecycle states."""
    to: Literal["draft", "validating", "locked", "active", "archived"]
    notes: Optional[str] = None


class PreviewBody(BaseModel):
    pipeline_json: PipelineJSON
    node_id: str = Field(..., description="Execute up to this node_id and return its output")
    sample_size: int = Field(1000, ge=1, le=10000, description="Max rows to return per dataframe port")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Phase 4-B0: pipeline input values")


class PipelineSummary(BaseModel):
    id: int
    name: str
    description: str
    status: str
    pipeline_kind: Optional[str] = None
    version: str
    parent_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    usage_stats: dict[str, Any] = Field(default_factory=dict)


def _pipeline_to_summary(row) -> dict[str, Any]:
    import json as _json
    usage_stats: dict[str, Any] = {}
    try:
        raw = getattr(row, "usage_stats", None) or "{}"
        usage_stats = _json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        usage_stats = {}
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "pipeline_kind": getattr(row, "pipeline_kind", None),
        "version": row.version,
        "parent_id": row.parent_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "usage_stats": usage_stats,
    }


# PR-B: 5-stage state machine. Each key = current status, value = allowed targets.
# "draft → archived" is allowed (abandon a draft you don't want); active is terminal
# except archive — editing an active pipeline must go through clone.
_TRANSITIONS: dict[str, set[str]] = {
    "draft":      {"validating", "archived"},
    "validating": {"locked", "draft"},      # can go back to draft to edit again
    "locked":     {"active", "draft"},      # publish → active; reject → back to draft
    "active":     {"archived"},             # retire only
    "archived":   set(),                    # terminal; clone to revive
}

# Legacy aliases used by old promote/deprecate endpoints — mapped for back-compat.
_LEGACY_STATUS_ALIASES: dict[str, str] = {
    "pi_run": "validating",
    "production": "active",
    "deprecated": "archived",
}


def _get_registry(request: Request) -> BlockRegistry:
    registry: Optional[BlockRegistry] = getattr(request.app.state, "block_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="BlockRegistry not initialised")
    return registry


@router.get("/blocks")
async def list_blocks(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List active blocks (pi_run + production)."""
    repo = BlockRepository(db)
    rows = await repo.list_active(category=category)
    out = []
    for b in rows:
        out.append(
            {
                "id": b.id,
                "name": b.name,
                "category": b.category,
                "version": b.version,
                "status": b.status,
                "description": b.description,
                "input_schema": json.loads(b.input_schema or "[]"),
                "output_schema": json.loads(b.output_schema or "[]"),
                "param_schema": json.loads(b.param_schema or "{}"),
                "examples": json.loads(b.examples or "[]"),
                "output_columns_hint": json.loads(getattr(b, "output_columns_hint", None) or "[]"),
                "is_custom": b.is_custom,
            }
        )
    return out


@router.post("/validate")
async def validate_pipeline(
    request: Request,
    pipeline_json: PipelineJSON,
) -> dict[str, Any]:
    """Run validator only; do not execute."""
    registry = _get_registry(request)
    validator = PipelineValidator(registry.catalog)
    errors = validator.validate(pipeline_json)
    return {"valid": len(errors) == 0, "errors": errors}


@router.post("/execute", response_model=ExecuteResponse)
async def execute_pipeline(
    request: Request,
    body: ExecuteRequest,
    db: AsyncSession = Depends(get_db),
) -> ExecuteResponse:
    """Validate then execute a Pipeline JSON. Creates a PipelineRun record."""
    registry = _get_registry(request)
    validator = PipelineValidator(registry.catalog)

    errors = validator.validate(body.pipeline_json)
    run_repo = PipelineRunRepository(db)

    if errors:
        run = await run_repo.create_run(
            pipeline_id=None,
            pipeline_version="adhoc",
            triggered_by=body.triggered_by,
            status="validation_error",
        )
        run = await run_repo.finish_run(
            run_id=run.id,
            status="validation_error",
            node_results={},
            error_message=json.dumps(errors, ensure_ascii=False),
        )
        await db.commit()
        return ExecuteResponse(
            run_id=run.id,
            status="validation_error",
            errors=[ValidationError(**e) for e in errors],
            error_message="Pipeline validation failed",
        )

    # Create run record BEFORE execution to get run_id
    run = await run_repo.create_run(
        pipeline_id=None,
        pipeline_version="adhoc",
        triggered_by=body.triggered_by,
        status="running",
    )
    await db.commit()

    executor = PipelineExecutor(registry)
    try:
        result = await executor.execute(body.pipeline_json, run_id=run.id, inputs=body.inputs)
    except Exception as e:  # noqa: BLE001
        logger.exception("Executor crashed")
        run = await run_repo.finish_run(
            run_id=run.id,
            status="failed",
            node_results={},
            error_message=f"Executor crashed: {type(e).__name__}: {e}",
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Executor crashed: {e}") from e

    run = await run_repo.finish_run(
        run_id=run.id,
        status=result["status"],
        node_results=result["node_results"],
        error_message=result.get("error_message"),
    )

    # PR-C telemetry — bump usage_stats for any complete invocation tied to a
    # saved pipeline (success OR failed — validation_error was a short-circuit
    # and never reaches this block). invoke_count semantics = total invocations,
    # last_triggered_at only updates when pipeline actually triggered.
    if body.pipeline_id is not None and result["status"] in {"success", "failed"}:
        try:
            pipe_repo = PipelineRepository(db)
            summary = result.get("result_summary") or {}
            triggered = (
                bool(summary.get("triggered")) if isinstance(summary, dict) else False
            )
            await pipe_repo.bump_usage_stats(body.pipeline_id, triggered=triggered)
        except Exception as e:  # noqa: BLE001
            logger.warning("usage_stats bump failed for pipeline %s: %s", body.pipeline_id, e)

    await db.commit()

    node_results_models: dict[str, NodeResult] = {}
    for node_id, nr in result["node_results"].items():
        node_results_models[node_id] = NodeResult(
            status=nr.get("status", "failed"),
            rows=nr.get("rows"),
            duration_ms=nr.get("duration_ms"),
            error=nr.get("error"),
            preview=nr.get("preview"),
        )

    return ExecuteResponse(
        run_id=run.id,
        status=result["status"],
        node_results=node_results_models,
        error_message=result.get("error_message"),
        duration_ms=result.get("duration_ms"),
        result_summary=result.get("result_summary"),
    )


@router.post("/migrate/skill/{skill_id}")
async def migrate_skill_to_pipeline(
    skill_id: int,
    dry_run: bool = True,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Phase 4-A: convert a legacy skill_definition to a Pipeline JSON.

    - `dry_run=True` (default): returns the generated Pipeline JSON without
      persisting. Use this to review before committing.
    - `dry_run=False`: also inserts into `pb_pipelines` as status=draft, linking
      back via metadata.migrated_from_skill_id.
    """
    from app.repositories.skill_definition_repository import SkillDefinitionRepository
    from app.services.pipeline_builder.skill_migrator import migrate_skill

    skill_repo = SkillDefinitionRepository(db)
    skill = await skill_repo.get_by_id(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id} not found")

    skill_dict = {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "source": skill.source,
        "binding_type": skill.binding_type,
        "trigger_patrol_id": skill.trigger_patrol_id,
        "steps_mapping": skill.steps_mapping,
        "input_schema": skill.input_schema,
        "output_schema": skill.output_schema,
    }
    result = migrate_skill(skill_dict)

    response: dict[str, Any] = {
        "skill_id": result.skill_id,
        "skill_name": result.skill_name,
        "status": result.status,
        "pipeline_json": result.pipeline_json,
        "notes": result.notes,
        "detected_mcps": result.detected_mcps,
        "persisted": False,
    }

    if not dry_run and result.status != "manual":
        pipeline_repo = PipelineRepository(db)
        rec = await pipeline_repo.create(
            name=f"[migrated] {skill.name}",
            description=f"Auto-migrated from skill #{skill.id}",
            status="draft",
            pipeline_json=result.pipeline_json,
        )
        await db.commit()
        response["persisted"] = True
        response["pipeline_id"] = rec.id

    return response


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    repo = PipelineRunRepository(db)
    run = await repo.get_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return {
        "id": run.id,
        "pipeline_id": run.pipeline_id,
        "pipeline_version": run.pipeline_version,
        "triggered_by": run.triggered_by,
        "status": run.status,
        "node_results": json.loads(run.node_results) if run.node_results else None,
        "error_message": run.error_message,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


# ---------------------------------------------------------------------------
# Phase 2 — Pipeline CRUD + lifecycle
# ---------------------------------------------------------------------------


@router.get("/pipelines")
async def list_pipelines(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    repo = PipelineRepository(db)
    rows = await repo.list_all(status=status)
    return [_pipeline_to_summary(r) for r in rows]


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: PipelineCreateBody,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = PipelineRepository(db)
    pipe = await repo.create(
        name=body.name,
        description=body.description,
        status="draft",
        pipeline_json=body.pipeline_json.model_dump(by_alias=True),
    )
    # PR-B: set pipeline_kind directly via attribute (repo.create doesn't know it yet)
    pipe.pipeline_kind = body.pipeline_kind
    await db.commit()
    return _pipeline_to_summary(pipe) | {"pipeline_json": json.loads(pipe.pipeline_json)}


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: int, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    return _pipeline_to_summary(pipe) | {"pipeline_json": json.loads(pipe.pipeline_json)}


@router.put("/pipelines/{pipeline_id}")
async def update_pipeline(
    pipeline_id: int,
    body: PipelineUpdateBody,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    # PR-B: active / locked / archived are read-only. Must Clone & Edit.
    if pipe.status in {"locked", "active", "archived"}:
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline status '{pipe.status}' is read-only — use Clone & Edit to create an editable copy",
        )

    pipe = await repo.update(
        pipeline_id,
        name=body.name,
        description=body.description,
        pipeline_json=body.pipeline_json.model_dump(by_alias=True) if body.pipeline_json else None,
        pipeline_kind=body.pipeline_kind,
    )
    await db.commit()
    return _pipeline_to_summary(pipe) | {"pipeline_json": json.loads(pipe.pipeline_json)}


async def _do_transition(
    pipe,
    target: str,
    *,
    registry: BlockRegistry,
    repo: PipelineRepository,
) -> Any:
    """PR-B: core state machine transition — shared by transition/promote/deprecate.

    Enforces:
      - Transition is allowed from current state
      - Base validation passes when moving out of draft (draft → validating / archived)
      - Kind-specific structural check when moving validating → locked
    Writes lifecycle timestamps (locked_at / published_at / archived_at) where relevant.
    """
    from datetime import datetime as _dt, timezone as _tz

    allowed = _TRANSITIONS.get(pipe.status, set())
    if target not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{pipe.status}' to '{target}'. Allowed: {sorted(allowed)}",
        )

    # draft → validating / locked → active require base validation to pass
    if pipe.status == "draft" and target == "validating":
        validator = PipelineValidator(registry.catalog)
        errors = validator.validate(json.loads(pipe.pipeline_json))
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "Pipeline must pass validation before entering validating", "errors": errors},
            )

    # validating → locked: enforce kind-specific structural rules (C11/C12).
    # Phase 5-UX-3b: kind is required at this point — reject unclassified pipelines.
    if pipe.status == "validating" and target == "locked":
        kind = getattr(pipe, "pipeline_kind", None)
        if not kind:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "pipeline_kind must be set (auto_patrol | diagnostic) before locking",
                    "errors": [{"rule": "kind_required_for_lock", "message": "Call PATCH /pipelines/{id} with pipeline_kind first"}],
                },
            )
        validator = PipelineValidator(registry.catalog, enforce_kind=kind)
        errors = validator.validate(json.loads(pipe.pipeline_json))
        if errors:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Pipeline fails {kind}-specific structural checks",
                    "errors": errors,
                },
            )

    # Mutate state + timestamps
    pipe = await repo.update_status(pipe.id, new_status=target)
    now = _dt.now(tz=_tz.utc)
    if target == "locked":
        pipe.locked_at = now
    elif target == "active":
        pipe.published_at = now
    elif target == "archived":
        pipe.archived_at = now
    elif target == "draft":
        # Back to draft — clear lock marker
        pipe.locked_at = None
        pipe.locked_by = None
    return pipe


@router.post("/pipelines/{pipeline_id}/transition")
async def transition_pipeline(
    pipeline_id: int,
    body: TransitionBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """PR-B unified lifecycle transition — preferred over /promote + /deprecate."""
    registry = _get_registry(request)
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")

    pipe = await _do_transition(pipe, body.to, registry=registry, repo=repo)
    await db.commit()
    return _pipeline_to_summary(pipe)


@router.post("/pipelines/{pipeline_id}/promote")
async def promote_pipeline(
    pipeline_id: int,
    body: PromoteBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Legacy shim — maps pi_run→validating, production→active. Prefer /transition."""
    target = _LEGACY_STATUS_ALIASES.get(body.target_status, body.target_status)
    registry = _get_registry(request)
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")

    # Legacy pi_run→validating→locked→active chain: for compat, allow promote
    # to skip through locked when target=active. Modern clients should use /transition.
    if target == "active" and pipe.status == "validating":
        pipe = await _do_transition(pipe, "locked", registry=registry, repo=repo)
    pipe = await _do_transition(pipe, target, registry=registry, repo=repo)
    await db.commit()
    return _pipeline_to_summary(pipe)


@router.post("/pipelines/{pipeline_id}/fork", status_code=201)
async def fork_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Clone & Edit — create an editable draft from any non-draft pipeline.

    PR-B renamed Fork → Clone & Edit semantically. URL kept for back-compat.
    """
    repo = PipelineRepository(db)
    src = await repo.get_by_id(pipeline_id)
    if src is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    # PR-B: allow clone from any non-draft state (including archived, so users
    # can revive retired pipelines).
    if src.status == "draft":
        raise HTTPException(
            status_code=409,
            detail="Cannot clone a draft — just edit it directly",
        )

    payload = json.loads(src.pipeline_json)
    meta = payload.get("metadata") or {}
    meta["fork_of"] = src.id
    meta["forked_at"] = datetime.utcnow().isoformat() + "Z"
    payload["metadata"] = meta

    forked = await repo.create(
        name=f"{src.name} (clone)",
        description=src.description,
        status="draft",
        pipeline_json=payload,
        parent_id=src.id,
    )
    # Carry pipeline_kind across clones (None if src was an ad-hoc unclassified pipeline)
    forked.pipeline_kind = getattr(src, "pipeline_kind", None)
    await db.commit()
    return _pipeline_to_summary(forked) | {"pipeline_json": payload}


@router.delete(
    "/pipelines/{pipeline_id}",
    status_code=204,
    response_class=Response,
)
async def delete_pipeline(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Hard-delete a pipeline. PR-B: only allowed for draft or archived
    (never validating/locked/active — must archive or go back to draft first)."""
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    if pipe.status not in {"draft", "archived"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete pipeline in '{pipe.status}' state; archive it first",
        )
    await repo.delete(pipeline_id)
    await db.commit()
    return Response(status_code=204)


@router.post("/pipelines/{pipeline_id}/deprecate")
async def deprecate_pipeline(
    pipeline_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Legacy shim — maps to transition(to=archived)."""
    registry = _get_registry(request)
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    if pipe.status == "archived":
        return _pipeline_to_summary(pipe)
    pipe = await _do_transition(pipe, "archived", registry=registry, repo=repo)
    await db.commit()
    return _pipeline_to_summary(pipe)


# ---------------------------------------------------------------------------
# PR-C / Phase 4-D — Publish + Skill Registry
# ---------------------------------------------------------------------------


class PublishBody(BaseModel):
    """User-approved DraftDoc payload (may differ from template default)."""

    reviewed_doc: dict[str, Any]
    published_by: Optional[str] = None


@router.post("/pipelines/{pipeline_id}/publish/draft-doc")
async def publish_draft_doc(
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Generate (or regenerate) a DraftDoc for review. Idempotent — does not
    mutate pipeline state. UI should show this in Review Modal before publish.
    """
    repo = PipelineRepository(db)
    pipe = await repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    # Allow draft-doc generation from validating OR locked (gives user a preview
    # before committing to lock).
    if pipe.status not in {"validating", "locked"}:
        raise HTTPException(
            status_code=409,
            detail=f"Can only generate doc for validating/locked pipelines (got '{pipe.status}')",
        )

    doc = generate_draft_doc(
        pipeline_id=pipe.id,
        pipeline_name=pipe.name,
        pipeline_version=pipe.version,
        pipeline_kind=getattr(pipe, "pipeline_kind", "diagnostic"),
        description=pipe.description or "",
        pipeline_json=json.loads(pipe.pipeline_json),
    )
    # Persist as draft on the pipeline row so reopening the modal shows the last doc
    pipe.auto_doc = json.dumps(doc, ensure_ascii=False)
    await db.commit()
    return doc


@router.post("/pipelines/{pipeline_id}/publish")
async def publish_pipeline(
    pipeline_id: int,
    body: PublishBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Publish a locked pipeline to the Skill Registry + transition to active.

    Body carries the reviewer-approved doc; we trust it as-is (frontend is the
    gate). Writes a row to pb_published_skills and flips pipeline to active.
    """
    registry = _get_registry(request)
    pipe_repo = PipelineRepository(db)
    pub_repo = PublishedSkillRepository(db)

    pipe = await pipe_repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")

    if pipe.status != "locked":
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline must be 'locked' before publish (got '{pipe.status}')",
        )

    kind = getattr(pipe, "pipeline_kind", None)
    # Phase 5-UX-7: treat legacy "diagnostic" as "skill" for back-compat
    if kind == "diagnostic":
        kind = "skill"
    if kind != "skill":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Only skill pipelines go to the Skill Registry. "
                f"kind='{kind}' routes elsewhere: "
                f"auto_patrol → /admin/auto-patrols binding, "
                f"auto_check → /pipelines/{{id}}/publish-auto-check with event_types."
            ),
        )

    doc = body.reviewed_doc
    # Validate required fields exist
    required_fields = ["slug", "name", "use_case", "inputs_schema", "outputs_schema"]
    missing = [f for f in required_fields if not doc.get(f)]
    if missing:
        raise HTTPException(status_code=422, detail=f"reviewed_doc missing fields: {missing}")

    # Refuse if slug already exists on an ACTIVE skill
    existing = await pub_repo.get_by_slug(doc["slug"])
    if existing is not None and existing.status == "active":
        raise HTTPException(
            status_code=409,
            detail=f"slug '{doc['slug']}' already exists — retire the old version or rename",
        )

    await pub_repo.create({
        "pipeline_id": pipe.id,
        "pipeline_version": pipe.version,
        "slug": doc["slug"],
        "name": doc.get("name") or pipe.name,
        "use_case": doc.get("use_case", ""),
        "when_to_use": doc.get("when_to_use") or [],
        "inputs_schema": doc.get("inputs_schema") or [],
        "outputs_schema": doc.get("outputs_schema") or {},
        "example_invocation": doc.get("example_invocation"),
        "tags": doc.get("tags") or [],
        "status": "active",
        "published_by": body.published_by or "admin",
    })

    pipe = await _do_transition(pipe, "active", registry=registry, repo=pipe_repo)
    await db.commit()
    return _pipeline_to_summary(pipe) | {"published_slug": doc["slug"]}


# ── Phase 5-UX-7: Auto-Check publish flow ─────────────────────────────────

class PublishAutoCheckBody(BaseModel):
    event_types: list[str] = Field(
        ...,
        description="List of alarm event_type strings this pipeline should auto-run on",
        min_length=1,
    )


@router.post("/pipelines/{pipeline_id}/publish-auto-check")
async def publish_auto_check(
    pipeline_id: int,
    body: PublishAutoCheckBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Publish an auto_check pipeline: bind to alarm event_types + flip to active.

    Inputs_mapping is implicit by name-match — pipeline input names must line up
    with alarm payload fields. The runtime alarm service resolves them.
    """
    from app.repositories.auto_check_trigger_repository import AutoCheckTriggerRepository

    pipe_repo = PipelineRepository(db)
    trigger_repo = AutoCheckTriggerRepository(db)

    pipe = await pipe_repo.get_by_id(pipeline_id)
    if pipe is None:
        raise HTTPException(status_code=404, detail=f"Pipeline {pipeline_id} not found")
    if pipe.status != "locked":
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline must be 'locked' before publish (got '{pipe.status}')",
        )
    if getattr(pipe, "pipeline_kind", None) != "auto_check":
        raise HTTPException(
            status_code=409,
            detail=f"publish-auto-check is only for pipeline_kind='auto_check' (got '{pipe.pipeline_kind}').",
        )

    # Replace trigger bindings atomically
    await trigger_repo.replace_for_pipeline(pipeline_id, body.event_types)

    # Flip to active
    registry = _get_registry(request)
    pipe = await _do_transition(pipe, "active", registry=registry, repo=pipe_repo)

    await db.commit()
    return _pipeline_to_summary(pipe) | {"event_types": body.event_types}


@router.get("/auto-check-rules")
async def list_auto_check_rules(
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all auto-check triggers with parent pipeline metadata."""
    from app.repositories.auto_check_trigger_repository import AutoCheckTriggerRepository

    trigger_repo = AutoCheckTriggerRepository(db)
    pipe_repo = PipelineRepository(db)
    triggers = await trigger_repo.list_all()
    out: list[dict[str, Any]] = []
    for t in triggers:
        pipe = await pipe_repo.get_by_id(t.pipeline_id)
        if pipe is None:
            continue
        out.append({
            "id": t.id,
            "pipeline_id": t.pipeline_id,
            "pipeline_name": pipe.name,
            "pipeline_status": pipe.status,
            "event_type": t.event_type,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        })
    return out


@router.delete(
    "/auto-check-rules/{trigger_id}",
    status_code=204,
    response_class=Response,
)
async def delete_auto_check_rule(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
):
    from app.models.pipeline_auto_check_trigger import PipelineAutoCheckTriggerModel
    row = (await db.execute(
        select(PipelineAutoCheckTriggerModel).where(
            PipelineAutoCheckTriggerModel.id == trigger_id
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Trigger {trigger_id} not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.get("/published-skills")
async def list_published_skills(
    include_retired: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    repo = PublishedSkillRepository(db)
    rows = await repo.list_all(include_retired=include_retired)
    return [repo.to_dict(r) for r in rows]


class SearchSkillsBody(BaseModel):
    query: str
    top_k: int = Field(10, ge=1, le=50)


@router.post("/published-skills/search")
async def search_published_skills(
    body: SearchSkillsBody,
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    repo = PublishedSkillRepository(db)
    rows = await repo.search(body.query, top_k=body.top_k)
    return [repo.to_dict(r) for r in rows]


@router.post("/published-skills/{skill_id}/retire")
async def retire_published_skill(
    skill_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    repo = PublishedSkillRepository(db)
    row = await repo.retire(skill_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"PublishedSkill {skill_id} not found")
    await db.commit()
    return repo.to_dict(row)


@router.get("/suggestions/{field}")
async def suggestions(field: str) -> list[str]:
    """Return suggestion values for a given param field (tool_id, step, ...).

    Used by SchemaForm <datalist> autocomplete. Lightweight proxy to simulator.
    """
    import httpx
    from app.config import get_settings

    settings = get_settings()
    sim_url = getattr(settings, "ONTOLOGY_SIM_URL", "") or ""

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            if field == "tool_id":
                if not sim_url:
                    return []
                r = await client.get(f"{sim_url.rstrip('/')}/api/v1/tools")
                if r.status_code != 200:
                    return []
                data = r.json()
                # expected: [{"tool_id": "EQP-01", "status": "..."}, ...]
                return sorted({item.get("tool_id") for item in data if item.get("tool_id")})
            if field == "step":
                # Phase 2: sample steps from EQP-01 summary (cheap, not exhaustive)
                if not sim_url:
                    return []
                r = await client.get(f"{sim_url.rstrip('/')}/api/v1/process/summary", params={"since": "24h"})
                if r.status_code != 200:
                    return []
                data = r.json()
                steps = sorted({item.get("step") for item in (data.get("by_step") or []) if item.get("step")})
                return steps
    except Exception as e:
        logger.warning("suggestions(%s) failed: %s", field, e)
        return []
    return []


@router.post("/preview")
async def preview_node(
    request: Request,
    body: PreviewBody,
) -> dict[str, Any]:
    """Run pipeline up to (and including) `node_id`; return that node's preview output.

    Does NOT persist a PipelineRun record — purely for UI preview.
    Preview is intentionally partial, so we skip endpoint-required (C7) validation.
    """
    registry = _get_registry(request)

    # Truncate pipeline to the target's ancestors first, THEN validate the subgraph.
    pipeline = body.pipeline_json
    target = body.node_id
    node_ids = {n.id for n in pipeline.nodes}
    if target not in node_ids:
        raise HTTPException(status_code=404, detail=f"Node '{target}' not in pipeline")

    # BFS upstream from target to find ancestors (inclusive)
    ancestors = {target}
    frontier = {target}
    while frontier:
        next_frontier: set[str] = set()
        for edge in pipeline.edges:
            if edge.to.node in frontier and edge.from_.node not in ancestors:
                ancestors.add(edge.from_.node)
                next_frontier.add(edge.from_.node)
        frontier = next_frontier

    truncated = pipeline.model_copy(
        update={
            "nodes": [n for n in pipeline.nodes if n.id in ancestors],
            "edges": [e for e in pipeline.edges if e.from_.node in ancestors and e.to.node in ancestors],
        }
    )

    # Validate the truncated subgraph, but ignore C7 (preview is partial by design)
    validator = PipelineValidator(registry.catalog)
    errors = [e for e in validator.validate(truncated) if e.get("rule") != "C7_ENDPOINTS"]
    if errors:
        return {"status": "validation_error", "errors": errors}

    executor = PipelineExecutor(registry)
    # Preview defaults to using pipeline.inputs' example values when caller
    # didn't explicitly provide; lets a template-ish pipeline preview cleanly.
    preview_inputs = {**body.inputs}
    for decl in truncated.inputs or []:
        if decl.name not in preview_inputs or preview_inputs[decl.name] is None:
            if decl.example is not None:
                preview_inputs[decl.name] = decl.example

    result = await executor.execute(
        truncated,
        preview_sample_size=body.sample_size,
        inputs=preview_inputs,
    )
    node_result = result["node_results"].get(target)
    return {
        "status": result["status"],
        "target": target,
        "node_result": node_result,
        # v1.3 C: return all ancestor results so the UI can warm up its per-node cache
        "all_node_results": result["node_results"],
        "error_message": result.get("error_message"),
        "result_summary": result.get("result_summary"),
    }
