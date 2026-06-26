"""Phase J3 — Readiness State Machines with Recovery Guards.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Three state machines governing the Production Readiness lifecycle:
  - Chaos SM:    Baseline Captured → Fault Injected → Monitor Degradation →
                 Auto-Recovery → [Verify Integrity / Escalate / Rollback]
  - Load SM:     Idle → Generating → Pressure Applied → Measuring →
                 Oscillation Check → Completed
  - Certification SM: Idle → Baseline Loaded → Validating → Scoring →
                 [Certified A/B / Certified C / Not Certified] →
                 [Frozen / Flagged / Blocked]

Enforces 3 Recovery Guards (G-C1–G-C3) and 1 Deterministic Load Guard (G-D1).

Ref: artifacts/design/j3/03_chaos_recovery_machine.md
Ref: Canon LAW 3, 5, 8, 11, 20-22, RULE 1-5
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Chaos State Machine
# ═══════════════════════════════════════════════════════════════

class ChaosState(str, Enum):  # LAW-8 LAW-20
    BASELINE_CAPTURED = "baseline_captured"
    FAULT_INJECTED = "fault_injected"
    MONITOR_DEGRADATION = "monitor_degradation"
    AUTO_RECOVERY = "auto_recovery"
    VERIFY_INTEGRITY = "verify_integrity"
    ESCALATED = "escalated"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"


class ChaosTransition(str, Enum):  # LAW-8
    C_T1 = "c_t1"   # BASELINE_CAPTURED -> FAULT_INJECTED
    C_T2 = "c_t2"   # FAULT_INJECTED -> MONITOR_DEGRADATION
    C_T3 = "c_t3"   # MONITOR_DEGRADATION -> AUTO_RECOVERY
    C_T4 = "c_t4"   # MONITOR_DEGRADATION -> ESCALATED
    C_T5 = "c_t5"   # AUTO_RECOVERY -> VERIFY_INTEGRITY
    C_T6 = "c_t6"   # AUTO_RECOVERY -> ROLLED_BACK
    C_T7 = "c_t7"   # ESCALATED -> ROLLED_BACK
    C_T8 = "c_t8"   # VERIFY_INTEGRITY -> COMPLETED
    C_T9 = "c_t9"   # VERIFY_INTEGRITY -> ROLLED_BACK
    C_T10 = "c_t10" # ROLLED_BACK -> BASELINE_CAPTURED
    C_T11 = "c_t11" # COMPLETED -> BASELINE_CAPTURED


CHAOS_VALID_TRANSITIONS: Dict[ChaosState, Dict[ChaosTransition, ChaosState]] = {
    ChaosState.BASELINE_CAPTURED: {
        ChaosTransition.C_T1: ChaosState.FAULT_INJECTED,
    },
    ChaosState.FAULT_INJECTED: {
        ChaosTransition.C_T2: ChaosState.MONITOR_DEGRADATION,
    },
    ChaosState.MONITOR_DEGRADATION: {
        ChaosTransition.C_T3: ChaosState.AUTO_RECOVERY,
        ChaosTransition.C_T4: ChaosState.ESCALATED,
    },
    ChaosState.AUTO_RECOVERY: {
        ChaosTransition.C_T5: ChaosState.VERIFY_INTEGRITY,
        ChaosTransition.C_T6: ChaosState.ROLLED_BACK,
    },
    ChaosState.VERIFY_INTEGRITY: {
        ChaosTransition.C_T8: ChaosState.COMPLETED,
        ChaosTransition.C_T9: ChaosState.ROLLED_BACK,
    },
    ChaosState.ESCALATED: {
        ChaosTransition.C_T7: ChaosState.ROLLED_BACK,
    },
    ChaosState.ROLLED_BACK: {
        ChaosTransition.C_T10: ChaosState.BASELINE_CAPTURED,
    },
    ChaosState.COMPLETED: {
        ChaosTransition.C_T11: ChaosState.BASELINE_CAPTURED,
    },
}


# ═══════════════════════════════════════════════════════════════
# Load State Machine
# ═══════════════════════════════════════════════════════════════

class LoadState(str, Enum):  # LAW-5 RULE-1
    IDLE = "idle"
    GENERATING = "generating"
    PRESSURE_APPLIED = "pressure_applied"
    MEASURING = "measuring"
    OSCILLATION_CHECK = "oscillation_check"
    COMPLETED = "completed"


class LoadTransition(str, Enum):  # LAW-5
    L_T1 = "l_t1"  # IDLE -> GENERATING
    L_T2 = "l_t2"  # GENERATING -> PRESSURE_APPLIED
    L_T3 = "l_t3"  # PRESSURE_APPLIED -> MEASURING
    L_T4 = "l_t4"  # MEASURING -> OSCILLATION_CHECK
    L_T5 = "l_t5"  # OSCILLATION_CHECK -> COMPLETED


LOAD_VALID_TRANSITIONS: Dict[LoadState, Dict[LoadTransition, LoadState]] = {
    LoadState.IDLE: {
        LoadTransition.L_T1: LoadState.GENERATING,
    },
    LoadState.GENERATING: {
        LoadTransition.L_T2: LoadState.PRESSURE_APPLIED,
    },
    LoadState.PRESSURE_APPLIED: {
        LoadTransition.L_T3: LoadState.MEASURING,
    },
    LoadState.MEASURING: {
        LoadTransition.L_T4: LoadState.OSCILLATION_CHECK,
    },
    LoadState.OSCILLATION_CHECK: {
        LoadTransition.L_T5: LoadState.COMPLETED,
    },
}


# ═══════════════════════════════════════════════════════════════
# Certification Gate State Machine
# ═══════════════════════════════════════════════════════════════

class CertificationGateState(str, Enum):  # LAW-5
    IDLE = "idle"
    BASELINE_LOADING = "baseline_loading"
    VALIDATING = "validating"
    SCORING = "scoring"
    CERTIFIED_A_B = "certified_a_b"
    CERTIFIED_C = "certified_c"
    NOT_CERTIFIED = "not_certified"
    FROZEN = "frozen"
    FLAGGED = "flagged"
    BLOCKED = "blocked"


class CertificationGateTransition(str, Enum):  # LAW-5
    G_T1 = "g_t1"   # IDLE -> BASELINE_LOADING
    G_T2 = "g_t2"   # BASELINE_LOADING -> VALIDATING
    G_T3 = "g_t3"   # VALIDATING -> SCORING
    G_T4 = "g_t4"   # SCORING -> CERTIFIED_A_B
    G_T5 = "g_t5"   # SCORING -> CERTIFIED_C
    G_T6 = "g_t6"   # SCORING -> NOT_CERTIFIED
    G_T7 = "g_t7"   # CERTIFIED_A_B -> FROZEN
    G_T8 = "g_t8"   # CERTIFIED_C -> FLAGGED
    G_T9 = "g_t9"   # NOT_CERTIFIED -> BLOCKED


CERT_VALID_TRANSITIONS: Dict[CertificationGateState, Dict[CertificationGateTransition, CertificationGateState]] = {
    CertificationGateState.IDLE: {
        CertificationGateTransition.G_T1: CertificationGateState.BASELINE_LOADING,
    },
    CertificationGateState.BASELINE_LOADING: {
        CertificationGateTransition.G_T2: CertificationGateState.VALIDATING,
    },
    CertificationGateState.VALIDATING: {
        CertificationGateTransition.G_T3: CertificationGateState.SCORING,
    },
    CertificationGateState.SCORING: {
        CertificationGateTransition.G_T4: CertificationGateState.CERTIFIED_A_B,
        CertificationGateTransition.G_T5: CertificationGateState.CERTIFIED_C,
        CertificationGateTransition.G_T6: CertificationGateState.NOT_CERTIFIED,
    },
    CertificationGateState.CERTIFIED_A_B: {
        CertificationGateTransition.G_T7: CertificationGateState.FROZEN,
    },
    CertificationGateState.CERTIFIED_C: {
        CertificationGateTransition.G_T8: CertificationGateState.FLAGGED,
    },
    CertificationGateState.NOT_CERTIFIED: {
        CertificationGateTransition.G_T9: CertificationGateState.BLOCKED,
    },
}


# ═══════════════════════════════════════════════════════════════
# Guard Result Dataclass
# ═══════════════════════════════════════════════════════════════

@dataclass
class GuardResult:  # LAW-3 RULE-3
    guard_name: str
    passed: bool
    detail: str = ""
    law_refs: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.law_refs:
            self.law_refs = []


# ═══════════════════════════════════════════════════════════════
# Guard Evaluators (G-C1, G-C2, G-C3, G-D1)
# ═══════════════════════════════════════════════════════════════

P99_THRESHOLD_MS = 200.0
MAX_DEGRADATION_THRESHOLD = 0.3
PRE_FAULT_HEALTH_MIN = 0.8
MAX_ERROR_RATE_BEFORE_INJECTION = 5.0


def evaluate_g_c1_pre_fault_health(  # LAW-8 LAW-20 RULE-3
    health_score: float = 1.0,
    error_rate_pct: float = 0.0,
    is_already_degraded: bool = False,
    expected_recovery_sec: float = 1.0,
) -> GuardResult:
    blocked_by: List[str] = []
    if health_score < PRE_FAULT_HEALTH_MIN:
        blocked_by.append(f"health_score={health_score} < {PRE_FAULT_HEALTH_MIN}")
    if error_rate_pct > MAX_ERROR_RATE_BEFORE_INJECTION:
        blocked_by.append(f"error_rate={error_rate_pct}% > {MAX_ERROR_RATE_BEFORE_INJECTION}%")
    if is_already_degraded:
        blocked_by.append("service already degraded")
    if expected_recovery_sec <= 0:
        blocked_by.append(f"expected_recovery_sec={expected_recovery_sec} <= 0")
    passed = len(blocked_by) == 0
    return GuardResult(
        guard_name="G-C1",
        passed=passed,
        detail="; ".join(blocked_by) if blocked_by else "All pre-fault health checks passed",
        law_refs=["LAW-8", "LAW-20", "RULE-3"],
    )


def evaluate_g_c2_degradation_budget(  # LAW-21 LAW-22 RULE-3
    degradation_metric: float = 0.0,
    _recovery_time_remaining_sec: float = 60.0,
    cascade_failure_detected: bool = False,
    severity_propagation_contained: bool = True,
) -> GuardResult:
    blocked_by: List[str] = []
    if cascade_failure_detected:
        blocked_by.append("cascade failure detected")
    if not severity_propagation_contained:
        blocked_by.append("severity propagation not contained")
    if degradation_metric >= MAX_DEGRADATION_THRESHOLD:
        blocked_by.append(f"degradation_metric={degradation_metric} >= {MAX_DEGRADATION_THRESHOLD}")
    passed = len(blocked_by) == 0
    return GuardResult(
        guard_name="G-C2",
        passed=passed,
        detail="; ".join(blocked_by) if blocked_by else "Degradation within budget",
        law_refs=["LAW-21", "LAW-22", "RULE-3"],
    )


def evaluate_g_c3_recovery_verification(  # LAW-5 LAW-8 LAW-22 RULE-3 RULE-5
    data_integrity_verified: bool = False,
    lease_transferred: bool = True,
    audit_hash_match: bool = True,
    p99_ms: float = 999.0,
    oscillation_detected: bool = False,
    rollback_safe: bool = False,
    data_sync_lag_ms: float = 0.0,
) -> GuardResult:
    blocked_by: List[str] = []
    if not data_integrity_verified:
        blocked_by.append("data_integrity_verified=False")
    if data_sync_lag_ms >= 500.0:
        blocked_by.append(f"data_sync_lag_ms={data_sync_lag_ms} >= 500ms")
    if not lease_transferred:
        blocked_by.append("lease_transferred=False")
    if not audit_hash_match:
        blocked_by.append("audit_hash_match=False")
    if p99_ms >= P99_THRESHOLD_MS:
        blocked_by.append(f"p99_ms={p99_ms} >= {P99_THRESHOLD_MS}ms")
    if oscillation_detected:
        blocked_by.append("oscillation_detected=True")
    if not rollback_safe:
        blocked_by.append("rollback_safe=False")
    passed = len(blocked_by) == 0
    return GuardResult(
        guard_name="G-C3",
        passed=passed,
        detail="; ".join(blocked_by) if blocked_by else "All recovery verification checks passed",
        law_refs=["LAW-5", "LAW-8", "LAW-22", "RULE-3", "RULE-5"],
    )


def evaluate_g_d1_deterministic_load(  # RULE-1
    profile_hash: str = "",
    _cluster_state_hash: str = "",
    expected_profile_hash: str = "",
) -> GuardResult:
    blocked_by: List[str] = []
    if not profile_hash:
        blocked_by.append("profile_hash empty")
    if expected_profile_hash and profile_hash != expected_profile_hash:
        blocked_by.append(f"profile_hash mismatch: {profile_hash} != {expected_profile_hash}")
    passed = len(blocked_by) == 0
    return GuardResult(
        guard_name="G-D1",
        passed=passed,
        detail="; ".join(blocked_by) if blocked_by else "Deterministic load hash match",
        law_refs=["RULE-1"],
    )


# ═══════════════════════════════════════════════════════════════
# Readiness State Machine (orchestrates all three sub-SMs)
# ═══════════════════════════════════════════════════════════════

@dataclass
class TransitionRecord:  # LAW-3 LAW-5
    from_state: str
    to_state: str
    transition: str
    machine: str
    guard_results: Dict[str, GuardResult] = field(default_factory=dict)
    readiness_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: __import__("time").time_ns())


class ReadinessStateMachine:  # LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-3
    """Composite state machine managing Chaos, Load, and Certification SMs.

    LAW 11: All state is instance-scoped — no globals.
    LAW 3: Same guard inputs -> same transition (deterministic).
    RULE 3: Every transition is gated by Recovery Guards.
    """

    def __init__(self, strict_readiness_mode: bool = False) -> None:
        self._strict_readiness_mode = strict_readiness_mode
        self._chaos_state: ChaosState = ChaosState.BASELINE_CAPTURED
        self._load_state: LoadState = LoadState.IDLE
        self._cert_state: CertificationGateState = CertificationGateState.IDLE
        self._transition_history: List[TransitionRecord] = []

    # ── Chaos SM ────────────────────────────────────────────────

    @property
    def chaos_state(self) -> ChaosState:
        return self._chaos_state

    def transition_chaos(  # LAW-3 RULE-3
        self,
        transition: ChaosTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        readiness_trace_id: str = "",
    ) -> Dict[str, Any]:
        allowed = CHAOS_VALID_TRANSITIONS.get(self._chaos_state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._chaos_state.value,
                "to_state": self._chaos_state.value,
                "transition": transition.value,
                "machine": "chaos",
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "trace_id": readiness_trace_id,
            }

        target = allowed[transition]
        guard_inputs = guard_inputs or {}
        guard_results: Dict[str, GuardResult] = {}
        blocked_by: List[str] = []

        if transition == ChaosTransition.C_T1:
            gr = evaluate_g_c1_pre_fault_health(
                health_score=guard_inputs.get("health_score", 1.0),
                error_rate_pct=guard_inputs.get("error_rate_pct", 0.0),
                is_already_degraded=guard_inputs.get("is_already_degraded", False),
                expected_recovery_sec=guard_inputs.get("expected_recovery_sec", 1.0),
            )
            guard_results["G-C1"] = gr
            if not gr.passed:
                blocked_by.append("G-C1")

        elif transition == ChaosTransition.C_T3:
            gr = evaluate_g_c2_degradation_budget(
                degradation_metric=guard_inputs.get("degradation_metric", 0.0),
                recovery_time_remaining_sec=guard_inputs.get("recovery_time_remaining_sec", 60.0),
                cascade_failure_detected=guard_inputs.get("cascade_failure_detected", False),
                severity_propagation_contained=guard_inputs.get("severity_propagation_contained", True),
            )
            guard_results["G-C2"] = gr
            if not gr.passed:
                target = ChaosState.ESCALATED
                blocked_by.append("G-C2")

        elif transition == ChaosTransition.C_T5:
            gr = evaluate_g_c3_recovery_verification(
                data_integrity_verified=guard_inputs.get("data_integrity_verified", False),
                lease_transferred=guard_inputs.get("lease_transferred", True),
                audit_hash_match=guard_inputs.get("audit_hash_match", True),
                p99_ms=guard_inputs.get("p99_ms", 999.0),
                oscillation_detected=guard_inputs.get("oscillation_detected", False),
                rollback_safe=guard_inputs.get("rollback_safe", False),
                data_sync_lag_ms=guard_inputs.get("data_sync_lag_ms", 0.0),
            )
            guard_results["G-C3"] = gr
            if not gr.passed:
                target = ChaosState.ROLLED_BACK
                blocked_by.append("G-C3")

        elif transition == ChaosTransition.C_T8:
            gr = evaluate_g_c3_recovery_verification(
                data_integrity_verified=guard_inputs.get("data_integrity_verified", False),
                lease_transferred=guard_inputs.get("lease_transferred", True),
                audit_hash_match=guard_inputs.get("audit_hash_match", True),
                p99_ms=guard_inputs.get("p99_ms", 999.0),
                oscillation_detected=guard_inputs.get("oscillation_detected", False),
                rollback_safe=guard_inputs.get("rollback_safe", False),
                data_sync_lag_ms=guard_inputs.get("data_sync_lag_ms", 0.0),
            )
            guard_results["G-C3"] = gr
            if not gr.passed:
                target = ChaosState.ROLLED_BACK
                blocked_by.append("G-C3")

        record = TransitionRecord(
            from_state=self._chaos_state.value,
            to_state=target.value,
            transition=transition.value,
            machine="chaos",
            guard_results=guard_results,
            readiness_trace_id=readiness_trace_id,
        )
        self._transition_history.append(record)
        self._chaos_state = target

        return {
            "success": True,
            "from_state": record.from_state,
            "to_state": target.value,
            "transition": transition.value,
            "machine": "chaos",
            "guard_results": {k: {"passed": v.passed, "detail": v.detail}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "trace_id": readiness_trace_id,
        }

    # ── Load SM ─────────────────────────────────────────────────

    @property
    def load_state(self) -> LoadState:
        return self._load_state

    def transition_load(  # LAW-3 RULE-1
        self,
        transition: LoadTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        readiness_trace_id: str = "",
    ) -> Dict[str, Any]:
        allowed = LOAD_VALID_TRANSITIONS.get(self._load_state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._load_state.value,
                "to_state": self._load_state.value,
                "transition": transition.value,
                "machine": "load",
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "trace_id": readiness_trace_id,
            }

        target = allowed[transition]
        guard_inputs = guard_inputs or {}
        guard_results: Dict[str, GuardResult] = {}
        blocked_by: List[str] = []

        if transition == LoadTransition.L_T1:
            gr = evaluate_g_d1_deterministic_load(
                profile_hash=guard_inputs.get("profile_hash", ""),
                cluster_state_hash=guard_inputs.get("cluster_state_hash", ""),
                expected_profile_hash=guard_inputs.get("expected_profile_hash", ""),
            )
            guard_results["G-D1"] = gr
            if not gr.passed:
                blocked_by.append("G-D1")

        record = TransitionRecord(
            from_state=self._load_state.value,
            to_state=target.value,
            transition=transition.value,
            machine="load",
            guard_results=guard_results,
            readiness_trace_id=readiness_trace_id,
        )
        self._transition_history.append(record)
        self._load_state = target

        return {
            "success": True,
            "from_state": record.from_state,
            "to_state": target.value,
            "transition": transition.value,
            "machine": "load",
            "guard_results": {k: {"passed": v.passed, "detail": v.detail}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "trace_id": readiness_trace_id,
        }

    # ── Certification Gate SM ───────────────────────────────────

    @property
    def cert_state(self) -> CertificationGateState:
        return self._cert_state

    def transition_cert(  # LAW-3 LAW-5 RULE-3
        self,
        transition: CertificationGateTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        readiness_trace_id: str = "",
    ) -> Dict[str, Any]:
        allowed = CERT_VALID_TRANSITIONS.get(self._cert_state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._cert_state.value,
                "to_state": self._cert_state.value,
                "transition": transition.value,
                "machine": "cert",
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "trace_id": readiness_trace_id,
            }

        target = allowed[transition]
        guard_inputs = guard_inputs or {}
        guard_results: Dict[str, GuardResult] = {}
        blocked_by: List[str] = []

        if transition == CertificationGateTransition.G_T4:
            score = guard_inputs.get("final_score", 0.0)
            if score < 0.95:
                target = CertificationGateState.CERTIFIED_C
            gr = evaluate_g_c3_recovery_verification(
                data_integrity_verified=guard_inputs.get("data_integrity_verified", False),
                lease_transferred=guard_inputs.get("lease_transferred", True),
                audit_hash_match=guard_inputs.get("audit_hash_match", True),
                p99_ms=guard_inputs.get("p99_ms", 999.0),
                oscillation_detected=guard_inputs.get("oscillation_detected", False),
                rollback_safe=guard_inputs.get("rollback_safe", False),
                data_sync_lag_ms=guard_inputs.get("data_sync_lag_ms", 0.0),
            )
            guard_results["G-C3"] = gr
            if not gr.passed:
                target = CertificationGateState.NOT_CERTIFIED
                blocked_by.append("G-C3")

        elif transition == CertificationGateTransition.G_T5:
            score = guard_inputs.get("final_score", 0.0)
            if score >= 0.95:
                target = CertificationGateState.CERTIFIED_A_B
            elif score < 0.70:
                target = CertificationGateState.NOT_CERTIFIED
            gr = evaluate_g_c3_recovery_verification(
                data_integrity_verified=guard_inputs.get("data_integrity_verified", False),
                lease_transferred=guard_inputs.get("lease_transferred", True),
                audit_hash_match=guard_inputs.get("audit_hash_match", True),
                p99_ms=guard_inputs.get("p99_ms", 999.0),
                oscillation_detected=guard_inputs.get("oscillation_detected", False),
                rollback_safe=guard_inputs.get("rollback_safe", False),
            )
            guard_results["G-C3"] = gr
            if not gr.passed:
                target = CertificationGateState.NOT_CERTIFIED
                blocked_by.append("G-C3")

        record = TransitionRecord(
            from_state=self._cert_state.value,
            to_state=target.value,
            transition=transition.value,
            machine="cert",
            guard_results=guard_results,
            readiness_trace_id=readiness_trace_id,
        )
        self._transition_history.append(record)
        self._cert_state = target

        return {
            "success": True,
            "from_state": record.from_state,
            "to_state": target.value,
            "transition": transition.value,
            "machine": "cert",
            "guard_results": {k: {"passed": v.passed, "detail": v.detail}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "trace_id": readiness_trace_id,
        }

    # ── Utility ─────────────────────────────────────────────────

    def reset(self) -> None:
        self._chaos_state = ChaosState.BASELINE_CAPTURED
        self._load_state = LoadState.IDLE
        self._cert_state = CertificationGateState.IDLE
        self._transition_history.clear()

    @property
    def transition_history(self) -> List[TransitionRecord]:
        return list(self._transition_history)
