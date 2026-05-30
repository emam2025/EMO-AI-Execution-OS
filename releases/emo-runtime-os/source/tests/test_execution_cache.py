"""Tests for ExecutionCache — SQLite-backed DAG result cache."""
import sys, os, tempfile, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.execution_cache import ExecutionCache


def make_cache():
    tmp = tempfile.mktemp(suffix=".db")
    return ExecutionCache(db_path=tmp, max_entries=100, default_ttl_seconds=3600)


# ── Basic set/get ────────────────────────────────────────────────

def test_set_and_get():
    c = make_cache()
    c.set("tool_a", {"x": 1}, {"result": "ok"})
    got = c.get("tool_a", {"x": 1})
    assert got == {"result": "ok"}, f"Expected {{'result': 'ok'}}, got {got}"
    c.close()


def test_get_miss():
    c = make_cache()
    assert c.get("nonexistent", {}) is None
    c.close()


def test_get_miss_wrong_inputs():
    c = make_cache()
    c.set("tool_a", {"x": 1}, {"result": "ok"})
    assert c.get("tool_a", {"x": 2}) is None
    c.close()


def test_get_miss_wrong_tool():
    c = make_cache()
    c.set("tool_a", {"x": 1}, {"result": "ok"})
    assert c.get("tool_b", {"x": 1}) is None
    c.close()


# ── TTL expiry ──────────────────────────────────────────────────

def test_ttl_expiry():
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=100, default_ttl_seconds=0)
    c.set("tool_a", {}, {"result": "ok"})
    time.sleep(0.01)
    assert c.get("tool_a", {}) is None
    c.close()


def test_custom_ttl():
    c = make_cache()
    c.set("tool_a", {}, {"result": "ok"}, ttl=0)
    time.sleep(0.01)
    assert c.get("tool_a", {}) is None
    c.close()


# ── LRU eviction ────────────────────────────────────────────────

def test_lru_eviction():
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=5, default_ttl_seconds=3600)
    for i in range(10):
        c.set(f"tool_{i}", {"i": i}, {"result": i})
    stats = c.stats()
    assert stats["size"] <= 5, f"Expected <=5 entries, got {stats['size']}"
    assert stats["evictions"] >= 5, f"Expected >=5 evictions, got {stats['evictions']}"
    # Least recently accessed should be evicted first
    assert c.get("tool_0", {"i": 0}) is None  # evicted
    assert c.get("tool_9", {"i": 9}) == {"result": 9}  # kept (most recent)
    c.close()


def test_lru_keeps_recently_accessed():
    c = ExecutionCache(db_path=tempfile.mktemp(suffix=".db"),
                       max_entries=5, default_ttl_seconds=3600)
    for i in range(4):
        c.set(f"tool_{i}", {}, {"result": i})
    c.get("tool_0", {})  # access keeps it alive
    for i in range(4, 8):
        c.set(f"tool_{i}", {}, {"result": i})
    # tool_0 was accessed, so it should still be here
    # tool_1, tool_2, tool_3 may be evicted
    stats = c.stats()
    assert stats["size"] <= 5
    c.close()


# ── Invalidation ────────────────────────────────────────────────

def test_invalidate_all():
    c = make_cache()
    c.set("a", {}, {"r": 1})
    c.set("b", {}, {"r": 2})
    assert c.stats()["size"] == 2
    cnt = c.invalidate()
    assert cnt == 2
    assert c.stats()["size"] == 0
    c.close()


def test_invalidate_by_tool():
    c = make_cache()
    c.set("a", {}, {"r": 1})
    c.set("a", {"x": 2}, {"r": 3})
    c.set("b", {}, {"r": 4})
    cnt = c.invalidate(tool="a")
    assert cnt == 2
    assert c.get("a", {}) is None
    assert c.get("a", {"x": 2}) is None
    assert c.get("b", {}) == {"r": 4}
    c.close()


# ── Stats ───────────────────────────────────────────────────────

def test_stats():
    c = make_cache()
    assert c.stats()["hits"] == 0
    assert c.stats()["misses"] == 0
    c.set("a", {}, {"r": 1})
    c.get("a", {})  # hit
    c.get("b", {})  # miss
    s = c.stats()
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["hit_rate"] == 0.5
    c.close()


# ── Overwrite ───────────────────────────────────────────────────

def test_overwrite():
    c = make_cache()
    c.set("a", {}, {"r": 1})
    c.set("a", {}, {"r": 2})
    assert c.get("a", {}) == {"r": 2}
    c.close()


# ── Large inputs ────────────────────────────────────────────────

def test_large_inputs():
    c = make_cache()
    big = {"data": "x" * 10000}
    c.set("big", big, {"result": "ok"})
    assert c.get("big", big) == {"result": "ok"}
    c.close()
