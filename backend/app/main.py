from fastapi import FastAPI

from app.routers import session, patch, agents, interrupt, output

app = FastAPI(title="PatchWise API", version="1.0.0")

app.include_router(session.router)
app.include_router(patch.router)
app.include_router(agents.router)
app.include_router(interrupt.router)
app.include_router(output.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "patchwise-backend"}
