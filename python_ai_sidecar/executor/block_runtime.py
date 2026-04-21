"""Block implementations.

Each function takes ``(params, upstream_rows)`` and returns the rows it emits.
Rows are plain ``list[dict]`` — JSON-serialisable throughout. Keeps the entire
executor free of pandas unless a given block actually needs it.

Registration is explicit (``REGISTRY``) so unknown blocks fail loudly rather
than silently falling through to a default.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("python_ai_sidecar.executor.blocks")

Rows = list[dict[str, Any]]
BlockFn = Callable[[dict, Rows], Rows]


# --- individual blocks ---

def _loader(params: dict, _upstream: Rows) -> Rows:
    """``load_inline_rows`` — params.rows is a literal list of dicts.

    Useful as a deterministic source for tests + Frontend previews.
    Real data-source blocks (e.g. ``load_process_history``) live in
    ``fastapi_backend_service.app.services.pipeline_executor`` and get
    imported in Phase 7.
    """
    rows = params.get("rows") or []
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _filter(params: dict, upstream: Rows) -> Rows:
    """``filter_rows`` — params.field / params.op / params.value.

    Supported ops: eq, ne, in, not_in, gt, gte, lt, lte.
    """
    field = params.get("field")
    op = (params.get("op") or "eq").lower()
    value = params.get("value")
    if not field:
        return list(upstream)

    def keep(r: dict) -> bool:
        v = r.get(field)
        if op == "eq":      return v == value
        if op == "ne":      return v != value
        if op == "in":      return v in (value or [])
        if op == "not_in":  return v not in (value or [])
        if op == "gt":      return v is not None and v > value
        if op == "gte":     return v is not None and v >= value
        if op == "lt":      return v is not None and v < value
        if op == "lte":     return v is not None and v <= value
        return True

    return [r for r in upstream if keep(r)]


def _count(_params: dict, upstream: Rows) -> Rows:
    """``count_rows`` — collapses upstream to a single ``{count: N}`` row."""
    return [{"count": len(upstream)}]


def _group_by(params: dict, upstream: Rows) -> Rows:
    """``group_count`` — bucket by field, count per bucket."""
    field = params.get("field")
    if not field:
        return _count(params, upstream)
    buckets: dict[Any, int] = {}
    for r in upstream:
        key = r.get(field)
        buckets[key] = buckets.get(key, 0) + 1
    return [{field: k, "count": v} for k, v in buckets.items()]


def _chart_table(params: dict, upstream: Rows) -> Rows:
    """``render_table`` — identity block that marks rows as terminal output."""
    title = params.get("title") or "Table"
    return [{"_render": "table", "title": title, "rows": list(upstream)}]


def _chart_line(params: dict, upstream: Rows) -> Rows:
    """``render_line_chart`` — identity with x_key / y_key metadata."""
    return [{
        "_render": "line_chart",
        "x_key": params.get("x_key"),
        "y_key": params.get("y_key"),
        "title": params.get("title") or "Line",
        "rows": list(upstream),
    }]


REGISTRY: dict[str, BlockFn] = {
    # canonical names (match seed.py in fastapi_backend_service)
    "load_inline_rows": _loader,
    "filter_rows": _filter,
    "count_rows": _count,
    "group_count": _group_by,
    "render_table": _chart_table,
    "render_line_chart": _chart_line,
}


def resolve(block_name: str | None) -> BlockFn | None:
    if not block_name:
        return None
    return REGISTRY.get(block_name)
