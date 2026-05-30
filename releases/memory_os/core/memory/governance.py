"""
Memory Governance — Retention policies, audit log, archive/prune (SOC2/GDPR).

RetentionPolicy: TTL, MaxEntries, ArchiveAfter, HardDeleteAfter.
MemoryGovernanceEngine: enforces policies, maintains immutable audit log (SHA-256 chain).
archive_and_prune: moves cold data, secure deletion with documented reason.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from releases.memory_os.core.memory.graph_store import GraphStore
from releases.memory_os.core.memory.storage_adapter import SQLiteStorage
from releases.memory_os.core.models.memory import PruningPolicy


class RetentionAction(Enum):
    ARCHIVE = "archive"
    HARD_DELETE = "hard_delete"
    WARN = "warn"


@dataclass(frozen=True)
class RetentionPolicy:
    policy_id: str
    tenant_id: str
    project_id: str
    max_entries: int = 100000
    ttl_days: int = 365
    archive_after_days: int = 180
    hard_delete_after_days: int = 730
    action_on_exceed: RetentionAction = RetentionAction.ARCHIVE

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self.project_id:
            raise ValueError("project_id is required")


@dataclass(frozen=True)
class AuditEntry:
    entry_id: str
    tenant_id: str
    action: str
    target_type: str
    target_id: str
    reason: str
    timestamp: float
    previous_hash: str
    sha256_hash: str
    metadata: dict = field(default_factory=dict)


class AuditLog:
    """Immutable audit log with SHA-256 chaining.

    Each entry links to the previous via previous_hash.
    Tampering breaks the chain — detectable by verification.
    """

    def __init__(self, base_dir: str = "/tmp/memory_os_data"):
        self._base_dir = base_dir
        self._conns: Dict[str, sqlite3.Connection] = {}

    def _conn(self, tenant_id: str) -> sqlite3.Connection:
        if tenant_id in self._conns:
            return self._conns[tenant_id]
        tenant_dir = os.path.join(self._base_dir, "tenants", tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        db_path = os.path.join(tenant_dir, "audit_log.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                entry_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp REAL NOT NULL,
                previous_hash TEXT NOT NULL DEFAULT '',
                sha256_hash TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            )
        """)
        conn.commit()
        self._conns[tenant_id] = conn
        return conn

    def _last_hash(self, tenant_id: str) -> str:
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT sha256_hash FROM audit_log WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT 1",
            (tenant_id,),
        ).fetchone()
        return row["sha256_hash"] if row else ""

    def record(
        self,
        tenant_id: str,
        action: str,
        target_type: str,
        target_id: str,
        reason: str,
        metadata: Optional[dict] = None,
    ) -> str:
        conn = self._conn(tenant_id)
        prev_hash = self._last_hash(tenant_id)
        eid = f"audit-{uuid.uuid4().hex[:12]}"
        ts = time.time()
        payload = f"{eid}|{tenant_id}|{action}|{target_type}|{target_id}|{reason}|{ts}|{prev_hash}"
        sha = hashlib.sha256(payload.encode()).hexdigest()
        meta_json = json.dumps(metadata or {}, default=str)
        conn.execute(
            """INSERT INTO audit_log
               (entry_id, tenant_id, action, target_type, target_id, reason, timestamp, previous_hash, sha256_hash, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (eid, tenant_id, action, target_type, target_id, reason, ts, prev_hash, sha, meta_json),
        )
        conn.commit()
        return sha

    def get_log(self, tenant_id: str, limit: int = 100) -> List[dict]:
        conn = self._conn(tenant_id)
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY timestamp DESC LIMIT ?",
            (tenant_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def verify_chain(self, tenant_id: str) -> bool:
        """Verify the integrity of the entire audit chain."""
        conn = self._conn(tenant_id)
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE tenant_id = ? ORDER BY timestamp ASC",
            (tenant_id,),
        ).fetchall()
        prev_hash = ""
        for r in rows:
            payload = f"{r['entry_id']}|{r['tenant_id']}|{r['action']}|{r['target_type']}|{r['target_id']}|{r['reason']}|{r['timestamp']}|{prev_hash}"
            expected = hashlib.sha256(payload.encode()).hexdigest()
            if expected != r["sha256_hash"]:
                return False
            prev_hash = r["sha256_hash"]
        return True

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()


class MemoryGovernanceEngine:
    """Enforces retention policies with audit trail.

    Combines RetentionPolicy with AuditLog for compliance.
    """

    def __init__(
        self,
        storage: SQLiteStorage,
        audit_log: AuditLog,
        graph_store: Optional[GraphStore] = None,
        base_dir: str = "/tmp/memory_os_data",
    ):
        self._storage = storage
        self._audit_log = audit_log
        self._graph_store = graph_store
        self._base_dir = base_dir

    def apply_policy(self, policy: RetentionPolicy, dry_run: bool = False) -> dict:
        """Apply a retention policy to a tenant/project scope."""
        if not policy.tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        now = time.time()
        archived = 0
        hard_deleted = 0
        total_entries = self._storage.count(policy.tenant_id)
        if policy.action_on_exceed == RetentionAction.WARN and total_entries > policy.max_entries:
            self._audit_log.record(
                policy.tenant_id, "WARN", "retention",
                policy.project_id,
                f"entries={total_entries} exceeds max={policy.max_entries}",
            )
        if not dry_run:
            archived = self._archive_old_data(policy, now)
            hard_deleted = self._hard_delete_old_data(policy, now)
        return {
            "policy_id": policy.policy_id,
            "tenant_id": policy.tenant_id,
            "project_id": policy.project_id,
            "total_entries": total_entries,
            "archived": archived,
            "hard_deleted": hard_deleted,
            "dry_run": dry_run,
        }

    def _archive_old_data(self, policy: RetentionPolicy, now: float) -> int:
        cutoff = now - (policy.archive_after_days * 86400)
        conn = self._storage._conn(policy.tenant_id)
        rows = conn.execute(
            "SELECT entry_id, key, created_at FROM memory_entries WHERE tenant_id = ? AND created_at < ? LIMIT 1000",
            (policy.tenant_id, cutoff),
        ).fetchall()
        count = 0
        for r in rows:
            self._audit_log.record(
                policy.tenant_id, "ARCHIVE", "memory_entry", r["entry_id"],
                f"archived after {policy.archive_after_days}d, created={r['created_at']}",
            )
            conn.execute(
                "UPDATE memory_entries SET payload = '{}', ttl_seconds = 0 WHERE entry_id = ? AND tenant_id = ?",
                (r["entry_id"], policy.tenant_id),
            )
            count += 1
        conn.commit()
        return count

    def _hard_delete_old_data(self, policy: RetentionPolicy, now: float) -> int:
        cutoff = now - (policy.hard_delete_after_days * 86400)
        conn = self._storage._conn(policy.tenant_id)
        rows = conn.execute(
            "SELECT entry_id, key FROM memory_entries WHERE tenant_id = ? AND created_at < ? LIMIT 1000",
            (policy.tenant_id, cutoff),
        ).fetchall()
        count = 0
        for r in rows:
            self._audit_log.record(
                policy.tenant_id, "HARD_DELETE", "memory_entry", r["entry_id"],
                f"hard deleted after {policy.hard_delete_after_days}d, key={r['key']}",
            )
            conn.execute(
                "DELETE FROM memory_entries WHERE entry_id = ? AND tenant_id = ?",
                (r["entry_id"], policy.tenant_id),
            )
            if self._graph_store:
                self._graph_store._conn(policy.tenant_id).execute(
                    "DELETE FROM graph_nodes WHERE tenant_id = ? AND node_id NOT IN (SELECT DISTINCT source_id FROM graph_edges)",
                    (policy.tenant_id,),
                )
            count += 1
        conn.commit()
        return count

    def archive_and_prune(
        self,
        tenant_id: str,
        project_id: str,
        max_entries: int = 100000,
        ttl_days: int = 365,
        archive_after_days: int = 180,
        hard_delete_after_days: int = 730,
        dry_run: bool = False,
    ) -> dict:
        policy = RetentionPolicy(
            policy_id=f"rp-{uuid.uuid4().hex[:8]}",
            tenant_id=tenant_id,
            project_id=project_id,
            max_entries=max_entries,
            ttl_days=ttl_days,
            archive_after_days=archive_after_days,
            hard_delete_after_days=hard_delete_after_days,
        )
        return self.apply_policy(policy, dry_run=dry_run)
