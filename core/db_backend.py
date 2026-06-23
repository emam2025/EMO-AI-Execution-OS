"""
Unified database backend — aiosqlite ↔ asyncpg abstraction.

Environment variable priority:
  1. DATABASE_URL (postgres://... or sqlite:///...)
  2. EMO_DB_PATH  (path to SQLite file, default: emo_ai.db)
"""

import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.db_backend")

# ── URL parsing ─────────────────────────────────────────────────────────

DEFAULT_SQLITE_PATH = os.getenv("EMO_DB_PATH", "emo_ai.db")
DATABASE_URL = os.getenv("DATABASE_URL", "")


def _parse_url(url: str) -> tuple[str, dict]:
    """Return (scheme, config_dict) from a database URL."""
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return ("postgresql", {"url": url})
    if url.startswith("sqlite:///"):
        path = url[10:]
        return ("sqlite", {"path": path})
    return ("", {})


def _detect_backend() -> tuple[str, dict]:
    """Auto-detect which backend to use."""
    if DATABASE_URL:
        scheme, cfg = _parse_url(DATABASE_URL)
        if scheme == "postgresql":
            return ("postgresql", cfg)
        if scheme == "sqlite":
            return ("sqlite", cfg)
        logger.warning("Unknown DATABASE_URL scheme, falling back to SQLite")
    return ("sqlite", {"path": DEFAULT_SQLITE_PATH})


# ── Parameter placeholder translation ───────────────────────────────────

_SQLITE_PLACEHOLDER = re.compile(r"(?<!\?)\?(?!\?|')")


def _translate_to_pg(sql: str) -> str:
    """Convert SQLite `?` placeholders to PostgreSQL `$1` style."""
    i = 0
    def _repl(m):
        nonlocal i
        i += 1
        return f"${i}"
    return _SQLITE_PLACEHOLDER.sub(_repl, sql)


# ── Abstract backend ────────────────────────────────────────────────────

class Cursor(ABC):
    """Unified cursor abstraction."""

    @abstractmethod
    async def fetchone(self):
        ...

    @abstractmethod
    async def fetchall(self):
        ...

    @property
    @abstractmethod
    def description(self):
        ...


class Connection(ABC):
    """Unified connection abstraction."""

    @abstractmethod
    async def execute(self, sql: str, parameters: tuple = ()):
        ...

    @abstractmethod
    async def executescript(self, script: str):
        ...

    @abstractmethod
    async def commit(self):
        ...

    @abstractmethod
    async def rollback(self):
        ...

    @abstractmethod
    async def close(self):
        ...

    @abstractmethod
    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        ...

    @abstractmethod
    async def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        ...

    @staticmethod
    @abstractmethod
    def _translate(sql: str) -> str:
        """Convert SQLite-isms to backend-native SQL.
        Override in each subclass. Default: identity.
        """
        ...


class DatabaseBackend(ABC):
    """Factory for database connections."""

    @abstractmethod
    async def connect(self) -> Connection:
        ...


# ── SQLite backend ──────────────────────────────────────────────────────

class _SQLiteCursor(Cursor):
    def __init__(self, cursor):
        self._cursor = cursor

    async def fetchone(self):
        return await self._cursor.fetchone()

    async def fetchall(self):
        return await self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description


class _SQLiteConnection(Connection):
    def __init__(self, path: str):
        import aiosqlite
        self._conn = None
        self._path = path

    async def connect(self):
        import aiosqlite
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        return self

    @staticmethod
    def _translate(sql: str) -> str:
        return sql

    async def execute(self, sql: str, parameters: tuple = ()):
        tsql = self._translate(sql)
        c = await self._conn.execute(tsql, parameters)
        return _SQLiteCursor(c)

    async def executescript(self, script: str):
        await self._conn.executescript(script)

    async def commit(self):
        await self._conn.commit()

    async def rollback(self):
        await self._conn.rollback()

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        tsql = self._translate(sql)
        c = await self._conn.execute(tsql, parameters)
        row = await c.fetchone()
        return dict(row) if row else None

    async def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        tsql = self._translate(sql)
        c = await self._conn.execute(tsql, parameters)
        rows = await c.fetchall()
        return [dict(r) for r in rows]

    def __await__(self):
        return self.connect().__await__()


