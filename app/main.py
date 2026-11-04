"""FastAPI application entry point — the outermost composition root.

Run locally with:
    uvicorn app.main:app --reload

Then visit http://localhost:8000/docs for the interactive API browser.

Architecture: see ARCHITECTURE.md (Onion Architecture). This module only wires
the HTTP edge — routers, CORS, health check — and delegates everything else
inward through app/api/v1.
"""
import logging
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.dependencies.providers import run_publish_due_posts
from app.api.v1.router import api_router
from app.infrastructure.config import settings
from app.infrastructure.scheduling.interval_runner import IntervalRunner

logger = logging.getLogger("app")


def _configure_file_log() -> None:
    """Keep warnings and tracebacks in logs/api.log (rotating) so a 500 can be
    traced after the terminal has scrolled away."""
    if any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
        return  # uvicorn --reload re-imports this module
    log_dir = Path(__file__).resolve().parents[1] / "logs"
    log_dir.mkdir(exist_ok=True)
    handler = RotatingFileHandler(log_dir / "api.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setLevel(logging.WARNING)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.addHandler(logging.StreamHandler())  # still print to the terminal
    logger.setLevel(logging.INFO)
    logger.propagate = False


_configure_file_log()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start the scheduled-post publisher with the server, stop it on exit."""
    runner = None
    if settings.BLOG_SCHEDULER_ENABLED:
        runner = IntervalRunner(
            "blog-publish-due", settings.BLOG_SCHEDULER_INTERVAL_SECONDS, run_publish_due_posts
        )
        runner.start()
    yield
    if runner is not None:
        runner.stop()


app = FastAPI(
    title="Portfolio API",
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Dev: wildcard origins so any localhost port works regardless of which URL
# the browser uses. Auth is Bearer-token only (no cookies), so
# allow_credentials must stay False — the CORS spec forbids credentials with
# a wildcard origin and Starlette enforces this at startup.
# Production: set CORS_ALLOWED_ORIGINS in .env to a space-separated list of
# real frontend origins and flip allow_credentials if you add cookie auth.
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS.split(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
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
    request_id = uuid.uuid4().hex[:12]
    logger.exception("Unhandled error [%s] on %s %s", request_id, request.method, request.url.path)
    origin = request.headers.get("origin")
    headers: dict[str, str] = {"X-Request-Id": request_id}
    if origin:
        # In dev, wildcard CORS is already set; in prod, echo the origin back
        # only if it matches the configured allow-list.
        allowed = settings.CORS_ALLOWED_ORIGINS.split()
        if settings.ENVIRONMENT != "production" or origin in allowed:
            headers["Access-Control-Allow-Origin"] = origin
            headers["Vary"] = "Origin"
    # Never echo str(exc) to the client: raw exception text can leak SQL,
    # file paths, or credentials. The full traceback is in the server log.
    # request_id lets you find the traceback in logs/api.log.
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred.",
            "detail": {"error": "INTERNAL", "message": "An internal error occurred.", "request_id": request_id},
        },
        headers=headers,
    )

# All v1 routers are grouped under /api/v1 (see app/api/v1/router.py).
app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe — confirms the server process is up."""
    return {"status": "ok", "env": settings.ENVIRONMENT}
