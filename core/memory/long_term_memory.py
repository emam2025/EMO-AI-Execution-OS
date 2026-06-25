"""LongTermMemory — persistent memory namespace with TTL, search, audit.

Long-term memory survives process restarts via database backing store.
Uses core/db_backend.py for persistence (SQLite or PostgreSQL).
Optionally integrates with VectorDB for semantic search.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer, RetrievalMode
from core.memory.trace_correlator import CognitiveTraceCorrelator


@dataclass
class LongTermMemoryEntry:
    entry_id: str
    agent_id: str
    key: str
    payload: Dict[str, Any]
    ttl_seconds: Optional[int] = None
    created_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    cognitive_trace_id: str = ""


class LongTermMemory:
    """Persistent long-term memory namespace.

    Key difference from ProjectMemory / AgentMemory:
    - Data survives process restarts
    - Backed by database (SQLite / PostgreSQL) via core/db_backend.py
    - Optional VectorDB integration for semantic search

    Wraps MemoryHierarchy on LONG_TERM layer for in-memory cache,
    but persists to database for durability.
    """

    def __init__(
        self,
        hierarchy: MemoryHierarchy,
        db=None,
        vector_db=None,
        trace_correlator: Optional[CognitiveTraceCorrelator] = None,
    ) -> None:
        self._hierarchy = hierarchy
        self._db = db
        self._vector_db = vector_db
        self._trace_correlator = trace_correlator or CognitiveTraceCorrelator()
        self._table = "long_term_memory"
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        if self._db:
            conn = await self._db.connect()
            try:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._table} (
                        entry_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        key TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        ttl_seconds INTEGER,
                        created_at TEXT NOT NULL,
                        last_accessed TEXT,
                        access_count INTEGER DEFAULT 0,
                        tags TEXT,
                        cognitive_trace_id TEXT,
                        UNIQUE(agent_id, key)
                    )
                """)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_ltm_agent
                    ON {self._table}(agent_id)
                """)
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_ltm_tags
                    ON {self._table}(tags)
                """)
                await conn.commit()
            finally:
                await conn.close()
        self._initialized = True

    async def _with_conn(self, callback):
        conn = await self._db.connect()
        try:
            return await callback(conn)
        finally:
            await conn.close()

    async def store(
        self,
        agent_id: str,
        key: str,
        payload: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
        tags: Optional[List[str]] = None,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")
        if not key:
            raise ValueError("key is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"ltm:{agent_id}",
        )
        compound_key = f"{agent_id}:{key}"
        now_ts = int(time.time())
        entry_id = str(uuid.uuid4())
        tags_list = tags or []

        result = await self._hierarchy.store(
            layer=MemoryLayer.LONG_TERM,
            key=compound_key,
            payload=payload,
            tenant_id=tenant_id or agent_id,
            isolation_policy="strict",
            cognitive_trace_id=trace_id,
            ttl_seconds=ttl_seconds,
        )

        if self._db:
            async def _do_store(conn):
                await conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {self._table}
                        (entry_id, agent_id, key, payload, ttl_seconds,
                         created_at, last_accessed, access_count, tags,
                         cognitive_trace_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        agent_id,
                        key,
                        json.dumps(payload),
                        ttl_seconds,
                        str(now_ts),
                        str(now_ts),
                        0,
                        json.dumps(tags_list),
                        trace_id,
                    ),
                )
                await conn.commit()
            await self._with_conn(_do_store)

        if self._vector_db:
            vector = self._payload_to_vector(payload)
            if vector:
                self._vector_db.upsert(
                    point_id=entry_id,
                    vector=vector,
                    payload={"agent_id": agent_id, "key": key, "tags": tags_list},
                )

        return {
            "status": "stored",
            "entry_id": entry_id,
            "agent_id": agent_id,
            "key": key,
            "ttl_seconds": ttl_seconds,
            "tags": tags_list,
            "cognitive_trace_id": trace_id,
            "hierarchy_result": result,
        }

    async def retrieve(
        self,
        agent_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id or not key:
            raise ValueError("agent_id and key are required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"ltm:{agent_id}:retrieve",
        )

        if self._db:
            async def _do_retrieve(conn):
                row = await conn.fetchone(
                    f"SELECT * FROM {self._table} WHERE agent_id = ? AND key = ?",
                    (agent_id, key),
                )
                if row is None:
                    return {
                        "status": "not_found",
                        "agent_id": agent_id,
                        "key": key,
                        "result": None,
                        "cognitive_trace_id": trace_id,
                    }
                now_ts = int(time.time())
                await conn.execute(
                    f"UPDATE {self._table} SET last_accessed = ?, access_count = access_count + 1 WHERE agent_id = ? AND key = ?",
                    (str(now_ts), agent_id, key),
                )
                await conn.commit()

                payload = json.loads(row["payload"])
                tags = json.loads(row["tags"]) if row.get("tags") else []
                entry = {
                    "entry_id": row["entry_id"],
                    "agent_id": row["agent_id"],
                    "key": row["key"],
                    "payload": payload,
                    "ttl_seconds": row["ttl_seconds"],
                    "created_at": row["created_at"],
                    "last_accessed": str(now_ts),
                    "access_count": row["access_count"] + 1,
                    "tags": tags,
                    "cognitive_trace_id": row["cognitive_trace_id"],
                }
                return {
                    "status": "ok",
                    "agent_id": agent_id,
                    "key": key,
                    "result": entry,
                    "cognitive_trace_id": trace_id,
                }
            return await self._with_conn(_do_retrieve)

        compound_key = f"{agent_id}:{key}"
        hierarchy_result = await self._hierarchy.retrieve(
            layer=MemoryLayer.LONG_TERM,
            query={"key": compound_key},
            tenant_id=tenant_id or agent_id,
            mode=RetrievalMode.EXACT,
            cognitive_trace_id=trace_id,
            limit=1,
        )

        if hierarchy_result["total"] > 0:
            entry = hierarchy_result["results"][0]
            if entry.get("payload", {}).get("_deleted"):
                return {
                    "status": "not_found",
                    "agent_id": agent_id,
                    "key": key,
                    "result": None,
                    "cognitive_trace_id": trace_id,
                }

        return {
            "status": "ok" if hierarchy_result["total"] > 0 else "not_found",
            "agent_id": agent_id,
            "key": key,
            "result": hierarchy_result["results"][0] if hierarchy_result["total"] > 0 else None,
            "cognitive_trace_id": trace_id,
        }

    async def search(
        self,
        agent_id: str,
        query: str = "",
        limit: int = 10,
        tags: Optional[List[str]] = None,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"ltm:{agent_id}:search",
        )

        if self._db:
            async def _do_search(conn):
                sql = f"SELECT * FROM {self._table} WHERE agent_id = ?"
                params: List[Any] = [agent_id]

                if query:
                    sql += " AND (key LIKE ? OR payload LIKE ?)"
                    like = f"%{query}%"
                    params.append(like)
                    params.append(like)

                if tags:
                    for tag in tags:
                        sql += " AND tags LIKE ?"
                        params.append(f"%{tag}%")

                sql += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = await conn.fetchall(sql, tuple(params))
                results = []
                for row in rows:
                    results.append({
                        "entry_id": row["entry_id"],
                        "agent_id": row["agent_id"],
                        "key": row["key"],
                        "payload": json.loads(row["payload"]),
                        "ttl_seconds": row["ttl_seconds"],
                        "created_at": row["created_at"],
                        "last_accessed": row["last_accessed"],
                        "access_count": row["access_count"],
                        "tags": json.loads(row["tags"]) if row.get("tags") else [],
                        "cognitive_trace_id": row["cognitive_trace_id"],
                    })

                return {
                    "status": "ok",
                    "agent_id": agent_id,
                    "query": query,
                    "results": results,
                    "total": len(results),
                    "cognitive_trace_id": trace_id,
                }
            return await self._with_conn(_do_search)

        compound_prefix = f"{agent_id}:"
        hierarchy_result = await self._hierarchy.retrieve(
            layer=MemoryLayer.LONG_TERM,
            query={"key": ""},
            tenant_id=tenant_id or agent_id,
            mode=RetrievalMode.HYBRID,
            cognitive_trace_id=trace_id,
            limit=limit,
        )

        all_results = hierarchy_result["results"]
        filtered = []
        for r in all_results:
            compound = r.get("key", "")
            if not compound.startswith(compound_prefix):
                continue
            if query:
                query_lower = query.lower()
                payload_str = str(r.get("payload", {})).lower()
                if query_lower not in compound.lower() and query_lower not in payload_str:
                    continue
            filtered.append(r)

        return {
            "status": "ok",
            "agent_id": agent_id,
            "query": query,
            "results": filtered[:limit],
            "total": len(filtered),
            "cognitive_trace_id": trace_id,
        }

    async def semantic_search(
        self,
        agent_id: str,
        query_vector: List[float],
        limit: int = 10,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not self._vector_db:
            return {
                "status": "error",
                "error": "VectorDB not configured",
                "agent_id": agent_id,
                "results": [],
                "total": 0,
                "cognitive_trace_id": cognitive_trace_id or "",
            }

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"ltm:{agent_id}:semantic",
        )

        vector_results = self._vector_db.search(query_vector, top_k=limit)
        vdb_entry_ids = {r["point_id"] for r in vector_results}

        if not self._db or not vdb_entry_ids:
            return {
                "status": "ok",
                "agent_id": agent_id,
                "query_vector": query_vector[:5],
                "results": vector_results,
                "total": len(vector_results),
                "cognitive_trace_id": trace_id,
            }

        async def _do_enrich(conn):
            placeholders = ",".join("?" for _ in vdb_entry_ids)
            rows = await conn.fetchall(
                f"SELECT * FROM {self._table} WHERE entry_id IN ({placeholders})",
                tuple(vdb_entry_ids),
            )
            db_map = {r["entry_id"]: r for r in rows}

            enriched = []
            for vr in vector_results:
                pid = vr["point_id"]
                if pid in db_map:
                    row = db_map[pid]
                    enriched.append({
                        **vr,
                        "agent_id": row["agent_id"],
                        "key": row["key"],
                        "payload": json.loads(row["payload"]),
                        "created_at": row["created_at"],
                        "tags": json.loads(row["tags"]) if row.get("tags") else [],
                    })
                else:
                    enriched.append(vr)

            return {
                "status": "ok",
                "agent_id": agent_id,
                "query_vector": query_vector[:5],
                "results": enriched,
                "total": len(enriched),
                "cognitive_trace_id": trace_id,
            }
        return await self._with_conn(_do_enrich)

    async def delete(
        self,
        agent_id: str,
        key: str,
        tenant_id: str = "",
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not agent_id or not key:
            raise ValueError("agent_id and key are required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            tenant_id or agent_id, f"ltm:{agent_id}:delete",
        )

        if self._db:
            async def _do_delete(conn):
                row = await conn.fetchone(
                    f"SELECT entry_id FROM {self._table} WHERE agent_id = ? AND key = ?",
                    (agent_id, key),
                )
                if row and self._vector_db:
                    self._vector_db.delete(row["entry_id"])
                await conn.execute(
                    f"DELETE FROM {self._table} WHERE agent_id = ? AND key = ?",
                    (agent_id, key),
                )
                await conn.commit()
            await self._with_conn(_do_delete)

        compound_key = f"{agent_id}:{key}"
        await self._hierarchy.store(
            layer=MemoryLayer.LONG_TERM,
            key=compound_key,
            payload={"_deleted": True},
            tenant_id=tenant_id or agent_id,
            isolation_policy="strict",
            cognitive_trace_id=trace_id,
        )

        return {
            "status": "deleted",
            "agent_id": agent_id,
            "key": key,
            "cognitive_trace_id": trace_id,
        }

    async def delete_agent(self, agent_id: str, tenant_id: str = "", cognitive_trace_id: str = "") -> Dict[str, Any]:
        if not agent_id:
            raise ValueError("agent_id is required")

        trace_id = cognitive_trace_id or self._trace_correlator.generate_cognitive_trace_id(
            agent_id, f"ltm:{agent_id}:delete_agent",
        )

        if self._db:
            async def _do_delete_agent(conn):
                if self._vector_db:
                    rows = await conn.fetchall(
                        f"SELECT entry_id FROM {self._table} WHERE agent_id = ?",
                        (agent_id,),
                    )
                    for row in rows:
                        self._vector_db.delete(row["entry_id"])
                await conn.execute(
                    f"DELETE FROM {self._table} WHERE agent_id = ?",
                    (agent_id,),
                )
                await conn.commit()
            await self._with_conn(_do_delete_agent)

        compound_key = f"{agent_id}:"
        existing_keys = [k for k in self._hierarchy._entries.get(tenant_id or agent_id, {}).get(MemoryLayer.LONG_TERM.value, {}) if k.startswith(compound_key)]
        for ck in existing_keys:
            await self._hierarchy.store(
                layer=MemoryLayer.LONG_TERM,
                key=ck,
                payload={"_deleted": True},
                tenant_id=tenant_id or agent_id,
                isolation_policy="strict",
                cognitive_trace_id=trace_id,
            )

        return {
            "status": "deleted",
            "agent_id": agent_id,
            "cognitive_trace_id": trace_id,
        }

    async def get_stats(
        self,
        agent_id: Optional[str] = None,
        cognitive_trace_id: str = "",
    ) -> Dict[str, Any]:
        trace_id = cognitive_trace_id or ""

        if not self._db:
            return {
                "status": "ok",
                "agent_id": agent_id or "*",
                "total_entries": 0,
                "total_agents": 0,
                "cognitive_trace_id": trace_id,
            }

        async def _do_stats(conn):
            if agent_id:
                row = await conn.fetchone(
                    f"""
                    SELECT COUNT(*) as cnt, COALESCE(SUM(access_count),0) as acc
                    FROM {self._table} WHERE agent_id = ?
                    """,
                    (agent_id,),
                )
                return {
                    "status": "ok",
                    "agent_id": agent_id,
                    "total_entries": row["cnt"] if row else 0,
                    "total_access_count": row["acc"] if row else 0,
                    "cognitive_trace_id": trace_id,
                }

            row = await conn.fetchone(
                f"""
                SELECT COUNT(*) as cnt,
                       COALESCE(SUM(access_count),0) as acc,
                       COUNT(DISTINCT agent_id) as agents
                FROM {self._table}
                """,
            )
            return {
                "status": "ok",
                "agent_id": "*",
                "total_entries": row["cnt"] if row else 0,
                "total_access_count": row["acc"] if row else 0,
                "total_agents": row["agents"] if row else 0,
                "cognitive_trace_id": trace_id,
            }
        return await self._with_conn(_do_stats)

    async def cleanup_expired(self, cognitive_trace_id: str = "") -> Dict[str, Any]:
        trace_id = cognitive_trace_id or ""
        if not self._db:
            return {"status": "ok", "deleted_count": 0, "cognitive_trace_id": trace_id}

        async def _do_cleanup(conn):
            row = await conn.fetchone(
                f"""
                SELECT COUNT(*) as cnt FROM {self._table}
                WHERE ttl_seconds IS NOT NULL
                  AND ttl_seconds > 0
                  AND (
                      CAST(strftime('%s', 'now') AS INTEGER) -
                      CAST(created_at AS INTEGER)
                  ) > ttl_seconds
                """,
            )
            before = row["cnt"] if row else 0

            await conn.execute(
                f"""
                DELETE FROM {self._table}
                WHERE ttl_seconds IS NOT NULL
                  AND ttl_seconds > 0
                  AND (
                      CAST(strftime('%s', 'now') AS INTEGER) -
                      CAST(created_at AS INTEGER)
                  ) > ttl_seconds
                """,
            )
            await conn.commit()

            return {
                "status": "ok",
                "deleted_count": before,
                "cognitive_trace_id": trace_id,
            }
        return await self._with_conn(_do_cleanup)

    def _payload_to_vector(self, payload: Dict[str, Any]) -> Optional[List[float]]:
        try:
            text = json.dumps(payload, sort_keys=True)
            import hashlib
            h = hashlib.sha256(text.encode()).digest()
            vec = [b / 255.0 for b in h[:384]]
            return vec
        except Exception:
            return None