class _SQLiteBackend(DatabaseBackend):
    def __init__(self, path: str):
        self._path = path

    async def connect(self) -> _SQLiteConnection:
        conn = _SQLiteConnection(self._path)
        await conn.connect()
        return conn


# ── PostgreSQL backend ─────────────────────────────────────────────────

class _PGCursor(Cursor):
    def __init__(self, rows: list, colnames: tuple):
        self._rows = rows
        self._colnames = colnames
        self._idx = 0

    async def fetchone(self):
        if self._idx >= len(self._rows):
            return None
        r = self._rows[self._idx]
        self._idx += 1
        return r

    async def fetchall(self):
        remaining = self._rows[self._idx:]
        self._idx = len(self._rows)
        return remaining

    @property
    def description(self):
        return self._colnames


class _PGConnection(Connection):
    def __init__(self, url: str):
        self._url = url
        self._conn = None

    async def connect(self):
        import asyncpg
        self._conn = await asyncpg.connect(self._url)
        return self

    @staticmethod
    def _translate(sql: str) -> str:
        sql = _translate_to_pg(sql)
        sql = sql.replace("datetime('now')", "NOW()")
        sql = sql.replace('datetime("now")', "NOW()")
        return sql

    async def execute(self, sql: str, parameters: tuple = ()):
        tsql = self._translate(sql)
        if parameters:
            stmt = await self._conn.prepare(tsql)
            rows = await stmt.fetch(*parameters)
        else:
            rows = await self._conn.fetch(tsql)
        if rows:
            colnames = tuple(rows[0].keys()) if rows else ()
            dict_rows = [dict(r) for r in rows]
        else:
            colnames = ()
            dict_rows = []
        return _PGCursor(dict_rows, colnames)

    async def executescript(self, script: str):
        # Split by semicolon and execute each DDL/DML statement
        statements = [s.strip() for s in script.split(";") if s.strip()]
        for stmt in statements:
            if not stmt:
                continue
            tsql = self._translate(stmt)
            await self._conn.execute(tsql)

    async def commit(self):
        # asyncpg auto-commits DDL by default; explicit commit for transactions
        pass

    async def rollback(self):
        await self._conn.execute("ROLLBACK")

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[Dict]:
        tsql = self._translate(sql)
        if parameters:
            row = await self._conn.fetchrow(tsql, *parameters)
        else:
            row = await self._conn.fetchrow(tsql)
        return dict(row) if row else None

    async def fetchall(self, sql: str, parameters: tuple = ()) -> List[Dict]:
        tsql = self._translate(sql)
        if parameters:
            rows = await self._conn.fetch(tsql, *parameters)
        else:
            rows = await self._conn.fetch(tsql)
        return [dict(r) for r in rows]

    def __await__(self):
        return self.connect().__await__()


class _PostgresBackend(DatabaseBackend):
    def __init__(self, url: str):
        self._url = url

    async def connect(self) -> _PGConnection:
        conn = _PGConnection(self._url)
        await conn.connect()
        return conn


# ── Factory ─────────────────────────────────────────────────────────────

def create_backend() -> DatabaseBackend:
    """Create the appropriate backend from environment config."""
    kind, cfg = _detect_backend()
    if kind == "postgresql":
        logger.info("Using PostgreSQL backend: %s", cfg["url"][:30] + "...")
        return _PostgresBackend(cfg["url"])
    logger.info("Using SQLite backend: %s", cfg["path"])
    return _SQLiteBackend(cfg["path"])
