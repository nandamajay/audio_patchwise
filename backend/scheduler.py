"""
PatchWise Scheduler - APScheduler with SQLite job store.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from database import get_write_connection
from seeder.lkml_preseeder import run_incremental_seed

logger = logging.getLogger(__name__)

JOBSTORE_DB = os.getenv("SCHEDULER_DB_PATH") or os.getenv("SQLITE_DB_PATH") or "/workspace/data/db/scheduler.db"
Path(JOBSTORE_DB).parent.mkdir(parents=True, exist_ok=True)

jobstores = {
    "default": SQLAlchemyJobStore(url=f"sqlite:///{JOBSTORE_DB}"),
}

scheduler = AsyncIOScheduler(jobstores=jobstores)

SCHEDULE_PRESETS = {
    "every_sunday_night": CronTrigger(day_of_week="sun", hour=23, minute=0),
    "every_day_midnight": CronTrigger(hour=0, minute=0),
    "every_6_hours": IntervalTrigger(hours=6),
    "every_hour": IntervalTrigger(hours=1),
    "manual_only": None,
}


async def log_seed_run(status: str, patches_fetched: int, duration_seconds: float, error: str | None = None):
    with get_write_connection() as conn:
        conn.execute(
            """
            INSERT INTO seed_run_history (status, patches_fetched, duration_seconds, error, run_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (status, patches_fetched, duration_seconds, error, datetime.now(timezone.utc).isoformat()),
        )


async def _mark_run_started() -> int:
    now = datetime.now(timezone.utc).isoformat()
    with get_write_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO seed_run_history (status, patches_fetched, duration_seconds, error, run_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("running", 0, 0.0, None, now),
        )
        return int(cur.lastrowid)


async def _finalize_run(run_id: int, status: str, patches_fetched: int, duration_seconds: float, error: str | None = None):
    with get_write_connection() as conn:
        conn.execute(
            """
            UPDATE seed_run_history
            SET status=?, patches_fetched=?, duration_seconds=?, error=?
            WHERE id=?
            """,
            (status, patches_fetched, duration_seconds, error, run_id),
        )


async def scheduled_lkml_seed() -> dict[str, Any]:
    """Run incremental LKML seed fetching only new patches."""
    start = datetime.now(timezone.utc)
    run_id = await _mark_run_started()
    logger.info("[Scheduler] Starting scheduled LKML incremental seed...")

    try:
        result = await run_incremental_seed()
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        await _finalize_run(run_id, "success", result["patches_fetched"], duration)
        logger.info(
            "[Scheduler] Seed complete - %s new patches in %.1fs",
            result["patches_fetched"],
            duration,
        )
        return result
    except Exception as exc:
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        await _finalize_run(run_id, "error", 0, duration, str(exc))
        logger.error("[Scheduler] Seed failed: %s", exc)
        raise


def on_job_executed(event):
    logger.info("[Scheduler] Job %s executed successfully", event.job_id)


def on_job_error(event):
    logger.error("[Scheduler] Job %s raised an error: %s", event.job_id, event.exception)


def start_scheduler(schedule_preset: str = "every_sunday_night"):
    if scheduler.running:
        logger.info("[Scheduler] APScheduler already running")
        return

    scheduler.add_listener(on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(on_job_error, EVENT_JOB_ERROR)

    trigger = SCHEDULE_PRESETS.get(schedule_preset)
    if trigger:
        scheduler.add_job(
            scheduled_lkml_seed,
            trigger,
            id="lkml_weekly_seed",
            name="LKML Incremental Pre-Seeder",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )
        logger.info("[Scheduler] LKML seed scheduled: %s", schedule_preset)

    scheduler.start()
    logger.info("[Scheduler] APScheduler started")


async def update_schedule(preset: str) -> dict[str, Any]:
    """Update schedule preset dynamically from UI."""
    if scheduler.get_job("lkml_weekly_seed"):
        scheduler.remove_job("lkml_weekly_seed")

    trigger = SCHEDULE_PRESETS.get(preset)
    if trigger:
        scheduler.add_job(
            scheduled_lkml_seed,
            trigger,
            id="lkml_weekly_seed",
            name="LKML Incremental Pre-Seeder",
            replace_existing=True,
            misfire_grace_time=3600,
            coalesce=True,
        )

    _update_env("SEED_SCHEDULE", preset)
    return {"status": "updated", "preset": preset}


def _update_env(key: str, value: str):
    env_path = Path(".env")
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    updated = False
    for idx, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[idx] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines))
