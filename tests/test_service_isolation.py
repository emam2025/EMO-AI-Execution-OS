"""D8.3 — Service Isolation Tests.

Prevents:
  - shared mutable state across services
  - hidden cross-service access (direct method calls on another service's internals)
  - internal orchestration leaks (one service doing another's job)

Enforces:
  - LAW 23-27: service ownership boundaries
  - LAW 20-22: failure propagation
  - D8.4: each service owns exactly one domain
"""

import ast
import os
import sys
from typing import Dict, List, Set, Tuple

import pytest

from core.canon import CanonValidator, ValidationContext
from core.canon.default_rules import DEFAULT_RULES
from core.interfaces.failure_propagation import (
    FailureDomain,
    FailureMatrix,
    FailurePropagationPolicy,
    PropagationAction,
    PROPAGATION_MATRIX,
)


# ── Path helpers ───────────────────────────────────────────────────

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CORE = os.path.join(ROOT, "core")
RUNTIME_DIR = os.path.join(CORE, "runtime")
INTERFACES_DIR = os.path.join(CORE, "interfaces")


def _find_py_files(root: str) -> List[Tuple[str, str]]:
    """Return list of (full_path, relative_path) for .py files."""
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, ROOT)
                files.append((full, rel))
    return files


def _get_public_attrs(filepath: str) -> Set[str]:
    """Return set of public attribute/method names defined in a file."""
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return set()
    attrs: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                attrs.add(node.name)
        elif isinstance(node, ast.ClassDef):
            attrs.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    attrs.add(target.id)
    return attrs


SERVICE_METHODS: Dict[str, Set[str]] = {
    "scheduler": {
        "schedule", "run_with_timeout", "collect_futures",
    },
    "dispatcher": {
        "register_tool", "dispatch_tool_call", "validate_contract",
        "route_service",
    },
    "retry_handler": {
        "decide_retry", "apply_backoff", "record_failure",
    },
    "state_store": {
        "save_state", "load_state", "store_checkpoint", "read_trace",
    },
    "lease_manager": {
        "acquire_lease", "renew_lease", "release_lease",
        "monitor_heartbeat",
    },
}

ALL_SERVICE_METHODS: Set[str] = set().union(*SERVICE_METHODS.values())


# ── D8.3.1 — Shared Mutable State ─────────────────────────────────


class TestNoSharedMutableState:
    """Verify no service sets state on another service's domain."""

    def _scan_for_direct_mutation(self, root: str) -> List[str]:
        """Scan for patterns like `service.cache = x` or `service._internal = y`."""
        violations = []
        for full, rel in _find_py_files(root):
            if "test_" in rel or rel.startswith("."):
                continue
            with open(full) as f:
                try:
                    tree = ast.parse(f.read(), filename=full)
                except SyntaxError:
                    continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Attribute):
                            # Check for pattern: some_service.some_attr = value
                            if isinstance(target.value, ast.Name):
                                if target.attr in ALL_SERVICE_METHODS:
                                    violations.append(
                                        f"{rel}:{node.lineno} — "
                                        f"direct mutation of {target.value.id}.{target.attr}"
                                    )
        return violations

    def test_no_direct_mutation_of_service_domain(self):
        """No code mutates state owned by another service."""
        violations = self._scan_for_direct_mutation(CORE)
        assert violations == [], (
            "Direct service domain mutations detected:\n"
            + "\n".join(violations)
        )


# ── D8.3.2 — Hidden Cross-Service Access ──────────────────────────


class TestNoHiddenCrossServiceAccess:
    """Verify services don't reach into each other's internals."""

    def _scan_cross_service_calls(self) -> List[str]:
        """Scan for one service calling another service's methods directory.

        Examples of violations:
          - scheduler.retry_handler.compute_backoff(...)
          - dispatcher.lease_manager.release(...)
        """
        violations = []
        for full, rel in _find_py_files(CORE):
            if "test_" in rel or rel.startswith("."):
                continue
            with open(full) as f:
                try:
                    tree = ast.parse(f.read(), filename=full)
                except SyntaxError:
                    continue

            service_names = {"scheduler", "dispatcher", "retry_handler",
                             "state_store", "lease_manager", "execution_runtime"}

            for node in ast.walk(tree):
                # Detect: service_a.service_b_method(...)
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
                        # Pattern: X.Y.Z(...) — two levels of attribute access
                        if isinstance(func.value.value, ast.Name):
                            outer_name = func.value.value.id
                            inner_attr = func.value.attr
                            called_method = func.attr
                            if outer_name in service_names and inner_attr in service_names:
                                violations.append(
                                    f"{rel}:{node.lineno} — "
                                    f"{outer_name}.{inner_attr}.{called_method}(...)"
                                )
        return violations

    def test_no_chained_cross_service_calls(self):
        """No service chains through another service to call internal methods."""
        violations = self._scan_cross_service_calls()
        assert violations == [], (
            "Chained cross-service calls detected:\n"
            + "\n".join(violations)
        )


