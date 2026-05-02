from __future__ import annotations

import logging
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routers import agents, interrupt, output, patch, session, settings
from core.screen_manager import screen_manager
from core.ssh_pool import ExecutionMode, ssh_pool
from startup_recovery import run_startup_recovery

logger = logging.getLogger(__name__)


try:
    from database import init_db
except Exception:
    from app.db.database import Base, engine

    def init_db():
        Base.metadata.create_all(bind=engine)


try:
    from knowledge.chroma_manager import start_write_worker
except Exception:

    async def start_write_worker():
        return None


try:
    from routes import scheduler_routes
except Exception:
    scheduler_routes = None


try:
    from scheduler import scheduler, start_scheduler
except Exception:

    class _NoopScheduler:
        running = False

        def shutdown(self):
            return None

    scheduler = _NoopScheduler()

    def start_scheduler(_preset: str):
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    await ssh_pool.start()
    await start_write_worker()

    schedule_preset = os.getenv("SEED_SCHEDULE", "every_sunday_night")
    start_scheduler(schedule_preset)

    try:
        await run_startup_recovery()
    except Exception as exc:
        logger.warning("[PatchWise] Startup recovery failed: %s", exc)

    if scheduler_routes and not any(route.path.startswith("/api/scheduler") for route in app.routes):
        app.include_router(scheduler_routes.router)

    logger.info("[PatchWise] All services started - ready for concurrent users")
    yield
    await ssh_pool.stop()
    if scheduler.running:
        scheduler.shutdown()
    logger.info("[PatchWise] Shutdown complete")


app = FastAPI(title="PatchWise API", version="1.0.0", lifespan=lifespan)

# Legacy routes
app.include_router(session.router)
app.include_router(patch.router)
app.include_router(agents.router)
app.include_router(interrupt.router)
app.include_router(output.router)
app.include_router(settings.router)

# Namespaced /api routes for unified nginx reverse-proxy flow
app.include_router(session.router, prefix="/api")
app.include_router(patch.router, prefix="/api")
app.include_router(interrupt.router, prefix="/api")
app.include_router(output.router, prefix="/api")
app.include_router(settings.router, prefix="/api")

# New API namespace (inject-based extensions) is optional for backward compatibility.
try:
    from api.session_routes import router as session_routes

    app.include_router(session_routes)
except Exception:
    pass

try:
    from api.submission_routes import router as submission_routes

    app.include_router(submission_routes)
except Exception:
    pass

try:
    from api.fetch_lore import router as lore_router

    app.include_router(lore_router)
except Exception:
    pass

try:
    from api.websocket import websocket_router

    app.include_router(websocket_router)
except Exception:
    pass

try:
    from api.inject21_routes import router as inject21_router

    app.include_router(inject21_router)
except Exception:
    pass

# Inject-specific patch upload endpoint package.
try:
    from routers.patch_input import router as patch_input_router

    app.include_router(patch_input_router)
except Exception:
    pass

try:
    from routers.history import router as history_router

    app.include_router(history_router)
except Exception:
    pass

try:
    from api.routes import router as advanced_router

    app.include_router(advanced_router)
except Exception:
    pass

try:
    from api.knowledge_routes import router as knowledge_router

    app.include_router(knowledge_router)
except Exception:
    pass

# Inject 14 routes.
try:
    from api.collab_routes import router as collab_router
    from api.rebase_routes import router as rebase_router
    from api.secrets_routes import router as secrets_router

    app.include_router(rebase_router)
    app.include_router(collab_router)
    app.include_router(secrets_router)
except Exception:
    pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "patchwise-backend"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "healthy", "service": "patchwise-backend"}


@app.get("/api/dev-compute/health")
async def dev_compute_health() -> dict:
    connected = ssh_pool.is_connected()
    mode = ssh_pool.mode.value
    status = "connected" if connected else "reconnecting"
    if mode == ExecutionMode.LOCAL_DOCKER.value:
        status = "fallback"
    screens = []
    if connected:
        try:
            screens = await asyncio.wait_for(screen_manager.list_screens(), timeout=3)
        except Exception:
            screens = []
    return {
        "status": status,
        "ssh_connected": connected,
        "mode": mode,
        "host": ssh_pool.host,
        "kernel_path": ssh_pool.kernel_path,
        "chanakya_screen": any("pw_chanakya_" in s for s in screens),
        "aryabhata_screen": any("pw_aryabhata_" in s for s in screens),
    }


@app.get("/api/dev-compute/screens")
async def dev_compute_screens() -> dict:
    if not ssh_pool.is_connected():
        return {"screens": []}
    try:
        screens = await asyncio.wait_for(screen_manager.list_screens(), timeout=3)
    except Exception:
        screens = []
    return {"screens": screens}


@app.post("/api/dev-compute/reconnect")
async def force_reconnect() -> dict:
    try:
        await ssh_pool._connect()
        await ssh_pool._restore_screen_sessions()
        return {"status": "reconnected", "mode": ssh_pool.mode.value}
    except Exception as exc:
        return {"status": "failed", "error": str(exc), "mode": ssh_pool.mode.value}
