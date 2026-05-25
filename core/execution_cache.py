"""Execution Cache — SQLite-backed DAG node result cache.

Persists tool execution results keyed by (tool_name, input_digest)
with configurable TTL and LRU eviction. Thread-safe for concurrent
access from the worker pool.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.execution_cache")

_DEFAULT_DB = str(Path(".ai") / "index" / "execution_cache.db")
_DEFAULT_MAX_ENTRIES = 2000
_DEFAULT_TTL = 3600  # 1 hour


class ExecutionCache:
    """SQLite-backed result cache for DAG node executions.

    Key derivation:
        SHA256(tool_name + '|' + json.dumps(inputs, sort_keys=True))

    Entries expire after TTL seconds. LRU eviction removes oldest
    accessed entries when the cache exceeds max_entries.
    """

    def __init__(
        self,
        db_path: str = _DEFAULT_DB,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
        default_ttl_seconds: int = _DEFAULT_TTL,
    ):
        self._db_path = db_path
        self._max_entries = max_entries
        self._default_ttl = default_ttl_seconds
        self._lock = threading.Lock()
        self._init_db()

        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._evictions = 0

    # ══════════════════════════════════════════════════════════════════
    # Public API
    # ══════════════════════════════════════════════════════════════════

    def get(self, tool: str, inputs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return cached result if found and not expired."""
        key = self._make_key(tool, inputs)
        with self._lock:
            row = self._fetch(key)
            if row is None:
                self._misses += 1
                return None
            created_at_val, ttl_val, result_json = row
            age = time.time() - created_at_val
            if age > ttl_val:
                self._delete(key)
                self._misses += 1
                return None
            self._touch(key)
            self._hits += 1
            return json.loads(result_json)

    def set(
        self,
        tool: str,
        inputs: Dict[str, Any],
        result: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """Store result in cache. Evicts LRU entries if over limit."""
        key = self._make_key(tool, inputs)
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._upsert(key, ttl, result, tool_name=tool)
            self._sets += 1
            self._evict_if_needed()

    def invalidate(self, tool: Optional[str] = None) -> int:
        """Invalidate cache entries. If tool is None, clears entire cache."""
        with self._lock:
            if tool is None:
                count = self._count_all()
                self._clear_all()
                return count
            count = self._delete_by_tool(tool)
            return count

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "sets": self._sets,
                "evictions": self._evictions,
                "hit_rate": round(hit_rate, 4),
                "size": self._count_all(),
                "max_entries": self._max_entries,
                "default_ttl_seconds": self._default_ttl,
            }

    def close(self) -> None:
        pass

    # ══════════════════════════════════════════════════════════════════
    # Internal
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _make_key(tool: str, inputs: Dict[str, Any]) -> str:
        raw = tool + "|" + json.dumps(inputs, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS execution_cache (
                    key_hash TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds REAL NOT NULL,
                    last_access REAL NOT NULL,
                    result TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_tool
                ON execution_cache(tool_name)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_last_access
                ON execution_cache(last_access)
            """)

    def _fetch(self, key: str) -> Optional[Tuple[float, float, str]]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT created_at, ttl_seconds, result FROM execution_cache WHERE key_hash=?",
                (key,),
            ).fetchone()
        return row  # type: ignore

    def _touch(self, key: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "UPDATE execution_cache SET last_access=? WHERE key_hash=?",
                (time.time(), key),
            )

    def _upsert(self, key: str, ttl: int, result: Dict[str, Any], *, tool_name: str = "") -> None:
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                INSERT INTO execution_cache (key_hash, tool_name, created_at, ttl_seconds, last_access, result)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key_hash) DO UPDATE SET
                    created_at=excluded.created_at,
                    ttl_seconds=excluded.ttl_seconds,
                    last_access=excluded.last_access,
                    result=excluded.result
            """, (key, tool_name, now, float(ttl), now, json.dumps(result)))

    def _delete(self, key: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM execution_cache WHERE key_hash=?", (key,))

    def _delete_by_tool(self, tool: str) -> int:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                "SELECT key_hash FROM execution_cache WHERE tool_name=?",
                (tool,),
            ).fetchall()
            count = len(rows)
            conn.execute("DELETE FROM execution_cache WHERE tool_name=?", (tool,))
            return count

    def _count_all(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM execution_cache").fetchone()
            return row[0] if row else 0

    def _clear_all(self) -> int:
        with sqlite3.connect(self._db_path) as conn:
            count = self._count_all()
            conn.execute("DELETE FROM execution_cache")
            return count

    def _evict_if_needed(self) -> None:
        count = self._count_all()
        if count <= self._max_entries:
            return
        excess = count - self._max_entries + 10  # evict a bit extra
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("""
                DELETE FROM execution_cache WHERE key_hash IN (
                    SELECT key_hash FROM execution_cache
                    ORDER BY last_access ASC
                    LIMIT ?
                )
            """, (excess,))
            self._evictions += excess
