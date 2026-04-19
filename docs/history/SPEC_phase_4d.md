# Phase 4-D — Publishing Workflow (Pipeline → Published Skill)

**Status:** Draft (2026-04-18)
**Author:** Gill + Claude (Tech Lead)
**Predecessor:** Phase 4-A (skill migrator), Phase 4-B (Auto Patrol binding), Phase 4-C MVP (PIPELINE_ONLY_MODE flag)

---

## 1. Context & Objective

### 1.1 Pain Points (Today)

- Pipeline Builder 已有 25 blocks + 38 examples，可以組裝複雜的診斷邏輯，但 **Agent 目前看不到這些 pipeline**。
- `/admin/skills`（legacy code-gen path）雖已標記 deprecated，Agent 仍靠 `execute_skill` 執行舊 skill，造成雙軌並行。
- Pipeline 的 `description` 欄位是使用者手填，LLM 沒有結構化的「use-case + input/output 說明」可以 RAG。
- Lock 機制尚未落實 — pipeline publish 後仍可被任意修改，缺乏審核/版本管理。

### 1.2 Core Objective

**讓 pipeline 正式取代 legacy skill，成為 Agent 的唯一工具來源（Tool Registry）。**

三大產物：

1. **LLM Auto-Documentation** — publish 時由 LLM 自動產生 structured doc（use_case / when_to_use / inputs / outputs / example_trigger）
2. **Published Skills Registry** — 獨立 table `pb_published_skills`，pgvector embedding，Agent 走 RAG 選用
3. **Lock & Audit** — published pipeline 進入鎖定狀態，修改需走 patch/reversion 流程

### 1.3 Non-Goals

- 不做 Pipeline marketplace（跨 tenant 分享）
- 不改 Pipeline Builder 現有 UI 的 node/edge 操作
- 不重寫 orchestrator_v2 — 只加 `search_published_skills` / `invoke_published_skill` 兩個 tool

---

## 2. Architecture & Design

### 2.1 Five-Step Publishing Workflow

```
┌─────────────────────────────────────────────────────────────────────┐
│  Pipeline Builder (existing)                                         │
│  ──────────────────────────                                          │
│  Step 1: Build & Validate                                            │
│    - User assembles DAG, runs preview, verifies triggered+evidence   │
│    - Status: draft → pi_run (promote existing)                       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ User clicks "Publish" (pi_run only)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 2: LLM Auto-Documentation                                      │
│  ───────────────────────────────                                     │
│  Backend POST /pipelines/{id}/publish/draft-doc                      │
│    → calls LLM (claude-opus-4-7 structured output) with:            │
│      - pipeline_json (nodes, edges, params)                          │
│      - inputs schema + user description                              │
│      - latest preview run (sample outputs)                           │
│    → returns DraftDoc:                                               │
│      {                                                               │
│        use_case: str,                                                │
│        when_to_use: str[],       # triggering conditions            │
│        inputs: [{name, type, description, example}],                 │
│        outputs: {                                                    │
│          triggered_meaning: str,                                     │
│          evidence_schema: str,                                       │
│          chart_summary: str | null                                   │
│        },                                                            │
│        example_invocation: {inputs: {...}},                          │
│        tags: str[]                                                   │
│      }                                                               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Draft returned to UI
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 3: Expert Audit & Lock (Review Modal)                          │
│  ──────────────────────────────────────────                          │
│  Frontend: /admin/pipeline-builder/{id}/publish                      │
│    - Show DraftDoc in editable form                                  │
│    - Side panel: pipeline preview (read-only canvas)                 │
│    - "Approve & Lock" button → POST /pipelines/{id}/publish          │
│      body: {reviewed_doc: {...}, lock: true}                        │
│    - Backend:                                                        │
│      1. Insert row into pb_published_skills                          │
│      2. Compute embedding (description + use_case) via pgvector      │
│      3. Set pipeline.status = "published"                            │
│      4. Set pipeline.locked_at = now(), locked_by = user             │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ published_skill_id returned
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 4: Skill Registry (Agent-Facing)                               │
│  ────────────────────────────────────                                │
│  orchestrator_v2 tools (new):                                        │
│    - search_published_skills(query: str, top_k: int = 5)             │
│        → pgvector cosine on embedding                                │
│        → returns [{id, name, use_case, when_to_use, inputs}]         │
│    - invoke_published_skill(skill_id: int, inputs: dict)             │
│        → resolves → pipeline_id                                      │
│        → executor.run(pipeline_json, inputs)                         │
│        → returns unified triggered+evidence+chart                    │
│  system prompt (updated when PIPELINE_ONLY_MODE):                   │
│    - Remove execute_skill                                            │
│    - Add search_published_skills + invoke_published_skill            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ Agent uses skill in live diagnosis
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Step 5: One-Click Execution (from UI)                               │
│  ────────────────────────────────────                                │
│  /admin/pipeline-builder (list page)                                 │
│    - "▶ Run" button for published rows                               │
│    - Opens existing Run Dialog (Phase 4-B0) with declared inputs     │
│    - Same path as Agent invocation (shared executor)                 │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Model Changes

**New table — `pb_published_skills`:**

```sql
CREATE TABLE pb_published_skills (
  id               SERIAL PRIMARY KEY,
  pipeline_id      INTEGER NOT NULL REFERENCES pb_pipelines(id),
  pipeline_version INTEGER NOT NULL,          -- snapshot version
  name             TEXT NOT NULL,
  slug             TEXT UNIQUE NOT NULL,       -- stable identifier for Agent
  use_case         TEXT NOT NULL,
  when_to_use      JSONB NOT NULL,             -- str[]
  inputs_schema    JSONB NOT NULL,             -- [{name,type,description,example}]
  outputs_schema   JSONB NOT NULL,
  example_invocation JSONB,
  tags             TEXT[] DEFAULT '{}',
  embedding        vector(1536),               -- pgvector
  status           TEXT DEFAULT 'active',      -- active | retired
  published_by     TEXT,
  published_at     TIMESTAMPTZ DEFAULT now(),
  retired_at       TIMESTAMPTZ,
  UNIQUE (pipeline_id, pipeline_version)
);

