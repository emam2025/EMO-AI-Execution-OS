"""Phase J3 — Chaos Engineering & Load Testing Data Models.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Design-only dataclass and enum definitions for the Production Readiness
Layer. Every model carries readiness_trace_id for end-to-end traceability
(LAW 8). No global state — all instances are scenario-scoped (LAW 11).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.13 (Chaos Engineering), §16 (Production Readiness)
Ref: artifacts/design/j3/protocols/01_readiness_protocols.py
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════
# Enums (canonical source — protocols/01_readiness_protocols.py
# duplicates these for design self-containment)
# ═══════════════════════════════════════════════════════════════

class FaultType(str, Enum):  # LAW-20
    NETWORK_PARTITION = "network_partition"
    WORKER_FAILURE = "worker_failure"
    DB_FAILOVER = "db_failover"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    LATENCY_INJECTION = "latency_injection"
    CONNECTION_DROP = "connection_drop"
    STORAGE_OUTAGE = "storage_outage"


class SeverityLevel(str, Enum):  # LAW-21
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RecoveryStrategy(str, Enum):  # LAW-8 LAW-22
    AUTO_RECOVER = "auto_recover"
    ROLLBACK = "rollback"
    ESCALATE = "escalate"
    MANUAL_INTERVENTION = "manual_intervention"


class LoadShape(str, Enum):  # RULE-1
    LINEAR_RAMP = "linear_ramp"
    STEP_FUNCTION = "step_function"
    SPIKE = "spike"
    CONSTANT = "constant"
    SINUSOIDAL = "sinusoidal"


class ValidationStatus(str, Enum):  # LAW-5
    PASS = "pass"
    FAIL = "fail"
    FLAG = "flag"
    SKIPPED = "skipped"


class CertificationGrade(str, Enum):  # LAW-5
    A = "A"
    B = "B"
    C = "C"
    F = "F"


class ChaosState(str, Enum):  # LAW-8
    BASELINE_CAPTURED = "baseline_captured"
    FAULT_INJECTED = "fault_injected"
    MONITOR_DEGRADATION = "monitor_degradation"
    AUTO_RECOVERY = "auto_recovery"
    VERIFY_INTEGRITY = "verify_integrity"
    ESCALATED = "escalated"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"


class LoadState(str, Enum):  # LAW-5
    IDLE = "idle"
    GENERATING = "generating"
    PRESSURE_APPLIED = "pressure_applied"
    MEASURING = "measuring"
    OSCILLATION_CHECK = "oscillation_check"
    COMPLETED = "completed"


# ═══════════════════════════════════════════════════════════════
# Model 1: ChaosScenario
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChaosScenario:  # LAW-8 LAW-11 LAW-20 LAW-21 RULE-3
    """A single chaos engineering scenario with fault injection parameters.

    LAW 8: expected_recovery_sec MUST be specified for recoverability SLO.
    LAW 11: Each ChaosScenario is an independent instance.
    LAW 20: target_service and fault_type define the fault boundary.
    LAW 21: severity determines the escalation path if recovery fails.
    RULE 3: expected_recovery_sec is validated by Recovery Guards.
    """
    scenario_id: str
    target_service: str
    fault_type: FaultType
    duration_sec: float
    expected_recovery_sec: float  # LAW-8 — NON-NEGOTIABLE
    severity: SeverityLevel
    readiness_trace_id: str  # LAW-8 — end-to-end traceability
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.AUTO_RECOVER
    chaos_state: ChaosState = ChaosState.BASELINE_CAPTURED
    created_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)
    scenario_hash: str = ""

    def __post_init__(self) -> None:
        if not self.scenario_hash:
            import hashlib
            raw = (
                f"{self.scenario_id}:{self.target_service}:{self.fault_type.value}:"
                f"{self.duration_sec}:{self.expected_recovery_sec}:{self.severity.value}"
            )
            self.scenario_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════
# Model 2: LoadProfile
# ═══════════════════════════════════════════════════════════════

@dataclass
class LoadProfile:  # LAW-5 LAW-11 RULE-1 RULE-2
    """Load testing profile defining concurrent workload parameters.

    LAW 5: Profile parameters determine stability measurement conditions.
    LAW 11: Each LoadProfile is an independent instance.
    RULE 1: Same fields -> same deterministic load curve hash. This
            prevents Non-Deterministic Test Drift.
    RULE 2: All fields validated (concurrent_users >= 1, dags_per_second > 0,
            duration_sec > 0, ramp_up_curve in LoadShape).
    """
    profile_id: str
    concurrent_users: int
    dags_per_second: float
    resource_multiplier: float
    duration_sec: float
    ramp_up_curve: LoadShape  # Determines load injection pattern
    readiness_trace_id: str  # LAW-8
    created_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)
    profile_hash: str = ""

    def __post_init__(self) -> None:
        if not self.profile_hash:
            import hashlib
            raw = (
                f"{self.profile_id}:{self.concurrent_users}:{self.dags_per_second}:"
                f"{self.resource_multiplier}:{self.duration_sec}:{self.ramp_up_curve.value}"
            )
            self.profile_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════
# Model 3: StabilityMetric
# ═══════════════════════════════════════════════════════════════

@dataclass
class StabilityMetric:  # LAW-3 LAW-5 LAW-11 RULE-1 RULE-3
    """Point-in-time stability measurement for a load test run.

    LAW 3: All metrics are measured and timestamped.
    LAW 5: p99_ms and oscillation_flag directly impact certification grade.
    LAW 11: Each StabilityMetric is an independent measurement instance.
    RULE 1: Same measurement parameters -> same metric values.
    RULE 3: p99_ms < threshold is a Recovery Guard condition.
    """
    metric_id: str
    p50_ms: float
    p99_ms: float
    throughput_ops_sec: float
    error_rate_pct: float
    oscillation_flag: bool
    readiness_trace_id: str  # LAW-8
    p999_ms: float = 0.0
    sample_count: int = 0
    measured_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Model 4: ReadinessReport
# ═══════════════════════════════════════════════════════════════

@dataclass
class ReadinessReport:  # LAW-3 LAW-5 LAW-8 LAW-21 LAW-22 RULE-3 RULE-5
    """Final readiness certification report produced by ICertificationGate.

    LAW 3: All validation results are captured with timestamps.
    LAW 5: final_score and grade determine production readiness.
    LAW 8: chaos_pass confirms recovery SLOs were met.
    LAW 21: severity_evaluation captures worst severity encountered.
    LAW 22: cascade_risk flag indicates cascading failure potential.
    RULE 3: certifiable is False if integrity or p99 guard fails.
    RULE 5: rollback_verified confirms rollback safety.
    """
    report_id: str
    chaos_pass: bool
    load_pass: bool
    integrity_pass: bool
    canon_compliance: bool
    final_score: float
    grade: CertificationGrade
    readiness_trace_id: str  # LAW-8
    severity_evaluation: SeverityLevel = SeverityLevel.LOW
    cascade_risk_detected: bool = False
    rollback_verified: bool = False
    certifiable: bool = False
    blocked_by: List[str] = field(default_factory=list)
    chaos_scenarios: List[ChaosScenario] = field(default_factory=list)
    load_profiles: List[LoadProfile] = field(default_factory=list)
    stability_metrics: List[StabilityMetric] = field(default_factory=list)
    generated_at_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    metadata: Dict[str, Any] = field(default_factory=dict)
    report_hash: str = ""

    def __post_init__(self) -> None:
        if not self.report_hash:
            import hashlib
            raw = (
                f"{self.report_id}:{self.final_score}:{self.grade.value}:"
                f"{self.chaos_pass}:{self.load_pass}:{self.integrity_pass}:"
                f"{self.canon_compliance}"
            )
            self.report_hash = hashlib.sha256(raw.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════════
# Model 5: ChaosExecutionLog
# ═══════════════════════════════════════════════════════════════

@dataclass
class ChaosExecutionLog:  # LAW-8 LAW-20 RULE-4
    """Audit log entry for a chaos injection + recovery cycle.

    LAW 8: Tracks recovery time vs expected_recovery_sec.
    LAW 20: Records fault boundary (target_service, fault_type).
    RULE 4: readiness_trace_id chains to the originating scenario.
    """
    log_id: str
    scenario_id: str
    injection_id: str
    target_service: str
    fault_type: FaultType
    injected_at_ns: int
    recovered_at_ns: int
    recovery_duration_ns: int
    recovery_slo_met: bool
    readiness_trace_id: str  # LAW-8
    state_transitions: List[ChaosState] = field(default_factory=list)
    guard_results: Dict[str, bool] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
