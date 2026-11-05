"""Small in-memory rate limiter for public write endpoints.

One backend instance is all this project runs, so process memory is enough. A
restart forgets the counts, which is acceptable for spam and abuse control.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def rate_limit(name: str, limit: int, window_seconds: int) -> Callable[[Request], None]:
    def check(request: Request) -> None:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _lock:
            hits = _hits[(name, client)]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": "RATE_LIMITED", "message": "Too many requests. Please try again later."},
                )
            hits.append(now)

    return check
