# Production Deploy Readiness — Phase 4 Pipeline Builder

**Audience:** engineer rolling out Phase 4 (Pipeline Builder + Published Skills +
5-stage lifecycle) to the production host at **43.213.71.239**.

**Precondition:** `PROD_REBUILD_REPORT.md` already passes locally — i.e. all 27
auto-migrated pipelines run preview cleanly; both skeleton rows (`DC sensor drift`
+ `Recipe consistency`) are acknowledged as stubs.

---

## 1. Scope

Production currently runs the **legacy skills-only** stack. After this deploy it
will additionally have:

- `pb_blocks` / `pb_pipelines` / `pb_pipeline_runs` / `pb_canvas_operations` / `pb_published_skills` tables
- 26 seeded blocks (source / transform / logic / output + new `block_data_view`)
- 5-stage lifecycle (draft → validating → locked → active → archived)
- Per-kind structural validators C11/C12
- Unified `/transition` endpoint + publish workflow

Legacy skills remain intact and continue running; the goal is **additive**, not
cut-over. Cut-over happens in Phase 4-F (next release).

---

## 2. Pre-flight on your laptop

```bash
cd fastapi_backend_refactored
source .venv/bin/activate

# a) full backend tests must pass
cd fastapi_backend_service
python -m pytest tests/pipeline_builder -q

# b) migrator dry-run on the prod dump must show 27/29 full
python -c "
import json
from app.services.pipeline_builder.skill_migrator import migrate_skill
skills = json.load(open('~/aiops_prod_backup/prod_skills.json'.replace('~', __import__('os').path.expanduser('~'))))
from collections import Counter
c = Counter(migrate_skill({**s, **{k: (__import__('json').dumps(s[k]) if not isinstance(s[k], str) and s[k] is not None else s[k]) for k in ('steps_mapping','input_schema','output_schema')}}).status for s in skills)
print(c)  # expect Counter({'full': 27, 'skeleton': 2})
"
```

---

## 3. Deploy Steps — on `ubuntu@43.213.71.239`

### 3.1 Backup first (always)

```bash
ssh ubuntu@43.213.71.239
sudo -u postgres pg_dump aiops_db > ~/backup_aiops_pre_phase4_$(date +%Y%m%d).sql
ls -lh ~/backup_aiops_pre_phase4_*.sql  # confirm non-empty
```

### 3.2 Pull latest code

```bash
cd ~/ai-ops-agentic-platform   # or wherever the repo lives on prod
git fetch origin
git checkout main             # or whichever branch carries the phase-4 merge
git pull --ff-only
git log -1 --oneline          # confirm the SHA matches local
```

### 3.3 Run DB migration via backend startup

`_safe_add_columns` is idempotent and uses savepoints (PR-D fix). Tables missing
from prod (`pb_blocks`, `pb_pipelines`, `pb_pipeline_runs`, `pb_canvas_operations`,
`pb_published_skills`) are created by `Base.metadata.create_all`. New columns on
existing tables (`pb_pipelines.usage_stats` etc.) are added under savepoints.

**Just restart the FastAPI backend — migration runs on lifespan startup:**

```bash
sudo systemctl restart fastapi-backend
sudo journalctl -u fastapi-backend -n 50 --no-pager | grep -iE 'migration|seeding|ready'
# look for:
#   "Pipeline Builder registry ready (26 blocks)"
#   "Startup seeding complete"
#   no ERROR lines from migration
```

If startup fails, restore from the pg_dump backup.

### 3.4 Verify schema post-migrate

```bash
sudo -u postgres psql aiops_db -c "\dt pb_*"
# expect: pb_blocks | pb_canvas_operations | pb_pipeline_runs | pb_pipelines | pb_published_skills

sudo -u postgres psql aiops_db -c "\d pb_pipelines" | grep -E 'pipeline_kind|usage_stats|locked_at'
# expect all three columns
```

### 3.5 Deploy frontend (aiops-app)

```bash
cd ~/ai-ops-agentic-platform/aiops-app
npm ci --production=false
npm run build
sudo systemctl restart aiops-app
# Test a page that exercises Phase 4 code:
curl -s http://localhost:8000/admin/pipeline-builder -o /dev/null -w "status=%{http_code}\n"
```

### 3.6 Run the prod-skills rebuild script on PROD

