"""Sliding-window rate limiter for API endpoints."""
import time
import threading
from typing import Dict, Tuple


class RateLimiter:
    """Sliding-window rate limiter keyed by user_id (or IP).

    Limits requests to *max_requests* per *window_seconds*.
    Thread-safe (RLock).  Uses a sliding-window counter stored as
    {key: [(timestamp, count), ...]}.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: Dict[str, list] = {}
        self._lock = threading.RLock()

    def _prune(self, key: str, now: float) -> None:
        """Remove expired entries for *key*."""
        window_start = now - self.window_seconds
        buckets = self._buckets.get(key)
        if buckets is None:
            return
        self._buckets[key] = [(ts, c) for ts, c in buckets if ts >= window_start]
        if not self._buckets[key]:
            del self._buckets[key]

    def _count(self, key: str, now: float) -> int:
        """Return total requests in current window for *key*."""
        self._prune(key, now)
        buckets = self._buckets.get(key)
        if buckets is None:
            return 0
        return sum(c for _, c in buckets)

    def check(self, key: str) -> Tuple[bool, int, int]:
        """Check if *key* is allowed.

        Returns:
            (allowed: bool, current_count: int, limit: int)
        """
        now = time.time()
        with self._lock:
            count = self._count(key, now)
            if count >= self.max_requests:
                return False, count, self.max_requests
            # Record this request
            if key not in self._buckets:
                self._buckets[key] = []
            if self._buckets[key] and self._buckets[key][-1][0] == now:
                # Same second — increment
                ts, c = self._buckets[key][-1]
                self._buckets[key][-1] = (ts, c + 1)
            else:
                self._buckets[key].append((now, 1))
            return True, count + 1, self.max_requests

    def reset(self, key: str) -> None:
        """Clear all tracking for *key*."""
        with self._lock:
            self._buckets.pop(key, None)