CREATE INDEX ix_pb_published_skills_embedding
  ON pb_published_skills USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX ix_pb_published_skills_status ON pb_published_skills(status);
```

**Modify `pb_pipelines`:**

```sql
ALTER TABLE pb_pipelines
  ADD COLUMN IF NOT EXISTS locked_at   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS locked_by   TEXT,
  ADD COLUMN IF NOT EXISTS published_skill_id INTEGER
    REFERENCES pb_published_skills(id);
```

New status transition: `draft → pi_run → published → retired`.
`deprecated` remains for pipelines that never made it to publish.

### 2.3 API Contract

**Backend (new):**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/pipeline-builder/pipelines/{id}/publish/draft-doc` | LLM generates DraftDoc (idempotent, cacheable) |
| POST | `/api/pipeline-builder/pipelines/{id}/publish` | Reviewer approves → inserts row + locks pipeline |
| POST | `/api/pipeline-builder/published-skills/{id}/retire` | Soft retire (status='retired', kept for audit) |
| GET  | `/api/pipeline-builder/published-skills` | List for UI (filter active/retired) |
| POST | `/api/pipeline-builder/published-skills/search` | pgvector search (Agent + UI) |

**Modify existing:**

- `PUT /pipelines/{id}` — reject if `status='published'` and `locked_at IS NOT NULL`, unless payload contains `{unlock: true}` (admin only, writes audit log)
- `POST /pipelines/{id}/promote` — block `pi_run → published` transition (publish is a separate flow)

### 2.4 Agent Tools

**`search_published_skills`** (read-only, cheap):

```python
async def search_published_skills(query: str, top_k: int = 5) -> list[dict]:
    """Find relevant diagnostic skills for the current question.
    Use this before invoke_published_skill to discover what skills exist.
    """
    embedding = await embed(query)
    rows = await pb_published_skills_repo.search_by_embedding(embedding, top_k)
    return [
        {"slug": r.slug, "use_case": r.use_case, "when_to_use": r.when_to_use,
         "inputs_schema": r.inputs_schema}
        for r in rows
    ]
```

**`invoke_published_skill`** (full execution):

