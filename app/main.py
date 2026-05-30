"""FastAPI application entry point — the outermost composition root.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API browser.

Architecture: see ARCHITECTURE.md (Onion Architecture). This module only wires
the HTTP edge — routers, CORS, health check — and delegates everything else
inward through app/api/v1.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.infrastructure.config import settings

app = FastAPI(
    title="Portfolio API",
    debug=settings.DEBUG,
)

# Allow the React+Vite dev server (and later, the production frontend) to
# call the API from a different origin. Tighten this list before launch.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # Vite default
        "http://localhost:3000",   # other common React dev port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All v1 routers are grouped under /api/v1 (see app/api/v1/router.py).
app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — confirms the server process is up."""
    return {"status": "ok", "env": settings.ENVIRONMENT}
