"""
Storage Adapter — SQLite-backed storage with row-level tenant isolation.

Provides IStorage interface for uniform access, prepared for sqlite-vec upgrade.
LAW-6 (tenant isolation) enforced via separate DB files per tenant.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from releases.memory_os.core.models.memory import MemoryEntry, MemoryLayer, MemoryScope


class IsolationViolation(Exception):
    """Raised when a cross-tenant access is detected."""


class IStorage(ABC):

    @abstractmethod
    def init_db(self, path: str) -> None:
        ...

    @abstractmethod
    def insert(self, entry: MemoryEntry) -> str:
        ...

    @abstractmethod
    def select(self, tenant_id: str, project_id: str, scope: MemoryScope, layer: Optional[MemoryLayer], limit: int) -> List[dict]:
        ...

    @abstractmethod
    def delete(self, entry_id: str, tenant_id: str) -> bool:
        ...

    @abstractmethod
    def count(self, tenant_id: str) -> int:
        ...


_LOCAL_STORES: dict = {}


def _content_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _get_store_path(base_dir: str, tenant_id: str) -> str:
    tenant_dir = os.path.join(base_dir, "tenants", tenant_id)
    os.makedirs(tenant_dir, exist_ok=True)
    return os.path.join(tenant_dir, "memory.db")


class SQLiteStorage(IStorage):

    def __init__(self, base_dir: str = "/tmp/memory_os_data"):
        self._base_dir = base_dir
        self._conns: Dict[str, sqlite3.Connection] = {}

    def _conn(self, tenant_id: str) -> sqlite3.Connection:
        if tenant_id in self._conns:
            return self._conns[tenant_id]
        db_path = _get_store_path(self._base_dir, tenant_id)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._init_db(conn)
        self._conns[tenant_id] = conn
        return conn

    def _init_db(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memory_entries (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                layer TEXT NOT NULL,
                key TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                payload TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'project',
                ttl_seconds INTEGER,
                importance_weight REAL DEFAULT 1.0,
                created_at REAL NOT NULL,
                UNIQUE(tenant_id, project_id, key)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_tenant
            ON memory_entries(tenant_id, project_id, layer)
        """)
        conn.commit()

    def init_db(self, path: str) -> None:
        conn = sqlite3.connect(path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._init_db(conn)
        conn.close()

    def insert(self, entry: MemoryEntry) -> str:
        if not entry.tenant_id:
            raise IsolationViolation("tenant_id is required")
        conn = self._conn(entry.tenant_id)
        created = entry.created_at or time.time()
        payload_json = json.dumps(entry.payload, default=str)
        conn.execute(
            """INSERT OR REPLACE INTO memory_entries
               (entry_id, tenant_id, project_id, agent_id, layer, key,
                content_hash, payload, scope, ttl_seconds, importance_weight, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.entry_id, entry.tenant_id, entry.project_id, entry.agent_id,
                entry.layer.value, entry.key, entry.content_hash,
                payload_json, entry.scope.value, entry.ttl_seconds,
                entry.importance_weight, created,
            ),
        )
        conn.commit()
        return entry.entry_id

    def select(
        self,
        tenant_id: str,
        project_id: str,
        scope: MemoryScope,
        layer: Optional[MemoryLayer] = None,
        limit: int = 10,
    ) -> List[dict]:
        if not tenant_id:
            raise IsolationViolation("tenant_id is required")
        conn = self._conn(tenant_id)
        clauses = ["tenant_id = ?"]
        params: list = [tenant_id]
        clauses.append("scope = ?")
        params.append(scope.value)
        if project_id and scope == MemoryScope.PROJECT:
            clauses.append("project_id = ?")
            params.append(project_id)
        if layer:
            clauses.append("layer = ?")
            params.append(layer.value)
        sql = (
            "SELECT * FROM memory_entries WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC LIMIT ?"
        )
        params.append(limit)
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def select_by_key(self, tenant_id: str, project_id: str, key: str) -> Optional[dict]:
        if not tenant_id:
            raise IsolationViolation("tenant_id is required")
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT * FROM memory_entries WHERE tenant_id = ? AND project_id = ? AND key = ?",
            (tenant_id, project_id, key),
        ).fetchone()
        return dict(row) if row else None

    def delete(self, entry_id: str, tenant_id: str) -> bool:
        if not tenant_id:
            raise IsolationViolation("tenant_id is required")
        conn = self._conn(tenant_id)
        cur = conn.execute(
            "DELETE FROM memory_entries WHERE entry_id = ? AND tenant_id = ?",
            (entry_id, tenant_id),
        )
        conn.commit()
        return cur.rowcount > 0

    def delete_expired(self, tenant_id: str) -> int:
        if not tenant_id:
            raise IsolationViolation("tenant_id is required")
        conn = self._conn(tenant_id)
        now = time.time()
        cur = conn.execute(
            "DELETE FROM memory_entries WHERE tenant_id = ? AND ttl_seconds IS NOT NULL AND (created_at + ttl_seconds) < ?",
            (tenant_id, now),
        )
        conn.commit()
        return cur.rowcount

    def count(self, tenant_id: str) -> int:
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM memory_entries WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