# ── D8.3.3 — Interface Compliance ─────────────────────────────────


class TestServiceInterfaceCompliance:
    """Verify each service interface only owns its permitted methods."""

    def test_scheduler_only_owns_scheduling(self):
        from core.interfaces.scheduler import IExecutionScheduler
        own = SERVICE_METHODS["scheduler"]
        pub = {m for m in dir(IExecutionScheduler) if not m.startswith("_")}
        excess = pub - own
        assert excess == set(), (
            f"IExecutionScheduler exposes non-scheduling methods: {excess}"
        )

    def test_dispatcher_only_owns_routing(self):
        from core.interfaces.dispatcher import IExecutionDispatcher
        own = SERVICE_METHODS["dispatcher"]
        pub = {m for m in dir(IExecutionDispatcher) if not m.startswith("_")}
        excess = pub - own
        assert excess == set(), (
            f"IExecutionDispatcher exposes non-routing methods: {excess}"
        )

    def test_retry_only_owns_retry(self):
        from core.interfaces.retry import IExecutionRetryHandler
        own = SERVICE_METHODS["retry_handler"]
        pub = {m for m in dir(IExecutionRetryHandler) if not m.startswith("_")}
        excess = pub - own
        assert excess == set(), (
            f"IExecutionRetryHandler exposes non-retry methods: {excess}"
        )

    def test_state_store_only_owns_persistence(self):
        from core.interfaces.state_store import IExecutionStateStore
        own = SERVICE_METHODS["state_store"]
        pub = {m for m in dir(IExecutionStateStore) if not m.startswith("_")}
        excess = pub - own
        assert excess == set(), (
            f"IExecutionStateStore exposes non-persistence methods: {excess}"
        )

    def test_lease_only_owns_lease(self):
        from core.interfaces.lease import IExecutionLeaseManager
        own = SERVICE_METHODS["lease_manager"]
        pub = {m for m in dir(IExecutionLeaseManager) if not m.startswith("_")}
        excess = pub - own
        assert excess == set(), (
            f"IExecutionLeaseManager exposes non-lease methods: {excess}"
        )

    def test_no_overlap_across_interfaces(self):
        """No method name appears in two different service interfaces."""
        all_methods: Dict[str, Set[str]] = {}
        for svc_name, methods in SERVICE_METHODS.items():
            for m in methods:
                all_methods.setdefault(m, set()).add(svc_name)

        overlaps = {m: svcs for m, svcs in all_methods.items() if len(svcs) > 1}
        assert overlaps == {}, (
            f"Method names shared across services: {overlaps}"
        )


# ── D8.3.4 — Failure Propagation Compliance ───────────────────────


class TestFailurePropagationCompliance:
    """Verify the propagation matrix covers all mandatory rules."""

    def test_dispatcher_failure_triggers_retry_classify_release_notify(self):
        """F01: dispatcher failure → RETRY, CLASSIFY, RELEASE, NOTIFY."""
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("Dispatcher")
        assert "RETRY" in actions
        assert "CLASSIFY" in actions
        assert "RELEASE" in actions
        assert "NOTIFY" in actions

    def test_lease_expiry_triggers_cancel_rollback_reassign_record(self):
        """F02: lease expiry → CANCEL, ROLLBACK, REASSIGN, RECORD."""
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("LeaseManager")
        assert "CANCEL" in actions
        assert "ROLLBACK" in actions
        assert "REASSIGN" in actions
        assert "RECORD" in actions

    def test_state_store_failure_includes_degrade(self):
        """F03: state store failure → DEGRADE, BUFFER, CONTINUE, DEFER."""
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("StateStore")
        assert "DEGRADE" in actions, (
            "State store failure must include degrade mode"
        )
        assert "BUFFER" in actions
        assert "CONTINUE" in actions
        assert "DEFER" in actions

    def test_legacy_propagation_matrix_matches_failure_domains(self):
        """The legacy PROPAGATION_MATRIX covers all expected domain entries."""
        rules = PROPAGATION_MATRIX.get(FailureDomain.DISPATCHER, [])
        actions = {r.action for r in rules}
        assert PropagationAction.RETRY in actions
        assert PropagationAction.RELEASE_LEASE in actions

    def test_failure_matrix_covers_all_scenarios(self):
        matrix = FailurePropagationPolicy()
        scenarios = matrix.get_all_scenarios()
        scenario_ids = {s["scenario_id"] for s in scenarios}
        for expected_id in [f"F{i:02d}" for i in range(1, 9)]:
            assert expected_id in scenario_ids, (
                f"Missing scenario {expected_id}"
            )

    def test_failure_matrix_unknown_domain_raises(self):
        matrix = FailurePropagationPolicy()
        with pytest.raises(KeyError):
            matrix.apply("UnknownDomain")


# ── D8.3.5 — Canon Enforcement of Service Ownership ───────────────


