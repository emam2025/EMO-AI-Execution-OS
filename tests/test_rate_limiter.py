"""Tests for RateLimiter."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.rate_limiter import RateLimiter


# ── Basic rate limiting ────────────────────────────────────────

def test_allows_first_request():
    rl = RateLimiter(max_requests=5, window_seconds=60)
    allowed, count, limit = rl.check("alice")
    assert allowed is True
    assert count == 1
    assert limit == 5


def test_allows_up_to_limit():
    rl = RateLimiter(max_requests=3, window_seconds=60)
    for i in range(3):
        allowed, count, _ = rl.check("bob")
        assert allowed is True
        assert count == i + 1


def test_blocks_after_limit():
    rl = RateLimiter(max_requests=2, window_seconds=60)
    rl.check("carol")
    rl.check("carol")
    allowed, count, limit = rl.check("carol")
    assert allowed is False
    assert count == 2  # block doesn't increment
    assert limit == 2


# ── Independent keys ──────────────────────────────────────────

def test_independent_keys():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    allowed_a, _, _ = rl.check("user_a")
    allowed_b, _, _ = rl.check("user_b")
    assert allowed_a is True
    assert allowed_b is True

    # Each at limit now
    assert rl.check("user_a")[0] is False
    assert rl.check("user_b")[0] is False


# ── Window expiry ─────────────────────────────────────────────

def test_window_expiry():
    rl = RateLimiter(max_requests=1, window_seconds=0.05)
    rl.check("dave")
    assert rl.check("dave")[0] is False
    time.sleep(0.06)
    allowed, _, _ = rl.check("dave")
    assert allowed is True


# ── Reset ──────────────────────────────────────────────────────

def test_reset():
    rl = RateLimiter(max_requests=1, window_seconds=60)
    rl.check("eve")
    assert rl.check("eve")[0] is False
    rl.reset("eve")
    allowed, _, _ = rl.check("eve")
    assert allowed is True


# ── Default params ────────────────────────────────────────────

def test_default_params():
    rl = RateLimiter()
    assert rl.max_requests == 100
    assert rl.window_seconds == 60


# ── High volume ───────────────────────────────────────────────

def test_high_volume():
    rl = RateLimiter(max_requests=1000, window_seconds=60)
    for i in range(1000):
        allowed, _, _ = rl.check("high_vol")
        assert allowed is True
    allowed, count, _ = rl.check("high_vol")
    assert allowed is False
    assert count == 1000  # block doesn't increment
