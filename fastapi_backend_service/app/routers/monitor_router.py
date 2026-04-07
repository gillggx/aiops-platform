"""System Monitor router — /api/v1/system/monitor."""

from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db

router = APIRouter(prefix="/system", tags=["system-monitor"])


@router.get("/monitor", summary="System health & background task status")
async def get_monitor(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    settings = get_settings()
    now = datetime.now(tz=timezone.utc)

    # ── Service health checks ─────────────────────────────────
    services = {}

    # Backend (self)
    services["backend"] = {"status": "UP", "port": 8001}

    # PostgreSQL
    try:
        await db.execute(text("SELECT 1"))
        services["postgresql"] = {"status": "UP"}
    except Exception as exc:
        services["postgresql"] = {"status": "DOWN", "error": str(exc)[:100]}

    # Simulator
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.ONTOLOGY_SIM_URL}/api/v1/status")
            sim_data = resp.json() if resp.is_success else {}
            services["simulator"] = {
                "status": "UP" if resp.is_success else "DOWN",
                "port": 8012,
                "data": sim_data,
            }
    except Exception as exc:
        services["simulator"] = {"status": "DOWN", "error": str(exc)[:100]}

    # ── Background tasks ──────────────────────────────────────
    from app.services.event_poller_service import get_poller_stats
    poller = get_poller_stats()

    # Cron scheduler
    try:
        from app.services.cron_scheduler_service import get_scheduler
        sched = get_scheduler()
        jobs = []
        for job in sched.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        scheduler = {"status": "RUNNING" if sched.running else "STOPPED", "jobs": jobs}
    except Exception:
        scheduler = {"status": "UNKNOWN", "jobs": []}

    # ── DB stats ──────────────────────────────────────────────
    db_stats = {}
    for table in ["skill_definitions", "mcp_definitions", "auto_patrols", "alarms",
                   "agent_memories", "agent_experience_memory", "agent_sessions", "event_types"]:
        try:
            result = await db.execute(text(f"SELECT count(*) FROM {table}"))
            db_stats[table] = result.scalar()
        except Exception:
            db_stats[table] = -1

    return {
        "timestamp": now.isoformat(),
        "services": services,
        "background_tasks": {
            "event_poller": poller,
            "cron_scheduler": scheduler,
        },
        "db_stats": db_stats,
    }