```python
async def invoke_published_skill(slug: str, inputs: dict) -> dict:
    """Execute a published skill with the given inputs.
    Returns unified {triggered, evidence, chart} contract.
    """
    skill = await pb_published_skills_repo.get_by_slug(slug)
    pipeline = await pb_pipelines_repo.get(skill.pipeline_id)
    # executor handles $inputs resolution (Phase 4-B0)
    return await pipeline_executor.run(pipeline.pipeline_json, inputs=inputs)
```

### 2.5 System Prompt Changes

When `PIPELINE_ONLY_MODE=true`:

```diff
- Tools: execute_skill, get_process_history, ...
+ Tools: search_published_skills, invoke_published_skill,
+        get_process_history, ...

+ ## Skill Discovery Protocol
+ When the user describes a diagnostic need:
+   1. First call search_published_skills with a natural-language query.
+   2. Review the returned skills' use_case + when_to_use.
+   3. If a skill matches, call invoke_published_skill with the required inputs.
+   4. If no skill matches, use lower-level MCPs (get_process_history etc.)
+      and consider suggesting the user create a new pipeline.
```

---

## 3. Step-by-Step Execution Plan

### Phase 4-D1 — Publishing Core (5–7 days)

1. **DB migration** — add `pb_published_skills` table + columns on `pb_pipelines`. Use `_safe_add_columns`.
2. **Repository** — `app/services/pipeline_builder/published_skills_repo.py` (CRUD + embedding search).
3. **LLM doc generator** — `app/services/pipeline_builder/doc_generator.py`
   - Prompt template reads pipeline_json + preview sample + inputs
   - Uses structured output (Pydantic schema)
   - Cost guard: reject if pipeline has >50 nodes (unlikely but defensive)
4. **Endpoints** — `draft-doc` + `publish` + `retire` in `pipeline_builder_router.py`
5. **Lock enforcement** — guard in `PUT /pipelines/{id}` + `DELETE /pipelines/{id}`
6. **UI — Publish Modal**
   - Entry point: green "Publish" button on pipeline detail page (visible when status='pi_run')
   - Modal: 2-column layout (draft form on left, pipeline preview on right)
   - "Regenerate Doc" button (re-calls LLM)
   - "Approve & Lock" submits → redirect to `/admin/published-skills/{id}`
7. **UI — Published Skills page** — `/admin/published-skills`
   - List published skills with search box (calls pgvector search)
   - Row actions: View, Retire, Run (opens Run Dialog)

### Phase 4-D2 — Agent Integration (3–4 days)

1. **Embedding service** — reuse existing (or add OpenAI text-embedding-3-small, 1536-dim)
2. **Agent tools** — `search_published_skills` + `invoke_published_skill` in `llm_call.py`
3. **`_visible_tools()` update** — when PIPELINE_ONLY_MODE: hide `execute_skill`, expose new tools
4. **System prompt patch** — add "Skill Discovery Protocol" section
5. **E2E test** — agent asks "過去一週 TOOL_A 有無 OOC pattern?" → Agent calls search → invoke → returns contract

### Phase 4-D3 — Lock & Migration (1–2 days)

1. **Lock patch flow** — admin-only `POST /pipelines/{id}/unlock` (audit logged)
2. **Version migration** — new publish = new `pipeline_version` row; old skill retains `pipeline_version` snapshot; Agent uses latest active
3. **Auto-Patrol wiring** — `auto_patrols.pipeline_id` can now also reference `published_skill_id` for audit trail

---

## 4. Edge Cases & Risks

### 4.1 LLM Doc Quality

**Risk:** LLM generates vague/wrong `use_case`, harms Agent retrieval.

**Mitigation:**
- Include 3 few-shot examples in prompt (hand-picked good docs)
- Require reviewer approval (no auto-publish)
- Allow editing every field before lock
- Track `doc_revision` counter; if >3, flag for human review

### 4.2 Embedding Drift

**Risk:** Embedding model updates or RAG quality drops as corpus grows.

**Mitigation:**
- Store model_name + dim in table metadata
- Re-embed job (`re_embed_all_published_skills`) as admin maintenance task
- Monitor search hit-rate via logs

### 4.3 Lock Bypass

**Risk:** Published skill has bug, but locked — hotfix becomes painful.

**Mitigation:**
- Unlock flow exists (admin + audit log)
- Unlock → edit → re-publish creates new `pipeline_version`
- Old version stays in registry until explicitly retired
- Agent defaults to latest active version (slug-based resolution)

