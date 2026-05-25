import os
import json
import aiosqlite
from typing import Dict, List, Optional
from datetime import datetime


DB_PATH = os.getenv("EMO_DB_PATH", "emo_ai.db")

INIT_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_active     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    path          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_sessions (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name          TEXT NOT NULL DEFAULT 'جلسة جديدة',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id            TEXT PRIMARY KEY,
    project_id    TEXT REFERENCES projects(id),
    session_id    TEXT REFERENCES project_sessions(id),
    user_id       TEXT REFERENCES users(id),
    name          TEXT NOT NULL DEFAULT 'محادثة جديدة',
    is_active     INTEGER NOT NULL DEFAULT 0,
    is_archived   INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id            TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content       TEXT NOT NULL,
    file_name     TEXT,
    file_type     TEXT,
    file_size     INTEGER,
    file_base64   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    session_id    TEXT REFERENCES project_sessions(id),
    project_id    TEXT REFERENCES projects(id),
    message       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'complete', 'error')),
    result        TEXT,
    error         TEXT,
    agent         TEXT,
    tool_used     TEXT,
    progress      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT REFERENCES users(id),
    action        TEXT NOT NULL,
    resource      TEXT,
    details       TEXT,
    ip_address    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_projects_active ON projects(is_active);
CREATE INDEX IF NOT EXISTS idx_projects_archived ON projects(is_archived);
CREATE INDEX IF NOT EXISTS idx_sessions_project ON project_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON project_sessions(is_active);
CREATE INDEX IF NOT EXISTS idx_sessions_archived ON project_sessions(is_archived);
CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id);
CREATE INDEX IF NOT EXISTS idx_conversations_session ON conversations(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
"""


class Database:
    """Async SQLite database manager for EMO AI."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        if self._initialized:
            return
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(INIT_SQL)
            # Migration: add is_archived column to conversations if it doesn't exist
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN is_archived INTEGER NOT NULL DEFAULT 0")
                await db.commit()
            except Exception:
                pass
            # Migration: add project_id and session_id to conversations
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN project_id TEXT REFERENCES projects(id)")
                await db.commit()
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN session_id TEXT REFERENCES project_sessions(id)")
                await db.commit()
            except Exception:
                pass
            # Migration: add project_id and session_id to tasks
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT REFERENCES projects(id)")
                await db.commit()
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE tasks ADD COLUMN session_id TEXT REFERENCES project_sessions(id)")
                await db.commit()
            except Exception:
                pass
            await db.commit()
        self._initialized = True

    # --- Tasks ---

    async def create_task(
        self,
        task_id: str,
        message: str,
        conversation_id: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO tasks (id, message, conversation_id, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'pending', ?, ?)",
                (task_id, message, conversation_id, now, now),
            )
            await db.commit()
        return {
            "id": task_id,
            "message": message,
            "status": "pending",
            "created_at": now,
        }

    async def update_task(
        self,
        task_id: str,
        **kwargs,
    ) -> Optional[Dict]:
        now = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [now, task_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE tasks SET {fields}, updated_at = ? WHERE id = ?",
                values,
            )
            await db.commit()
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def get_task(self, task_id: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def list_tasks(
        self,
        limit: int = 10,
        status: Optional[str] = None,
    ) -> List[Dict]:
        query = "SELECT * FROM tasks"
        params: list = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def cleanup_old_tasks(self, max_age_hours: int = 24) -> int:
        """Delete tasks older than max_age_hours."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM tasks WHERE created_at < datetime('now', ?)",
                (f"-{max_age_hours} hours",),
            )
            await db.commit()
            return cursor.rowcount

    # --- Projects ---

    async def create_project(
        self,
        project_id: str,
        name: str,
        path: str,
        description: str = "",
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO projects (id, name, path, description, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (project_id, name, path, description, now, now),
            )
            await db.commit()
        return {"id": project_id, "name": name, "path": path, "description": description, "created_at": now}

    async def get_projects(self, archived: bool = False) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT p.id, p.name, p.path, p.description, p.is_active, p.is_archived, p.created_at, "
                "COUNT(DISTINCT s.id) as session_count, COUNT(DISTINCT c.id) as conversation_count "
                "FROM projects p "
                "LEFT JOIN project_sessions s ON p.id = s.project_id "
                "LEFT JOIN conversations c ON p.id = c.project_id "
                "WHERE p.is_archived = ? "
                "GROUP BY p.id ORDER BY p.updated_at DESC",
                (1 if archived else 0,)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def get_active_project(self) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT * FROM projects WHERE is_active = 1 LIMIT 1")
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def activate_project(self, project_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE projects SET is_active = 0")
            await db.execute("UPDATE projects SET is_active = 1 WHERE id = ?", (project_id,))
            await db.commit()
        return True

    async def archive_project(self, project_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE projects SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            await db.commit()
        return True

    async def unarchive_project(self, project_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE projects SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, project_id),
            )
            await db.commit()
        return True

    async def delete_project(self, project_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM project_sessions WHERE project_id = ?", (project_id,))
            await db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            await db.commit()
        return True

    async def update_project(self, project_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [now, project_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE projects SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    # --- Project Sessions ---

    async def create_session(
        self,
        session_id: str,
        project_id: str,
        name: str = "جلسة جديدة",
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO project_sessions (id, project_id, name, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, project_id, name, now, now),
            )
            await db.commit()
        return {"id": session_id, "project_id": project_id, "name": name, "created_at": now}

    async def get_sessions(self, project_id: str, archived: bool = False) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT s.id, s.name, s.is_active, s.is_archived, s.created_at, "
                "COUNT(DISTINCT c.id) as conversation_count "
                "FROM project_sessions s "
                "LEFT JOIN conversations c ON s.id = c.session_id "
                "WHERE s.project_id = ? AND s.is_archived = ? "
                "GROUP BY s.id ORDER BY s.updated_at DESC",
                (project_id, 1 if archived else 0)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def activate_session(self, session_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE project_sessions SET is_active = 0")
            await db.execute("UPDATE project_sessions SET is_active = 1 WHERE id = ?", (session_id,))
            await db.commit()
        return True

    async def archive_session(self, session_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE project_sessions SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()
        return True

    async def unarchive_session(self, session_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE project_sessions SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, session_id),
            )
            await db.commit()
        return True

    async def delete_session(self, session_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM project_sessions WHERE id = ?", (session_id,))
            await db.commit()
        return True

    async def update_session(self, session_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [now, session_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE project_sessions SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    # --- Conversations ---

    async def create_conversation(
        self,
        conv_id: str,
        name: str = "محادثة جديدة",
        user_id: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO conversations (id, name, user_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, name, user_id, now, now),
            )
            await db.commit()
        return {"id": conv_id, "name": name, "created_at": now}

    async def get_conversations(self, archived: bool = False) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT c.id, c.name, c.is_active, c.is_archived, c.created_at, "
                "COUNT(m.id) as message_count "
                "FROM conversations c LEFT JOIN messages m ON c.id = m.conversation_id "
                "WHERE c.is_archived = ? "
                "GROUP BY c.id ORDER BY c.updated_at DESC",
                (1 if archived else 0,)
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    async def activate_conversation(self, conv_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE conversations SET is_active = 0")
            await db.execute(
                "UPDATE conversations SET is_active = 1 WHERE id = ?",
                (conv_id,),
            )
            await db.commit()
        return True

    async def update_conversation_name(self, conv_id: str, name: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE conversations SET name = ?, updated_at = ? WHERE id = ?",
                (name, now, conv_id),
            )
            await db.commit()
        return True

    async def update_conversation(self, conv_id: str, **kwargs) -> bool:
        now = datetime.utcnow().isoformat()
        fields = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [now, conv_id]
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE conversations SET {fields}, updated_at = ? WHERE id = ?", values)
            await db.commit()
        return True

    async def archive_conversation(self, conv_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE conversations SET is_archived = 1, is_active = 0, updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            await db.commit()
        return True

    async def unarchive_conversation(self, conv_id: str) -> bool:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE conversations SET is_archived = 0, updated_at = ? WHERE id = ?",
                (now, conv_id),
            )
            await db.commit()
        return True

    async def delete_conversation(self, conv_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
            await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
            await db.commit()
        return True

    # --- Messages ---

    async def add_message(
        self,
        msg_id: str,
        conversation_id: str,
        role: str,
        content: str,
        file_name: Optional[str] = None,
        file_type: Optional[str] = None,
        file_size: Optional[int] = None,
        file_base64: Optional[str] = None,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, file_name, file_type, file_size, file_base64, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (msg_id, conversation_id, role, content, file_name, file_type, file_size, file_base64, now),
            )
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
            await db.commit()
        return {"id": msg_id, "role": role, "content": content, "created_at": now}

    async def get_messages(self, conversation_id: str) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC",
                (conversation_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_dict(r, cursor.description) for r in rows]

    # --- Users ---

    async def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
    ) -> Dict:
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO users (id, username, password_hash, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, username, password_hash, now, now),
            )
            await db.commit()
        return {"id": user_id, "username": username, "created_at": now}

    async def get_user(self, username: str) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM users WHERE username = ?", (username,)
            )
            row = await cursor.fetchone()
        if row:
            return self._row_to_dict(row, cursor.description)
        return None

    async def get_users_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            row = await cursor.fetchone()
        return row[0] if row else 0

    # --- Audit Logs ---

    async def log_action(
        self,
        action: str,
        user_id: Optional[str] = None,
        resource: Optional[str] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO audit_logs (user_id, action, resource, details, ip_address) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, action, resource, details, ip_address),
            )
            await db.commit()

    # --- Helpers ---

    @staticmethod
    def _row_to_dict(row: tuple, description: list) -> Dict:
        return {desc[0]: value for desc, value in zip(description, row)}


db = Database()
