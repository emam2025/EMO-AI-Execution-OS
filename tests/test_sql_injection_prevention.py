"""HIGH-001A Task 1 — SQL Injection Prevention Tests.

Tests the frozenset-based column whitelisting in core/db.py.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else os.getcwd(), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.db import (
    Database,
    InvalidColumnError,
    ALLOWED_TASK_COLUMNS,
    ALLOWED_PROJECT_COLUMNS,
    ALLOWED_SESSION_COLUMNS,
    ALLOWED_CONVERSATION_COLUMNS,
)


class TestColumnWhitelist:
    """_whitelist_columns unit tests."""

    def test_allows_valid_columns(self):
        result = Database._whitelist_columns(
            ALLOWED_TASK_COLUMNS, {"status": "complete", "progress": 100}, "tasks"
        )
        assert "status = ?" in result
        assert "progress = ?" in result
        assert result.count("?") == 2

    def test_rejects_invalid_column(self):
        with pytest.raises(InvalidColumnError) as exc:
            Database._whitelist_columns(
                ALLOWED_TASK_COLUMNS, {"evil_column": "x", "status": "ok"}, "tasks"
            )
        assert "evil_column" in str(exc.value)
        assert "tasks" in str(exc.value)

    def test_rejects_all_invalid(self):
        with pytest.raises(InvalidColumnError):
            Database._whitelist_columns(
                ALLOWED_TASK_COLUMNS,
                {"DROP TABLE users": "x", "1=1": "y"},
                "tasks",
            )

    def test_empty_provided_ok(self):
        # Empty kwargs is valid (no-op update)
        result = Database._whitelist_columns(
            ALLOWED_TASK_COLUMNS, {}, "tasks"
        )
        assert result == ""

    def test_frozenset_immutable(self):
        with pytest.raises(AttributeError):
            ALLOWED_TASK_COLUMNS.add("injected")  # type: ignore


class TestUpdateTaskSqlInjection:
    """Integration-level tests for update_task SQL safety."""

    @pytest.mark.asyncio
    async def test_update_task_valid_columns_succeeds(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        await db.initialize()
        await db.create_task("t1", "hello")
        from datetime import datetime
        result = await db.update_task("t1", status="complete", progress=100)
        assert result is not None
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_update_task_invalid_column_raises(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        db = Database(db_path)
        await db.initialize()
        await db.create_task("t1", "hello")
        with pytest.raises(InvalidColumnError):
            await db.update_task("t1", evil_injection="x", status="ok")
