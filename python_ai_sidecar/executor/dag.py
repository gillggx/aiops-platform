"""Topologically walks a pipeline DAG and runs each node through the registry.

Contract (matches Frontend's pipeline_json shape):
    {
      "nodes": [{"id": "n1", "block": "load_inline_rows", "params": {...}}, ...],
      "edges": [{"from": "n1", "to": "n2"}, ...]
    }
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .block_runtime import REGISTRY, Rows, resolve

log = logging.getLogger("python_ai_sidecar.executor.dag")


class DAGError(RuntimeError):
    """Raised when the pipeline is malformed (cycle, missing node, unknown block)."""


def _topo_sort(nodes: list[dict], edges: list[dict]) -> list[str]:
    """Kahn's algorithm. Raises DAGError on cycle."""
    ids = [n["id"] for n in nodes if "id" in n]
    id_set = set(ids)
    indeg = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges or []:
        a, b = e.get("from"), e.get("to")
        if a not in id_set or b not in id_set:
            continue
        adj[a].append(b)
        indeg[b] = indeg.get(b, 0) + 1
    order: list[str] = []
    ready = [i for i in ids if indeg[i] == 0]
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in adj.get(n, []):
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    if len(order) != len(ids):
        raise DAGError("cycle detected in pipeline DAG")
    return order


def _inbound_rows(node_id: str, edges: list[dict], outputs: dict[str, Rows]) -> Rows:
    incoming = [e.get("from") for e in (edges or []) if e.get("to") == node_id]
    rows: Rows = []
    for src in incoming:
        rows.extend(outputs.get(src, []))
    return rows


def execute_dag(pipeline_json: dict | None) -> dict:
    """Returns per-node status + row counts, matching Frontend's expected shape."""
    if not isinstance(pipeline_json, dict):
        return {"status": "validation_error", "reason": "pipeline_json missing"}
    nodes = pipeline_json.get("nodes") or []
    edges = pipeline_json.get("edges") or []
    if not isinstance(nodes, list) or not nodes:
        return {"status": "validation_error", "reason": "no nodes"}

    order = _topo_sort(nodes, edges)
    by_id = {n["id"]: n for n in nodes if "id" in n}
    outputs: dict[str, Rows] = {}
    node_results: dict[str, dict[str, Any]] = {}

    for nid in order:
        n = by_id[nid]
        block_name = n.get("block") or n.get("type")
        params = n.get("params") or {}
        fn = resolve(block_name)
        if not fn:
            node_results[nid] = {
                "status": "error",
                "error": f"unknown block: {block_name}",
                "available": sorted(REGISTRY.keys()),
            }
            continue
        upstream = _inbound_rows(nid, edges, outputs)
        t0 = time.monotonic()
        try:
            out = fn(params, upstream)
            outputs[nid] = out if isinstance(out, list) else []
            node_results[nid] = {
                "status": "success",
                "rows": len(outputs[nid]),
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "block": block_name,
            }
        except Exception as ex:  # noqa: BLE001
            log.exception("block %s failed", block_name)
            node_results[nid] = {
                "status": "error",
                "error": str(ex)[:300],
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "block": block_name,
            }

    terminal_ids = [nid for nid in order if not any(
        e.get("from") == nid for e in (edges or []))]
    preview: Rows = []
    for tid in terminal_ids:
        preview.extend(outputs.get(tid, []))

    has_error = any(r.get("status") == "error" for r in node_results.values())
    return {
        "status": "error" if has_error else "success",
        "node_results": node_results,
        "preview": preview[:100],  # cap for transport
        "terminal_nodes": terminal_ids,
    }
