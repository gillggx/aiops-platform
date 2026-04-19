"""Phase 5-UX-7: dispatch alarms → auto_check pipelines.

When an alarm is created, this service looks up pipeline_auto_check_triggers
bound to that alarm's trigger_event and runs each pipeline with inputs
resolved from the alarm payload by name-match.

Inputs resolution (implicit mapping):
  - For each declared pipeline input (PipelineInput.name):
      1. If alarm_payload has that key → use its value
      2. Else if the input has a default → use default
      3. Else raise InputResolutionError (alarm can't satisfy this pipeline)

The pipeline's own input_schema therefore self-documents exactly what it
expects from the alarm. No explicit mapping needed.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pipeline import PipelineModel
from app.repositories.auto_check_trigger_repository import AutoCheckTriggerRepository
from app.repositories.pipeline_repository import PipelineRepository
from app.schemas.pipeline import PipelineJSON
from app.services.pipeline_builder.block_registry import BlockRegistry
from app.services.pipeline_builder.executor import PipelineExecutor

logger = logging.getLogger(__name__)


class InputResolutionError(Exception):
    def __init__(self, pipeline_id: int, missing_input: str):
        self.pipeline_id = pipeline_id
        self.missing_input = missing_input
        super().__init__(
            f"Pipeline {pipeline_id} declares input '{missing_input}' but the alarm "
            f"payload has no such field and the input has no default."
        )


def _resolve_inputs(
    pipeline_json: PipelineJSON, alarm_payload: dict[str, Any]
) -> dict[str, Any]:
    """Resolve pipeline inputs from alarm payload by name-match. Returns dict
    name→value. Raises InputResolutionError if a required input can't be
    resolved."""
    resolved: dict[str, Any] = {}
    for inp in pipeline_json.inputs or []:
        name = inp.name
        if name in alarm_payload:
            resolved[name] = alarm_payload[name]
            continue
        default = inp.default
        if default is not None:
            resolved[name] = default
            continue
        # No value from alarm, no default
        if inp.required:
            raise InputResolutionError(pipeline_id=0, missing_input=name)
        # Optional with no default — just leave it unset
    return resolved


async def dispatch_alarm_to_auto_checks(
    db: AsyncSession,
    *,
    alarm_id: int,
    trigger_event: str,
    alarm_payload: dict[str, Any],
    block_registry: BlockRegistry | None = None,
) -> list[dict[str, Any]]:
    """Fire all auto_check pipelines bound to trigger_event.

    Returns a list of run summaries (one per pipeline). Never raises to the
    caller — a failure in any single pipeline is logged + included in the list
    with status='failed'. The calling alarm creation flow should not be
    blocked by this dispatch.
    """
    trigger_repo = AutoCheckTriggerRepository(db)
    pipe_repo = PipelineRepository(db)

    triggers = await trigger_repo.list_by_event(trigger_event)
    if not triggers:
        return []

    # Load registry once
    if block_registry is None:
        block_registry = BlockRegistry()
        await block_registry.load_from_db(db)

    executor = PipelineExecutor(block_registry)
    out: list[dict[str, Any]] = []

    for trig in triggers:
        pipe: PipelineModel | None = await pipe_repo.get_by_id(trig.pipeline_id)
        if pipe is None:
            logger.warning(
                "auto_check trigger %s references missing pipeline %d",
                trig.id, trig.pipeline_id,
            )
            continue
        if pipe.status != "active":
            logger.info(
                "Skipping auto_check pipeline %d (status=%s, not active)",
                pipe.id, pipe.status,
            )
            continue

        try:
            pipeline_json = PipelineJSON.model_validate(json.loads(pipe.pipeline_json))
        except Exception as e:  # noqa: BLE001
            logger.exception("auto_check pipeline %d has corrupt JSON: %s", pipe.id, e)
            out.append({
                "pipeline_id": pipe.id,
                "trigger_event": trigger_event,
                "status": "failed",
                "error_message": f"Corrupt pipeline JSON: {e}",
            })
            continue

        try:
            resolved_inputs = _resolve_inputs(pipeline_json, alarm_payload)
        except InputResolutionError as e:
            logger.warning(
                "auto_check pipeline %d cannot run on alarm %d: %s",
                pipe.id, alarm_id, e,
            )
            out.append({
                "pipeline_id": pipe.id,
                "trigger_event": trigger_event,
                "status": "failed",
                "error_message": str(e),
            })
            continue

        try:
            result = await executor.execute(pipeline_json, inputs=resolved_inputs)
            out.append({
                "pipeline_id": pipe.id,
                "trigger_event": trigger_event,
                "status": result.get("status", "unknown"),
                "run_id": result.get("run_id"),
                "duration_ms": result.get("duration_ms"),
                "triggered": (result.get("result_summary") or {}).get("triggered") if result.get("result_summary") else None,
            })
            logger.info(
                "auto_check dispatched: alarm=%d pipeline=%d status=%s",
                alarm_id, pipe.id, result.get("status"),
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("auto_check pipeline %d executor crashed", pipe.id)
            out.append({
                "pipeline_id": pipe.id,
                "trigger_event": trigger_event,
                "status": "failed",
                "error_message": f"{type(e).__name__}: {e}",
            })

    return out
