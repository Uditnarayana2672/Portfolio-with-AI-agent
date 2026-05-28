"""FastAPI application entry point.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API browser.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.endpoints import users as users_endpoints
from app.core.config import settings

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

# All routers are grouped under /api/v1. Add more files here as you build them.
app.include_router(users_endpoints.router, prefix="/api/v1", tags=["users"])


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — confirms the server process is up."""
    return {"status": "ok", "env": settings.ENVIRONMENT}
