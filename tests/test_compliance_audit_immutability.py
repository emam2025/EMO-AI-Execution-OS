"""Phase J2 — Compliance Audit Immutability Tests.  # LAW-5 LAW-11 LAW-12 LAW-26 LAW-27 RULE-1 RULE-3

10 tests across 3 groups:
  1. Audit Trail Collection (4 tests) — entry_id, chain_hash, enterprise_trace_id
  2. Chain Integrity (3 tests) — hash chain verification, broken chain detection
  3. GDPR/SOC2 Validation (3 tests) — compliance checks, archive integrity

Ref: EXEC-DIRECTIVE-ENT-001 §Task-3
Ref: Canon LAW 26 (Multi-framework), LAW 27 (Unique audit hashes)
"""

from __future__ import annotations

import datetime

import pytest

from core.enterprise.compliance_auditor import ComplianceAuditor, GDPR_REQUIREMENTS, SOC2_REQUIREMENTS


ENTERPRISE_TRACE_ID = "ent_test_compliance_001"
TENANT = "tenant_compliance_test"


# ═════════════════════════════════════════════════════════════════════
# Group 1: Audit Trail Collection (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestAuditTrailCollection:
    """Audit entries carry correct metadata and hash chain."""

    @pytest.mark.asyncio
    async def test_collect_returns_entry_id_and_hash(self) -> None:
        auditor = ComplianceAuditor()
        result = await auditor.collect_audit_trail(
            TENANT, "dag_execute", "operator_1", "dag:001", ENTERPRISE_TRACE_ID,
        )
        assert "entry_id" in result
        assert "hash" in result
        assert len(result["entry_id"]) == 16

    @pytest.mark.asyncio
    async def test_collect_carries_enterprise_trace_id(self) -> None:
        auditor = ComplianceAuditor()
        result = await auditor.collect_audit_trail(
            TENANT, "pause", "operator_2", "dag:002", ENTERPRISE_TRACE_ID,
        )
        assert result["trace_id"] == ENTERPRISE_TRACE_ID

    @pytest.mark.asyncio
    async def test_consecutive_entries_chain_hashes(self) -> None:
        auditor = ComplianceAuditor()
        a = await auditor.collect_audit_trail(TENANT, "action_a", "op1", "r1", "trace_a")
        b = await auditor.collect_audit_trail(TENANT, "action_b", "op2", "r2", "trace_b")
        assert a["hash"] != b["hash"]

    @pytest.mark.asyncio
    async def test_compliance_hash_present_on_collect(self) -> None:
        auditor = ComplianceAuditor()
        result = await auditor.collect_audit_trail(
            TENANT, "force_retry", "operator_3", "dag:003", ENTERPRISE_TRACE_ID,
        )
        assert "compliance_hash" in result
        assert len(result["compliance_hash"]) == 32


# ═════════════════════════════════════════════════════════════════════
# Group 2: Chain Integrity (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestChainIntegrity:
    """Hash chain verification detects tampering."""

    @pytest.mark.asyncio
    async def test_empty_chain_returns_valid(self) -> None:
        auditor = ComplianceAuditor()
        result = await auditor.verify_chain_integrity()
        assert result["valid"]
        assert result["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_valid_chain_after_multiple_entries(self) -> None:
        auditor = ComplianceAuditor()
        for i in range(5):
            await auditor.collect_audit_trail(
                TENANT, f"action_{i}", f"op{i}", f"r{i}", f"trace_{i}",
            )
        result = await auditor.verify_chain_integrity()
        assert result["valid"]
        assert result["total_entries"] == 5

    @pytest.mark.asyncio
    async def test_broken_chain_detected(self) -> None:
        auditor = ComplianceAuditor()
        await auditor.collect_audit_trail(TENANT, "good", "op1", "r1", "trace_1")
        await auditor.collect_audit_trail(TENANT, "good", "op2", "r2", "trace_2")
        auditor._audit_entries[1]["entry_hash"] = "tampered_hash"
        result = await auditor.verify_chain_integrity()
        assert not result["valid"]
        assert result["broken_at"] == 1


# ═════════════════════════════════════════════════════════════════════
# Group 3: GDPR/SOC2 Validation & Archive (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestComplianceValidationAndArchive:
    """GDPR/SOC2 checks pass; archive preserves chain integrity."""

    def test_gdpr_requirements_defined(self) -> None:
        assert len(GDPR_REQUIREMENTS) == 5
        assert "data_residency_enforced" in GDPR_REQUIREMENTS
        assert "right_to_erasure_supported" in GDPR_REQUIREMENTS

    def test_soc2_requirements_defined(self) -> None:
        assert len(SOC2_REQUIREMENTS) == 5
        assert "security_monitoring_enabled" in SOC2_REQUIREMENTS

    @pytest.mark.asyncio
    async def test_archive_preserves_remaining_entries(self) -> None:
        auditor = ComplianceAuditor()
        await auditor.collect_audit_trail(TENANT, "a1", "op1", "r1", "t1")
        await auditor.collect_audit_trail(TENANT, "a2", "op2", "r2", "t2")
        result = await auditor.archive_logs(TENANT, "P99999D", ENTERPRISE_TRACE_ID)
        assert result["archived_count"] == 0  # within retention
        assert result["retained_count"] == 2
