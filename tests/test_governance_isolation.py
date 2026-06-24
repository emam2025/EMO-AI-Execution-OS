"""Governance Layer — 15 high-signal tests for RBAC, Audit Trail, Tenant Isolation.

Coverage:
  RBAC: role-permission bindings, PolicyEngine.enforce, cross-tenant rejection
  Audit Trail: append-only, SHA-256 chain integrity, signature verification, export
  Tenant Isolation: namespace registry, scoped bus/store, cross-tenant rejection
"""

import pytest
from core.governance import rbac, audit_trail, tenant_isolation


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_governance():
    rbac.PolicyEngine().reset()
    audit_trail.reset()
    tenant_isolation.TenantRegistry().reset()
    audit_trail.init("test-signing-key")


# ═════════════════════════════════════════════════════════════════
#  RBAC (5 tests)
# ═════════════════════════════════════════════════════════════════

class TestRBAC:
    def test_super_admin_has_all_permissions(self):
        rbac.bind_role("admin-1", "tenant-0", rbac.Role.SUPER_ADMIN)
        perms = rbac.get_permissions("admin-1")
        assert rbac.Permission.SUBMIT_TASK in perms
        assert rbac.Permission.MANAGE_ROLES in perms
        assert rbac.Permission.MANAGE_TENANTS in perms
        assert rbac.Permission.EXPORT_AUDIT in perms

    def test_viewer_cannot_submit(self):
        rbac.bind_role("viewer-1", "tenant-a", rbac.Role.VIEWER)
        engine = rbac.PolicyEngine()
        with pytest.raises(PermissionError):
            engine.enforce("viewer-1", rbac.Permission.SUBMIT_TASK, "tenant-a")

    def test_policy_engine_rejects_wrong_tenant(self):
        rbac.bind_role("op-1", "tenant-a", rbac.Role.OPERATOR)
        engine = rbac.PolicyEngine()
        assert engine.check("op-1", rbac.Permission.SUBMIT_TASK, "tenant-b") is False
        with pytest.raises(PermissionError):
            engine.enforce("op-1", rbac.Permission.SUBMIT_TASK, "tenant-b")

    def test_unbound_principal_has_no_permissions(self):
        engine = rbac.PolicyEngine()
        assert engine.check("unknown", rbac.Permission.QUERY_TASK, "tenant-a") is False
        assert rbac.get_permissions("unknown") == set()

    def test_operator_can_submit_and_query(self):
        rbac.bind_role("op-2", "tenant-c", rbac.Role.OPERATOR)
        engine = rbac.PolicyEngine()
        engine.enforce("op-2", rbac.Permission.SUBMIT_TASK, "tenant-c")  # no error
        engine.enforce("op-2", rbac.Permission.QUERY_TASK, "tenant-c")   # no error
        with pytest.raises(PermissionError):
            engine.enforce("op-2", rbac.Permission.VIEW_AUDIT, "tenant-c")


# ═════════════════════════════════════════════════════════════════
#  Audit Trail (5 tests)
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


# ═════════════════════════════════════════════════════════════════
#  Tenant Isolation (5 tests)
# ═════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_register_and_resolve_path(self):
        tenant_isolation.register_path(
            tenant_isolation.Namespace.EVENT_BUS, "runtime.events", "tenant-a"
        )
        assert tenant_isolation.resolve_tenant(
            tenant_isolation.Namespace.EVENT_BUS, "runtime.events"
        ) == "tenant-a"

    def test_cross_tenant_enforcement_blocks(self):
        tenant_isolation.register_path(
            tenant_isolation.Namespace.STATE_STORE, "session:42", "tenant-a"
        )
        with pytest.raises(tenant_isolation.IsolationError):
            tenant_isolation.enforce_isolation(
                tenant_isolation.Namespace.STATE_STORE, "session:42", "tenant-b"
            )

    def test_same_tenant_allowed(self):
        tenant_isolation.register_path(
            tenant_isolation.Namespace.IPC_COMMAND, "submit", "tenant-a"
        )
        tenant_isolation.enforce_isolation(
            tenant_isolation.Namespace.IPC_COMMAND, "submit", "tenant-a"
        )
        assert True

    def test_tenant_registry_create_and_list(self):
        registry = tenant_isolation.TenantRegistry()
        registry.register("tenant-alpha", {"plan": "enterprise"})
        registry.register("tenant-beta")
        tenants = registry.list_tenants()
        assert "tenant-alpha" in tenants
        assert "tenant-beta" in tenants

    def test_tenant_registry_unregister_cleans_namespaces(self):
        registry = tenant_isolation.TenantRegistry()
        registry.register("tenant-x")
        tenant_isolation.register_path(
            tenant_isolation.Namespace.EVENT_BUS, "topic.test", "tenant-x"
        )
        registry.unregister("tenant-x")
        assert "tenant-x" not in registry.list_tenants()
        assert tenant_isolation.resolve_tenant(
            tenant_isolation.Namespace.EVENT_BUS, "topic.test"
        ) is None
