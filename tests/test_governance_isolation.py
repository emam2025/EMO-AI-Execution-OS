"""Governance Layer — Audit Trail tests for module-level API.

Coverage:
  Audit Trail: append-only, SHA-256 chain integrity, signature verification, export
"""

import pytest
from core.governance import audit_trail


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_governance():
    audit_trail.reset()
    audit_trail.init("test-signing-key")


# ═════════════════════════════════════════════════════════════════
#  Audit Trail (6 tests)
# ═════════════════════════════════════════════════════════════════

class TestAuditTrail:
    def test_append_only_no_modification(self):
        r1 = audit_trail.append("submit", "p1", "t1", "task:123", "allowed")
        r2 = audit_trail.append("query", "p1", "t1", "task:123", "allowed")
        log = audit_trail.get_log()
        assert len(log) == 2
        assert log[0]["record_id"] == r1.record_id
        assert log[1]["record_id"] == r2.record_id

    def test_chain_integrity_no_violations(self):
        audit_trail.append("submit", "p1", "t1", "task:1", "allowed")
        audit_trail.append("query", "p2", "t1", "task:1", "allowed")
        audit_trail.append("admin", "admin-1", "t1", "system", "allowed")
        assert audit_trail.verify_integrity() == []

    def test_chain_integrity_detects_tamper(self):
        audit_trail.append("submit", "p1", "t1", "task:1", "allowed")
        audit_trail._AUDIT_LOG[0]["signature"] = "tampered"
        violations = audit_trail.verify_integrity()
        assert len(violations) >= 1

    def test_signature_verification(self):
        record = audit_trail.append("submit", "p1", "t1", "task:1", "allowed")
        log = audit_trail.get_log()
        assert audit_trail.verify_signature(log[-1]) is True

    def test_content_tamper_detected_by_signature(self):
        audit_trail.append("submit", "p1", "t1", "task:1", "allowed")
        audit_trail._AUDIT_LOG[0]["outcome"] = "blocked"
        assert audit_trail.verify_signature(audit_trail._AUDIT_LOG[0]) is False

    def test_tampered_signature_fails_verification(self):
        r = audit_trail.append("query", "p2", "t2", "task:2", "denied")
        log = audit_trail.get_log()
        record = dict(log[-1])
        record["signature"] = "tampered"
        assert audit_trail.verify_signature(record) is False
