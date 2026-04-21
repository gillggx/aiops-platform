# Phase 5d — Playwright Readiness Note

## TL;DR

Existing Playwright specs in [aiops-app/e2e/](../../aiops-app/e2e/):

- `smoke.spec.ts`          — basic navigation
- `agent-panel.spec.ts`    — Copilot chat
- `pipeline-builder.spec.ts` — Pipeline Builder Glass Box
- `data-explorer.spec.ts`  — ad-hoc pipeline preview
- `agent-v3-benchmark.spec.ts` — agent perf check

They run against whatever `FASTAPI_BASE_URL` points at, so switching to Java is
a one-line env change. **But** feature parity is not 1:1 yet — see the table.

## Compatibility Matrix (Java API only, no Python sidecar smarts)

| Spec | Hits | Java CRUD ready? | Blocked by | Expected result |
|---|---|:---:|---|---|
| smoke.spec.ts | `/api/v1/health`, page nav | ✅ | — | should pass |
| agent-panel.spec.ts | `/api/v1/agent/chat` SSE | ⚠️ | LLM stub only (5b) | flow passes, reply is stub text |
| pipeline-builder.spec.ts | `/api/v1/pipelines` + `/agent/build` SSE | ✅ + ⚠️ | Glass Box scaffold emits placeholder event (5b) | structural assertions pass, semantic assertions may fail |
| data-explorer.spec.ts | `/api/v1/agent/pipeline/execute` | ⚠️ | DAG walker only supports 6 block types (5c) | passes for pipelines using supported blocks; fails for advanced blocks |
| agent-v3-benchmark.spec.ts | throughput of chat | ⚠️ | stub LLM is synchronous echo, throughput numbers not representative | numbers will look great but aren't meaningful |

## Running against Java shadow

```bash
cd aiops-app

# 1. Start all three locally:
#    - Java API on :8002
#    - Python sidecar on :8050
#    - Next.js dev on :8000
#
#    (see scripts/perf-smoke.sh for a ready-made live boot recipe.)
#    Ensure FASTAPI_BASE_URL in .env.local points at http://localhost:8002

# 2. Run the subset we know passes cleanly:
npx playwright test e2e/smoke.spec.ts

# 3. Run the Agent / Builder specs but expect "stub reply" assertions to
#    fail until Phase 6+ wires the real LLM:
npx playwright test e2e/agent-panel.spec.ts
```

## What Phase 6 delivers on top of this

- Java + Python sidecar deploy artifacts and systemd units (Java runs in
  shadow mode on :8002 at first; Frontend continues to hit old Python :8001
  until we flip `FASTAPI_BASE_URL` in `.env.local` and restart Next.js).
- `scripts/perf-smoke.sh` to run read-heavy benchmark before cutover.
- Rollback script.

## Non-Goals (deferred to Phase 7)

- Full feature-parity pipeline executor (pandas/scipy/sklearn blocks).
- Real LLM provider wiring (OpenAI / Anthropic / Bedrock).
- Real Mongo event poller + NATS subscriber bodies.

These all land in the already-carved slots (`agent_orchestrator/llm.py`,
`executor/block_runtime.py`, `background/*`) so porting is one PR per surface.
