"""Graph Query Engine for the AI Code Intelligence Layer.

Read-only query layer over the repository graph (graph_edges table).
Provides traversal, impact analysis, and symbol ranking for the AI
context engine.

Architecture:
    Parser -> Indexer -> DBWriter -> GraphQuery

GraphQuery never writes to the database.  It uses short-lived read-only
SQLite connections.
"""

import json
import sqlite3
from collections import deque
from typing import Any, Dict, List, Optional, Set


class GraphQuery:
    """Read-only graph query engine.

    All connections are short-lived (open, query, close).  No writes
    are performed.  Safe for concurrent use with WAL-mode databases.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ── helpers ─────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        """Open a short-lived read-only connection with WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @staticmethod
    def _safe_json(raw: Optional[str]) -> dict:
        """Parse a JSON properties column safely."""
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _call_count(props: dict) -> int:
        """Extract call_count from a properties dict."""
        return props.get("call_count", 1)

    def _symbol_name(self, symbol_id: str) -> Optional[str]:
        """Resolve a symbol's name from its id (text)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name FROM symbols WHERE CAST(id AS TEXT) = ?",
                (symbol_id,),
            ).fetchone()
            return row["name"] if row else None

    # ── batch helpers ───────────────────────────────────────────────────

    def batch_symbol_metadata(
        self, symbol_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch metadata for many symbols in a single query.

        Returns:
            Dict mapping symbol_id → metadata dict with name, file_path,
            properties, symbol_type, line_number.
        """
        if not symbol_ids:
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        placeholders = ",".join("?" for _ in symbol_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT CAST(s.id AS TEXT) AS sid, s.name, s.symbol_type,
                           s.line_number, s.properties, f.path AS file_path
                    FROM symbols s
                    LEFT JOIN files f ON f.id = s.file_id
                    WHERE CAST(s.id AS TEXT) IN ({placeholders})""",
                symbol_ids,
            ).fetchall()
        for row in rows:
            result[row["sid"]] = {
                "name": row["name"],
                "symbol_type": row["symbol_type"],
                "line_number": row["line_number"],
                "file_path": row["file_path"],
                "properties": self._safe_json(row["properties"]),
            }
        return result

    def batch_callee_counts(
        self, symbol_ids: List[str],
    ) -> Dict[str, int]:
        """Get outgoing callee count for each symbol in one query.

        Returns:
            Dict mapping symbol_id → number of direct callees.
        """
        if not symbol_ids:
            return {}
        result: Dict[str, int] = {}
        placeholders = ",".join("?" for _ in symbol_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT source_id, COUNT(*) AS cnt
                    FROM graph_edges
                    WHERE source_type = 'symbol'
                      AND source_id IN ({placeholders})
                      AND resolved = 1
                      AND target_id IS NOT NULL
                    GROUP BY source_id""",
                symbol_ids,
            ).fetchall()
        for row in rows:
            result[row["source_id"]] = row["cnt"]
        return result

    def batch_resolve_names(
        self, symbol_ids: List[str],
    ) -> Dict[str, str]:
        """Resolve names for many symbol IDs in one query.

        Returns:
            Dict mapping symbol_id → symbol_name.
        """
        if not symbol_ids:
            return {}
        result: Dict[str, str] = {}
        placeholders = ",".join("?" for _ in symbol_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT CAST(id AS TEXT) AS sid, name
                    FROM symbols
                    WHERE CAST(id AS TEXT) IN ({placeholders})""",
                symbol_ids,
            ).fetchall()
        for row in rows:
            result[row["sid"]] = row["name"]
        return result

    # ── get_callers / get_callees ───────────────────────────────────────

    def get_callers(
        self, symbol_id: str, min_calls: int = 0
    ) -> List[Dict[str, Any]]:
        """Return all symbols that call the given symbol.

        Args:
            symbol_id: Symbol id as text.
            min_calls: Minimum call_count; callers with fewer calls are
                       filtered out.

        Returns:
            List of dicts with keys: symbol_id, symbol_name, call_count,
            edge_type.
        """
        results: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.source_id, e.properties, e.edge_type
                   FROM graph_edges e
                   WHERE e.target_type = 'symbol'
                     AND e.target_id = ?
                     AND e.resolved = 1""",
                (symbol_id,),
            ).fetchall()

        for row in rows:
            props = self._safe_json(row["properties"])
            count = self._call_count(props)
            if count < min_calls:
                continue
            name = self._symbol_name(row["source_id"])
            results.append(
                {
                    "symbol_id": row["source_id"],
                    "symbol_name": name,
                    "call_count": count,
                    "edge_type": row["edge_type"],
                }
            )
        return results

    def get_callees(
        self, symbol_id: str
    ) -> List[Dict[str, Any]]:
        """Return all direct callees of a symbol.

        Args:
            symbol_id: Symbol id as text.

        Returns:
            List of dicts with keys: symbol_id, symbol_name, edge_type,
            properties.
        """
        results: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.target_id, e.edge_type, e.properties
                   FROM graph_edges e
                   WHERE e.source_type = 'symbol'
                     AND e.source_id = ?
                     AND e.resolved = 1
                     AND e.target_id IS NOT NULL""",
                (symbol_id,),
            ).fetchall()

        for row in rows:
            name = self._symbol_name(row["target_id"])
            props = self._safe_json(row["properties"])
            results.append(
                {
                    "symbol_id": row["target_id"],
                    "symbol_name": name,
                    "edge_type": row["edge_type"],
                    "properties": props,
                }
            )
        return results

    # ── traversal ───────────────────────────────────────────────────────

    def traverse_depth(
        self,
        start_symbol_id: str,
        depth: int = 2,
        edge_types: tuple = ("call",),
        include_unresolved: bool = False,
    ) -> Dict[str, Any]:
        """Breadth-first traversal of the call graph starting from a symbol.

        Args:
            start_symbol_id: Starting symbol id (text).
            depth: Maximum traversal depth (>= 1).
            edge_types: Tuple of edge types to follow (default: ("call",)).
            include_unresolved: If True, also traverse unresolved edges.

        Returns:
            Dict with:
                nodes: list of {symbol_id, symbol_name, depth}
                edges: list of {source_id, target_id, edge_type, resolved}
        """
        if depth < 1:
            return {"nodes": [], "edges": []}

        visited_nodes: set[str] = set()
        nodes: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []
        queue: deque = deque()

        # Seed
        visited_nodes.add(start_symbol_id)
        name = self._symbol_name(start_symbol_id)
        nodes.append(
            {"symbol_id": start_symbol_id, "symbol_name": name, "depth": 0}
        )

        # Each queue entry: (current_symbol_id, current_depth)
        queue.append((start_symbol_id, 0))

        while queue:
            current_id, current_depth = queue.popleft()
            next_depth = current_depth + 1
            if next_depth > depth:
                continue

            with self._connect() as conn:
                if include_unresolved:
                    placeholders = ",".join("?" for _ in edge_types)
                    rows = conn.execute(
                        f"""SELECT target_id, edge_type, resolved
                           FROM graph_edges
                           WHERE source_type = 'symbol'
                             AND source_id = ?
                             AND edge_type IN ({placeholders})""",
                        (current_id, *edge_types),
                    ).fetchall()
                else:
                    placeholders = ",".join("?" for _ in edge_types)
                    rows = conn.execute(
                        f"""SELECT target_id, edge_type, resolved
                           FROM graph_edges
                           WHERE source_type = 'symbol'
                             AND source_id = ?
                             AND resolved = 1
                             AND target_id IS NOT NULL
                             AND edge_type IN ({placeholders})""",
                        (current_id, *edge_types),
                    ).fetchall()

            for row in rows:
                target_id = row["target_id"]
                if not target_id:
                    continue
                edges.append(
                    {
                        "source_id": current_id,
                        "target_id": target_id,
                        "edge_type": row["edge_type"],
                        "resolved": row["resolved"],
                    }
                )
                if target_id not in visited_nodes:
                    visited_nodes.add(target_id)
                    tgt_name = self._symbol_name(target_id)
                    nodes.append(
                        {
                            "symbol_id": target_id,
                            "symbol_name": tgt_name,
                            "depth": next_depth,
                        }
                    )
                    queue.append((target_id, next_depth))

        return {"nodes": nodes, "edges": edges}

    # ── impact analysis ─────────────────────────────────────────────────

    def impact_analysis(self, file_id: str) -> Dict[str, Any]:
        """Find all symbols/files impacted by a changed file.

        Starts from all symbols in the given file, then traverses INCOMING
        call edges (i.e. who calls these symbols) to find dependents.

        Args:
            file_id: File id as text.

        Returns:
            Dict with:
                root_symbols: symbols in the changed file
                impacted_symbols: symbols that (transitively) depend on root symbols
                impacted_files: files containing impacted symbols (deduplicated)
                traversal_depth: depth used to find impacts
        """
        # 1. Find all symbols in the file
        root_symbols: List[Dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT CAST(id AS TEXT) AS sid, name FROM symbols WHERE file_id = ?",
                (file_id,),
            ).fetchall()

        for row in rows:
            root_symbols.append(
                {"symbol_id": row["sid"], "symbol_name": row["name"]}
            )

        if not root_symbols:
            return {
                "root_symbols": [],
                "impacted_symbols": [],
                "impacted_files": [],
                "traversal_depth": 0,
            }

        # 2. Traverse incoming edges (who calls these symbols?)
        impacted_symbols: List[Dict[str, Any]] = []
        visited: set[str] = set()
        file_ids_seen: set[str] = set()
        queue: deque = deque()

        for rs in root_symbols:
            visited.add(rs["symbol_id"])

        with self._connect() as conn:
            for rs in root_symbols:
                callers = conn.execute(
                    """SELECT e.source_id, e.edge_type
                       FROM graph_edges e
                       WHERE e.target_type = 'symbol'
                         AND e.target_id = ?
                         AND e.resolved = 1""",
                    (rs["symbol_id"],),
                ).fetchall()

                for c in callers:
                    cid = c["source_id"]
                    if cid not in visited:
                        visited.add(cid)
                        cname = None
                        cfile = None
                        cinfo = conn.execute(
                            """SELECT s.name, CAST(s.file_id AS TEXT) AS fid
                               FROM symbols s
                               WHERE CAST(s.id AS TEXT) = ?""",
                            (cid,),
                        ).fetchone()
                        if cinfo:
                            cname = cinfo["name"]
                            cfile = cinfo["fid"]
                            file_ids_seen.add(cfile)

                        impacted_symbols.append(
                            {
                                "symbol_id": cid,
                                "symbol_name": cname,
                                "edge_type": c["edge_type"],
                                "file_id": cfile,
                            }
                        )
                        queue.append(cid)

        # 3. BFS for transitive impacts (max depth 3)
        max_depth = min(len(queue), 3)
        depth = 0
        while queue and depth < max_depth:
            depth += 1
            level_size = len(queue)
            for _ in range(level_size):
                current = queue.popleft()
                callers = conn.execute(
                    """SELECT e.source_id, e.edge_type
                       FROM graph_edges e
                       WHERE e.target_type = 'symbol'
                         AND e.target_id = ?
                         AND e.resolved = 1""",
                    (current,),
                ).fetchall()

                for c in callers:
                    cid = c["source_id"]
                    if cid not in visited:
                        visited.add(cid)
                        cname = None
                        cfile = None
                        cinfo = conn.execute(
                            """SELECT s.name, CAST(s.file_id AS TEXT) AS fid
                               FROM symbols s
                               WHERE CAST(s.id AS TEXT) = ?""",
                            (cid,),
                        ).fetchone()
                        if cinfo:
                            cname = cinfo["name"]
                            cfile = cinfo["fid"]
                            file_ids_seen.add(cfile)

                        impacted_symbols.append(
                            {
                                "symbol_id": cid,
                                "symbol_name": cname,
                                "edge_type": c["edge_type"],
                                "file_id": cfile,
                            }
                        )
                        queue.append(cid)

        # 4. Resolve file paths for impacted files
        impacted_files: List[Dict[str, str]] = []
        with self._connect() as conn:
            for fid in file_ids_seen:
                row = conn.execute(
                    "SELECT path FROM files WHERE id = ?", (fid,)
                ).fetchone()
                if row:
                    impacted_files.append({"file_id": fid, "path": row["path"]})

        return {
            "root_symbols": root_symbols,
            "impacted_symbols": impacted_symbols,
            "impacted_files": impacted_files,
            "traversal_depth": depth,
        }

    # ── top symbols ─────────────────────────────────────────────────────

    def top_symbols(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Find the most-called symbols in the repository.

        Ranks symbols by the total incoming call_count from resolved edges.

        Args:
            limit: Maximum number of results.

        Returns:
            List of dicts with keys: symbol_id, symbol_name, total_calls,
            file_path.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT e.target_id,
                          SUM(COALESCE(json_extract(e.properties, '$.call_count'), 1))
                              AS total_calls,
                          s.name,
                          f.path
                   FROM graph_edges e
                   JOIN symbols s ON CAST(s.id AS TEXT) = e.target_id
                   JOIN files f ON f.id = s.file_id
                   WHERE e.resolved = 1
                     AND e.target_id IS NOT NULL
                   GROUP BY e.target_id
                   ORDER BY total_calls DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

        return [
            {
                "symbol_id": row["target_id"],
                "symbol_name": row["name"],
                "total_calls": row["total_calls"],
                "file_path": row["path"],
            }
            for row in rows
        ]

    # ── metadata queries (used by AIContextEngine) ──────────────────────

    def resolve_symbol_name(self, name: str) -> Optional[str]:
        """Resolve a symbol *name* to its string id.

        Returns ``None`` if no symbol with that name exists.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT CAST(id AS TEXT) AS id FROM symbols WHERE name = ? ORDER BY id DESC LIMIT 1",
                (name,),
            ).fetchone()
        return row["id"] if row else None

    def get_symbol_metadata(self, symbol_id_or_name: str) -> Optional[Dict[str, Any]]:
        """Return metadata for a symbol.

        Args:
            symbol_id: Symbol id as text.

        Returns:
            Dict with keys: id, name, file_id, symbol_type, line_number,
            signature, docstring, properties (parsed JSON, if non-empty),
            or None if not found.
        """
        with self._connect() as conn:
            # Try by id first
            row = conn.execute(
                """SELECT CAST(id AS TEXT) AS id, name,
                          CAST(file_id AS TEXT) AS file_id,
                          symbol_type, line_number, signature, docstring,
                          properties
                   FROM symbols
                   WHERE CAST(id AS TEXT) = ?""",
                (symbol_id_or_name,),
            ).fetchone()
            # Fallback: by name
            if not row:
                row = conn.execute(
                    """SELECT CAST(id AS TEXT) AS id, name,
                              CAST(file_id AS TEXT) AS file_id,
                              symbol_type, line_number, signature, docstring,
                              properties
                       FROM symbols
                       WHERE name = ?
                       ORDER BY id DESC LIMIT 1""",
                    (symbol_id_or_name,),
                ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["properties"] = self._safe_json(row["properties"])
        return result

    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Return metadata for a file.

        Args:
            file_id: File id as text.

        Returns:
            Dict with keys: id, path, name, extension, size, hash,
            or None if not found.
        """
        with self._connect() as conn:
            row = conn.execute(
                """SELECT CAST(id AS TEXT) AS id, path, name, extension
                   FROM files WHERE id = ?""",
                (file_id,),
            ).fetchone()
        if not row:
            return None
        return dict(row)

    def get_file_symbols(self, file_id: str) -> List[Dict[str, Any]]:
        """Return all symbols belonging to a file.

        Args:
            file_id: File id as text.

        Returns:
            List of symbol dicts (id, name, symbol_type, signature).
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT CAST(id AS TEXT) AS id, name, symbol_type, signature
                   FROM symbols WHERE file_id = ?""",
                (file_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_file_dependencies(self, file_id: str) -> List[Dict[str, Any]]:
        """Return file-level import/export dependencies.

        Args:
            file_id: File id as text.

        Returns:
            List of dicts with keys: target_module, import_type, line_number.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT target_module, import_type, line_number
                   FROM file_dependencies WHERE source_file_id = ?""",
                (file_id,),
            ).fetchall()
        return [dict(r) for r in rows]
