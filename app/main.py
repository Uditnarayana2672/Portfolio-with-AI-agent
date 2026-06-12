"""FastAPI application entry point — the outermost composition root.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API browser.

Architecture: see ARCHITECTURE.md (Onion Architecture). This module only wires
the HTTP edge — routers, CORS, health check — and delegates everything else
inward through app/api/v1.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.infrastructure.config import settings

logger = logging.getLogger("app")

ALLOWED_ORIGINS = [
    "http://localhost:5173",   # Vite default
    "http://localhost:3000",   # other common React dev port
]

app = FastAPI(
    title="Portfolio API",
    debug=settings.DEBUG,
)

# Allow the React+Vite dev server (and later, the production frontend) to
# call the API from a different origin. Tighten this list before launch.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Convert any unhandled error into a JSON 500 that still carries CORS
    headers.

    Without this, an unhandled exception is turned into a 500 by Starlette's
    outermost ServerErrorMiddleware — which runs *outside* CORSMiddleware, so the
    response lacks ``Access-Control-Allow-Origin`` and the browser reports a bare
    "Network Error" instead of the real failure. Handling it here keeps the
    response inside the CORS scope and gives the frontend a readable message.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    origin = request.headers.get("origin")
    headers = {}
    if origin in ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    # Never echo str(exc) to the client: raw exception text can leak SQL,
    # file paths, or credentials. The full traceback is in the server log.
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "An internal error occurred."},
        headers=headers,
    )

# All v1 routers are grouped under /api/v1 (see app/api/v1/router.py).
app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — confirms the server process is up."""
    return {"status": "ok", "env": settings.ENVIRONMENT}
