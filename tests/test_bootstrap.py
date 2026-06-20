"""Phase 3.9 — Composition Root Finalization tests.

Covers:
  - DI enforcement: no ``ExecutionEngine(`` outside allowed modules
  - EmoRuntime lifecycle (build → start → shutdown)
  - Boot contract validation
  - Context manager protocol
  - Convenience method delegation
"""

import ast
import importlib.util
import os
import sys
from typing import List, Set

import pytest

from core.runtime.bootstrap import EmoRuntime, BootContractError


# ── Helpers ────────────────────────────────────────────────────────

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

ALLOWED_EXECUTION_ENGINE_FILES: Set[str] = {
    # Definition file
    os.path.normpath("core/execution_engine.py"),
    # Composition root (internal)
    os.path.normpath("core/composition/root.py"),
    # Factory modules (delegated from CompositionRoot)
    os.path.normpath("core/composition/factories/runtime_factory.py"),
    os.path.normpath("core/composition/factories/intelligence_factory.py"),
    os.path.normpath("core/composition/factories/enterprise_factory.py"),
    os.path.normpath("core/composition/factories/observability_factory.py"),
    # Bootstrap wrapper
    os.path.normpath("core/runtime/bootstrap.py"),
}


def _find_py_files(root: str) -> List[str]:
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip __pycache__, virtual envs, hidden dirs, releases archive
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d != "__pycache__"
            and d != "site-packages" and d != "node_modules"
            and d != "releases"
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root)
                if rel.startswith("tests/"):
                    continue
                if rel.startswith("venv") or rel.startswith(".venv"):
                    continue
                py_files.append((full, rel))
    return py_files


def _check_execution_engine_instantiation(filepath: str) -> List[str]:
    """Return list of line numbers where ExecutionEngine(...) is called."""
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []

    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # Direct call: ExecutionEngine(...)
            if isinstance(func, ast.Name) and func.id == "ExecutionEngine":
                lines.append(node.lineno)
            # Attribute call: something.ExecutionEngine(...)
            if isinstance(func, ast.Attribute) and func.attr == "ExecutionEngine":
                lines.append(node.lineno)
    return lines


# ── DI Enforcement ─────────────────────────────────────────────────


class TestDIEnforcement:
    """Verify that ExecutionEngine is only instantiated in allowed files.

    This enforces LAW 13 — ONLY CompositionRoot may instantiate
    ExecutionEngine.
    """

    @pytest.fixture(scope="class")
    def violations(self) -> List[tuple]:
        """Scan all non-test Python files for illegal instantiation."""
        result = []
        for full, rel in _find_py_files(ROOT):
            if rel in ALLOWED_EXECUTION_ENGINE_FILES:
                continue
            if rel.startswith("tests/"):
                continue
            lines = _check_execution_engine_instantiation(full)
            if lines:
                result.append((rel, lines))
        return result

    def test_no_illegal_execution_engine_instantiation(self, violations):
        assert violations == [], (
            f"ExecutionEngine illegally instantiated in: "
            + "; ".join(f"{f}:{','.join(map(str,ls))}" for f, ls in violations)
        )

    def test_no_hidden_import_in_non_di_modules(self):
        """Verify no non-DI modules import ExecutionEngine class directly.

        Imports of IExecutionEngine (the protocol) are fine.
        """
        suspicious = []
        root = os.path.join(ROOT, "core")
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".") and d != "__pycache__"
            ]
            for fn in filenames:
                if not fn.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, fn)
                rel = os.path.relpath(filepath, ROOT)
                if rel in ALLOWED_EXECUTION_ENGINE_FILES:
                    continue
                with open(filepath) as f:
                    try:
                        tree = ast.parse(f.read(), filename=filepath)
                    except SyntaxError:
                        continue
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        names = [a.name for a in node.names]
                        if module == "core.execution_engine" and "ExecutionEngine" in names:
                            suspicious.append((rel, node.lineno, names))
                            break
        assert suspicious == [], (
            f"Files importing ExecutionEngine directly: "
            + "; ".join(f"{f}:{l} ({n})" for f, l, n in suspicious)
        )


