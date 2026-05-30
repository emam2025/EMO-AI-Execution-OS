"""Default Canon ruleset — CanonRule model instances."""

from typing import Any, Callable, Dict, List

from core.canon.result import CanonRule
from core.canon.rules import (
    law_14, law_15, law_16, law_17, law_18, law_19,
    law_20, law_21, law_22, law_23, law_24, law_25, law_26, law_27,
    law_28, law_29, law_30,
)


DEFAULT_RULES: List[CanonRule] = [
    CanonRule(
        id="LAW_14",
        description="All boundary decisions MUST be derived from CodeGraph analysis",
        severity="CRITICAL",
        evaluate=law_14,
        message="CodeGraph not available for boundary decision",
    ),
    CanonRule(
        id="LAW_15",
        description="No refactor is valid unless dependency graph is updated first",
        severity="CRITICAL",
        evaluate=law_15,
        message="Stale dependency graph detected — must regenerate CodeGraph first",
    ),
    CanonRule(
        id="LAW_16",
        description="Any node with risk_score > 0.8 MUST be decomposed",
        severity="CRITICAL",
        evaluate=law_16,
        message="High-risk node exists and is not decomposed",
    ),
    CanonRule(
        id="LAW_17",
        description="Runtime behavior MUST be observable as graph transformations",
        severity="HIGH",
        evaluate=law_17,
        message="No event bus — runtime behavior is not observable",
    ),
    CanonRule(
        id="LAW_18",
        description="Static and runtime architecture MUST be continuously reconciled",
        severity="HIGH",
        evaluate=law_18,
        message="No drift detector — architecture reconciliation disabled",
    ),
    CanonRule(
        id="LAW_19",
        description="All execution traces MUST be explainable",
        severity="MEDIUM",
        evaluate=law_19,
        message="No RuntimeIntelligence — traces are not explainable",
    ),
    # ── D8.2 — Failure Propagation ──
    CanonRule(
        id="LAW_20",
        description="Every service MUST have a defined failure propagation policy",
        severity="CRITICAL",
        evaluate=law_20,
        message="No FailurePropagationPolicy — cross-service failure handling undefined",
    ),
    CanonRule(
        id="LAW_21",
        description="Dispatcher failure MUST trigger scheduler retry, retry classification, and lease release",
        severity="HIGH",
        evaluate=law_21,
        message="Dispatcher failure propagation incomplete — missing retry, classify, or lease release",
    ),
    CanonRule(
        id="LAW_22",
        description="Lease expiry MUST trigger cancel, rollback, and reassign",
        severity="HIGH",
        evaluate=law_22,
        message="Lease expiry propagation incomplete — missing cancel, rollback, or reassign",
    ),
    # ── D8.4 — Service Ownership ──
    CanonRule(
        id="LAW_23",
        description="IExecutionScheduler MUST own execution ordering only",
        severity="HIGH",
        evaluate=law_23,
        message="Scheduler exposes non-scheduling methods — ownership boundary violated",
    ),
    CanonRule(
        id="LAW_24",
        description="IExecutionDispatcher MUST own execution routing only",
        severity="HIGH",
        evaluate=law_24,
        message="Dispatcher exposes non-routing methods — ownership boundary violated",
    ),
    CanonRule(
        id="LAW_25",
        description="IExecutionRetryHandler MUST own retry semantics only",
        severity="HIGH",
        evaluate=law_25,
        message="Retry handler exposes non-retry methods — ownership boundary violated",
    ),
    CanonRule(
        id="LAW_26",
        description="IExecutionStateStore MUST own persistence and traces only",
        severity="HIGH",
        evaluate=law_26,
        message="State store exposes non-persistence methods — ownership boundary violated",
    ),
    CanonRule(
        id="LAW_27",
        description="No two services MAY share ownership of the same domain",
        severity="HIGH",
        evaluate=law_27,
        message="Domain ownership overlap detected — shared methods found across services",
    ),
    # ── GAP 4 — Evolution Meta-Governance ──
    CanonRule(
        id="LAW_28",
        description="Human-in-the-loop Evolution Gate — any Canon/Architecture change requires explicit approval",
        severity="CRITICAL",
        evaluate=law_28,
        message="No evolution approval gate — system can auto-mutate without human oversight",
    ),
    CanonRule(
        id="LAW_29",
        description="Immutable Audit Trail for Evolution — every evolution change must be logged and replayable",
        severity="HIGH",
        evaluate=law_29,
        message="No evolution audit log — changes cannot be traced or replayed",
    ),
    CanonRule(
        id="LAW_30",
        description="Safe Rollback Requirement — any evolution must be reversible without system corruption",
        severity="HIGH",
        evaluate=law_30,
        message="No evolution rollback mechanism — changes cannot be safely reverted",
    ),
]
