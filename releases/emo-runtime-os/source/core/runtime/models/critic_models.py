"""Phase G2 — Critic Agent: Runtime Models.  # LAW-7 LAW-8 LAW-12

Mirrors artifacts/design/g2/models/02_diagnosis_and_review_models.py
for runtime importability.

Shared types used by all G2 components.

Ref: Canon LAW 7, LAW 8, LAW 12, RULE 1, RULE 3, RULE 5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SeverityLevel(str, Enum):  # LAW-7
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class CorrectionType(str, Enum):  # LAW-8
    SEMANTIC_FIX = "semantic_fix"
    TOPOLOGY_ADJUST = "topology_adjust"
    CONSTRAINT_RELAX = "constraint_relax"
    RESOURCE_REALLOCATE = "resource_reallocate"
    ROLLBACK = "rollback"


class ReviewSignal(str, Enum):  # LAW-8
    APPROVE = "approve"
    CORRECT = "correct"
    REJECT_PLAN = "reject_plan"
    ESCALATE = "escalate"
    OPTIMIZE_RUNTIME = "optimize_runtime"


class CorrectionGuardReason(str, Enum):  # LAW-8 RULE-3
    INSUFFICIENT_DIAGNOSIS_SIGNALS = "insufficient_diagnosis_signals"
    BELOW_CONFIDENCE_THRESHOLD = "below_confidence_threshold"
    NOT_ROLLBACK_SAFE = "not_rollback_safe"
    PLAN_IN_TERMINAL_STATE = "plan_in_terminal_state"
    EXCEEDS_MAX_CORRECTIONS = "exceeds_max_corrections"


@dataclass
class DiagnosisReport:  # LAW-7 LAW-12
    plan_id: str = ""
    critic_trace_id: str = ""
    failure_trace: Dict[str, Any] = field(default_factory=dict)
    root_cause: str = ""
    root_cause_node: str = ""
    correction_suggestion: str = ""
    confidence_score: float = 0.0
    severity_level: SeverityLevel = SeverityLevel.INFO
    evidence_chain: List[Dict[str, Any]] = field(default_factory=list)
    matched_signature_id: str = ""
    timestamp_ns: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.confidence_score >= 0.75 and (
            self.severity_level in (SeverityLevel.WARNING, SeverityLevel.ERROR, SeverityLevel.CRITICAL)
        )

    @property
    def requires_escalation(self) -> bool:
        return self.severity_level == SeverityLevel.CRITICAL


@dataclass
class FailureSignature:  # LAW-7
    signature_id: str = ""
    label: str = ""
    error_type: str = ""
    stack_pattern: str = ""
    resource_state: Dict[str, float] = field(default_factory=dict)
    severity: SeverityLevel = SeverityLevel.WARNING
    category: str = "unknown"
    match_confidence: float = 0.0
    suggested_correction: str = ""
    created_at_ns: int = 0


@dataclass
class CorrectionPayload:  # LAW-8
    patch_type: CorrectionType = CorrectionType.SEMANTIC_FIX
    affected_nodes: List[str] = field(default_factory=list)
    estimated_risk: float = 0.0
    rollback_safe: bool = True
    trace_id: str = ""
    critic_trace_id: str = ""
    estimated_impact: Dict[str, Any] = field(default_factory=dict)
    constraint_violations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def meets_correction_guards(self) -> bool:
        return self.rollback_safe and self.estimated_risk < 0.5


@dataclass
class CorrectionGuardResult:  # LAW-8 RULE-3
    allowed: bool = False
    reason: str = ""
    failed_guard: Optional[CorrectionGuardReason] = None
    diagnosis_signal_count: int = 0
    confidence: float = 0.0
    rollback_safe: bool = False


@dataclass
class RuntimeReviewSnapshot:  # LAW-12
    plan_ids: List[str] = field(default_factory=list)
    critic_trace_id: str = ""
    signal: ReviewSignal = ReviewSignal.APPROVE
    max_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    slowest_node: str = ""
    resource_leak_detected: bool = False
    determinism_violation_detected: bool = False
    optimization_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    timestamp_ns: int = 0
