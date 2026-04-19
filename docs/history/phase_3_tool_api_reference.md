# Phase 3.2 Agent Tool API Reference

**Status:** Released 2026-04-18
**Consumer:** the Glass Box Agent (Claude Sonnet 4.6 via Anthropic tool-use).
**Source of truth:** [`app/services/agent_builder/tools.py`](../fastapi_backend_service/app/services/agent_builder/tools.py) + [`prompt.py`](../fastapi_backend_service/app/services/agent_builder/prompt.py).

This document describes the 13 tools the Agent can call while building a
pipeline. It mirrors `TOOL_DEFINITIONS` sent to the LLM — if you add/modify
tools, update this reference AND `claude_tool_defs()` (they must stay in sync).

---

## Contract

Every tool is an `async` method on `BuilderToolset`. Calls go through
`toolset.dispatch(name, args)` which:
1. Validates the tool name
2. Starts a timer
3. Calls the method with `**args`
4. Appends an `Operation` to `session.operations` (with result + elapsed_ms)
5. On `ToolError`, appends an `ErrorEvent` and re-raises

Error response shape visible to the LLM:
```json
{"error": true, "code": "<error_code>", "message": "...", "hint": "..."}
```

---

## Canvas Operations (8)

### `list_blocks(category?)`
Return the full block catalog (or just one category).

**Input:** `{ category?: "source"|"transform"|"logic"|"output"|"custom" }`
**Output:** `{ blocks: [{name, version, category, status, description, input_schema, output_schema, param_schema}], count: int }`

Agent should call this first to see what's available — zero hardcoded catalog in the system prompt.

---

### `add_node(block_name, block_version?, position?, params?)`
Add a new node. Auto-offsets position by 30px if it collides with an existing node.

**Input:** `{ block_name: str, block_version?: str = "1.0.0", position?: {x, y}, params?: dict }`
**Output:** `{ node_id: "n<N>", position: {x, y} }`

**Errors:**
- `BLOCK_NOT_FOUND` — block_name+version not in catalog

---

### `remove_node(node_id)`
Remove a node and all edges touching it.

**Input:** `{ node_id: str }`
**Output:** `{ removed_node: str, removed_edges: [edge_id, ...] }`

**Errors:** `NODE_NOT_FOUND`

---

### `connect(from_node, from_port, to_node, to_port)`
Create an edge. Port types must match (enforced via catalog port type metadata).

**Input:** `{ from_node: str, from_port: str, to_node: str, to_port: str }`
**Output:** `{ edge_id: "e<N>" }` (or `{edge_id, note: "already exists"}`)

**Errors:**
- `NODE_NOT_FOUND` — either endpoint node missing
- `PORT_NOT_FOUND` — port name not in block's schema (hint lists available ports)
- `PORT_TYPE_MISMATCH` — e.g. dataframe → dict

---

### `disconnect(edge_id)`

**Input:** `{ edge_id: str }`
**Output:** `{ removed_edge: str }`
**Errors:** `EDGE_NOT_FOUND`

---

### `set_param(node_id, key, value)`
Schema-validated. Checks that `key` is in the block's `param_schema.properties`, and if the property has an `enum`, the value must match.

**Input:** `{ node_id: str, key: str, value: any }`
**Output:** `{ node_id: str, params: {key: value, ...} }`

**Errors:**
- `NODE_NOT_FOUND`
- `PARAM_NOT_IN_SCHEMA` (hint lists allowed keys)
- `PARAM_ENUM_VIOLATION`

---

### `move_node(node_id, position)`
Reposition a node — purely cosmetic (no effect on execution).

**Input:** `{ node_id: str, position: {x, y} }`
**Output:** `{ node_id: str, position: {x, y} }`
**Errors:** `NODE_NOT_FOUND`

---

### `rename_node(node_id, label)`
Set a custom display label.

**Input:** `{ node_id: str, label: str }`
**Output:** `{ node_id: str, display_label: str }`
**Errors:** `NODE_NOT_FOUND`

