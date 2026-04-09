"""ChartMiddleware — automatic chart generation from output_schema + findings.outputs.

Middleware layer between Skill execution and frontend rendering.
Responsibility: transform raw data → chart DSL based on output_schema type declarations.

LLM code only needs to produce data in _findings.outputs.
ChartMiddleware reads output_schema types and auto-generates chart DSL.

Extensible via register():
    ChartMiddleware.register("heatmap", build_heatmap)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Chart DSL color palette (consistent with frontend ChartIntentRenderer)
_SERIES_COLORS = ["#4299e1", "#38a169", "#d69e2e", "#9f7aea", "#ed8936", "#e53e3e"]

# ── Chart type → builder registry ──────────────────────────────────────────────

_BUILDERS: Dict[str, Callable[[Any, dict], Any]] = {}


def register(schema_type: str, builder: Callable[[Any, dict], Any]) -> None:
    """Register a chart builder for a given output_schema type."""
    _BUILDERS[schema_type] = builder


def process(outputs: Dict[str, Any], output_schema: List[dict]) -> List[dict]:
    """Process all output_schema fields and auto-generate charts.

    Returns a list of chart DSL dicts ready for frontend rendering.
    Only processes fields whose type has a registered builder.
    """
    charts: List[dict] = []
    for field in output_schema:
        field_type = field.get("type", "")
        builder = _BUILDERS.get(field_type)
        if not builder:
            continue
        key = field.get("key", "")
        data = outputs.get(key)
        if data is None:
            continue
        try:
            result = builder(data, field)
            if isinstance(result, list):
                charts.extend(result)
            elif isinstance(result, dict):
                charts.append(result)
        except Exception as exc:
            logger.warning("ChartMiddleware builder '%s' failed for key '%s': %s", field_type, key, exc)
    return charts


# ── Builders ───────────────────────────────────────────────────────────────────

def _build_spc_chart(data: Any, schema: dict) -> List[dict]:
    """SPC chart: split by group_key into independent charts with per-group UCL/LCL rules.

    Input data: list of flat dicts with group_key (e.g. chart_type), value, ucl, lcl, is_ooc.
    Output: one chart DSL per group (e.g. 5 charts for xbar/r/s/p/c).
    """
    if not isinstance(data, list) or not data:
        return []

    group_key = schema.get("group_key", "chart_type")
    x_key = schema.get("x_key", "eventTime")
    value_key = schema.get("value_key", "value")
    ucl_key = schema.get("ucl_key", "ucl")
    lcl_key = schema.get("lcl_key", "lcl")
    highlight_key = schema.get("highlight_key", "is_ooc")

    # Group data
    groups: Dict[str, list] = {}
    for record in data:
        g = str(record.get(group_key, "unknown"))
        groups.setdefault(g, []).append(record)

    _TITLE_MAP = {
        "xbar_chart": "X-bar", "r_chart": "R", "s_chart": "S",
        "p_chart": "P", "c_chart": "C",
    }

    charts = []
    for group_name in sorted(groups.keys()):
        group_data = groups[group_name]
        # Sort chronologically
        group_data.sort(key=lambda r: str(r.get(x_key, "")))

        # Extract UCL/LCL from first record (consistent within group)
        ucl = group_data[0].get(ucl_key)
        lcl = group_data[0].get(lcl_key)
        values = [r.get(value_key) for r in group_data if r.get(value_key) is not None]
        cl = sum(values) / len(values) if values else 0

        rules = []
        if ucl is not None:
            rules.append({"value": ucl, "label": "UCL", "style": "danger"})
        if lcl is not None:
            rules.append({"value": lcl, "label": "LCL", "style": "danger"})
        rules.append({"value": round(cl, 4), "label": "CL", "style": "center"})

        title = f"{_TITLE_MAP.get(group_name, group_name)} Chart"
        label = schema.get("label", "")
        if label:
            title = f"{title} — {label}"

        charts.append({
            "type": "line",
            "title": title,
            "data": group_data,
            "x": x_key,
            "y": [value_key],
            "rules": rules,
            "highlight": {"field": highlight_key, "eq": True} if highlight_key else None,
        })

    return charts


def _build_line_chart(data: Any, schema: dict) -> Optional[dict]:
    """Single line chart."""
    if not isinstance(data, list) or not data:
        return None
    x_key = schema.get("x_key", "index")
    y_keys = schema.get("y_keys", ["value"])
    highlight_key = schema.get("highlight_key")

    rules = []
    # Auto-detect UCL/LCL from data if present
    if data and isinstance(data[0], dict):
        sample = data[0]
        if "ucl" in sample and "ucl" not in y_keys:
            rules.append({"value": sample["ucl"], "label": "UCL", "style": "danger"})
        if "lcl" in sample and "lcl" not in y_keys:
            rules.append({"value": sample["lcl"], "label": "LCL", "style": "danger"})

    return {
        "type": "line",
        "title": schema.get("label", "Chart"),
        "data": data,
        "x": x_key,
        "y": y_keys,
        "rules": rules,
        "highlight": {"field": highlight_key, "eq": True} if highlight_key else None,
    }


def _build_bar_chart(data: Any, schema: dict) -> Optional[dict]:
    """Bar chart."""
    if not isinstance(data, list) or not data:
        return None
    return {
        "type": "bar",
        "title": schema.get("label", "Chart"),
        "data": data,
        "x": schema.get("x_key", "category"),
        "y": schema.get("y_keys", ["value"]),
        "rules": [],
        "highlight": None,
    }


def _build_scatter_chart(data: Any, schema: dict) -> Optional[dict]:
    """Scatter plot."""
    if not isinstance(data, list) or not data:
        return None
    return {
        "type": "scatter",
        "title": schema.get("label", "Chart"),
        "data": data,
        "x": schema.get("x_key", "x"),
        "y": schema.get("y_keys", ["y"]),
        "rules": [],
        "highlight": {"field": schema.get("highlight_key"), "eq": True} if schema.get("highlight_key") else None,
    }


def _build_multi_line_chart(data: Any, schema: dict) -> List[dict]:
    """Multi-line chart: one chart per group."""
    if not isinstance(data, list) or not data:
        return []

    group_key = schema.get("group_key", "group")
    x_key = schema.get("x_key", "eventTime")
    y_key = schema.get("y_key", "value")
    highlight_key = schema.get("highlight_key")

    groups: Dict[str, list] = {}
    for record in data:
        g = str(record.get(group_key, "default"))
        groups.setdefault(g, []).append(record)

    charts = []
    for group_name, group_data in sorted(groups.items()):
        group_data.sort(key=lambda r: str(r.get(x_key, "")))
        charts.append({
            "type": "line",
            "title": f"{schema.get('label', 'Chart')} — {group_name}",
            "data": group_data,
            "x": x_key,
            "y": [y_key],
            "rules": [],
            "highlight": {"field": highlight_key, "eq": True} if highlight_key else None,
        })

    return charts


# ── Register built-in builders ─────────────────────────────────────────────────

register("spc_chart", _build_spc_chart)
register("line_chart", _build_line_chart)
register("bar_chart", _build_bar_chart)
register("scatter_chart", _build_scatter_chart)
register("multi_line_chart", _build_multi_line_chart)
