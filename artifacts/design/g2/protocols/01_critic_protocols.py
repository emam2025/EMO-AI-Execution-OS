"""Phase G2 — Critic Agent: Protocols.  # LAW-7 LAW-8 LAW-12

Formal typing.Protocol definitions for the Critic Agent subsystem.
Each protocol maps to a specific ROADMAP Phase G2 responsibility:

  ICriticAgent         — Top-level orchestrator (diagnose → correct → review → publish)
  IFailureDiagnoser    — Pattern matching, root-cause isolation, confidence scoring
  IPlanCorrectionEngine— Semantic fix, topology adjustment, constraint validation
  IRuntimeReviewer     — Latency observation, resource leak detection, determinism checks

Ref: Canon LAW 7 (Failure Propagation), LAW 8 (Governance), LAW 12 (Traceability)
Ref: Canon RULE 1 (Determinism), RULE 3 (Feedback-Adaptation), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.13
Ref: ROADMAP Phase G2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ── Re-usable value types (shared across protocols) ──────────────


class ReviewSignal(str, Enum):  # LAW-8
    APPROVE = "approve"
    CORRECT = "correct"
    REJECT_PLAN = "reject_plan"
    ESCALATE = "escalate"
    OPTIMIZE_RUNTIME = "optimize_runtime"


class CorrectionType(str, Enum):  # LAW-8
    SEMANTIC_FIX = "semantic_fix"
    TOPOLOGY_ADJUST = "topology_adjust"
    CONSTRAINT_RELAX = "constraint_relax"
    RESOURCE_REALLOCATE = "resource_reallocate"
    ROLLBACK = "rollback"


class SeverityLevel(str, Enum):  # LAW-7
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ═══════════════════════════════════════════════════════════════════
# 1. ICriticAgent
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class ICriticAgent(Protocol):  # LAW-8 LAW-12
    """Top-level orchestrator of the Critic Agent subsystem.

    Consumes F4 traces, D9 feedback signals, and G1 plans to:
      - diagnose failures
      - propose corrections
      - review runtime execution
      - publish assessments to EventBus

    LAW 12: Every diagnosis carries a critic_trace_id.
    LAW 8: Every assessment is published for governance audit.
    """

    def diagnose_failure(
        self,
        plan_id: str,
        failure_trace: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyse a failure trace and produce a structured report.

        Args:
            plan_id:     The G1 ExecutionPlan.plan_id under review.
            failure_trace:  Raw or pre-processed trace from F4 TraceCollector.
            context:     Optional runtime snapshot (worker topology, DAG state).

        Returns:
            A DiagnosisReport-compatible dict with keys:
              plan_id, critic_trace_id, failure_trace, root_cause,
              correction_suggestion, confidence_score, severity_level,
              timestamp.
        """

    def propose_correction(
        self,
        plan_id: str,
        diagnosis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Produce a structured correction given a diagnosis.

        Args:
            plan_id:    The failing plan.
            diagnosis:  The DiagnosisReport dict from diagnose_failure.

        Returns:
            A CorrectionPayload-compatible dict with keys:
              patch_type, affected_nodes, estimated_risk, rollback_safe,
              trace_id, critic_trace_id.
        """

    def evaluate_runtime(
        self,
        review_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Review runtime execution health and flag violations.

        Args:
            review_context:  Dict containing:
              - execution_latency:  float (ms)
              - resource_usage:     Dict[str, float]
              - determinism_hash:   str
              - worker_id:          str
              - plan_ids:           List[str]

        Returns:
            A ReviewSignal-str and supporting evidence dict.
        """

    def publish_assessment(
        self,
        plan_id: str,
        report: Dict[str, Any],
    ) -> None:
        """Publish a diagnosis/correction/review assessment to EventBus.

        §15.13: All assessments MUST be routed via EventBus topics:
          - critic.diagnosis.completed
          - critic.correction.proposed
          - critic.runtime.reviewed

        LAW 20-22: FailureMatrix MUST emit related events if
        diagnosis severity >= ERROR level.
        """


# ═══════════════════════════════════════════════════════════════════
# 2. IFailureDiagnoser
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IFailureDiagnoser(Protocol):  # LAW-7 LAW-12
    """Failure diagnosis subsystem.

    Analyses error patterns, matches against known signatures,
    isolates root causes, and rates diagnostic confidence.

    LAW 7: All failures MUST be propagated to EventBus.
    RULE 5: Recovery paths MUST be deterministic.
    """

    def analyze_error_pattern(
        self,
        trace: Dict[str, Any],
        known_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Match a failure trace against known error patterns.

        Args:
            trace:  F4 trace span data.
            known_patterns:  Optional list of {pattern_id, regex, category}.

        Returns:
            Dict with matched_pattern_id, category, match_confidence.
        """

    def match_failure_signature(
        self,
        error_type: str,
        stack_pattern: str,
        resource_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Match a failure against the FailureSignature registry.

        Returns:
            Dict with signature_id, label, severity, match_score.
        """

    def isolate_root_cause(
        self,
        trace: Dict[str, Any],
        signature: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Isolate root cause from trace + matched signature.

        Returns:
            Dict with root_cause_node, root_cause_type, evidence_chain.
        """

    def rate_confidence(
        self,
        evidence_chain: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Rate diagnostic confidence (0.0 – 1.0) based on evidence.

        RULE 1: Must be deterministic — same evidence → same score.
        Returns confidence >= 0.75 for actionable diagnosis.
        """


# ═══════════════════════════════════════════════════════════════════
# 3. IPlanCorrectionEngine
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IPlanCorrectionEngine(Protocol):  # LAW-8 RULE-3
    """Plan correction engine.

    Applies semantic fixes, adjusts DAG topology, validates constraints,
    and estimates rollback risk.

    RULE 3: Every correction MUST require ≥ 1 diagnosis signal
    AND confidence ≥ 0.75 AND rollback_safe = true.
    """

    def apply_semantic_fix(
        self,
        plan: Dict[str, Any],
        correction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply a semantic correction to a plan node.

        Returns:  Updated plan dict.
        """

    def adjust_topology(
        self,
        dag: List[Dict[str, Any]],
        affected_nodes: List[str],
        strategy: str = "reorder",
    ) -> List[Dict[str, Any]]:
        """Adjust DAG topology (reorder, bypass, insert barrier).

        Returns:  Updated edges list.
        """

    def validate_constraint_compliance(
        self,
        corrected_plan: Dict[str, Any],
        constraints: Optional[List[str]] = None,
    ) -> bool:
        """Validate corrected plan against all active constraints.

        Returns:  True if all constraints satisfied.
        """

    def estimate_impact(
        self,
        plan_id: str,
        correction: Dict[str, Any],
        baseline: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Estimate risk, cost, and side effects of a correction.

        Returns:  Dict with risk_score, cost_delta, affected_node_count,
                  rollback_complexity.
        """


# ═══════════════════════════════════════════════════════════════════
# 4. IRuntimeReviewer
# ═══════════════════════════════════════════════════════════════════


@runtime_checkable
class IRuntimeReviewer(Protocol):  # LAW-12 RULE-1
    """Runtime execution reviewer.

    Observes latency, detects resource leaks, flags determinism
    violations, and suggests optimisations.

    RULE 1: All review outputs MUST be deterministic.
    LAW 12: Every review is traceable via critic_trace_id.
    """

    def observe_execution_latency(
        self,
        execution_trace: List[Dict[str, Any]],
        threshold_ms: float = 1000.0,
    ) -> Dict[str, Any]:
        """Observe execution latency from F4 trace data.

        Returns:  Dict with max_latency, p95_latency, slowest_node,
                  threshold_breached (bool).
        """

    def detect_resource_leak(
        self,
        worker_snapshots: List[Dict[str, Any]],
        threshold_delta: float = 0.15,
    ) -> Dict[str, Any]:
        """Detect resource leaks across worker snapshots.

        Returns:  Dict with leak_detected (bool), affected_workers,
                  delta_percent, estimated_leak_bytes.
        """

    def flag_determinism_violation(
        self,
        expected_hash: str,
        actual_hash: str,
        execution_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Flag a non-deterministic execution.

        RULE 1: Same input + same context → same output.
        Returns:  Dict with violation_detected (bool), hash_mismatch,
                  context_snapshot.
        """

    def suggest_optimization(
        self,
        plan: Dict[str, Any],
        trace: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Suggest optimisations based on plan+trace analysis.

        Returns:  List of suggestion dicts with node_id, current_cost,
                  estimated_improvement, suggestion_type.
        """
