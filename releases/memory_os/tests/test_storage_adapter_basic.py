"""Task 4 — Storage adapter: 5 tests for SQLite-backed IStorage."""

import os
import tempfile

import pytest

from releases.memory_os.core.memory.storage_adapter import IsolationViolation, SQLiteStorage
from releases.memory_os.core.models.memory import MemoryEntry, MemoryLayer, MemoryScope


@pytest.fixture
def storage():
    tmp = tempfile.mkdtemp(prefix="mem_test_")
    s = SQLiteStorage(base_dir=tmp)
    yield s
    s.close()


def _entry(tenant: str = "t1", project: str = "p1", key: str = "k1"):
    return MemoryEntry(
        entry_id=f"e-{key}",
        tenant_id=tenant,
        project_id=project,
        agent_id="a1",
        layer=MemoryLayer.EPISODIC,
        key=key,
        content_hash="h1",
        payload={"data": key},
        scope=MemoryScope.PROJECT,
        created_at=1000,
    )


class TestStorageBasic:
    def test_insert_and_select(self, storage):
        e = _entry()
        storage.insert(e)
        rows = storage.select("t1", "p1", MemoryScope.PROJECT)
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "e-k1"

    def test_select_scoped_by_tenant(self, storage):
        storage.insert(_entry("t1", "p1", "k1"))
        storage.insert(_entry("t2", "p1", "k2"))
        rows = storage.select("t1", "p1", MemoryScope.PROJECT)
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "e-k1"

    def test_select_scoped_by_project(self, storage):
        storage.insert(_entry("t1", "p1", "k1"))
        storage.insert(_entry("t1", "p2", "k2"))
        rows = storage.select("t1", "p1", MemoryScope.PROJECT)
        assert len(rows) == 1
        assert rows[0]["project_id"] == "p1"

    def test_delete(self, storage):
        e = _entry()
        storage.insert(e)
        assert storage.delete("e-k1", "t1") is True
        rows = storage.select("t1", "p1", MemoryScope.PROJECT)
        assert len(rows) == 0

    def test_count(self, storage):
        storage.insert(_entry("t1", "p1", "k1"))
        storage.insert(_entry("t1", "p1", "k2"))
        assert storage.count("t1") == 2
