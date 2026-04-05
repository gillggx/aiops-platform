# AIOps Platform

An AI-powered factory operations platform for automated process monitoring, anomaly detection, and diagnostic analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  aiops-app (Next.js 15)                                 │
│  Admin UI · AlarmCenter · Agent Chat · Skill Designer   │
└──────────────────┬──────────────────────────────────────┘
                   │ REST / SSE
┌──────────────────▼──────────────────────────────────────┐
│  fastapi_backend_service (FastAPI)                       │
│  Auto-Patrol · Diagnostic Rules · MCP · Agent · Alarms  │
└──────────┬─────────────────────────────┬────────────────┘
           │ HTTP                         │ HTTP
┌──────────▼──────────┐     ┌────────────▼───────────────┐
│  OntologySimulator   │     │  LLM (Claude / Ollama)     │
│  /api/v1/events      │     │  Skill generation · Agent  │
│  /api/v1/context/... │     └────────────────────────────┘
└─────────────────────┘
```

## Core Features

| Feature | Description |
|---|---|
| **Auto-Patrol** | Scheduled/event-driven monitoring rules with LLM-generated Python logic |
| **Alarm Center** | Two-layer alarm view: Auto-Patrol trigger reason + Diagnostic Rule findings |
| **Diagnostic Rules** | Deep-dive analysis triggered by alarms; two-phase AI generation with live console |
| **MCP Builder** | Visual data pipeline builder — system MCPs connect to OntologySimulator APIs |
| **Agent** | Conversational AI for factory data analysis using registered MCPs as tools |
| **Skill Designer** | AI-powered skill builder for custom monitoring logic |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- An Anthropic API key **or** a running Ollama instance

---

### Step 1 — Clone the repo

```bash
git clone https://github.com/gillggx/aiops-platform.git
cd aiops-platform
```

Everything below assumes you are in this `aiops-platform/` directory.

---

### Step 2 — Backend

**Prerequisite — PostgreSQL + pgvector** (macOS via Homebrew):

```bash
brew install postgresql@17 pgvector
brew services start postgresql@17
createdb aiops
psql aiops -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Backend setup:

```bash
cd fastapi_backend_service
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create your `.env` file:

```bash
cp ../.env.example .env
```

Open `.env` and set at minimum:

```env
DATABASE_URL="postgresql+asyncpg://<user>@localhost:5432/aiops"
ANTHROPIC_API_KEY=sk-ant-...          # or configure OLLAMA_* below
SECRET_KEY=<run: openssl rand -hex 32>
INTERNAL_API_TOKEN=any-shared-secret
```

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

**Verify:** open [http://localhost:8000/docs](http://localhost:8000/docs) — you should see the Swagger UI.

> First startup auto-creates all tables via SQLAlchemy `create_all()` and seeds default users, system MCPs, and event types — no `alembic upgrade` needed for a fresh DB.
>
> Default login: **admin / admin**

**Migrating from SQLite?** If you have an existing `dev.db` to transfer:

```bash
# 1. Export SQLite → JSONL dumps
../.venv/bin/python scripts/migration/export_sqlite.py

# 2. Build empty Postgres schema
DATABASE_URL="postgresql+asyncpg://<user>@localhost:5432/aiops" \
    ../.venv/bin/python -c "import asyncio, main; from app.database import init_db; asyncio.run(init_db())"

# 3. Import data
DATABASE_URL="postgresql+asyncpg://<user>@localhost:5432/aiops" \
    ../.venv/bin/python scripts/migration/import_postgres.py

# 4. Stamp alembic head
PYTHONPATH="$PWD" DATABASE_URL="postgresql+asyncpg://<user>@localhost:5432/aiops" \
    ../.venv/bin/alembic stamp head
```

Scripts handle FK cycles (skill ↔ auto_patrol) and legacy SQLite quirks (user_id=0 system memories).

---

### Step 3 — Frontend

Open a new terminal tab, from the repo root:

```bash
cd aiops-app
npm install
```

Create your `.env.local` file:

```bash
cat > .env.local << 'EOF'
FASTAPI_BASE_URL=http://localhost:8000
INTERNAL_API_TOKEN=any-shared-secret
NEXT_PUBLIC_APP_TITLE=AIOps Platform
EOF
```

> `INTERNAL_API_TOKEN` must match the value you set in the backend `.env`.

Start the frontend:

```bash
npm run dev
```

**Verify:** open [http://localhost:3000](http://localhost:3000) and log in with **admin / admin**.

---

### Step 4 — OntologySimulator (optional — factory demo data)

Open a new terminal tab, from the repo root:

```bash
cd ontology_simulator/frontend
npm install && npm run dev
```

**Verify:** open [http://localhost:8012](http://localhost:8012).

Then in the AIOps UI go to **Admin → System MCPs** and confirm `get_process_context` and `get_process_history` point to `http://localhost:8012`.

---

### Step 5 — Docker (alternative to steps 2–4)

If you prefer to run everything in containers:

```bash
cp .env.example .env   # then edit .env as in Step 2
docker compose up
```

| Service | URL |
|---|---|
| Backend | http://localhost:8000 |
| Frontend | http://localhost:3000 |
| Simulator | http://localhost:8012 |

---

## Environment Variables

Full list in [`.env.example`](.env.example). Key variables:

| Variable | Description |
|---|---|
| `DATABASE_URL` | SQLite (default, dev) or PostgreSQL (prod) |
| `SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `LLM_PROVIDER` | `anthropic` or `ollama` |
| `ANTHROPIC_API_KEY` | Required when `LLM_PROVIDER=anthropic` |
| `OLLAMA_BASE_URL` | Required when `LLM_PROVIDER=ollama` (e.g. `http://localhost:11434/v1`) |
| `OLLAMA_MODEL` | Ollama model name (e.g. `qwen3:8b`) |
| `ONTOLOGY_SIM_URL` | OntologySimulator base URL (default: `http://localhost:8012`) |
| `INTERNAL_API_TOKEN` | Shared token between Next.js proxy and FastAPI |

---

## Project Structure

```
aiops-platform/
├── fastapi_backend_service/    # FastAPI backend
│   ├── app/
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── repositories/       # DB access layer
│   │   ├── routers/            # FastAPI route handlers
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   └── services/           # Business logic
│   ├── main.py                 # App entry point + startup seeding
│   └── requirements.txt
├── aiops-app/                  # Main frontend (Next.js 15)
│   └── src/app/
│       ├── admin/              # Admin pages (skills, patrols, MCPs, alarms)
│       ├── api/admin/          # Next.js API routes (proxy to FastAPI)
│       └── operations/         # AlarmCenter, Agent
├── ontology_simulator/         # Factory process simulator (data source)
│   └── frontend/               # Simulator UI (Next.js)
└── docker-compose.yml
```

## Tech Stack

**Backend** — FastAPI 0.115 · SQLAlchemy 2.0 (async) · SQLite / PostgreSQL · Alembic · Claude / Ollama

**Frontend** — Next.js 15 · React 19 · SSE streaming for AI generation console

## API Docs

With the backend running: [http://localhost:8000/docs](http://localhost:8000/docs)
