"""Execution Memory Layer – Phase 14.

Records every execution as structured memory: sessions group queries,
reasoning traces explain decisions, task memory persists cross-query
workflows, and planning history enables autonomous retries.

Tables:
    sessions           – top-level execution unit per query
    session_events     – ordered sequence within a session
    reasoning_traces   – why decisions were made
    task_memory        – cross-query task tracking
    plan_history       – versioned plan attempts

Architecture:
    User Query
        ↓
    Orchestrator ─→ ExecutionMemory.create_session()
        ↓                ↓
    PlanExecutor ──→ session_events (retrieval → plan → action → result)
        ↓                ↓
    AI Agent ──────→ reasoning_traces (why this symbol / weight / refactor)
        ↓
    Task Memory ←── Plan History ←── autonomous retry
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.execution_memory")

_DEFAULT_DB = str(Path(".ai") / "index" / "execution_memory.db")


# ======================================================================
# Data types
# ======================================================================

@dataclass
class ExecutionSession:
    """A single top-level execution unit."""
    session_id: str = ""
    query: str = ""
    strategy: str = ""
    started_at: float = 0.0
    completed_at: Optional[float] = None
    status: str = "active"  # active | completed | failed | rolled_back
    result_summary: Optional[Dict[str, Any]] = None
    feedback: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionEvent:
    """An ordered event within a session."""
    event_id: int = 0
    session_id: str = ""
    sequence: int = 0
    event_type: str = ""  # retrieval | plan | action | result | weight_change | feedback
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class ReasoningTrace:
    """Why a decision was made."""
    trace_id: int = 0
    session_id: str = ""
    trace_type: str = ""  # symbol_selection | weight_change | refactor_suggestion | tool_choice
    target_id: str = ""   # symbol_id, strategy, etc.
    reason: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class TaskRecord:
    """Cross-query task tracking."""
    task_id: str = ""
    description: str = ""
    symbols: List[str] = field(default_factory=list)
    files: List[str] = field(default_factory=list)
    impact_chain: List[str] = field(default_factory=list)
    previous_attempts: List[str] = field(default_factory=list)  # plan_ids
    status: str = "active"  # active | completed | failed | blocked
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlanAttempt:
    """A versioned plan attempt."""
    plan_id: str = ""
    session_id: str = ""
    task_id: str = ""
    plan_number: int = 1
    steps: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "proposed"  # proposed | running | succeeded | failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: float = 0.0
    completed_at: Optional[float] = None


# ======================================================================
# ExecutionMemory
# ======================================================================

class ExecutionMemory:
    """Persistent execution memory with session grouping + reasoning.

    Usage:
        mem = ExecutionMemory()

        # 1. Session lifecycle
        sid = mem.create_session("find auth", strategy="balanced")
        mem.complete_session(sid, {"top_symbol": "validate"})
        mem.fail_session(sid, "Graph unavailable")

        # 2. Events within session
        mem.add_event(sid, "retrieval", {"symbols": ["s1", "s2"]})
        mem.add_event(sid, "plan", {"steps": 3})

        # 3. Reasoning traces
        mem.add_reasoning(sid, "symbol_selection", "s1",
                          "Highest importance score", {"score": 8.5})

        # 4. Task memory
        tid = mem.create_task("refactor auth flow", symbols=["s1", "s2"])
        mem.update_task_symbols(tid, ["s3", "s4"])

        # 5. Plan history
        pid = mem.create_plan(sid, tid, steps=[{"action": "explain"}])
        mem.succeed_plan(pid, {"summary": "done"})
    """

    def __init__(self, db_path: str = _DEFAULT_DB):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_schema()

    # ═══════════════════════════════════════════════════════════════════
    # 1 – Session lifecycle
    # ═══════════════════════════════════════════════════════════════════

    def create_session(
        self,
        query: str,
        strategy: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new execution session.  Returns session_id."""
        sid = str(uuid.uuid4())
        self._insert_session(sid, query, strategy, time.time(), metadata or {})
        logger.debug("Session created: %s — %s", sid[:8], query[:60])
        return sid

    def complete_session(
        self,
        session_id: str,
        result_summary: Optional[Dict[str, Any]] = None,
        feedback: Optional[float] = None,
    ) -> None:
        self._update_session(session_id, "completed", time.time(),
                              result_summary, feedback)

    def fail_session(
        self,
        session_id: str,
        reason: Optional[str] = None,
        feedback: Optional[float] = None,
    ) -> None:
        self._update_session(session_id, "failed", time.time(),
                              {"error": reason} if reason else None, feedback)

    def rollback_session(
        self,
        session_id: str,
        reason: Optional[str] = None,
        feedback: Optional[float] = None,
    ) -> None:
        self._update_session(session_id, "rolled_back", time.time(),
                              {"reason": reason} if reason else None, feedback)

    def get_session(self, session_id: str) -> Optional[ExecutionSession]:
        row = self._fetch_session(session_id)
        return self._row_to_session(row) if row else None

    def recent_sessions(
        self, limit: int = 20, status: Optional[str] = None,
    ) -> List[ExecutionSession]:
        rows = self._fetch_recent_sessions(limit, status)
        return [self._row_to_session(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════
    # 2 – Session events
    # ═══════════════════════════════════════════════════════════════════

    def add_event(
        self,
        session_id: str,
        event_type: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Add an ordered event to a session.  Returns event_id."""
        seq = self._next_sequence(session_id)
        eid = self._insert_event(session_id, seq, event_type, detail or {})
        return eid

    def session_events(
        self, session_id: str, limit: int = 100,
    ) -> List[SessionEvent]:
        rows = self._fetch_events(session_id, limit)
        return [self._row_to_event(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════
    # 3 – Reasoning traces
    # ═══════════════════════════════════════════════════════════════════

    def add_reasoning(
        self,
        session_id: str,
        trace_type: str,
        target_id: str,
        reason: str,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Record why a decision was made.  Returns trace_id."""
        tid = self._insert_reasoning(session_id, trace_type, target_id,
                                      reason, evidence or {})
        return tid

    def session_reasoning(
        self, session_id: str,
    ) -> List[ReasoningTrace]:
        rows = self._fetch_reasoning(session_id)
        return [self._row_to_reasoning(r) for r in rows]

    def reasoning_by_type(
        self, trace_type: str, limit: int = 50,
    ) -> List[ReasoningTrace]:
        rows = self._fetch_reasoning_by_type(trace_type, limit)
        return [self._row_to_reasoning(r) for r in rows]

    # ═══════════════════════════════════════════════════════════════════
    # 4 – Task memory
    # ═══════════════════════════════════════════════════════════════════

    def create_task(
        self,
        description: str,
        symbols: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        impact_chain: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a cross-query task record.  Returns task_id."""
        tid = str(uuid.uuid4())
        now = time.time()
        self._insert_task(tid, description, json.dumps(symbols or []),
                           json.dumps(files or []),
                           json.dumps(impact_chain or []),
                           "active", now, now,
                           json.dumps(metadata or {}))
        logger.info("Task created: %s — %s", tid[:8], description[:60])
        return tid

    def update_task(
        self,
        task_id: str,
        symbols: Optional[List[str]] = None,
        files: Optional[List[str]] = None,
        impact_chain: Optional[List[str]] = None,
        status: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_task(task_id, symbols, files, impact_chain, status, metadata)

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        row = self._fetch_task(task_id)
        return self._row_to_task(row) if row else None

    def find_tasks(
        self, query: str, limit: int = 10,
    ) -> List[TaskRecord]:
        """Find tasks whose description contains keywords."""
        rows = self._fetch_tasks_like(query, limit)
        return [self._row_to_task(r) for r in rows]

    def complete_task(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_task(task_id, status="completed", metadata=metadata)

    def fail_task(
        self, task_id: str, metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_task(task_id, status="failed", metadata=metadata)

    # ═══════════════════════════════════════════════════════════════════
    # 5 – Plan history
    # ═══════════════════════════════════════════════════════════════════

    def create_plan(
        self,
        session_id: str,
        task_id: str,
        steps: List[Dict[str, Any]],
    ) -> str:
        """Create a new plan attempt.  Auto-increments plan_number."""
        pid = str(uuid.uuid4())
        pn = self._next_plan_number(task_id)
        self._insert_plan(pid, session_id, task_id, pn,
                           json.dumps(steps), "proposed", None, None,
                           time.time(), None)
        return pid

    def update_plan_result(
        self, plan_id: str, result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        status = "failed" if error else "succeeded"
        self._update_plan(plan_id, status, time.time(),
                           json.dumps(result) if result else None, error)

    def succeed_plan(
        self, plan_id: str, result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_plan(plan_id, "succeeded", time.time(),
                           json.dumps(result) if result else None, None)

    def fail_plan(
        self, plan_id: str, error: str,
        partial_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._update_plan(plan_id, "failed", time.time(),
                           json.dumps(partial_result) if partial_result else None,
                           error)

    def get_plan(self, plan_id: str) -> Optional[PlanAttempt]:
        row = self._fetch_plan(plan_id)
        return self._row_to_plan(row) if row else None

    def task_plans(self, task_id: str) -> List[PlanAttempt]:
        """All plans for a task, ordered by plan_number."""
        rows = self._fetch_task_plans(task_id)
        return [self._row_to_plan(r) for r in rows]

    def session_plans(self, session_id: str) -> List[PlanAttempt]:
        rows = self._fetch_session_plans(session_id)
        return [self._row_to_plan(r) for r in rows]

    def latest_plan(self, task_id: str) -> Optional[PlanAttempt]:
        """Most recent plan for a task."""
        rows = self._fetch_task_plans(task_id, limit=1)
        return self._row_to_plan(rows[0]) if rows else None

    # ═══════════════════════════════════════════════════════════════════
    # Utility
    # ═══════════════════════════════════════════════════════════════════

    def clear(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                for table in ("sessions", "session_events", "reasoning_traces",
                              "task_memory", "plan_history"):
                    conn.execute(f"DELETE FROM {table}")
                conn.commit()
            finally:
                conn.close()

    # ═══════════════════════════════════════════════════════════════════
    # Schema
    # ═══════════════════════════════════════════════════════════════════

    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            conn = self._connect()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        strategy TEXT DEFAULT '',
                        started_at REAL NOT NULL,
                        completed_at REAL,
                        status TEXT DEFAULT 'active',
                        result_summary TEXT,
                        feedback REAL,
                        metadata TEXT DEFAULT '{}'
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS session_events (
                        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL REFERENCES sessions(session_id),
                        sequence INTEGER NOT NULL,
                        event_type TEXT NOT NULL,
                        detail TEXT DEFAULT '{}',
                        timestamp REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reasoning_traces (
                        trace_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL REFERENCES sessions(session_id),
                        trace_type TEXT NOT NULL,
                        target_id TEXT DEFAULT '',
                        reason TEXT NOT NULL,
                        evidence TEXT DEFAULT '{}',
                        timestamp REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS task_memory (
                        task_id TEXT PRIMARY KEY,
                        description TEXT NOT NULL,
                        symbols TEXT DEFAULT '[]',
                        files TEXT DEFAULT '[]',
                        impact_chain TEXT DEFAULT '[]',
                        previous_attempts TEXT DEFAULT '[]',
                        status TEXT DEFAULT 'active',
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        metadata TEXT DEFAULT '{}'
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS plan_history (
                        plan_id TEXT PRIMARY KEY,
                        session_id TEXT NOT NULL,
                        task_id TEXT NOT NULL REFERENCES task_memory(task_id),
                        plan_number INTEGER NOT NULL,
                        steps TEXT DEFAULT '[]',
                        status TEXT DEFAULT 'proposed',
                        result TEXT,
                        error TEXT,
                        started_at REAL NOT NULL,
                        completed_at REAL,
                        FOREIGN KEY (task_id) REFERENCES task_memory(task_id)
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_status
                    ON sessions(status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_sessions_ts
                    ON sessions(started_at)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_events_session
                    ON session_events(session_id, sequence)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reasoning_session
                    ON reasoning_traces(session_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reasoning_type
                    ON reasoning_traces(trace_type)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tasks_status
                    ON task_memory(status)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_plans_task
                    ON plan_history(task_id, plan_number)
                """)

                # Migration: add dag_trace column (Phase 16 – DAG Replay)
                try:
                    conn.execute("ALTER TABLE sessions ADD COLUMN dag_trace TEXT")
                except sqlite3.OperationalError:
                    pass  # column already exists

                conn.commit()
            finally:
                conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.row_factory = sqlite3.Row
        return conn

    # ── session CRUD ────────────────────────────────────────────────────

    def _insert_session(self, sid: str, query: str, strategy: str,
                         ts: float, metadata: Dict[str, Any]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO sessions (session_id, query, strategy, started_at, status, metadata)"
                    " VALUES (?, ?, ?, ?, 'active', ?)",
                    (sid, query, strategy, ts, json.dumps(metadata)),
                )
                conn.commit()
            finally:
                conn.close()

    def _update_session(self, sid: str, status: str, ts: float,
                         result: Optional[Dict], feedback: Optional[float]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                parts = ["UPDATE sessions SET status=?, completed_at=?"]
                params: List[Any] = [status, ts]
                if result is not None:
                    parts.append(", result_summary=?")
                    params.append(json.dumps(result))
                if feedback is not None:
                    parts.append(", feedback=?")
                    params.append(feedback)
                parts.append(" WHERE session_id=?")
                params.append(sid)
                conn.execute(" ".join(parts), params)
                conn.commit()
            finally:
                conn.close()

    def _fetch_session(self, sid: str) -> Optional[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM sessions WHERE session_id=?", (sid,)
                ).fetchone()
            finally:
                conn.close()

    def _fetch_recent_sessions(self, limit: int, status: Optional[str]) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                if status:
                    return conn.execute(
                        "SELECT * FROM sessions WHERE status=? ORDER BY started_at DESC LIMIT ?",
                        (status, limit),
                    ).fetchall()
                return conn.execute(
                    "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            finally:
                conn.close()

    # ── DAG trace storage ────────────────────────────────────────────────

    def store_dag_trace(
        self, session_id: str, dag_trace: Dict[str, Any],
    ) -> None:
        """Store the DAG execution trace for a session."""
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "UPDATE sessions SET dag_trace=? WHERE session_id=?",
                    (json.dumps(dag_trace), session_id),
                )
                conn.commit()
            finally:
                conn.close()

    def get_dag_trace(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the DAG execution trace for a session."""
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT dag_trace FROM sessions WHERE session_id=?", (session_id,)
                ).fetchone()
                if row and row["dag_trace"]:
                    return json.loads(row["dag_trace"])
                return None
            finally:
                conn.close()

    @staticmethod
    def _row_to_session(row: sqlite3.Row) -> ExecutionSession:
        return ExecutionSession(
            session_id=row["session_id"],
            query=row["query"],
            strategy=row["strategy"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            status=row["status"],
            result_summary=json.loads(row["result_summary"]) if row["result_summary"] else None,
            feedback=row["feedback"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # ── event CRUD ──────────────────────────────────────────────────────

    def _next_sequence(self, session_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT MAX(sequence) as mx FROM session_events WHERE session_id=?",
                    (session_id,),
                ).fetchone()
                return (row["mx"] or 0) + 1
            finally:
                conn.close()

    def _insert_event(self, session_id: str, seq: int, etype: str,
                       detail: Dict[str, Any]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO session_events (session_id, sequence, event_type, detail, timestamp)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (session_id, seq, etype, json.dumps(detail), time.time()),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def _fetch_events(self, session_id: str, limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM session_events WHERE session_id=? ORDER BY sequence ASC LIMIT ?",
                    (session_id, limit),
                ).fetchall()
            finally:
                conn.close()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> SessionEvent:
        return SessionEvent(
            event_id=row["event_id"],
            session_id=row["session_id"],
            sequence=row["sequence"],
            event_type=row["event_type"],
            detail=json.loads(row["detail"]) if row["detail"] else {},
            timestamp=row["timestamp"],
        )

    # ── reasoning CRUD ──────────────────────────────────────────────────

    def _insert_reasoning(self, session_id: str, trace_type: str,
                           target_id: str, reason: str,
                           evidence: Dict[str, Any]) -> int:
        with self._lock:
            conn = self._connect()
            try:
                cur = conn.execute(
                    "INSERT INTO reasoning_traces (session_id, trace_type, target_id, reason, evidence, timestamp)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (session_id, trace_type, target_id, reason,
                     json.dumps(evidence), time.time()),
                )
                conn.commit()
                return cur.lastrowid
            finally:
                conn.close()

    def _fetch_reasoning(self, session_id: str) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM reasoning_traces WHERE session_id=? ORDER BY timestamp ASC",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_reasoning_by_type(self, trace_type: str, limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM reasoning_traces WHERE trace_type=? ORDER BY timestamp DESC LIMIT ?",
                    (trace_type, limit),
                ).fetchall()
            finally:
                conn.close()

    @staticmethod
    def _row_to_reasoning(row: sqlite3.Row) -> ReasoningTrace:
        return ReasoningTrace(
            trace_id=row["trace_id"],
            session_id=row["session_id"],
            trace_type=row["trace_type"],
            target_id=row["target_id"],
            reason=row["reason"],
            evidence=json.loads(row["evidence"]) if row["evidence"] else {},
            timestamp=row["timestamp"],
        )

    # ── task CRUD ───────────────────────────────────────────────────────

    def _insert_task(self, tid: str, desc: str, symbols: str, files: str,
                      impact: str, status: str, created: float, updated: float,
                      metadata: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO task_memory (task_id, description, symbols, files, impact_chain, status, created_at, updated_at, metadata)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (tid, desc, symbols, files, impact, status, created, updated, metadata),
                )
                conn.commit()
            finally:
                conn.close()

    def _update_task(self, tid: str,
                      symbols: Optional[List[str]] = None,
                      files: Optional[List[str]] = None,
                      impact_chain: Optional[List[str]] = None,
                      status: Optional[str] = None,
                      metadata: Optional[Dict] = None) -> None:
        with self._lock:
            conn = self._connect()
            try:
                parts = ["UPDATE task_memory SET updated_at=?"]
                params: List[Any] = [time.time()]
                if symbols is not None:
                    parts.append(", symbols=?")
                    params.append(json.dumps(symbols))
                if files is not None:
                    parts.append(", files=?")
                    params.append(json.dumps(files))
                if impact_chain is not None:
                    parts.append(", impact_chain=?")
                    params.append(json.dumps(impact_chain))
                if status is not None:
                    parts.append(", status=?")
                    params.append(status)
                if metadata is not None:
                    parts.append(", metadata=?")
                    params.append(json.dumps(metadata))
                parts.append(" WHERE task_id=?")
                params.append(tid)
                conn.execute(" ".join(parts), params)
                conn.commit()
            finally:
                conn.close()

    def _fetch_task(self, tid: str) -> Optional[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM task_memory WHERE task_id=?", (tid,)
                ).fetchone()
            finally:
                conn.close()

    def _fetch_tasks_like(self, query: str, limit: int) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                like = f"%{query}%"
                return conn.execute(
                    "SELECT * FROM task_memory WHERE description LIKE ?"
                    " ORDER BY updated_at DESC LIMIT ?",
                    (like, limit),
                ).fetchall()
            finally:
                conn.close()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> TaskRecord:
        return TaskRecord(
            task_id=row["task_id"],
            description=row["description"],
            symbols=json.loads(row["symbols"]) if row["symbols"] else [],
            files=json.loads(row["files"]) if row["files"] else [],
            impact_chain=json.loads(row["impact_chain"]) if row["impact_chain"] else [],
            previous_attempts=json.loads(row["previous_attempts"]) if row["previous_attempts"] else [],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # ── plan CRUD ───────────────────────────────────────────────────────

    def _next_plan_number(self, task_id: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                row = conn.execute(
                    "SELECT MAX(plan_number) as mx FROM plan_history WHERE task_id=?",
                    (task_id,),
                ).fetchone()
                return (row["mx"] or 0) + 1
            finally:
                conn.close()

    def _insert_plan(self, pid: str, sid: str, tid: str, pn: int,
                      steps: str, status: str, result: Optional[str],
                      error: Optional[str], started: float,
                      completed: Optional[float]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.execute(
                    "INSERT INTO plan_history (plan_id, session_id, task_id, plan_number, steps, status, result, error, started_at, completed_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (pid, sid, tid, pn, steps, status, result, error, started, completed),
                )
                conn.commit()
            finally:
                conn.close()

    def _update_plan(self, pid: str, status: str, completed: float,
                      result: Optional[str], error: Optional[str]) -> None:
        with self._lock:
            conn = self._connect()
            try:
                parts = ["UPDATE plan_history SET status=?, completed_at=?"]
                params: List[Any] = [status, completed]
                if result is not None:
                    parts.append(", result=?")
                    params.append(result)
                if error is not None:
                    parts.append(", error=?")
                    params.append(error)
                parts.append(" WHERE plan_id=?")
                params.append(pid)
                conn.execute(" ".join(parts), params)
                conn.commit()
            finally:
                conn.close()

    def _fetch_plan(self, pid: str) -> Optional[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM plan_history WHERE plan_id=?", (pid,)
                ).fetchone()
            finally:
                conn.close()

    def _fetch_task_plans(self, task_id: str, limit: int = 50) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM plan_history WHERE task_id=? ORDER BY plan_number DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
            finally:
                conn.close()

    def _fetch_session_plans(self, session_id: str) -> List[sqlite3.Row]:
        with self._lock:
            conn = self._connect()
            try:
                return conn.execute(
                    "SELECT * FROM plan_history WHERE session_id=? ORDER BY started_at DESC",
                    (session_id,),
                ).fetchall()
            finally:
                conn.close()

    @staticmethod
    def _row_to_plan(row: sqlite3.Row) -> PlanAttempt:
        return PlanAttempt(
            plan_id=row["plan_id"],
            session_id=row["session_id"],
            task_id=row["task_id"],
            plan_number=row["plan_number"],
            steps=json.loads(row["steps"]) if row["steps"] else [],
            status=row["status"],
            result=json.loads(row["result"]) if row["result"] else None,
            error=row["error"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )
