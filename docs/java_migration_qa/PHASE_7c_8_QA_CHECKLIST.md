# Phase 7c + 8 — QA Checklist

- **Owner**: Claude (tech lead), user (reviewer)
- **Pre-condition**: Frontend currently on old Python :8001 (rolled back from failed cutover)
- **Success criteria**: Frontend lives on Java :8002, alarm generation uses new Pipeline engine, user experiences zero regression
- **Rollback SLO**: < 30 s at any step

---

## Phase 7c — Activate migrated pipelines (still on old Python runtime)

### 7c-1. Pre-flight: pipeline ↔ skill parity diff

> Goal: confirm each `[migrated] *` pipeline actually **replicates** the behaviour of the source Skill before we wire it to production. No activation if any pipeline diverges.

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 7c-1.1 | Enumerate all `pb_pipelines` with `name LIKE '[migrated] %'` | 10 rows (matches current count) | list recorded |
| 7c-1.2 | For each migrated pipeline, resolve its **source Skill** (via name stripped of `[migrated] ` prefix OR explicit `parent_id`) | 1:1 mapping found | no unmatched pipelines |
| 7c-1.3 | For each pair, diff: `pipeline_json.nodes[*].block+params` vs `skill.steps_mapping[*].python_code` — same data loaders, same filters, same thresholds, same output columns | semantic equivalence | human sign-off per pair |
| 7c-1.4 | For each pair, diff: `pipeline.description` / `auto_doc` vs `skill.description` | content drift flagged | summary reviewed |
| 7c-1.5 | For each pair, dry-run both on same event payload (pick 1 OOC event from recent `generated_events`) — compare emitted alarm severity/title/summary | identical conclusion | spot-check 3 pipelines minimum |
| 7c-1.6 | Write parity report (`docs/java_migration_qa/PIPELINE_PARITY_DIFF.md`) | file present, each pair green or documented | commit |

**Gate**: all 1.6 rows green → proceed to 7c-2. Any red → fix pipeline_json first.

### 7c-2. Activation (still old Python runtime)

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 7c-2.1 | For each migrated pipeline paired with an auto-patrol, `UPDATE pb_pipelines SET status='active'` | status flipped | psql verify |
| 7c-2.2 | `UPDATE auto_patrols SET pipeline_id=<X>` for the 5 patrols that have a matching pipeline | 5 rows updated, `skill_id` retained as fallback | psql verify |
| 7c-2.3 | For event-triggered patrols, populate `pipeline_auto_check_triggers(pipeline_id, event_type)` | rows inserted | psql verify |
| 7c-2.4 | Old Python's `auto_patrol_service.py` prefers `pipeline_id` over `skill_id` when both set (confirm behaviour by reading code OR adding a flag) | pipeline path taken | code review or 1 live trace |
| 7c-2.5 | Restart `fastapi-backend.service` to pick up any schema caches | restart clean | `systemctl is-active` |

### 7c-3. Runtime validation (comparison window)

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 7c-3.1 | Watch `alarms` table for 30 min — new rows appear | new alarms still generated | `SELECT COUNT(*) FROM alarms WHERE created_at > NOW() - interval '30 min'` > 0 |
| 7c-3.2 | Cross-check: for each new alarm, inspect `execution_logs.llm_readable_data` JSON — it should reference pipeline execution, NOT skill steps_mapping | pipeline signature present | sample 5 alarms |
| 7c-3.3 | Alarm **title / severity / summary** drift check — compare 5 new alarms against 5 historical (pre-cutover) alarms with same trigger | no meaningful drift | manual review |
| 7c-3.4 | Diagnostic-rule chain (`triggered_by='alarm:XXX'`) still fires | >0 diagnostic runs | `SELECT COUNT(*) FROM execution_logs WHERE triggered_by LIKE 'alarm:%' AND started_at > NOW() - interval '30 min'` |
| 7c-3.5 | No new 500 errors in `journalctl -u fastapi-backend --since '30 min ago'` | clean logs | `grep -c ERROR` = 0 (or pre-existing only) |

### 7c-4. Rollback plan (7c)

- `UPDATE auto_patrols SET pipeline_id=NULL` — 1 SQL, alarms return to Skill engine within minutes
- `UPDATE pb_pipelines SET status='draft' WHERE status='active' AND name LIKE '[migrated]%'` — safe to leave as active, just unused

---

## Phase 8 — Frontend cutover to Java :8002

### 8-1. Parity probe (exhaustive, automated)

> Goal: for every `/api/*` route the Frontend proxies, prove Java returns a response **shape-compatible** with Python's response. Run BEFORE any cutover attempt.

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 8-1.1 | Enumerate every `aiops-app/src/app/api/**/route.ts` — list upstream path, method, body shape | 40+ routes catalogued | file `docs/java_migration_qa/FRONTEND_API_AUDIT.md` |
| 8-1.2 | Write `scripts/parity-probe.sh` — for each route, call both `:8001` and `:8002` with the same admin JWT, record status code + response shape | script present | committed |
| 8-1.3 | Run probe; classify each route into one of: `identical`, `envelope-diff`, `path-diff`, `auth-diff`, `404-java` | bucket counts recorded | report in `FRONTEND_API_AUDIT.md` |