### 4.4 Input Binding Drift

**Risk:** Pipeline declares `inputs: [{name: "toolId"}]` but DraftDoc says `inputs: [{name: "tool_id"}]`.

**Mitigation:**
- DraftDoc generator reads `pipeline_json.inputs` directly, doesn't let LLM rename
- LLM only writes `description` + `example` fields
- Validator on publish: `inputs_schema.name[]` must equal `pipeline_json.inputs.name[]`

### 4.5 Retired Skill Still Referenced

**Risk:** Auto-Patrol bound to skill that gets retired.

**Mitigation:**
- On retire: check `auto_patrols WHERE pipeline_id=?` — if any, return 409 Conflict with list
- Force-retire flag available; if used, patrols auto-disabled with reason logged

### 4.6 Cost Control

**Risk:** `draft-doc` calls LLM; if users spam the button, cost balloons.

**Mitigation:**
- Cache DraftDoc by `(pipeline_id, pipeline_version_hash)` — reuse until pipeline content changes
- Rate limit: max 10 draft-doc calls per pipeline per hour

### 4.7 Search Relevance

**Risk:** Agent's query is in Chinese, published skills are in mixed Chinese/English.

**Mitigation:**
- Use multilingual embedding model (text-embedding-3-small handles zh/en well)
- `use_case` field recommended to include both zh + en keywords
- Log every search query + top-k + chosen skill → offline eval

### 4.8 Concurrent Publish

**Risk:** Two reviewers click Publish simultaneously.

**Mitigation:**
- UNIQUE constraint on `(pipeline_id, pipeline_version)` — second write fails
- Frontend disables button while in-flight

---

## 5. Design Evaluation Notes

### 5.1 Why separate table (`pb_published_skills`)?

- Decouples registry from pipeline CRUD (simpler lock enforcement)
- Allows multiple published versions of same pipeline over time (audit trail)
- Embedding column only loaded when needed (pgvector extension scoped)

### 5.2 Why LLM auto-doc instead of user-written?

- Users already write short `description` — LLM expands to structured DraftDoc (use_case, when_to_use, I/O)
- Structured form → reliable RAG + consistent Agent reasoning
- Reviewer still edits anything they disagree with

### 5.3 Why slug instead of numeric id for Agent?

- Stable across versions (v1 retired, v2 active — same slug)
- Human-readable in logs ("invoke 'tool-ooc-5-of-10'" vs "invoke 42")

### 5.4 Why not delete legacy `execute_skill` in 4-D?

- Scheduled for Phase 4-E (legacy deprecation)
- 4-D runs with feature flag — gives 2-week soak period with both paths

### 5.5 Cache strategy

- DraftDoc: cache by pipeline JSON hash (invalidated on pipeline edit)
- Embedding: write-through on publish (no cache — write once per version)
- Search: no cache (pgvector is fast; query patterns are diverse)

### 5.6 Open questions for Gill

1. **Reviewer authentication** — 目前沒 login 系統，`published_by` 先用固定 "admin" or require `X-User` header?
2. **Slug generation** — auto-generate from `name` (slugify) or require manual input?
3. **Migration of 4-A skeleton pipelines** — 那 2 條 skeleton 要不要強制手工補完才能 publish?
4. **Embedding model choice** — OpenAI text-embedding-3-small（便宜 + 多語）vs local model?

---

## 6. Acceptance Criteria

- [ ] Pipeline 從 `pi_run` 可點 Publish → 走完流程 → `published` 狀態
- [ ] Published pipeline 無法直接 `PUT` 編輯（除非 unlock）
- [ ] `pb_published_skills` 表有 embedding，pgvector search 可 <100ms 回傳 top-5
- [ ] Agent with `PIPELINE_ONLY_MODE=true` 看不到 `execute_skill`，只看得到 `search_published_skills` + `invoke_published_skill`
- [ ] Agent 可以從 "TOOL_A 最近 5 次 OOC" 這種問題 → search → invoke → 回傳 contract
- [ ] UI `/admin/published-skills` 可列出、檢索、retire、run
- [ ] All existing Pipeline Builder regression tests pass
- [ ] 新增 integration test: publish → search → invoke 端到端

---

**Next action:** Await approval; on "開始開發" → begin Phase 4-D1 DB migration + repo + LLM doc generator.
