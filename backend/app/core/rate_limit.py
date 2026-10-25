"""In-memory sliding-window rate limiter.

Limitation: counts live in this process only. With several server instances each instance
counts separately, and a restart resets the counts. That is acceptable for a single-instance
deployment; a shared store (e.g. Redis) would be needed beyond that.
"""

import math
import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimitedError


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = math.ceil(hits[0] + window_seconds - now)
                raise RateLimitedError(details={"retry_after_seconds": retry_after})
            hits.append(now)
            if len(self._hits) > 10_000:
                self._prune(now, window_seconds)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def _prune(self, now: float, window_seconds: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - window_seconds]:
            del self._hits[key]


rate_limiter = RateLimiter()
