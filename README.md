# AIOps Platform v2.0

半導體製造廠的 **AI Agent 平台**。製程工程師透過自然語言對話完成異常根因分析、設備診斷、自動化巡檢。

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  aiops-app  (Next.js 15 · React 19)                    Port 3000 │
│  ┌─────────────────────┐   ┌───────────────────────────────┐    │
│  │  Operations Center   │   │  Knowledge Studio (Admin)     │    │
│  │  Alarm Center        │   │  Diagnostic Rules Builder     │    │
│  │  Agent Chat (Copilot)│   │  Auto-Patrols Manager         │    │
│  │  Equipment Drill-Down│   │  MCP / Skill Management       │    │
│  │  Topology View       │   │  Agent Memory Management      │    │
│  └─────────────────────┘   └───────────────────────────────┘    │
│                  │ REST / SSE                                      │
│                  │ AIOps Report Contract (共同語言)                │
└──────────────────┬───────────────────────────────────────────────┘
                   │
         ┌─────────▼──────────────────────────────────────────────┐
         │  fastapi_backend_service  (FastAPI)            Port 8000 │
         │                                                          │
         │  ┌─ Agent ──────────────────────────────────────────┐  │
         │  │  LangGraph v2 Orchestrator                        │  │
         │  │  Context Loader (Soul Prompt + MCP Catalog + RAG) │  │
         │  │  Tool Dispatcher (22 tools)                       │  │
         │  │  Session Manager (sliding window + summarization) │  │
         │  └──────────────────────────────────────────────────┘  │
         │                                                          │
         │  ┌─ Platform ───────────────────────────────────────┐  │
         │  │  Diagnostic Rule Service (AI 2-phase generation)  │  │
         │  │  Auto-Patrol + Alarm + Cron Scheduler             │  │
         │  │  Experience Memory (pgvector + reflective lifecycle)│  │
         │  │  Sandbox Execution (numpy/pandas/scipy)           │  │
         │  └──────────────────────────────────────────────────┘  │
         │                                                          │
         │  PostgreSQL + pgvector │ Anthropic Claude │ Ollama bge-m3│
         └──────────┬───────────────────────────────────────────────┘
                    │ HTTP (MCP calls)
         ┌──────────▼──────────────────────────────────────────────┐
         │  ontology_simulator  (FastAPI + MongoDB)       Port 8012 │
         │  合成製程資料：LOT/TOOL/SPC/APC/DC/EC/FDC/OCAP/RECIPE   │
         │  NATS event bus → Auto-Patrol trigger                    │
         └─────────────────────────────────────────────────────────┘
```

**aiops-contract**（獨立 package）定義 Agent ↔ Frontend 的共用型別（AIOpsReportContract）。

---

## Projects

| Project | 說明 | Spec |
|---------|------|------|
| [fastapi_backend_service](fastapi_backend_service/) | Backend API + AI Agent | [SPEC.md](fastapi_backend_service/SPEC.md) |
| [aiops-app](aiops-app/) | Frontend (Next.js) | [SPEC.md](aiops-app/SPEC.md) |
| [ontology_simulator](ontology_simulator/) | 製程模擬器 (MongoDB) | [SPEC.md](ontology_simulator/SPEC.md) |

---

## Quick Start

### Prerequisites

- Python 3.11+, Node.js 20+
- PostgreSQL 17 + pgvector extension
- MongoDB（for ontology_simulator）
- Anthropic API key **or** Ollama

### 1. Clone

```bash
git clone https://github.com/gillggx/aiops-platform.git
cd aiops-platform
```

### 2. Backend

```bash
cd fastapi_backend_service
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # edit DATABASE_URL, ANTHROPIC_API_KEY, SECRET_KEY
uvicorn main:app --reload --port 8000
```

首次啟動自動建表 + seed（default users, system MCPs, event types）。
Default login: **admin / admin**

### 3. Frontend

```bash
cd aiops-app
npm install
cat > .env.local << 'EOF'
FASTAPI_BASE_URL=http://localhost:8000
INTERNAL_API_TOKEN=any-shared-secret
EOF
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### 4. Simulator

```bash
cd ontology_simulator
pip install -r requirements.txt
PORT=8012 uvicorn main:app --port 8012
```

### All-in-one

```bash
bash start.sh
```

---

## Core Features

| Feature | 說明 |
|---------|------|
| **AI Agent (Copilot)** | 自然語言對話，LangGraph v2 orchestrator，6-stage pipeline |
| **Diagnostic Rules** | AI 兩階段生成診斷規則（step plan → per-step code），sandbox 試跑 |
| **Auto-Patrol** | 排程 / 事件驅動巡檢，condition_met → 自動建立 Alarm |
| **MCP System** | Agent 的工具集 — System MCP（資料源）+ Custom MCP + Automation MCP |
| **Experience Memory** | pgvector 向量搜尋 + 反思式生命週期（Write → Retrieve → Feedback → Decay） |
| **Analysis → Promote** | Agent ad-hoc 分析可一鍵提升為永久 Diagnostic Rule |
| **Contract Rendering** | AIOpsReportContract — Vega-Lite 圖表 + evidence chain + suggested actions |

---

## Environment Variables

See [`.env.example`](.env.example) for full list.

| Variable | 說明 |
|----------|------|
| `DATABASE_URL` | PostgreSQL 連線字串 |
| `ANTHROPIC_API_KEY` | Claude API key |
| `OLLAMA_BASE_URL` | Ollama endpoint (bge-m3 embedding) |
| `ONTOLOGY_SIM_URL` | OntologySimulator base URL (default: localhost:8012) |
| `SECRET_KEY` | JWT signing key |
| `INTERNAL_API_TOKEN` | Next.js ↔ FastAPI shared token |

---

## Documentation

- Historical specs and PRDs: [`docs/history/`](docs/history/)
- Per-project specs: each project's `SPEC.md`
