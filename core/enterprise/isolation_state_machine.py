"""Phase J2 — Tenant Isolation State Machine.  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-27 RULE-1 RULE-3

13-transition tenant request lifecycle: Request Received → Tenant Validation →
Quota Check → Route Execution → [Meter Usage / Block / Suspend].
Enforces 5 Leakage Guards (G-L1–G-L5) and Deterministic Audit Guard (G-A1).

LAW 11: All state is instance-scoped — no globals.
LAW 23: Isolation boundary enforced on every transition.
LAW 27: Every route decision is auditable via deterministic hash.
RULE 3: Every transition is gated by guards.

Ref: artifacts/design/j2/03_tenant_isolation_machine.md §1-3
Ref: Canon LAW 11, 23, 24, 25, 27, RULE 1, 3
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


class RoutingState(str, Enum):  # LAW-23
    IDLE = "idle"
    REQUEST_RECEIVED = "request_received"
    TENANT_VALIDATION = "tenant_validation"
    QUOTA_CHECK = "quota_check"
    ROUTE_EXECUTE = "route_execute"
    METER_USAGE = "meter_usage"
    AGGREGATE_FLUSH = "aggregate_flush"
    AUDIT_LOG = "audit_log"
    COMPLETED = "completed"
    ROUTING_FAILED = "routing_failed"
    QUOTA_EXCEEDED = "quota_exceeded"
    SUSPENDED = "suspended"


class RoutingTransition(str, Enum):  # LAW-23
    T1 = "t1"   # IDLE -> REQUEST_RECEIVED
    T2 = "t2"   # REQUEST_RECEIVED -> TENANT_VALIDATION
    T3 = "t3"   # TENANT_VALIDATION -> QUOTA_CHECK (allowed)
    T4 = "t4"   # TENANT_VALIDATION -> ROUTING_FAILED (blocked)
    T5 = "t5"   # QUOTA_CHECK -> ROUTE_EXECUTE (quota ok)
    T6 = "t6"   # QUOTA_CHECK -> QUOTA_EXCEEDED (quota exhausted)
    T7 = "t7"   # ROUTE_EXECUTE -> METER_USAGE
    T8 = "t8"   # METER_USAGE -> AGGREGATE_FLUSH
    T9 = "t9"   # AGGREGATE_FLUSH -> AUDIT_LOG
    T10 = "t10" # AUDIT_LOG -> COMPLETED
    T11 = "t11" # ROUTING_FAILED -> COMPLETED
    T12 = "t12" # QUOTA_EXCEEDED -> COMPLETED
    T13 = "t13" # SUSPENDED -> IDLE (reinstated)


VALID_TRANSITIONS: Dict[RoutingState, Dict[RoutingTransition, RoutingState]] = {
    RoutingState.IDLE: {
        RoutingTransition.T1: RoutingState.REQUEST_RECEIVED,
    },
    RoutingState.REQUEST_RECEIVED: {
        RoutingTransition.T2: RoutingState.TENANT_VALIDATION,
    },
    RoutingState.TENANT_VALIDATION: {
        RoutingTransition.T3: RoutingState.QUOTA_CHECK,
        RoutingTransition.T4: RoutingState.ROUTING_FAILED,
    },
    RoutingState.QUOTA_CHECK: {
        RoutingTransition.T5: RoutingState.ROUTE_EXECUTE,
        RoutingTransition.T6: RoutingState.QUOTA_EXCEEDED,
    },
    RoutingState.ROUTE_EXECUTE: {
        RoutingTransition.T7: RoutingState.METER_USAGE,
    },
    RoutingState.METER_USAGE: {
        RoutingTransition.T8: RoutingState.AGGREGATE_FLUSH,
    },
    RoutingState.AGGREGATE_FLUSH: {
        RoutingTransition.T9: RoutingState.AUDIT_LOG,
    },
    RoutingState.AUDIT_LOG: {
        RoutingTransition.T10: RoutingState.COMPLETED,
    },
    RoutingState.ROUTING_FAILED: {
        RoutingTransition.T11: RoutingState.COMPLETED,
    },
    RoutingState.QUOTA_EXCEEDED: {
        RoutingTransition.T12: RoutingState.COMPLETED,
    },
    RoutingState.SUSPENDED: {
        RoutingTransition.T13: RoutingState.IDLE,
    },
}


@dataclass
class GuardResult:  # LAW-3 RULE-3
    guard_name: str
    passed: bool
    detail: str = ""
    hash: str = ""

    def __post_init__(self) -> None:
        if not self.hash:
            raw = f"{self.guard_name}:{self.passed}:{self.detail}"
            self.hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class RoutingTransitionRecord:  # LAW-5 LAW-12
    from_state: RoutingState
    to_state: RoutingState
    transition: RoutingTransition
    guard_results: Dict[str, GuardResult] = field(default_factory=dict)
    timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    enterprise_trace_id: str = ""


class IsolationStateMachine:  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-27 RULE-1 RULE-3
    """13-transition isolation state machine with Leakage Guards.

    Enforces:
      G-L1: Cross-tenant access (shared_resource_flag AND scope_verified
            AND target.policy != STRICT)
      G-L2: Quota exhaustion (requested_units <= available)
      G-L3: Metering boundary (tenant_id match + isolation_boundary)
      G-L4: Billing flush integrity (tenant match + positive cost)
      G-L5: Suspension (overdue threshold + idempotent)
      G-A1: Deterministic audit hash verification
    """

    def __init__(self) -> None:
        self._state: RoutingState = RoutingState.IDLE
        self._transition_history: List[RoutingTransitionRecord] = []

    @property
    def state(self) -> RoutingState:
        return self._state

    @property
    def transition_history(self) -> List[RoutingTransitionRecord]:
        return list(self._transition_history)

    def transition(  # LAW-3 RULE-3
        self,
        transition: RoutingTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        enterprise_trace_id: str = "",
    ) -> Dict[str, Any]:
        allowed = VALID_TRANSITIONS.get(self._state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._state.value,
                "to_state": self._state.value,
                "transition": transition.value,
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "enterprise_trace_id": enterprise_trace_id,
            }

        target = allowed[transition]
        guard_results: Dict[str, GuardResult] = {}
        blocked_by: List[str] = []
        inputs = guard_inputs or {}

        if transition == RoutingTransition.T3:
            gr = self._evaluate_g_l1(inputs)
            guard_results.update(gr)
            if not gr.get("G-L1_cross_tenant", GuardResult("", True)).passed:
                blocked_by.append("G-L1")

        elif transition == RoutingTransition.T5:
            gr = self._evaluate_g_l2(inputs)
            guard_results.update(gr)
            if not gr.get("G-L2_quota", GuardResult("", True)).passed:
                blocked_by.append("G-L2")
                target = RoutingState.QUOTA_EXCEEDED

        elif transition == RoutingTransition.T7:
            gr = self._evaluate_g_l3(inputs)
            guard_results.update(gr)
            if not gr.get("G-L3_metering_boundary", GuardResult("", True)).passed:
                blocked_by.append("G-L3")

        elif transition == RoutingTransition.T8:
            gr = self._evaluate_g_l4(inputs)
            guard_results.update(gr)
            if not gr.get("G-L4_flush_integrity", GuardResult("", True)).passed:
                blocked_by.append("G-L4")

        elif transition == RoutingTransition.T13:
            gr = self._evaluate_g_l5(inputs)
            guard_results.update(gr)
            if not gr.get("G-L5_suspension", GuardResult("", True)).passed:
                blocked_by.append("G-L5")

        elif transition == RoutingTransition.T9:
            gr = self._evaluate_g_a1(inputs)
            guard_results.update(gr)
            if not gr.get("G-A1_audit_hash", GuardResult("", True)).passed:
                blocked_by.append("G-A1")

        if blocked_by:
            if transition != RoutingTransition.T5:
                target = self._state

        record = RoutingTransitionRecord(
            from_state=self._state,
            to_state=target,
            transition=transition,
            guard_results=guard_results,
            enterprise_trace_id=enterprise_trace_id,
        )
        self._transition_history.append(record)
        self._state = target

        return {
            "success": len(blocked_by) == 0,
            "from_state": record.from_state.value,
            "to_state": target.value,
            "transition": transition.value,
            "guard_results": {k: {"passed": v.passed, "detail": v.detail, "hash": v.hash}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "reason": f"Blocked by: {blocked_by}" if blocked_by else "",
            "enterprise_trace_id": enterprise_trace_id,
        }

    # ── G-L1: Cross-Tenant Access Isolation (LAW 11, 23; RULE 3) ──

    def _evaluate_g_l1(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        requesting = inputs.get("requesting_tenant", "")
        target = inputs.get("target_tenant", "")
        shared = inputs.get("shared_resource_flag", False)
        verified = inputs.get("scope_verified", False)
        policy = inputs.get("target_isolation_policy", "strict")

        if requesting == target:
            passed = True
            detail = "Same tenant — no cross-tenant access needed"
        else:
            passed = shared and verified and policy != "strict"
            detail = (
                f"cross_tenant: requesting={requesting}, target={target}, "
                f"shared={shared}, verified={verified}, policy={policy}"
            )

        return {"G-L1_cross_tenant": GuardResult("G-L1_cross_tenant", passed, detail)}

    # ── G-L2: Quota Exhaustion Guard (LAW 24; RULE 3) ──

    def _evaluate_g_l2(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        requested = Decimal(str(inputs.get("requested_units", 0)))
        available = Decimal(str(inputs.get("available_units", 0)))
        passed = requested <= available
        return {"G-L2_quota": GuardResult("G-L2_quota", passed, f"requested={requested}, available={available}")}

    # ── G-L3: Metering Boundary Guard (LAW 23, 11; RULE 3) ──

    def _evaluate_g_l3(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        record_tenant = inputs.get("record_tenant_id", "")
        exec_tenant = inputs.get("executing_tenant_id", "")
        boundary = inputs.get("isolation_boundary")

        passed = (record_tenant == exec_tenant) and boundary is not None
        detail = f"record_tenant={record_tenant}, exec_tenant={exec_tenant}, boundary_set={boundary is not None}"
        return {"G-L3_metering_boundary": GuardResult("G-L3_metering_boundary", passed, detail)}

    # ── G-L4: Billing Flush Integrity Guard (LAW 24, 25; RULE 1, 2) ──

    def _evaluate_g_l4(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        records = inputs.get("records", [])
        flush_tenant = inputs.get("flush_tenant", "")
        tenant_match = all(r.get("tenant_id") == flush_tenant for r in records)
        positive_cost = len(records) > 0 and all(Decimal(str(r.get("cost_units", 0))) > Decimal("0") for r in records)
        passed = tenant_match and positive_cost
        detail = f"records={len(records)}, tenant_match={tenant_match}, positive_cost={positive_cost}"
        return {"G-L4_flush_integrity": GuardResult("G-L4_flush_integrity", passed, detail)}

    # ── G-L5: Suspension Guard (LAW 25; RULE 3, 5) ──

    def _evaluate_g_l5(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        overdue_count = inputs.get("overdue_invoice_count", 0)
        has_failed = inputs.get("has_failed_payment", False)
        already_suspended = inputs.get("already_suspended", False)
        threshold = inputs.get("max_overdue_threshold", 3)

        passed = (overdue_count >= threshold or has_failed) and not already_suspended
        detail = f"overdue={overdue_count}, threshold={threshold}, failed={has_failed}, suspended={already_suspended}"
        return {"G-L5_suspension": GuardResult("G-L5_suspension", passed, detail)}

    # ── G-A1: Deterministic Audit Guard (LAW 27; RULE 1) ──

    def _evaluate_g_a1(self, inputs: Dict[str, Any]) -> Dict[str, GuardResult]:
        entry_hash = inputs.get("entry_hash", "")
        expected_hash = inputs.get("expected_hash", "")
        schema_version = inputs.get("schema_version", "v1")

        computed = self.compute_audit_hash(
            inputs.get("tenant_id", ""),
            inputs.get("action", ""),
            inputs.get("actor", ""),
            inputs.get("target_resource", ""),
            inputs.get("compliance_framework", ""),
            inputs.get("retention_policy", ""),
            schema_version,
        )
        passed = entry_hash == computed and entry_hash == expected_hash
        detail = f"hash_match={passed}, schema={schema_version}"
        return {"G-A1_audit_hash": GuardResult("G-A1_audit_hash", passed, detail)}

    @staticmethod
    def compute_audit_hash(  # LAW-27 RULE-1
        tenant_id: str,
        action: str,
        actor: str,
        target_resource: str,
        compliance_framework: str,
        retention_policy: str,
        schema_version: str = "v1",
    ) -> str:
        raw = f"{tenant_id}:{action}:{actor}:{target_resource}:{compliance_framework}:{retention_policy}:{schema_version}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def reset(self) -> None:
        self._state = RoutingState.IDLE
        self._transition_history.clear()
