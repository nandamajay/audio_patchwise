from fastapi import FastAPI

from app.routers import session, patch, agents, interrupt, output

app = FastAPI(title="PatchWise API", version="1.0.0")

app.include_router(session.router)
app.include_router(patch.router)
app.include_router(agents.router)
app.include_router(interrupt.router)
app.include_router(output.router)

# New API namespace (inject-based extensions) is optional for backward compatibility.
try:
    from api.session_routes import router as session_routes
    from api.submission_routes import router as submission_routes
    from api.websocket import websocket_router

    app.include_router(session_routes)
    app.include_router(submission_routes)
    app.include_router(websocket_router)
except Exception:
    # Keep core API available even if extension modules are not installed.
    pass


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "patchwise-backend"}