---

## Introspection (3)

### `get_state()`
Full snapshot of current canvas.

**Input:** `{}`
**Output:**
```json
{
  "name": "...",
  "node_count": N,
  "edge_count": M,
  "nodes": [{id, block_id, params}, ...],
  "edges": [{id, from:{node,port}, to:{node,port}}, ...]
}
```

---

### `preview(node_id, sample_size?=50)`
Execute pipeline up to `node_id` and return that node's output summary.

Internally: truncates pipeline to ancestors of `node_id` + the target, validates the subgraph (skipping C7 endpoint rule since partial), runs executor, summarizes preview.

**Input:** `{ node_id: str, sample_size?: int = 50 }`
**Output (dataframe port):**
```json
{
  "status": "success",
  "rows": <int>,
  "preview": {
    "data": {
      "type": "dataframe",
      "columns": ["eventTime", "toolID", ...],
      "total_rows": <int>,
      "sample_rows": [{<first 5 rows truncated>}]
    }
  }
}
```

**Output (chart port):**
```json
{
  "status": "success",
  "preview": {
    "chart_spec": {
      "type": "chart_spec",
      "mark": "bar",
      "encoding": {...},
      "data_values_count": <int>
    }
  }
}
```

**On validation failure:** `{status: "validation_error", errors: [...]}`

Agent uses `preview` BEFORE setting column-type parameters to discover available columns.

---

### `validate()`
Run all 7 pipeline validation rules (see SPEC §4.2).

**Input:** `{}`
**Output:** `{ valid: bool, errors: [{rule, message, node_id?, edge_id?}, ...] }`

---

## Communication (1)

### `explain(message, highlight_nodes?)`
Write a short message to the PE's chat panel. UI highlights the referenced nodes briefly.

**Input:** `{ message: str, highlight_nodes?: [str] }`
**Output:** `{ chat_appended: true }`

Emitted as a `chat` SSE event (distinct from `operation`).

---

## Lifecycle (1)

### `finish(summary)`
Mark the task complete. **GATE:** requires `validate()` to return `{valid: true}`, else raises `FINISH_BLOCKED` and the Agent must fix errors first.

**Input:** `{ summary: str }`
**Output:** `{ status: "finished", summary: str }`

**Errors:**
- `FINISH_BLOCKED` — validator errors exist (hint includes first 3)

---

## Tool definitions for Claude tool-use API

See `claude_tool_defs()` in `prompt.py`. Each tool has a JSON-schema for its
input + a `description`. The last tool in the list carries `cache_control:
ephemeral` so all tool defs are cached together along with the system prompt.

---

## Session lifecycle

1. `POST /api/v1/agent/build` creates a session → returns `session_id`
2. Frontend opens `EventSource(GET /api/v1/agent/build/stream/{session_id})`
3. Backend orchestrator runs the tool-use loop, emitting `StreamEvent`s
4. Events: `chat` (from explain), `operation` (each tool call), `error` (tool failures), `done` (final state)
5. `POST /api/v1/agent/build/{session_id}/cancel` sets a cooperative cancel flag
6. Session cleared from registry after 5 minutes of inactivity

---

## Deterministic constraints

- `MAX_TURNS = 30` — Agent dies if it hasn't called `finish()` by then
- `MAX_SAME_TOOL_RETRY = 3` — same (tool, args) three times in a row aborts
- Prompt cache: system + tools marked `ephemeral` for 90%+ hit rate after first call
- Model: `claude-sonnet-4-6` (configurable via orchestrator param)

---

## Adding a new tool

1. Add an `async def` to `BuilderToolset` with the signature documented in this doc
2. Append a Claude tool-def in `TOOL_DEFINITIONS` (prompt.py)
3. If the tool mutates canvas, add the op case to `applyOperationToCanvas` in `useAgentStream.ts` (so live replay updates the UI)
4. Update this reference doc
5. Add a unit test in `test_agent_tools.py`

Keep the system prompt neutral — let the block `description` + tool schemas carry the semantics.
