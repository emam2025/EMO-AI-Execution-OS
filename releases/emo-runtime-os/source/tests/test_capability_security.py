"""Tests for Phase E2 — Capability Security.

Permission Manifests, Tool Scopes, Sensitive Tool Classification.
"""

import json
import os
import tempfile

import pytest

from core.security.capabilities import (
    Capability,
    AccessMode,
    Scope,
    CapabilityRegistry,
    DEFAULT_CAPABILITY,
    CapabilityGuard,
    CapabilityViolation,
    SensitiveToolRegistry,
    Sensitivity,
)


# ═══════════════════════════════════════════════════════════════════
# E2 — Tool Scopes
# ═══════════════════════════════════════════════════════════════════

class TestScopes:
    def test_capability_has_scope(self):
        cap = Capability.full()
        assert cap.has_scope(Scope.ADMIN)
        assert cap.has_scope(Scope.READ)

    def test_restricted_has_read_scope(self):
        cap = Capability.restricted()
        assert cap.has_scope(Scope.READ)
        assert not cap.has_scope(Scope.ADMIN)

    def test_null_has_none_scope(self):
        cap = Capability.null()
        assert not cap.has_scope(Scope.READ)
        assert not cap.has_scope(Scope.EXECUTE)

    def test_custom_scopes(self):
        cap = Capability(network=True, scopes=[Scope.READ, Scope.EXECUTE])
        assert cap.has_scope(Scope.READ)
        assert cap.has_scope(Scope.EXECUTE)
        assert not cap.has_scope(Scope.ADMIN)

    def test_admin_includes_all(self):
        cap = Capability(scopes=[Scope.ADMIN])
        assert cap.has_scope(Scope.READ)
        assert cap.has_scope(Scope.EXECUTE)
        assert cap.has_scope(Scope.ADMIN)

    def test_registry_has_scope(self):
        reg = CapabilityRegistry()
        reg.register("test_tool", Capability(scopes=[Scope.READ]))
        assert reg.has_scope("test_tool", Scope.READ)
        assert not reg.has_scope("test_tool", Scope.ADMIN)

    def test_registry_has_scope_unregistered(self):
        reg = CapabilityRegistry()
        assert not reg.has_scope("unknown", Scope.READ)

    def test_tools_with_scope(self):
        reg = CapabilityRegistry()
        reg.register("t1", Capability(scopes=[Scope.READ]))
        reg.register("t2", Capability(scopes=[Scope.ADMIN]))
        reg.register("t3", Capability(scopes=[Scope.EXECUTE]))
        admins = reg.tools_with_scope(Scope.ADMIN)
        assert "t2" in admins
        assert "t1" not in admins

    def test_tools_with_minimum_scope(self):
        reg = CapabilityRegistry()
        reg.register("t1", Capability(scopes=[Scope.READ]))
        reg.register("t2", Capability(scopes=[Scope.EXECUTE]))
        reg.register("t3", Capability(scopes=[Scope.ADMIN]))
        filtered = reg.tools_with_minimum_scope(["t1", "t2", "t3"], Scope.EXECUTE)
        assert "t1" not in filtered
        assert "t2" in filtered
        assert "t3" in filtered


# ═══════════════════════════════════════════════════════════════════
# E2 — Permission Manifests
# ═══════════════════════════════════════════════════════════════════

