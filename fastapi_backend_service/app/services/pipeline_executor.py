"""Pipeline Executor — runs the 4-stage data pipeline (Stage 3~6).

Called by tool_execute when LLM outputs a plan_pipeline tool call.
Executes: Data Retrieval → Data Transform → Compute → Presentation

Each stage produces a pipeline_card (for SSE/Console display).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def execute_pipeline(
    plan: Dict[str, Any],
    db_session: Any,
    sim_url: str,
) -> Dict[str, Any]:
    """Execute a data pipeline from a plan JSON.

    Args:
        plan: LLM-generated pipeline plan with keys:
            - data_retrieval: {mcp, params}
            - data_transform: {description} (optional)
            - compute: {description, type} (optional)
            - presentation: {data_source, chart_type, ...} (optional)
        db_session: async DB session for MCP executor
        sim_url: ontology simulator URL

    Returns:
        {
            pipeline_cards: [...],  # one per stage, for Console display
            flat_data: {...},       # 6 flat datasets
            flat_metadata: {...},   # statistics
            processed_data: [...],  # after transform
            compute_results: [...], # after compute
            ui_config: {...},       # for DataExplorer
            llm_summary: str,       # text summary for LLM synthesis
        }
    """
    pipeline_cards: List[Dict[str, Any]] = []
    flat_data = None
    flat_metadata = None
    processed_data = None
    compute_results = None
    ui_config = None
    llm_summary = ""

    # ── Stage 3: Data Retrieval ──────────────────────────────────────────────

    retrieval = plan.get("data_retrieval", {})
    mcp_name = retrieval.get("mcp", "get_process_info")
    mcp_params = retrieval.get("params", {})

    t0 = time.time()
    try:
        from app.services.skill_executor_service import build_mcp_executor
        from app.config import get_settings
        executor = build_mcp_executor(db_session, sim_url=sim_url)
        raw_result = await executor(mcp_name, mcp_params)
        raw_result = raw_result if isinstance(raw_result, dict) else {}
        elapsed_retrieval = round(time.time() - t0, 2)

        # Count events
        events = raw_result.get("events", [])
        event_count = len(events) if isinstance(events, list) else 0

        pipeline_cards.append({
            "stage": 3, "name": "Data Retrieval", "icon": "📡",
            "status": "complete", "elapsed": elapsed_retrieval,
            "summary": f"{mcp_name}({', '.join(f'{k}={v}' for k, v in mcp_params.items() if v)}) → {event_count} events",
            "detail": {
                "mcp": mcp_name, "params": mcp_params,
                "event_count": event_count,
            },
        })
    except Exception as exc:
        logger.exception("Pipeline Stage 3 failed: %s", exc)
        pipeline_cards.append({
            "stage": 3, "name": "Data Retrieval", "icon": "📡",
            "status": "error", "elapsed": round(time.time() - t0, 2),
            "summary": f"Error: {exc}",
        })
        return _build_result(pipeline_cards, llm_summary=f"資料擷取失敗: {exc}")

    # ── Stage 4: Data Transform ──────────────────────────────────────────────

    t0 = time.time()
    try:
        from app.services.data_flattener import flatten as data_flatten, build_llm_summary

        # Layer 1: Base flatten (deterministic, no LLM)
        flat_result = data_flatten(raw_result)
        flat_data = flat_result.to_dict()
        flat_metadata = flat_result.metadata

        # Layer 2: Custom transform (if plan specifies)
        transform_desc = (plan.get("data_transform") or {}).get("description", "")
        transform_code = None
        if transform_desc:
            # Generate and execute transform code
            processed_data, transform_code = await _run_transform(
                transform_desc, flat_data, flat_metadata, flat_result
            )

        elapsed_transform = round(time.time() - t0, 2)

        base_sizes = {k: len(v) for k, v in flat_data.items() if isinstance(v, list) and v}
        pipeline_cards.append({
            "stage": 4, "name": "Data Transform", "icon": "🔄",
            "status": "complete", "elapsed": elapsed_transform,
            "summary": f"Base: {', '.join(f'{k}={v}' for k, v in base_sizes.items())}"
                       + (f" → Custom: {len(processed_data or [])} rows" if processed_data else ""),
            "detail": {
                "base_flatten": base_sizes,
                "custom_transform": bool(transform_desc),
                "custom_code": transform_code,
                "output_rows": len(processed_data or []),
            },
        })

        # Build LLM summary with samples
        llm_summary = build_llm_summary(flat_metadata, flat_result)

    except Exception as exc:
        logger.exception("Pipeline Stage 4 failed: %s", exc)
        pipeline_cards.append({
            "stage": 4, "name": "Data Transform", "icon": "🔄",
            "status": "error", "elapsed": round(time.time() - t0, 2),
            "summary": f"Error: {exc}",
        })
        return _build_result(pipeline_cards, flat_data=flat_data, flat_metadata=flat_metadata,
                             llm_summary=f"資料轉換失敗: {exc}")

    # ── Stage 5: Compute (optional) ──────────────────────────────────────────

    compute_spec = plan.get("compute")
    if compute_spec and compute_spec.get("description"):
        t0 = time.time()
        try:
            compute_results, compute_code = await _run_compute(
                compute_spec["description"],
                flat_data, processed_data, flat_metadata
            )
            elapsed_compute = round(time.time() - t0, 2)

            pipeline_cards.append({
                "stage": 5, "name": "Compute", "icon": "🔬",
                "status": "complete", "elapsed": elapsed_compute,
                "summary": f"{compute_spec.get('type', 'custom')} → {len(compute_results or [])} results",
                "detail": {
                    "type": compute_spec.get("type", "custom"),
                    "code": compute_code,
                    "results": compute_results[:5] if compute_results else [],
                },
            })

            # Append compute results to LLM summary
            if compute_results:
                llm_summary += "\n\n═══ COMPUTE RESULTS ═══\n"
                llm_summary += json.dumps(compute_results[:10], ensure_ascii=False, default=str)
                llm_summary += "\n═════════════════════"

        except Exception as exc:
            logger.exception("Pipeline Stage 5 failed: %s", exc)
            pipeline_cards.append({
                "stage": 5, "name": "Compute", "icon": "🔬",
                "status": "error", "elapsed": round(time.time() - t0, 2),
                "summary": f"Error: {exc}",
            })
    else:
        pipeline_cards.append({
            "stage": 5, "name": "Compute", "icon": "🔬",
            "status": "skipped", "elapsed": 0,
            "summary": "Not needed",
        })

    # ── Stage 6: Presentation ────────────────────────────────────────────────

    presentation = plan.get("presentation")
    if presentation:
        # Build UI config for DataExplorer
        ui_config = {
            "ui_component": "DataExplorer",
            "query_info": {
                "mcp": mcp_name,
                "params": mcp_params,
                "result_summary": f"{flat_metadata.get('total_events', 0)} events, "
                                  f"{flat_metadata.get('ooc_count', 0)} OOC "
                                  f"({flat_metadata.get('ooc_rate', 0)}%)",
            },
            "initial_view": presentation,
            "available_datasets": flat_metadata.get("available_datasets", []),
        }
        # Add processed_data and compute_results as extra datasets
        if processed_data:
            flat_data["processed_data"] = processed_data
        if compute_results:
            flat_data["compute_results"] = compute_results

        pipeline_cards.append({
            "stage": 6, "name": "Presentation", "icon": "📊",
            "status": "complete", "elapsed": 0,
            "summary": f"DataExplorer: {presentation.get('data_source', '?')} "
                       f"({presentation.get('chart_type', 'auto')})",
            "detail": {"ui_config": ui_config},
        })
    else:
        pipeline_cards.append({
            "stage": 6, "name": "Presentation", "icon": "📊",
            "status": "skipped", "elapsed": 0,
            "summary": "Text only (no chart)",
        })

    return _build_result(
        pipeline_cards, flat_data, flat_metadata,
        processed_data, compute_results, ui_config, llm_summary,
    )


def _build_result(
    pipeline_cards, flat_data=None, flat_metadata=None,
    processed_data=None, compute_results=None, ui_config=None, llm_summary="",
):
    return {
        "status": "success",
        "pipeline_cards": pipeline_cards,
        "flat_data": flat_data,
        "flat_metadata": flat_metadata,
        "processed_data": processed_data,
        "compute_results": compute_results,
        "ui_config": ui_config,
        "llm_summary": llm_summary,
    }


# ── Code generation + execution ──────────────────────────────────────────────

async def _run_transform(
    description: str,
    flat_data: Dict[str, Any],
    flat_metadata: Dict[str, Any],
    flat_result: Any,
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """Generate and execute transform code. Returns (processed_data, code_text)."""
    from app.utils.llm_client import get_llm_client
    import json as _json

    # Build context for code generation
    samples = ""
    for ds_name in (flat_metadata.get("available_datasets") or []):
        ds = flat_data.get(ds_name, [])
        if ds:
            samples += f"\n_flat_data['{ds_name}'] ({len(ds)} rows):\n"
            for row in ds[:2]:
                compact = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
                samples += f"  {_json.dumps(compact, ensure_ascii=False, default=str)}\n"

    prompt = (
        f"生成 Python code 來處理以下資料。\n\n"
        f"可用資料：\n{samples}\n"
        f"需求：{description}\n\n"
        f"規則：\n"
        f"- Input: _flat_data (dict, 每個 key 是 dataset name, value 是 list of dicts)\n"
        f"- Output: 把結果 assign 到 _processed_data (list of dicts)\n"
        f"- 只用 Python 標準庫 + numpy\n"
        f"- 不要 import requests/os/sys/matplotlib/plotly\n"
        f"- 不要呼叫 execute_mcp\n\n"
        f"只輸出 Python code，不要解釋。"
    )

    llm = get_llm_client()
    resp = await llm.create(
        system="你是 Python code generator。只輸出可執行的 Python code，不要 markdown。",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    code = (resp.text or "").strip()
    # Strip markdown fences
    if code.startswith("```"):
        code = "\n".join(code.split("\n")[1:])
    if code.endswith("```"):
        code = "\n".join(code.split("\n")[:-1])

    # Execute in sandbox
    namespace = {"_flat_data": flat_data, "_processed_data": None, "true": True, "false": False, "null": None}
    try:
        import numpy as np
        namespace["np"] = np
        namespace["numpy"] = np
    except ImportError:
        pass
    exec(code, namespace)
    processed = namespace.get("_processed_data")
    return (processed if isinstance(processed, list) else None), code


async def _run_compute(
    description: str,
    flat_data: Dict[str, Any],
    processed_data: Optional[List[Dict]],
    flat_metadata: Dict[str, Any],
) -> tuple[Optional[List[Dict]], Optional[str]]:
    """Generate and execute compute code. Returns (results, code_text)."""
    from app.utils.llm_client import get_llm_client
    import json as _json

    # Build data context
    data_desc = ""
    if processed_data:
        data_desc += f"_processed_data ({len(processed_data)} rows):\n"
        for row in processed_data[:3]:
            compact = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
            data_desc += f"  {_json.dumps(compact, ensure_ascii=False, default=str)}\n"
    else:
        for ds_name in (flat_metadata.get("available_datasets") or [])[:3]:
            ds = flat_data.get(ds_name, [])
            if ds:
                data_desc += f"_flat_data['{ds_name}'] ({len(ds)} rows):\n"
                for row in ds[:2]:
                    compact = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}
                    data_desc += f"  {_json.dumps(compact, ensure_ascii=False, default=str)}\n"

    prompt = (
        f"生成 Python code 來做統計計算。\n\n"
        f"可用資料：\n{data_desc}\n"
        f"需求：{description}\n\n"
        f"規則：\n"
        f"- Input: _flat_data (dict of datasets), _processed_data (list or None)\n"
        f"- Output: 把結果 assign 到 _compute_results (list of dicts)\n"
        f"- 可用：numpy, scipy.stats, collections, math\n"
        f"- 不要 import requests/os/sys/matplotlib/plotly\n\n"
        f"只輸出 Python code，不要解釋。"
    )

    llm = get_llm_client()
    resp = await llm.create(
        system="你是 Python code generator。只輸出可執行的 Python code，不要 markdown。",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2048,
    )
    code = (resp.text or "").strip()
    if code.startswith("```"):
        code = "\n".join(code.split("\n")[1:])
    if code.endswith("```"):
        code = "\n".join(code.split("\n")[:-1])

    namespace = {
        "_flat_data": flat_data,
        "_processed_data": processed_data,
        "_compute_results": None,
        "true": True, "false": False, "null": None,
    }
    try:
        import numpy as np
        namespace["np"] = np
        namespace["numpy"] = np
    except ImportError:
        pass
    try:
        from scipy import stats as scipy_stats
        namespace["scipy_stats"] = scipy_stats
    except ImportError:
        pass
    from collections import defaultdict, Counter
    namespace["defaultdict"] = defaultdict
    namespace["Counter"] = Counter
    import math
    namespace["math"] = math

    exec(code, namespace)
    results = namespace.get("_compute_results")
    return (results if isinstance(results, list) else None), code