**Gate**: no route stays in `404-java` or `auth-diff` after shim work.

### 8-2. Java compat shim (fix every non-identical bucket)

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 8-2.1 | For every `envelope-diff`, add a Java `@GetMapping("/legacy/xxx")` that returns direct-array shape, OR change Frontend proxy to unwrap `data.items` (prefer Java-side change so Frontend stays untouched) | shim merged | probe re-run shows identical |
| 8-2.2 | For every `path-diff` (e.g. Python `/api/v1/admin/alarms`, Java `/api/v1/alarms`), add Java path alias or update Frontend route | resolved | probe re-run shows identical |
| 8-2.3 | For every `auth-diff`: Java `InternalSecurityFilter` (NEW) accepts both forms of token: (a) JWT signed by our secret, (b) shared-secret string matching `INTERNAL_API_TOKEN` env. Frontend's long-lived shared-secret token is now accepted. | dual-auth filter present | probe re-run shows identical |
| 8-2.4 | For 404 Java routes (endpoints not yet ported — e.g. `/api/v1/admin/auto-patrols/[id]/try-run`), Java returns `502 sidecar_fallback` or direct-proxies to old Python | fallback registered | probe re-run green |
| 8-2.5 | Re-run full probe — every route in `identical` bucket | 100% identical | probe artifact committed |

### 8-3. Page-by-page manual smoke (pre-cutover on Java directly)

> Goal: drive Java directly via a browser session pointed at :8002, exercise each main page, before flipping Frontend.

| Page | Endpoint calls | Expected |
|---|---|---|
| 機台總覽 (works already) | `/api/ontology/*` (ontology-simulator unchanged) | ✅ |
| Alarm Center | `/api/admin/alarms`, `/api/admin/alarms/[id]/acknowledge` | list + detail + ack |
| 戰況總結 | `/api/agent/briefing` | LLM summary visible |
| Skill 管理 | `/api/admin/skills`, `/api/admin/my-skills` | list + draft + try-run |
| Pipeline Builder | `/api/pipeline-builder/*` (20+ routes) | list + create + validate + execute + publish |
| Data Explorer | `/api/pipeline-builder/preview`, `/execute` | ad-hoc runs work |
| Auto-Patrol Center | `/api/admin/auto-patrols` | list + edit + trigger |
| AI Agent (chat) | `/api/agent/chat` (SSE) | Claude responds with tokens |
| AI Agent (build) | `/api/agent/build*` | Glass Box pipeline emitted |
| Admin - Monitor | `/api/admin/monitor` | counts visible |
| Admin - Rules / Events | `/api/admin/rules`, `/api/admin/event-types/*` | CRUD works |

### 8-4. Cutover + 1-hour watch

| # | Check | Expected | Pass criteria |
|---|---|---|---|
| 8-4.1 | Backup `.env.local` → `.env.local.pre-java-cutover` (idempotent) | file saved | ls |
| 8-4.2 | Flip `FASTAPI_BASE_URL=http://localhost:8002`, restart `aiops-app.service` | active | `systemctl is-active` |
| 8-4.3 | 30-min live-traffic watch — no UI page hits a red error, `journalctl -u aiops-java-api` no new WARN/ERROR | clean | logs tail review |
| 8-4.4 | `audit_logs` populating with real users | rows w/ username | psql |
| 8-4.5 | Alarm engine still firing (phase 7c pipelines) | new rows in `alarms` | psql |

### 8-5. Rollback plan (8)

```bash
sudo cp /opt/aiops/aiops-app/.env.local.pre-java-cutover /opt/aiops/aiops-app/.env.local
sudo systemctl restart aiops-app.service
# Frontend back on :8001 in < 10 s
```

---

## Test totals target

| Layer | Current | After 7c+8 |
|---|---|---|
| Java unit + integration | 34/0 | ≥ 40/0 (new envelope shim tests) |
| Python sidecar unit | 15/0 | 15/0 (no sidecar changes this phase) |
| Parity probe | n/a | 100 % identical on every Frontend /api/* route |
| Live EC2 smoke | rollback | 11 pages × HTTP 200 |

## Non-goals (push to Phase 9+)

- Porting `agent_orchestrator_v2` / `agent_builder` / `pipeline_executor` into sidecar (stays on fallback)
- Dropping `fastapi-backend.service` (still needed as fallback target)
- Flyway schema ownership (Python's Alembic still canonical for 7c/8)

---

## Sign-off

- [ ] 7c-1 parity diff report approved
- [ ] 7c runtime validation clean for 30 min
- [ ] 8-1 probe 100 % identical
- [ ] 8-3 every main page smoke green
- [ ] 8-4 live-traffic watch clean for 1 h
- [ ] No new ERROR in any of 5 journalctl streams

> **請確認這份 QA Checklist 是否符合預期？若確認無誤，請回覆「開始開發」。**
> 開始後我會依序：parity diff → 7c activation → 7c validation → parity probe → 8 shim → 8 cutover → post-watch，中間遇到 checklist 任何一項紅燈立即暫停報告。