# ── Lifecycle ──────────────────────────────────────────────────────


class TestEmoRuntimeLifecycle:
    """Test the full lifecycle of EmoRuntime."""

    def test_build_returns_self(self):
        r = EmoRuntime()
        assert r.build() is r

    def test_start_builds_if_needed(self):
        r = EmoRuntime()
        r.start()
        assert r.is_built
        assert r.is_started

    def test_full_cycle(self):
        r = EmoRuntime()
        r.build()
        assert r.is_built
        assert not r.is_started
        r.start()
        assert r.is_started
        assert r.engine is not None
        r.shutdown()
        assert not r.is_started

    def test_double_start_is_idempotent(self):
        r = EmoRuntime()
        r.build().start()
        assert r.is_started
        r.start()
        assert r.is_started

    def test_double_shutdown_is_idempotent(self):
        r = EmoRuntime()
        r.build().start()
        r.shutdown()
        assert not r.is_started
        r.shutdown()
        assert not r.is_started

    def test_context_manager(self):
        with EmoRuntime() as r:
            assert r.is_built
            assert r.is_started
            assert r.engine is not None
        assert not r.is_started

    def test_engine_property_raises_before_build(self):
        r = EmoRuntime()
        with pytest.raises(RuntimeError, match="not built"):
            _ = r.engine

    def test_intelligence_property_raises_before_build(self):
        r = EmoRuntime()
        with pytest.raises(RuntimeError, match="not built"):
            _ = r.intelligence

    def test_root_property_raises_before_build(self):
        r = EmoRuntime()
        with pytest.raises(RuntimeError, match="not built"):
            _ = r.root

    def test_intelligence_is_wired(self):
        with EmoRuntime() as r:
            assert r.intelligence is not None
            # Test it's responsive
            result = r.intelligence.explain_execution("nonexistent")
            assert isinstance(result, dict)

    def test_convenience_execute_raises_before_build(self):
        r = EmoRuntime()
        with pytest.raises(RuntimeError, match="not built"):
            r.execute(None)  # type: ignore


# ── Boot Contract ──────────────────────────────────────────────────


class TestBootContract:
    """Boot contract validation."""

    def test_empty_registry_warns(self, caplog):
        caplog.set_level("WARNING")
        with EmoRuntime(config={"tool_registry": {}}):
            msgs = "\n".join(caplog.messages)
            assert "tool_registry is empty" in msgs, msgs

    def test_no_optimizer_logs_info(self, caplog):
        caplog.set_level("INFO")
        with EmoRuntime():
            assert any(
                "no DAG optimizer" in msg
                for msg in caplog.messages
            )

    def test_default_config(self):
        r = EmoRuntime()
        r.build()
        assert r._config["worker_pool_size"] == 4

    def test_custom_worker_pool_size(self):
        r = EmoRuntime(config={"worker_pool_size": 8})
        r.build()
        assert r._config["worker_pool_size"] == 8


# ── Wiring Map ─────────────────────────────────────────────────────


class TestWiringMap:
    """Verify that the runtime wiring map is complete."""

    def test_all_services_accessible(self):
        """Every service listed in the wiring map is accessible."""
        with EmoRuntime() as r:
            root = r.root
            # Core infrastructure
            assert root.event_bus is not None
            assert root.event_store is not None
            # CodeGraph integration
            assert root.codegraph_bridge is not None
            # Drift detection
            assert root.drift_store is not None
            assert root.codegraph_drift is not None
            # Canon enforcement
            assert root.canon_validator is not None
            # Runtime intelligence
            assert root.runtime_intelligence is not None
            # Execution engine
            assert root.build_execution_engine() is not None
            # Internal layers
            assert root.execution_core is not None
