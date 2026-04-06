"""Analysis Router — execute ad-hoc analysis (one-time Skill) + promote to Diagnostic Rule.

POST /analysis/run      — execute Agent-generated python code in sandbox
POST /analysis/promote  — save successful analysis as a permanent Diagnostic Rule
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.response import StandardResponse
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import UserModel
from app.repositories.skill_definition_repository import SkillDefinitionRepository
from app.services.skill_executor_service import SkillExecutorService, build_mcp_executor

router = APIRouter(prefix="/analysis", tags=["analysis"])


# ── Request / Response schemas ────────────────────────────────────────────────

class AnalysisStep(BaseModel):
    step_id: str
    nl_segment: str
    python_code: str


class RunAnalysisRequest(BaseModel):
    title: str = "Ad-hoc 分析"
    steps: List[AnalysisStep] = Field(..., min_length=1)
    input_params: Dict[str, Any] = Field(default_factory=dict)


class PromoteRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    auto_check_description: str = ""
    steps_mapping: List[Dict[str, Any]] = Field(..., min_length=1)
    input_schema: List[Dict[str, Any]] = Field(default_factory=list)
    output_schema: List[Dict[str, Any]] = Field(default_factory=list)


# ── Run ad-hoc analysis ──────────────────────────────────────────────────────

@router.post("/run", response_model=StandardResponse)
async def run_analysis(
    body: RunAnalysisRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """Execute Agent-generated python code in the same sandbox as Diagnostic Rules.

    Returns findings + charts + the original steps_mapping (for promote).
    """
    settings = get_settings()
    svc = SkillExecutorService(
        skill_repo=SkillDefinitionRepository(db),
        mcp_executor=build_mcp_executor(db, sim_url=settings.ONTOLOGY_SIM_URL),
    )

    steps = [s.model_dump() for s in body.steps]

    step_results, raw_findings, error, charts = await svc._run_script(
        steps=steps,
        event_payload=body.input_params,
    )

    if error:
        return StandardResponse.error(message=f"分析執行失敗：{error}")

    # Build findings dict
    findings = {}
    if raw_findings and isinstance(raw_findings, dict):
        findings = raw_findings

    # Infer input_schema from input_params keys
    input_schema_inferred = [
        {"key": k, "type": "string", "required": True, "description": ""}
        for k in body.input_params.keys()
    ]

    return StandardResponse.success(
        data={
            "title": body.title,
            "findings": findings,
            "charts": charts or [],
            "step_results": [
                {"step_id": sr.step_id, "status": sr.status, "error": sr.error}
                for sr in step_results
            ],
            # Payload for promote
            "steps_mapping": steps,
            "input_params": body.input_params,
            "input_schema_inferred": input_schema_inferred,
        },
        message=body.title,
    )


# ── Promote to Diagnostic Rule ───────────────────────────────────────────────

@router.post("/promote", response_model=StandardResponse)
async def promote_to_rule(
    body: PromoteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> StandardResponse:
    """Save a successful ad-hoc analysis as a permanent Diagnostic Rule.

    The new rule appears in skill_catalog and /admin/skills. Agent will
    use execute_skill for it next time instead of regenerating code.
    """
    from app.services.diagnostic_rule_service import DiagnosticRuleService
    from app.schemas.diagnostic_rule import DiagnosticRuleCreate

    svc = DiagnosticRuleService(
        repo=SkillDefinitionRepository(db),
        db=db,
    )

    create_body = DiagnosticRuleCreate(
        name=body.name,
        description=body.description,
        auto_check_description=body.auto_check_description or body.description,
        steps_mapping=body.steps_mapping,
        input_schema=body.input_schema,
        output_schema=body.output_schema,
        visibility="public",
    )

    result = await svc.create(create_body, created_by=current_user.id)
    return StandardResponse.success(
        data=result.model_dump(),
        message=f"已儲存為 Diagnostic Rule: {body.name}",
    )
