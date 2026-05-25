"""Memory Pressure Control.

Manages DAG execution under memory/resource constraints:

  1. DAG size limiter — reject or truncate graphs that exceed
     configurable node / depth limits before execution.
  2. Streaming execution — run the DAG one level at a time,
     yielding partial results after each level completes.
  3. Partial execution checkpoints — save execution progress to
     SQLite so a large DAG can be resumed after an interruption.

All operations are deterministic — given the same DAG and same
limits, the output is always the same.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from .models.dag import (
        DependencyGraph, PlanNode, NodeState,
    )

logger = logging.getLogger("emo_ai.memory_pressure")

# Version — bump when checkpoint schema changes.
MEMORY_PRESSURE_VERSION = "1.0.0"

_DEFAULT_CHECKPOINT_PATH = Path(os.environ.get(
    "EMO_AI_CHECKPOINT_DB",
    ".ai/index/checkpoint.db",
))


@dataclass
class PressureLimits:
    """Configurable constraints for DAG execution."""
    max_nodes: int = 50
    max_depth: int = 20
    max_parallel: int = 8  # max nodes in a single level


class DAGSizeLimiter:
    """Checks a DAG against pressure limits before execution.

    Safe: evaluates the DAG without modifying it.
    """

    def __init__(self, limits: Optional[PressureLimits] = None):
        self._limits = limits or PressureLimits()

    def check(self, dag: DependencyGraph) -> List[str]:
        """Return a list of constraint violations (empty = OK)."""
        errors: List[str] = []
        n_nodes = len(dag.nodes)
        if n_nodes > self._limits.max_nodes:
            errors.append(
                f"DAG has {n_nodes} nodes, max is {self._limits.max_nodes}"
            )
        depth = self._compute_depth(dag)
        if depth > self._limits.max_depth:
            errors.append(
                f"DAG depth is {depth}, max is {self._limits.max_depth}"
            )
        max_level = self._max_level_width(dag)
        if max_level > self._limits.max_parallel:
            errors.append(
                f"DAG level width is {max_level}, "
                f"max parallel is {self._limits.max_parallel}"
            )
        return errors

    @staticmethod
    def _compute_depth(dag: DependencyGraph) -> int:
        topo = dag.topo_sort()
        depth: Dict[str, int] = {}
        for node in topo:
            preds = dag.predecessors(node.id)
            depth[node.id] = max(
                (depth[p.id] for p in preds), default=0
            ) + 1
        return max(depth.values()) if depth else 0

    @staticmethod
    def _max_level_width(dag: DependencyGraph) -> int:
        groups = dag.independent_branches()
        return max((len(g) for g in groups), default=0)


class StreamingExecutor:
    """Executes a DAG level by level, yielding after each level.

    Each yielded dict contains:
      - level: int (1-indexed)
      - nodes: list of node results for this level
      - completed: total completed count
      - total: total node count

    Usage:
        executor = StreamingExecutor()
        for partial in executor.run(dag, node_runner):
            print(partial)  # progressive results
    """

    def __init__(self):
        self._cancelled = threading.Event()

    def run(
        self,
        dag: DependencyGraph,
        node_runner,
    ) -> Iterator[Dict[str, Any]]:
        """Yield partial results after each depth level completes."""
        groups = dag.independent_branches()
        total_nodes = len(dag.nodes)
        completed = 0
        node_results: Dict[str, Any] = {}

        for level_idx, level_nodes in enumerate(groups, 1):
            if self._cancelled.is_set():
                yield {
                    "level": level_idx,
                    "status": "cancelled",
                    "completed": completed,
                    "total": total_nodes,
                    "nodes": [],
                }
                return

            level_results: List[Dict[str, Any]] = []
            for node in level_nodes:
                try:
                    result = node_runner(node)
                    result["node_id"] = node.id
                    node_results[node.id] = result
                    level_results.append(result)
                    if result.get("status") in ("completed", "cached"):
                        completed += 1
                except Exception as e:
                    node_results[node.id] = {
                        "status": "failed",
                        "node_id": node.id,
                        "error": str(e),
                    }
                    level_results.append(node_results[node.id])

            yield {
                "level": level_idx,
                "status": "running",
                "completed": completed,
                "total": total_nodes,
                "nodes": level_results,
                "all_results": dict(node_results),
            }

        yield {
            "level": len(groups),
            "status": "completed",
            "completed": total_nodes,
            "total": total_nodes,
            "nodes": [],
            "all_results": dict(node_results),
        }

    def cancel(self) -> None:
        self._cancelled.set()


class CheckpointManager:
    """Saves and restores DAG execution progress.

    Checkpoints are stored in a local SQLite DB. Each checkpoint
    records:
      - session_id
      - completed node IDs
      - serialized node results
      - DAG snapshot (nodes + edges)

    A checkpointed execution can be resumed by skipping already-
    completed nodes and starting from the next uncompleted level.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DEFAULT_CHECKPOINT_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        try:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        session_id TEXT NOT NULL,
                        node_id TEXT NOT NULL,
                        result TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (session_id, node_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS checkpoint_sessions (
                        session_id TEXT PRIMARY KEY,
                        dag_json TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
        except Exception as e:
            logger.warning("Checkpoint DB init failed: %s", e)

    def save(
        self,
        session_id: str,
        dag: DependencyGraph,
        node_id: str,
        result: Dict[str, Any],
    ) -> None:
        """Record a single completed node result."""
        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO checkpoints "
                        "(session_id, node_id, result, created_at) "
                        "VALUES (?, ?, ?, ?)",
                        (session_id, node_id,
                         json.dumps(result), time.time()),
                    )
                    conn.execute(
                        "INSERT OR REPLACE INTO checkpoint_sessions "
                        "(session_id, dag_json, created_at, updated_at) "
                        "VALUES (?, ?, COALESCE((SELECT created_at FROM "
                        "checkpoint_sessions WHERE session_id=?), ?), ?)",
                        (session_id, json.dumps(dag.to_dict()),
                         session_id, time.time(), time.time()),
                    )
            except Exception as e:
                logger.debug("Checkpoint save failed: %s", e)

    def restore(
        self, session_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Restore a previous execution session.

        Returns:
            { "dag": DependencyGraph, "completed": {node_id: result, ...} }
            or None if the session does not exist.
        """
        from .models.dag import DependencyGraph as DG, PlanNode as PN

        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    row = conn.execute(
                        "SELECT dag_json, created_at FROM "
                        "checkpoint_sessions WHERE session_id=?",
                        (session_id,),
                    ).fetchone()
                    if row is None:
                        return None

                    completed: Dict[str, Any] = {}
                    rows = conn.execute(
                        "SELECT node_id, result FROM checkpoints "
                        "WHERE session_id=?",
                        (session_id,),
                    ).fetchall()
                    for node_id, result_json in rows:
                        completed[node_id] = json.loads(result_json)

                    dag_json = json.loads(row[0])
                    dag = DG()
                    if "nodes" in dag_json:
                        for nid, ndata in dag_json["nodes"].items():
                            node = PN(
                                id=nid,
                                tool=ndata.get("tool", ""),
                                inputs=ndata.get("inputs", {}),
                            )
                            dag.add_node(node)
                    if "edges" in dag_json:
                        for edata in dag_json["edges"]:
                            dag.add_edge(
                                edata.get("source_id") or edata["source"],
                                edata.get("target_id") or edata["target"],
                                edata.get("condition", "success"),
                            )

                    return {"dag": dag, "completed": completed}
            except Exception as e:
                logger.debug("Checkpoint restore failed: %s", e)
                return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return metadata for all checkpointed sessions."""
        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    rows = conn.execute(
                        "SELECT session_id, created_at, updated_at FROM "
                        "checkpoint_sessions ORDER BY updated_at DESC",
                    ).fetchall()
                    return [
                        {
                            "session_id": r[0],
                            "created_at": r[1],
                            "updated_at": r[2],
                        }
                        for r in rows
                    ]
            except Exception as e:
                logger.debug("List checkpoints failed: %s", e)
                return []

    def delete(self, session_id: str) -> None:
        """Remove a checkpoint session."""
        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    conn.execute(
                        "DELETE FROM checkpoints WHERE session_id=?",
                        (session_id,),
                    )
                    conn.execute(
                        "DELETE FROM checkpoint_sessions WHERE session_id=?",
                        (session_id,),
                    )
            except Exception as e:
                logger.debug("Checkpoint delete failed: %s", e)

    def completed_nodes(self, session_id: str) -> Set[str]:
        """Return set of completed node IDs for a session."""
        with self._lock:
            try:
                with sqlite3.connect(str(self._db_path)) as conn:
                    rows = conn.execute(
                        "SELECT node_id FROM checkpoints "
                        "WHERE session_id=?",
                        (session_id,),
                    ).fetchall()
                    return {r[0] for r in rows}
            except Exception as e:
                logger.debug("Completed nodes query failed: %s", e)
                return set()
