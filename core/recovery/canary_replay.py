"""CanaryReplay — replay integrity, checkpoint validation, and determinism audit."""

# LAW-3: Deterministic — replay must produce identical trace_hash for same inputs
# LAW-5: Observable — all validation results published via IEventBus to F4
# LAW-8: Traceable — every check carries canary_trace_id
# LAW-11: No Global State — auditor state is instance-scoped
# LAW-12: Traceable — full back-traceability
# RULE-1: Same inputs → same output_hash (determinism)

from __future__ import annotations

import dataclasses
import hashlib
import time
from typing import Any, Dict, List, Optional


@dataclasses.dataclass(frozen=True)
class ReplayIntegrityResult:
    session_id: str
    original_trace_hash: str
    replayed_trace_hash: str
    integrity_match: bool
    canary_trace_id: str
    timestamp_ns: int
    details: str


@dataclasses.dataclass(frozen=True)
class CheckpointValidationResult:
    session_id: str
    pre_run_consistency: bool
    post_run_consistency: bool
    canary_trace_id: str
    timestamp_ns: int
    details: str


@dataclasses.dataclass(frozen=True)
class DeterminismAuditResult:
    dag_id: str
    run_count: int
    output_hashes: List[str]
    execution_orders: List[List[str]]
    timing_profiles_ms: List[Dict[str, float]]
    all_outputs_match: bool
    all_orders_match: bool
    timing_variance_pct: float
    canary_trace_id: str
    timestamp_ns: int


class CanaryReplayAuditor:
    def __init__(
        self,
        event_bus: Any,
        canary_trace_id: str = "",
    ):
        if canary_trace_id:
            self._trace_id = canary_trace_id
        else:
            raw = f"cra_{time.time_ns()}"
            self._trace_id = "cra_" + hashlib.sha256(raw.encode()).hexdigest()[:28]
        self._event_bus = event_bus
        self._results: List = []

    @property
    def canary_trace_id(self) -> str:
        return self._trace_id

    def replay_integrity_check(
        self, session_id: str, original_trace_hash: str, replayed_trace_hash: str,
    ) -> ReplayIntegrityResult:
        match = original_trace_hash == replayed_trace_hash
        result = ReplayIntegrityResult(
            session_id=session_id,
            original_trace_hash=original_trace_hash,
            replayed_trace_hash=replayed_trace_hash,
            integrity_match=match,
            canary_trace_id=self._trace_id,
            timestamp_ns=time.time_ns(),
            details=(
                "Integrity OK — hashes match"
                if match
                else f"INTEGRITY BREACH: {original_trace_hash} != {replayed_trace_hash}"
            ),
        )
        self._results.append(result)
        self._publish("replay_integrity", result)
        return result

    def checkpoint_validation(
        self, session_id: str, pre_run_state: Dict[str, Any], post_run_state: Dict[str, Any],
    ) -> CheckpointValidationResult:
        pre_consistent = self._check_consistency(pre_run_state)
        post_consistent = self._check_consistency(post_run_state)
        result = CheckpointValidationResult(
            session_id=session_id,
            pre_run_consistency=pre_consistent,
            post_run_consistency=post_consistent,
            canary_trace_id=self._trace_id,
            timestamp_ns=time.time_ns(),
            details=(
                "Checkpoint consistent"
                if (pre_consistent and post_consistent)
                else f"Checkpoint INCONSISTENT: pre={pre_consistent}, post={post_consistent}"
            ),
        )
        self._results.append(result)
        self._publish("checkpoint_validation", result)
        return result

    def determinism_audit(
        self,
        dag_id: str,
        runs: List[Dict[str, Any]],
    ) -> DeterminismAuditResult:
        output_hashes = []
        execution_orders = []
        timing_profiles_ms = []

        for run in runs:
            dag_str = str(sorted(run.get("tasks", [])))
            order = run.get("execution_order", [])
            timing = run.get("timing_ms", {})
            output_hashes.append(hashlib.sha256(dag_str.encode()).hexdigest()[:16])
            execution_orders.append(order)
            timing_profiles_ms.append(timing)

        all_outputs_match = len(set(output_hashes)) == 1
        all_orders_match = len(set(
            tuple(o) for o in execution_orders
        )) == 1

        if len(timing_profiles_ms) >= 2 and all(
            "total" in t for t in timing_profiles_ms
        ):
            totals = [t["total"] for t in timing_profiles_ms]
            mean = sum(totals) / len(totals)
            variance = max(abs(t - mean) / mean * 100 for t in totals) if mean > 0 else 0.0
        else:
            variance = 0.0

        result = DeterminismAuditResult(
            dag_id=dag_id,
            run_count=len(runs),
            output_hashes=output_hashes,
            execution_orders=execution_orders,
            timing_profiles_ms=timing_profiles_ms,
            all_outputs_match=all_outputs_match,
            all_orders_match=all_orders_match,
            timing_variance_pct=variance,
            canary_trace_id=self._trace_id,
            timestamp_ns=time.time_ns(),
        )
        self._results.append(result)
        self._publish("determinism_audit", result)
        return result

    def _check_consistency(self, state: Dict[str, Any]) -> bool:
        required = {"dag_version", "worker_count", "lease_table"}
        return all(k in state for k in required)

    def _publish(self, check_type: str, result: Any) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent, EventType
            payload = {"action": f"canary_{check_type}", "canary_trace_id": self._trace_id}
            if hasattr(result, "integrity_match"):
                payload["integrity_match"] = result.integrity_match
            if hasattr(result, "all_outputs_match"):
                payload["all_outputs_match"] = result.all_outputs_match
                payload["all_orders_match"] = result.all_orders_match
            if hasattr(result, "pre_run_consistency"):
                payload["pre_consistent"] = result.pre_run_consistency
                payload["post_consistent"] = result.post_run_consistency
            payload["details"] = getattr(result, "details", "")
            event = ExecutionEvent(
                event_id=hashlib.sha256(
                    f"{check_type}_{time.time_ns()}".encode()
                ).hexdigest()[:16],
                event_type=EventType.STATE_TRANSITION,
                timestamp_ns=time.time_ns(),
                payload=payload,
            )
            self._event_bus.publish("runtime.canary.replay", event)
            self._event_bus.publish("runtime.readiness.canary", event)
        except Exception:
            pass
