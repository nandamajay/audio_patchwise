from fastapi import FastAPI

from app.routers import agents, interrupt, output, patch, session, settings

app = FastAPI(title="PatchWise API", version="1.0.0")

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
    from api.routes import router as advanced_routes

    app.include_router(advanced_routes)
except Exception:
    pass

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
    from api.websocket import websocket_router

    app.include_router(websocket_router)
except Exception:
    pass

# Inject-specific patch upload endpoint package.
try:
    from routers.patch_input import router as patch_input_router

    app.include_router(patch_input_router)
except Exception:
    pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "patchwise-backend"}


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok", "service": "patchwise-backend"}
