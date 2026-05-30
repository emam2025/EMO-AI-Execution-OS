"""
R2 Memory OS — 15 isolation and contract tests.

Groups:
  TestZeroR1Dependency        (5) — prevent any import from runtime-os/
  TestProtocolIntegrity       (5) — verify protocol signatures and models
  TestTenantIsolationInModels (5) — enforce tenant_id and cognitive_trace_id
"""

import importlib
import importlib.util
import inspect
import os
import sys
from dataclasses import fields, FrozenInstanceError
from pathlib import Path

import pytest

MEMORY_OS_ROOT = Path(__file__).resolve().parent.parent
RUNTIME_OS_ROOT = MEMORY_OS_ROOT.parent / "runtime-os"

CORE_DIR = MEMORY_OS_ROOT / "core"
INTERFACES_DIR = MEMORY_OS_ROOT / "core" / "interfaces"
MEMORY_INTERFACES_DIR = MEMORY_OS_ROOT / "core" / "interfaces" / "memory"
MODELS_DIR = MEMORY_OS_ROOT / "core" / "models"


def _import_from_path(module_name, file_path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ═════════════════════════════════════════════════════════════════
#  Group 1: Zero R1 Dependency (5 tests)
# ═════════════════════════════════════════════════════════════════

class TestZeroR1Dependency:
    def test_no_r1_path_in_sys_path(self):
        for p in sys.path:
            assert "runtime-os" not in p, f"R1 path found in sys.path: {p}"

    def test_can_import_memory_os_interfaces(self):
        hier = _import_from_path(
            "memory_hierarchy",
            MEMORY_INTERFACES_DIR / "hierarchy.py",
        )
        comp = _import_from_path(
            "memory_compiler",
            MEMORY_INTERFACES_DIR / "compiler.py",
        )
        sk = _import_from_path(
            "memory_skill_graph",
            MEMORY_INTERFACES_DIR / "skill_graph.py",
        )
        assert hasattr(hier, "IMemoryHierarchy")
        assert hasattr(comp, "IContextCompiler")
        assert hasattr(sk, "ISkillGraphManager")

    def test_can_import_memory_os_models(self):
        mod = _import_from_path("memory_models", MODELS_DIR / "memory.py")
        assert hasattr(mod, "MemoryEntry")
        assert hasattr(mod, "ContextWindow")
        assert hasattr(mod, "ForgettingPolicy")
        assert hasattr(mod, "MemoryScope")

    def test_r1_governance_not_importable_from_memory_os(self):
        r1_gov = RUNTIME_OS_ROOT / "core" / "governance" / "rbac.py"
        if r1_gov.exists():
            with pytest.raises((ImportError, Exception)):
                _import_from_path("r1_rbac_stub", str(r1_gov))
        else:
            pytest.skip("R1 runtime-os not present")

    def test_r1_core_not_importable_from_memory_os(self):
        r1_engine = RUNTIME_OS_ROOT / "core" / "execution_engine.py"
        if r1_engine.exists():
            with pytest.raises((ImportError, Exception)):
                _import_from_path("r1_engine_stub", str(r1_engine))
        else:
            pytest.skip("R1 runtime-os not present")


# ═════════════════════════════════════════════════════════════════
#  Group 2: Protocol Integrity (5 tests)
# ═════════════════════════════════════════════════════════════════

class TestProtocolIntegrity:
    def _get_protocol_members(self, file_path, class_name):
        mod = _import_from_path(f"proto_{class_name}", file_path)
        cls = getattr(mod, class_name)
        return [
            m for m in dir(cls)
            if not m.startswith("_") and not m.startswith("classmethod")
        ], cls

    def test_imemory_hierarchy_has_required_methods(self):
        methods, _ = self._get_protocol_members(
            MEMORY_INTERFACES_DIR / "hierarchy.py", "IMemoryHierarchy"
        )
        for req in ["store", "retrieve", "prune", "get_context_window"]:
            assert req in methods, f"IMemoryHierarchy missing: {req}"

    def test_icontext_compiler_has_required_methods(self):
        methods, _ = self._get_protocol_members(
            MEMORY_INTERFACES_DIR / "compiler.py", "IContextCompiler"
        )
        for req in ["compress_trace", "inject_intelligence", "validate_boundary"]:
            assert req in methods, f"IContextCompiler missing: {req}"

    def test_iskill_graph_manager_has_required_methods(self):
        methods, _ = self._get_protocol_members(
            MEMORY_INTERFACES_DIR / "skill_graph.py", "ISkillGraphManager"
        )
        for req in ["record", "retrieve", "update_weight"]:
            assert req in methods, f"ISkillGraphManager missing: {req}"

    def test_all_protocols_have_tenant_id_param(self):
        for fname, cls_name in [
            ("hierarchy.py", "IMemoryHierarchy"),
            ("compiler.py", "IContextCompiler"),
            ("skill_graph.py", "ISkillGraphManager"),
        ]:
            methods, cls = self._get_protocol_members(
                MEMORY_INTERFACES_DIR / fname, cls_name
            )
            for m_name in methods:
                member = getattr(cls, m_name, None)
                if callable(member) and hasattr(member, "__annotations__"):
                    try:
                        sig = inspect.signature(member)
                        params = list(sig.parameters.keys())
                        assert "tenant_id" in params, \
                            f"{cls_name}.{m_name} missing tenant_id"
                    except (ValueError, TypeError):
                        pass

    def test_all_protocols_have_cognitive_trace_id_param(self):
        for fname, cls_name in [
            ("hierarchy.py", "IMemoryHierarchy"),
            ("compiler.py", "IContextCompiler"),
            ("skill_graph.py", "ISkillGraphManager"),
        ]:
            methods, cls = self._get_protocol_members(
                MEMORY_INTERFACES_DIR / fname, cls_name
            )
            for m_name in methods:
                member = getattr(cls, m_name, None)
                if callable(member) and hasattr(member, "__annotations__"):
                    try:
                        sig = inspect.signature(member)
                        params = list(sig.parameters.keys())
                        assert "cognitive_trace_id" in params, \
                            f"{cls_name}.{m_name} missing cognitive_trace_id"
                    except (ValueError, TypeError):
                        pass


# ═════════════════════════════════════════════════════════════════
#  Group 3: Tenant Isolation in Models (5 tests)
# ═════════════════════════════════════════════════════════════════

class TestTenantIsolationInModels:
    def _get_model(self, model_name):
        mod = _import_from_path("mem_models_test", MODELS_DIR / "memory.py")
        return getattr(mod, model_name)

    def test_memory_entry_requires_tenant_id(self):
        cls = self._get_model("MemoryEntry")
        from releases.memory_os.core.models.memory import MemoryLayer
        with pytest.raises(ValueError, match="tenant_id"):
            cls(
                entry_id="e1",
                tenant_id="",
                project_id="p1",
                agent_id="a1",
                layer=MemoryLayer.EPISODIC,
                key="k1",
                payload={},
                content_hash="abc",
            )

    def test_memory_entry_requires_project_id(self):
        cls = self._get_model("MemoryEntry")
        from releases.memory_os.core.models.memory import MemoryLayer
        with pytest.raises(ValueError, match="project_id"):
            cls(
                entry_id="e1",
                tenant_id="tenant-1",
                project_id="",
                agent_id="a1",
                layer=MemoryLayer.EPISODIC,
                key="k1",
                payload={},
                content_hash="abc",
            )

    def test_context_window_requires_tenant_id(self):
        cls = self._get_model("ContextWindow")
        with pytest.raises(ValueError, match="tenant_id"):
            cls(
                window_id="w1",
                tenant_id="",
                project_id="p1",
                cognitive_trace_id="trace-1",
                trace_id="t1",
                entries=[],
            )

    def test_forgetting_policy_requires_cognitive_trace_id(self):
        cls = self._get_model("ForgettingPolicy")
        from releases.memory_os.core.models.memory import PruningPolicy
        with pytest.raises(ValueError, match="cognitive_trace_id"):
            cls(
                policy_id="p1",
                tenant_id="tenant-1",
                project_id="p1",
                cognitive_trace_id="",
                pruning_policy=PruningPolicy.TTL,
            )

    def test_forgetting_policy_requires_project_id(self):
        cls = self._get_model("ForgettingPolicy")
        from releases.memory_os.core.models.memory import PruningPolicy
        with pytest.raises(ValueError, match="project_id"):
            cls(
                policy_id="p1",
                tenant_id="tenant-1",
                project_id="",
                cognitive_trace_id="ct1",
                pruning_policy=PruningPolicy.TTL,
            )