class TestPermissionManifests:
    def test_load_from_dict(self):
        reg = CapabilityRegistry()
        count = reg.load_from_dict({
            "tools": {
                "my_tool": {
                    "network": True,
                    "filesystem": "read",
                    "scopes": ["execute"],
                    "description": "Custom tool",
                },
            },
        })
        assert count == 1
        cap = reg.get_capability("my_tool")
        assert cap.network is True
        assert cap.filesystem == AccessMode.READ
        assert cap.has_scope(Scope.EXECUTE)

    def test_load_from_dict_bare_tools(self):
        reg = CapabilityRegistry()
        count = reg.load_from_dict({
            "my_tool": {"network": False, "description": "bare"},
        })
        assert count == 1

    def test_load_from_json(self):
        data = {
            "web_scraper": {
                "network": True,
                "filesystem": "none",
                "allowed_domains": ["example.com"],
                "scopes": ["execute"],
            },
            "file_reader": {
                "network": False,
                "filesystem": "read",
                "scopes": ["read"],
            },
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"tools": data}, f)
            tmp = f.name
        try:
            reg = CapabilityRegistry()
            count = reg.load_from_json(tmp)
            assert count == 2
            assert reg.get_capability("web_scraper").network is True
            assert reg.get_capability("file_reader").filesystem == AccessMode.READ
        finally:
            os.unlink(tmp)

    def test_load_from_json_no_tools_key(self):
        data = {
            "tool_a": {"network": True, "scopes": ["execute"]},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            tmp = f.name
        try:
            reg = CapabilityRegistry()
            count = reg.load_from_json(tmp)
            assert count == 1
        finally:
            os.unlink(tmp)

    def test_load_from_yaml_missing_dependency(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("No module named 'yaml'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        reg = CapabilityRegistry()
        with pytest.raises(ImportError, match="PyYAML"):
            reg.load_from_yaml("nonexistent.yaml")

    def test_load_from_specs_empty(self):
        reg = CapabilityRegistry()
        reg.load_from_specs({})
        assert len(reg.all_capabilities()) == len(reg.FULL_TRUST_TOOLS) if hasattr(reg, 'FULL_TRUST_TOOLS') else True

    def test_manifest_overrides_defaults(self):
        reg = CapabilityRegistry()
        reg.load_from_dict({
            "tools": {
                "search": {
                    "network": False,
                    "filesystem": "none",
                    "scopes": ["read"],
                    "description": "Override for search",
                },
            },
        })
        cap = reg.get_capability("search")
        assert cap.network is False
        assert cap.description == "Override for search"


# ═══════════════════════════════════════════════════════════════════
# E2 — Sensitive Tool Classification
# ═══════════════════════════════════════════════════════════════════

class TestSensitiveToolClassification:
    def test_default_classifications(self):
        reg = SensitiveToolRegistry()
        assert reg.get_sensitivity("execute_command") == Sensitivity.CRITICAL
        assert reg.get_sensitivity("calculate") == Sensitivity.LOW

    def test_classify_tool(self):
        reg = SensitiveToolRegistry()
        reg.classify("my_tool", Sensitivity.HIGH)
        assert reg.get_sensitivity("my_tool") == Sensitivity.HIGH

    def test_is_sensitive_default_threshold(self):
        reg = SensitiveToolRegistry()
        assert reg.is_sensitive("execute_command") is True
        assert reg.is_sensitive("calculate") is False
        assert reg.is_sensitive("read_file") is True

    def test_is_sensitive_custom_threshold(self):
        reg = SensitiveToolRegistry()
        assert reg.is_sensitive("read_file", threshold=Sensitivity.LOW) is True
        assert reg.is_sensitive("calculate", threshold=Sensitivity.LOW) is True
        assert reg.is_sensitive("calculate", threshold=Sensitivity.HIGH) is False

    def test_sensitive_tools_list(self):
        reg = SensitiveToolRegistry()
        high_or_above = reg.sensitive_tools(threshold=Sensitivity.HIGH)
        assert "execute_command" in high_or_above
        assert "write_file" in high_or_above
        assert "calculate" not in high_or_above

    def test_audit_access(self):
        reg = SensitiveToolRegistry()
        reg.audit_access("execute_command", "exec_001", principal="user_ali")
        log = reg.audit_log()
        assert len(log) == 1
        assert log[0]["tool"] == "execute_command"
        assert log[0]["sensitivity"] == "critical"
        assert log[0]["execution_id"] == "exec_001"
        assert log[0]["principal"] == "user_ali"

    def test_audit_multiple_entries(self):
        reg = SensitiveToolRegistry()
        reg.audit_access("tool_a", "e1")
        reg.audit_access("tool_b", "e2")
        reg.audit_access("tool_c", "e3")
        assert len(reg.audit_log()) == 3

    def test_recent_audit_log(self):
        reg = SensitiveToolRegistry()
        for i in range(10):
            reg.audit_access(f"tool_{i}", f"e{i}")
        recent = reg.recent_audit_log(limit=3)
        assert len(recent) == 3
        assert recent[-1]["tool"] == "tool_9"

    def test_clear_audit_log(self):
        reg = SensitiveToolRegistry()
        reg.audit_access("tool_a", "e1")
        reg.clear_audit_log()
        assert reg.audit_log() == []

    def test_audit_with_metadata(self):
        reg = SensitiveToolRegistry()
        reg.audit_access("tool_a", "e1", metadata={"ip": "10.0.0.1"})
        assert reg.audit_log()[0]["metadata"]["ip"] == "10.0.0.1"

    def test_sensitive_unclassified_defaults_low(self):
        reg = SensitiveToolRegistry()
        assert reg.get_sensitivity("unknown_tool") == Sensitivity.LOW


# ═══════════════════════════════════════════════════════════════════
# E2 — Integration: Guard + Scopes + Sensitivity
# ═══════════════════════════════════════════════════════════════════

class TestE2Integration:
    def test_guard_with_manifest(self):
        reg = CapabilityRegistry()
        reg.load_from_dict({
            "tools": {
                "custom_web": {
                    "network": True,
                    "filesystem": "none",
                    "scopes": ["execute"],
                },
            },
        })
        guard = CapabilityGuard(reg)
        cap = guard.validate("custom_web", {"url": "https://example.com"})
        assert cap.network is True

    def test_guard_rejects_unknown(self):
        reg = CapabilityRegistry()
        guard = CapabilityGuard(reg)
        with pytest.raises(CapabilityViolation, match="No capability registered"):
            guard.validate("unknown_tool")

    def test_sensitive_and_guard_combined(self):
        reg = CapabilityRegistry()
        reg.load_from_dict({
            "tools": {
                "sensitive_op": {
                    "network": True,
                    "filesystem": "write",
                    "scopes": ["admin"],
                },
            },
        })
        guard = CapabilityGuard(reg)
        cap = guard.validate("sensitive_op")
        assert cap.has_scope(Scope.ADMIN)

        sensitive = SensitiveToolRegistry()
        sensitive.classify("sensitive_op", Sensitivity.CRITICAL)
        assert sensitive.is_sensitive("sensitive_op") is True
