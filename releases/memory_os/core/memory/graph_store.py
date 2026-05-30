"""
Graph Store — SQLite-based lightweight graph storage (LAW-6, LAW-11).

IGraphStore: nodes + edges in isolated SQLite tables.
Every query enforces tenant_id/project_id isolation.
Zero external graph engines — pure SQLite adjacency.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from releases.memory_os.core.memory.entity_extractor import (
    EdgeType,
    Entity,
    EntityType,
    Relationship,
)


class GraphStore:
    """SQLite-backed graph store with row-level tenant isolation.

    Tables:
      - graph_nodes: entities with metadata
      - graph_edges: directed relationships with weight/type
    """

    def __init__(self, base_dir: str = "/tmp/memory_os_data"):
        self._base_dir = base_dir
        self._conns: Dict[str, sqlite3.Connection] = {}

    def _conn(self, tenant_id: str) -> sqlite3.Connection:
        if tenant_id in self._conns:
            return self._conns[tenant_id]
        tenant_dir = os.path.join(self._base_dir, "tenants", tenant_id)
        os.makedirs(tenant_dir, exist_ok=True)
        db_path = os.path.join(tenant_dir, "graph.db")
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        self._init_schema(conn)
        self._conns[tenant_id] = conn
        return conn

    def _init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                node_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                context TEXT DEFAULT '',
                source_text TEXT DEFAULT '',
                embedding_id TEXT DEFAULT '',
                created_at REAL NOT NULL,
                UNIQUE(tenant_id, project_id, name)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                edge_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                metadata TEXT DEFAULT '{}',
                created_at REAL NOT NULL,
                FOREIGN KEY(source_id) REFERENCES graph_nodes(node_id),
                FOREIGN KEY(target_id) REFERENCES graph_nodes(node_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_tenant
            ON graph_nodes(tenant_id, project_id, entity_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_edges_source
            ON graph_edges(source_id, edge_type)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_graph_edges_target
            ON graph_edges(target_id, edge_type)
        """)
        conn.commit()

    # ── node operations ──────────────────────────────────────

    def add_node(self, entity: Entity) -> str:
        conn = self._conn(entity.tenant_id)
        existing = conn.execute(
            "SELECT node_id FROM graph_nodes WHERE tenant_id = ? AND project_id = ? AND name = ?",
            (entity.tenant_id, entity.project_id, entity.name),
        ).fetchone()
        if existing:
            return existing["node_id"]
        conn.execute(
            """INSERT INTO graph_nodes
               (node_id, tenant_id, project_id, name, entity_type, context, source_text, embedding_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (entity.entity_id, entity.tenant_id, entity.project_id, entity.name,
             entity.entity_type.value, entity.context, entity.source_text,
             entity.embedding_id, time.time()),
        )
        conn.commit()
        return entity.entity_id

    def get_node(self, node_id: str, tenant_id: str) -> Optional[dict]:
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT * FROM graph_nodes WHERE node_id = ? AND tenant_id = ?",
            (node_id, tenant_id),
        ).fetchone()
        return dict(row) if row else None

    def find_nodes_by_type(self, tenant_id: str, project_id: str, entity_type: str) -> List[dict]:
        conn = self._conn(tenant_id)
        rows = conn.execute(
            "SELECT * FROM graph_nodes WHERE tenant_id = ? AND project_id = ? AND entity_type = ?",
            (tenant_id, project_id, entity_type),
        ).fetchall()
        return [dict(r) for r in rows]

    def find_node_by_name(self, tenant_id: str, project_id: str, name: str) -> Optional[dict]:
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT * FROM graph_nodes WHERE tenant_id = ? AND project_id = ? AND name = ?",
            (tenant_id, project_id, name),
        ).fetchone()
        return dict(row) if row else None

    # ── edge operations ──────────────────────────────────────

    def add_edge(self, rel: Relationship) -> str:
        conn = self._conn(rel.tenant_id)
        rel_id = f"rel-{uuid.uuid4().hex[:12]}"
        meta_json = json.dumps(rel.metadata, default=str)
        conn.execute(
            """INSERT OR IGNORE INTO graph_edges
               (edge_id, tenant_id, project_id, source_id, target_id, edge_type, weight, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rel_id, rel.tenant_id, rel.project_id, rel.source_id, rel.target_id,
             rel.edge_type.value, rel.weight, meta_json, time.time()),
        )
        conn.commit()
        return rel_id

    # ── traversal ────────────────────────────────────────────

    def get_neighbors(
        self,
        entity_id: str,
        tenant_id: str,
        project_id: str = "",
        depth: int = 1,
        edge_type: Optional[str] = None,
    ) -> List[dict]:
        conn = self._conn(tenant_id)
        node = self.get_node(entity_id, tenant_id)
        if not node:
            return []
        visited: set = {entity_id}
        results: List[dict] = []
        current: List[str] = [entity_id]
        for _ in range(depth):
            if not current:
                break
            placeholders = ",".join("?" for _ in current)
            edge_filter = "AND e.edge_type = ?" if edge_type else ""
            params: list = [tenant_id] + current
            if edge_type:
                params.append(edge_type)
            rows = conn.execute(
                f"""SELECT n.*, e.edge_type AS _edge_type, e.weight AS _edge_weight
                    FROM graph_edges e
                    JOIN graph_nodes n ON n.node_id = e.target_id
                    WHERE e.tenant_id = ? AND e.source_id IN ({placeholders})
                    {edge_filter}
                    UNION
                    SELECT n.*, e.edge_type AS _edge_type, e.weight AS _edge_weight
                    FROM graph_edges e
                    JOIN graph_nodes n ON n.node_id = e.source_id
                    WHERE e.tenant_id = ? AND e.target_id IN ({placeholders})
                    {edge_filter}""",
                params + [tenant_id] + current + ([edge_type] if edge_type else []),
            ).fetchall()
            next_ids: List[str] = []
            for r in rows:
                rd = dict(r)
                if rd["node_id"] not in visited:
                    visited.add(rd["node_id"])
                    next_ids.append(rd["node_id"])
                    if project_id and rd.get("project_id") != project_id:
                        continue
                    results.append(rd)
            current = next_ids
        return results

    def query_path(self, start_id: str, end_id: str, tenant_id: str, max_depth: int = 4) -> List[dict]:
        """BFS-based path finding between two nodes (no cycles)."""
        if start_id == end_id:
            node = self.get_node(start_id, tenant_id)
            return [node] if node else []
        conn = self._conn(tenant_id)
        visited: set = {start_id}
        queue: List[Tuple[str, list]] = [(start_id, [start_id])]
        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            rows = conn.execute(
                """SELECT target_id AS neighbor FROM graph_edges
                   WHERE tenant_id = ? AND source_id = ?
                   UNION
                   SELECT source_id AS neighbor FROM graph_edges
                   WHERE tenant_id = ? AND target_id = ?""",
                (tenant_id, current, tenant_id, current),
            ).fetchall()
            for r in rows:
                nid = r["neighbor"]
                if nid == end_id:
                    full_path = path + [nid]
                    nodes = []
                    for pid in full_path:
                        node = conn.execute(
                            "SELECT * FROM graph_nodes WHERE node_id = ? AND tenant_id = ?",
                            (pid, tenant_id),
                        ).fetchone()
                        if node:
                            nodes.append(dict(node))
                    return nodes
                if nid not in visited:
                    visited.add(nid)
                    queue.append((nid, path + [nid]))
        return []

    def count_nodes(self, tenant_id: str, project_id: str = "") -> int:
        conn = self._conn(tenant_id)
        if project_id:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_nodes WHERE tenant_id = ? AND project_id = ?",
                (tenant_id, project_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM graph_nodes WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchone()
        return row["cnt"] if row else 0

    def count_edges(self, tenant_id: str) -> int:
        conn = self._conn(tenant_id)
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM graph_edges WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return row["cnt"] if row else 0

    def close(self) -> None:
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()
