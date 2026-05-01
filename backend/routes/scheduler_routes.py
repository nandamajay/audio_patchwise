from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter

from database import get_db_connection
from scheduler import SCHEDULE_PRESETS, scheduler, scheduled_lkml_seed, update_schedule

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


@router.get("/status")
async def get_scheduler_status():
    """Return current schedule with run history and aggregate stats."""
    job = scheduler.get_job("lkml_weekly_seed")

    conn = get_db_connection()
    history = conn.execute(
        """
        SELECT * FROM seed_run_history
        ORDER BY run_at DESC LIMIT 10
        """
    ).fetchall()
    stats = conn.execute(
        """
        SELECT
            COUNT(*) as total_runs,
            COALESCE(SUM(patches_fetched), 0) as total_patches,
            COALESCE(AVG(duration_seconds), 0) as avg_duration,
            COALESCE(SUM(CASE WHEN status='success' THEN 1 ELSE 0 END), 0) as successful_runs
        FROM seed_run_history
        """
    ).fetchone()

    return {
        "job_active": job is not None,
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "current_preset": _get_env("SEED_SCHEDULE", "every_sunday_night"),
        "available_presets": list(SCHEDULE_PRESETS.keys()),
        "run_history": [dict(row) for row in history],
        "stats": dict(stats) if stats else {},
    }


@router.post("/update")
async def update_scheduler(preset: str):
    """Update schedule preset from UI."""
    return await update_schedule(preset)


@router.post("/run-now")
async def trigger_manual_seed():
    """Trigger an immediate incremental seed run."""
    asyncio.create_task(scheduled_lkml_seed())
    return {"status": "started", "message": "Incremental seed started in background"}


@router.get("/progress")
async def get_seed_progress():
    """Poll current active seed run progress."""
    conn = get_db_connection()
    active = conn.execute(
        """
        SELECT * FROM seed_run_history
        WHERE status = 'running'
        ORDER BY run_at DESC LIMIT 1
        """
    ).fetchone()
    return {"active": active is not None, "data": dict(active) if active else None}


def _get_env(key: str, default: str = "") -> str:
    env_path = Path(".env")
    if not env_path.exists():
        return default

    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1]
    return default
