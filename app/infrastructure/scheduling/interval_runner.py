"""In-process interval runner (infrastructure layer).

Runs one callable every N seconds on a daemon thread — used to publish
scheduled blog posts. Deliberately tiny instead of a scheduler dependency: one
job, fixed interval, and the job itself is safe to run concurrently or twice
(it claims rows with SKIP LOCKED), so missed or overlapping ticks are harmless.

If the host sleeps when idle, this thread sleeps too; the external cron hitting
POST /api/v1/internal/blogs/publish-due is the safety net.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger("app.scheduler")


class IntervalRunner:
    def __init__(self, name: str, interval_seconds: float, job: Callable[[], None]) -> None:
        self._name = name
        self._interval = interval_seconds
        self._job = job
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name=self._name, daemon=True)
        self._thread.start()
        logger.info("%s started (every %ss)", self._name, self._interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self._job()
            except Exception:  # keep ticking; one bad run must not kill the loop
                logger.exception("%s run failed", self._name)