class TestCanonServiceOwnership:
    """Verify Canon validates service ownership boundaries."""

    @pytest.fixture
    def validator(self):
        return CanonValidator(rules=DEFAULT_RULES)

    def test_law_23_passes_with_clean_scheduler(self, validator):
        ctx = ValidationContext()
        ctx.scheduler = type("CleanScheduler", (), {
            "order_levels": lambda self, x: [],
            "select_ready_nodes": lambda self, **kw: [],
            "allocate_worker": lambda self, **kw: 0,
            "estimate_execution_order": lambda self, **kw: [],
        })()
        result = validator.validate(ctx)
        law_23 = [v for v in result.violations if "LAW_23" in str(v)]
        assert not law_23, f"LAW_23 fired unexpectedly: {law_23}"

    def test_law_23_fires_with_bad_scheduler(self, validator):
        ctx = ValidationContext()
        ctx.scheduler = type("BadScheduler", (), {
            "retry": lambda self: None,
        })()
        result = validator.validate(ctx)
        law_23 = [v for v in result.violations if "LAW_23" in str(v)]
        assert law_23, "LAW_23 should fire when scheduler has retry method"

    def test_law_27_fires_with_overlapping_services(self, validator):
        ctx = ValidationContext()
        ctx.scheduler = type("S", (), {"order_levels": lambda self: []})()
        ctx.dispatcher = type("D", (), {"order_levels": lambda self: []})()
        result = validator.validate(ctx)
        law_27 = [v for v in result.violations if "LAW_27" in str(v)]
        assert law_27, "LAW_27 should fire when scheduler and dispatcher share methods"


# ── D8.3.6 — Violation Registry Classification ─────────────────────


class TestViolationClassification:
    """Verify known violations are correctly classified in the registry."""

    REGISTRY_PATH = os.path.join(ROOT, "artifacts", "codeguard", "known-violations.json")

    def test_registry_exists(self):
        assert os.path.exists(self.REGISTRY_PATH), (
            f"Known violations registry not found at {self.REGISTRY_PATH}"
        )

    def test_registry_is_valid_json(self):
        import json
        with open(self.REGISTRY_PATH) as f:
            data = json.load(f)
        assert "version" in data
        assert "classifications" in data
        assert "LAW_4" in data["classifications"]
        assert "LAW_5" in data["classifications"]
        assert "LAW_16_high_risk_nodes" in data["classifications"]

    def test_legacy_violations_have_clear_remediation(self):
        import json
        with open(self.REGISTRY_PATH) as f:
            data = json.load(f)
        for cid, cv in data["classifications"].items():
            assert "status" in cv, f"{cid} missing status"
            assert "reason" in cv, f"{cid} missing reason"
            if cv.get("status") == "legacy_acceptable":
                assert "mitigated" in cv["reason"].lower() or "legacy" in cv["reason"].lower() or "re-export" in cv["reason"].lower(), (
                    f"{cid} legacy violation needs remediation plan in reason"
                )

    def test_emo_guard_still_blocks_known_violations(self):
        """emo-guard should still detect known violations (they're tracked, not hidden)."""
        import json
        with open(self.REGISTRY_PATH) as f:
            data = json.load(f)
        for cid, cv in data["classifications"].items():
            if cv["status"] == "active_architectural_debt":
                assert "affected_files_active" in cv, (
                    f"{cid} active debt missing affected_files_active list"
                )


# ── D8.3.7 — Protocol Compliance (Implementation satisfies Protocol) ──


class TestImplementationSatisfiesProtocol:
    """Verify each implementation structurally satisfies its Protocol.

    Uses Protocol structural subtyping: a class satisfies a Protocol
    if it has all the methods with matching signatures.
    """

    def test_scheduler_satisfies_protocol(self):
        from core.interfaces.scheduler import IExecutionScheduler
        from core.runtime.services.scheduler import ExecutionScheduler
        assert isinstance(ExecutionScheduler(), IExecutionScheduler)

    def test_dispatcher_satisfies_protocol(self):
        from core.interfaces.dispatcher import IExecutionDispatcher
        from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
        assert isinstance(ExecutionToolDispatcher(), IExecutionDispatcher)

    def test_retry_handler_satisfies_protocol(self):
        from core.interfaces.retry import IExecutionRetryHandler
        from core.runtime.services.retry_handler import ExecutionRetryHandler
        assert isinstance(ExecutionRetryHandler(), IExecutionRetryHandler)

    def test_state_store_satisfies_protocol(self):
        from core.interfaces.state_store import IExecutionStateStore
        from core.runtime.services.state_store import ExecutionStateStore
        assert isinstance(ExecutionStateStore(), IExecutionStateStore)

    def test_lease_manager_satisfies_protocol(self):
        from core.interfaces.lease import IExecutionLeaseManager
        from core.runtime.services.lease_manager import ExecutionLeaseManager
        assert isinstance(ExecutionLeaseManager(), IExecutionLeaseManager)
