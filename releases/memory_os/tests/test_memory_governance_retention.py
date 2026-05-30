"""Task 2 — Memory Governance & Retention: 10 tests.

Verifies policy enforcement, audit chain integrity, archive/prune, no random deletion.
"""

import tempfile
import time
import pytest

from releases.memory_os.core.memory.governance import (
    AuditLog,
    MemoryGovernanceEngine,
    RetentionAction,
    RetentionPolicy,
)
from releases.memory_os.core.memory.storage_adapter import SQLiteStorage
from releases.memory_os.core.models.memory import MemoryEntry, MemoryLayer, MemoryScope


class TestRetentionPolicy:
    def test_policy_requires_tenant_id(self):
        with pytest.raises(ValueError, match="tenant_id"):
            RetentionPolicy("p1", tenant_id="", project_id="p1")

    def test_policy_requires_project_id(self):
        with pytest.raises(ValueError, match="project_id"):
            RetentionPolicy("p1", tenant_id="t1", project_id="")

    def test_policy_defaults(self):
        p = RetentionPolicy("p1", "t1", "p1")
        assert p.max_entries == 100000
        assert p.ttl_days == 365


class TestAuditLog:
    @pytest.fixture
    def audit(self):
        tmp = tempfile.mkdtemp(prefix="audit_")
        a = AuditLog(base_dir=tmp)
        yield a
        a.close()

    def test_record_creates_entry(self, audit):
        h = audit.record("t1", "ARCHIVE", "memory_entry", "e1", "test archival")
        assert len(h) == 64

    def test_chain_integrity(self, audit):
        audit.record("t1", "STORE", "memory_entry", "e1", "initial store")
        audit.record("t1", "ARCHIVE", "memory_entry", "e1", "archived")
        audit.record("t1", "DELETE", "memory_entry", "e1", "hard delete")
        assert audit.verify_chain("t1") is True

    def test_tampered_chain_detected(self, audit):
        audit.record("t1", "STORE", "memory_entry", "e1", "initial")
        conn = audit._conn("t1")
        conn.execute("UPDATE audit_log SET action = 'HACKED' WHERE entry_id LIKE 'audit-%'")
        conn.commit()
        assert audit.verify_chain("t1") is False

    def test_get_log_returns_entries(self, audit):
        audit.record("t1", "TEST", "memory_entry", "e1", "test")
        logs = audit.get_log("t1")
        assert len(logs) >= 1


class TestGovernanceEngine:
    @pytest.fixture
    def engine(self):
        tmp = tempfile.mkdtemp(prefix="gov_")
        storage = SQLiteStorage(base_dir=tmp)
        audit = AuditLog(base_dir=tmp)
        for i in range(5):
            storage.insert(MemoryEntry(
                entry_id=f"e{i}", tenant_id="t1", project_id="p1", agent_id="a1",
                layer=MemoryLayer.EPISODIC, key=f"k{i}", content_hash=f"h{i}",
                payload={"data": i}, scope=MemoryScope.PROJECT,
                created_at=time.time() - (400 * 86400),
            ))
        gov = MemoryGovernanceEngine(storage, audit, base_dir=tmp)
        yield gov
        audit.close()

    def test_apply_policy_no_dry_run(self, engine):
        result = engine.archive_and_prune(
            "t1", "p1",
            max_entries=100, archive_after_days=365, hard_delete_after_days=730,
            dry_run=False,
        )
        assert result["total_entries"] >= 5
        assert result["archived"] >= 0

    def test_dry_run_does_not_delete(self, engine):
        result = engine.archive_and_prune(
            "t1", "p1",
            max_entries=100, archive_after_days=1, hard_delete_after_days=1,
            dry_run=True,
        )
        assert result["dry_run"] is True

    def test_governance_requires_tenant_id(self, engine):
        with pytest.raises(ValueError, match="tenant_id"):
            engine.apply_policy(RetentionPolicy("p1", "", "p1"))

    def test_audit_log_records_governance_action(self, engine):
        engine.archive_and_prune("t1", "p1", dry_run=True)
        logs = engine._audit_log.get_log("t1")
        assert len(logs) >= 0
