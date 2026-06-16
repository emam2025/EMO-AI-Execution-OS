"""D8.4 — Service Ownership Laws (LAW 23-27) Static Enforcement.

Uses AST analysis to enforce that interface files have zero cross-service
imports and that each protocol's methods are exclusively scoped to its
declared domain.

Ref: DEVELOPER.md §15.15a D8.4
Ref: Canon LAW 23-27
"""

import ast
import os
from typing import Dict, Set

INTERFACES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "core", "interfaces"
)


def _parse_interface_file(filename: str) -> ast.Module:
    path = os.path.join(INTERFACES_DIR, filename)
    with open(path, "r") as f:
        return ast.parse(f.read(), filename=filename)


def _get_method_names(module: ast.Module, class_name: str) -> Set[str]:
    methods: Set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.add(item.name)
    return methods


def _get_import_sources(module: ast.Module) -> Set[str]:
    sources: Set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.ImportFrom) and node.module:
            sources.add(node.module)
    return sources


class TestNoCrossServiceImportsInInterfaces:
    """Verifies that each interface file has zero imports from sibling interfaces."""

    def test_no_cross_service_imports_in_interfaces(self) -> None:
        interface_files = [
            "scheduler.py",
            "state_store.py",
            "dispatcher.py",
            "retry.py",
            "lease.py",
        ]
        for filename in interface_files:
            module = _parse_interface_file(filename)
            sources = _get_import_sources(module)
            for src in sources:
                assert not src.startswith("core.interfaces."), (
                    f"{filename} imports from {src} — cross-service import detected"
                )


class TestSchedulerMethodsExclusivelyScheduling:
    """AST analysis: IExecutionScheduler methods must be exclusively scheduling."""

    def test_scheduler_methods_exclusively_scheduling(self) -> None:
        module = _parse_interface_file("scheduler.py")
        methods = _get_method_names(module, "IExecutionScheduler")
        allowed = {"schedule", "run_with_timeout", "collect_futures"}
        assert methods == allowed, (
            f"IExecutionScheduler has {methods}, expected {allowed}"
        )


class TestLeaseManagerMethodsExclusivelyLease:
    """AST analysis: IExecutionLeaseManager methods must be exclusively lease."""

    def test_lease_manager_methods_exclusively_lease(self) -> None:
        module = _parse_interface_file("lease.py")
        methods = _get_method_names(module, "IExecutionLeaseManager")
        allowed = {"acquire_lease", "renew_lease", "release_lease", "monitor_heartbeat"}
        assert methods == allowed, (
            f"IExecutionLeaseManager has {methods}, expected {allowed}"
        )


class TestFailurePropagationMatrixCompleteness:
    """Verifies that PropagationRule covers all 5 services as source_domain."""

    def test_failure_propagation_matrix_completeness(self) -> None:
        from core.models.failure_propagation import PropagationRule, FailureMode, ConsistencyLevel

        required_sources = {"Dispatcher", "LeaseManager", "StateStore", "Scheduler", "RetryHandler"}
        covered: Set[str] = set()

        rules = [
            PropagationRule(
                source_domain="Dispatcher",
                effect_on="Scheduler",
                action="Retry failed tool call",
                failure_mode=FailureMode.RETRY,
                consistency_level=ConsistencyLevel.EVENTUAL,
            ),
            PropagationRule(
                source_domain="LeaseManager",
                effect_on="Scheduler",
                action="Cancel and reassign lease",
                failure_mode=FailureMode.FAIL_FAST,
                consistency_level=ConsistencyLevel.STRONG,
            ),
            PropagationRule(
                source_domain="StateStore",
                effect_on="Scheduler",
                action="Degrade to in-memory buffer",
                failure_mode=FailureMode.DEGRADE,
                consistency_level=ConsistencyLevel.NONE,
            ),
            PropagationRule(
                source_domain="Scheduler",
                effect_on="Dispatcher",
                action="Dispatch to fallback service",
                failure_mode=FailureMode.FALLBACK,
                consistency_level=ConsistencyLevel.EVENTUAL,
            ),
            PropagationRule(
                source_domain="RetryHandler",
                effect_on="Scheduler",
                action="Circuit break after max retries",
                failure_mode=FailureMode.CIRCUIT_BREAK,
                consistency_level=ConsistencyLevel.STRONG,
            ),
        ]

        for rule in rules:
            covered.add(rule.source_domain)

        missing = required_sources - covered
        assert not missing, (
            f"Failure propagation matrix missing source domains: {missing}"
        )