This converts the 29 legacy skills into 27 draft pipelines using prod's own data.
Script is **idempotent** — safe to re-run.

```bash
cd ~/ai-ops-agentic-platform/fastapi_backend_service
# Use prod's own JSON — dumped directly from local DB, not scp'd in.
sudo -u postgres psql aiops_db -t -A -c "SELECT json_agg(s) FROM skill_definitions s" > /tmp/prod_skills.json
python -m scripts.rebuild_prod_skills_locally \
    --input /tmp/prod_skills.json \
    --report /tmp/PROD_REBUILD_REPORT_actual.md
# Confirm "Totals: {'full': 27, 'skeleton': 2}" in output
cat /tmp/PROD_REBUILD_REPORT_actual.md | head -40
rm /tmp/prod_skills.json   # don't leave the dump on disk
```

### 3.7 Smoke tests

```bash
# all API health
curl -s http://localhost:8001/api/v1/pipeline-builder/blocks | python3 -c "import json,sys;print(len(json.load(sys.stdin)))"   # expect 26
curl -s http://localhost:8001/api/v1/pipeline-builder/pipelines?status=draft | python3 -c "import json,sys;print(len(json.load(sys.stdin)))"   # expect ~27

# from frontend (via nginx → next)
curl -s -I http://localhost/admin/pipeline-builder | head -3
curl -s -I http://localhost/admin/published-skills | head -3
```

---

## 4. Rollback (if Step 3.3 blows up)

```bash
sudo systemctl stop fastapi-backend aiops-app
sudo -u postgres psql -c 'DROP DATABASE aiops_db;'
sudo -u postgres psql -c 'CREATE DATABASE aiops_db OWNER aiops;'
sudo -u postgres psql aiops_db < ~/backup_aiops_pre_phase4_YYYYMMDD.sql
git checkout <previous SHA>
sudo systemctl start fastapi-backend aiops-app
```

---

## 5. Post-deploy — Manual 30-minute checklist

| # | Check | Expected |
|---|---|---|
| 1 | Open `/admin/pipeline-builder` | List shows 27 `[migrated] ...` pipelines, all `draft`, kind mix diagnostic/auto_patrol |
| 2 | Click any diagnostic pipeline → Run Full | Preview succeeds on at least one; data_view renders rows |
| 3 | Promote 1 sample pipeline draft → validating → locked | Transitions work; C11/C12 gate correctly |
| 4 | Publish the one above | Entry appears in `/admin/published-skills` |
| 5 | Agent Copilot ask "EQP-01 最近 50 次 process" | Agent calls `search_published_skills`, not `execute_skill` |
| 6 | `/admin/skills` still renders with red "frozen" banner | Legacy rules still viewable; create button gone |
| 7 | Auto-patrol running against its skill still fires | Legacy auto-patrol path unaffected |

---

## 6. Scope boundaries

**What this deploy DOES NOT do:**

- Delete any `skill_definitions` rows.
- Remove the `execute_skill` API endpoint (still served; just deprecated-logged).
- Flip `PIPELINE_ONLY_MODE` on prod — default is True in code but prod systemd
  unit should set `PIPELINE_ONLY_MODE=false` initially until we confirm pipelines
  cover every Copilot use case.
- Touch `auto_patrols.pipeline_id` binding — existing auto-patrols continue to
  use their embedded skill path. Migrating those is Phase 4-F.

**Phase 4-F (future release) will:**

- Physically remove `execute_skill` / `execute_analysis` tool definitions.
- Drop unused legacy endpoints.
- Archive `skill_definitions` rows that have a mapped `pb_pipelines` entry.
- Remove `/admin/skills` + `/admin/my-skills` from routing.

---

## 7. Schema diff reference (for sanity)

New tables after this deploy:

- `pb_blocks` (block catalog — seeded from `seed.py` on lifespan)
- `pb_pipelines` — pipeline JSON + lifecycle state
- `pb_pipeline_runs` — execution history
- `pb_canvas_operations` — Glass Box Agent operations audit
- `pb_published_skills` — Phase 4-D skill registry

New columns on existing tables:

- `auto_patrols.pipeline_id INTEGER REFERENCES pb_pipelines(id)`
- `auto_patrols.input_binding TEXT`
- `auto_patrols.skill_id DROP NOT NULL`
- `skill_definitions.pipeline_config TEXT`

No column deletions. Phase 4-F will revisit.
