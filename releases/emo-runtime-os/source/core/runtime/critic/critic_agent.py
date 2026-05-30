"""Phase G2 — Critic Agent.  # LAW-8 LAW-12 LAW-20-22

Concrete implementation of ICriticAgent.

Top-level orchestrator consuming F4 traces, D9 signals, and G1 plans.
Diagnoses failures, proposes corrections, reviews runtime execution,
and publishes all assessments to EventBus.

Correction Guards (RULE 3): require ≥1 diagnosis signal AND
confidence >= 0.75 AND rollback_safe = true.

Ref: Canon LAW 8, LAW 12, LAW 20-22, RULE 1, RULE 3
Ref: artifacts/design/g2/protocols/01_critic_protocols.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.critic_models import (
    CorrectionGuardResult,
    CorrectionGuardReason,
    CorrectionPayload,
    CorrectionType,
    DiagnosisReport,
    ReviewSignal,
    RuntimeReviewSnapshot,
    SeverityLevel,
)
from core.runtime.critic.diagnosis_state_machine import (
    DiagnosisState,
    DiagnosisStateMachine,
)
from core.runtime.critic.failure_diagnoser import FailureDiagnoser
from core.runtime.critic.plan_correction_engine import PlanCorrectionEngine
from core.runtime.critic.runtime_reviewer import RuntimeReviewer
from core.runtime.critic.trace_correlator import CriticTraceCorrelator

logger = logging.getLogger("emo_ai.critic.critic_agent")


class CriticAgent:  # LAW-8 LAW-12
    """Top-level orchestrator of the G2 Critic Agent subsystem.

    LAW 12: Every diagnosis carries a critic_trace_id.
    LAW 8: Every assessment is published for governance audit.
    LAW 20-22: All failure-related events propagate via EventBus.
    """

    def __init__(
        self,
        failure_diagnoser: FailureDiagnoser,
        correction_engine: PlanCorrectionEngine,
        runtime_reviewer: RuntimeReviewer,
        state_machine: DiagnosisStateMachine,
        trace_correlator: CriticTraceCorrelator,
        event_bus: Optional[Any] = None,
        strict_critic_mode: bool = False,
    ) -> None:
        self._diagnoser = failure_diagnoser
        self._correction_engine = correction_engine
        self._reviewer = runtime_reviewer
        self._sm = state_machine
        self._correlator = trace_correlator
        self._event_bus = event_bus
        self._strict_critic_mode = strict_critic_mode
        self._diagnosis_store: Dict[str, DiagnosisReport] = {}
        self._correction_store: Dict[str, CorrectionPayload] = {}
        self._review_store: Dict[str, RuntimeReviewSnapshot] = {}
        self._cached_determinism_hashes: Dict[str, str] = {}

    # ── Properties ──────────────────────────────────────────────

    @property
    def state_machine(self) -> DiagnosisStateMachine:
        return self._sm

    @property
    def diagnoser(self) -> FailureDiagnoser:
        return self._diagnoser

    @property
    def correction_engine(self) -> PlanCorrectionEngine:
        return self._correction_engine

    @property
    def reviewer(self) -> RuntimeReviewer:
        return self._reviewer

    @property
    def trace_correlator(self) -> CriticTraceCorrelator:
        return self._correlator

    # ── diagnose_failure ────────────────────────────────────────

    def diagnose_failure(  # LAW-12
        self,
        plan_id: str,
        failure_trace: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        critic_trace_id = self._correlator.generate_trace_id(plan_id, failure_trace)

        self._sm.force_set(DiagnosisState.FAILURE_OBSERVED)
        ok, reason = self._sm.transition(DiagnosisState.PATTERN_MATCH, trace=failure_trace)
        if not ok:
            raise RuntimeError(f"Guard blocked: {reason}")

        self._correlator.record_correlation(plan_id, "g2_critic", critic_trace_id)

        pattern_result = self._diagnoser.analyze_error_pattern(failure_trace)
        match_conf = pattern_result.get("match_confidence", 0.0)

        if match_conf >= DiagnosisStateMachine.MATCH_CONFIDENCE_MIN:
            ok, _ = self._sm.transition(DiagnosisState.ROOT_CAUSE_ISOLATE, match_confidence=match_conf)
            if not ok:
                self._sm.force_set(DiagnosisState.FAILURE_OBSERVED)
                raise RuntimeError(f"Failed to isolate root cause")
        else:
            self._sm.transition(DiagnosisState.NO_OP, match_confidence=match_conf)

        diagnosis = self._diagnoser.diagnose(plan_id, failure_trace, critic_trace_id)

        self._diagnosis_store[plan_id] = diagnosis

        self._emit("critic.diagnosis.completed", {
            "plan_id": plan_id,
            "critic_trace_id": critic_trace_id,
            "severity": diagnosis.severity_level.value,
            "confidence": diagnosis.confidence_score,
            "state": "diagnosed",
        })

        cache_key = self._sm.cache_deterministic_review(
            failure_trace, {"plan_id": plan_id}, diagnosis, context
        )
        self._cached_determinism_hashes[critic_trace_id] = cache_key

        return {
            "plan_id": diagnosis.plan_id,
            "critic_trace_id": diagnosis.critic_trace_id,
            "failure_trace": diagnosis.failure_trace,
            "root_cause": diagnosis.root_cause,
            "correction_suggestion": diagnosis.correction_suggestion,
            "confidence_score": diagnosis.confidence_score,
            "severity_level": diagnosis.severity_level.value,
            "timestamp": diagnosis.timestamp_ns,
            "evidence_chain": diagnosis.evidence_chain,
        }

    # ── propose_correction ──────────────────────────────────────

    def propose_correction(  # RULE-3
        self,
        plan_id: str,
        diagnosis: Dict[str, Any],
    ) -> Dict[str, Any]:
        if self._strict_critic_mode and self._sm.current not in (
            DiagnosisState.ROOT_CAUSE_ISOLATE, DiagnosisState.FAILURE_OBSERVED,
            DiagnosisState.CORRECT,
        ):
            raise RuntimeError(
                f"Cannot propose correction from state {self._sm.current.value}"
            )

        if isinstance(diagnosis, dict):
            diag_report = DiagnosisReport(**{
                k: v for k, v in diagnosis.items()
                if k in DiagnosisReport.__dataclass_fields__
            })
        else:
            diag_report = diagnosis

        if not diag_report.critic_trace_id:
            diag_report.critic_trace_id = self._correlator.generate_trace_id(plan_id, {})

        # Correction Guards (RULE 3)
        guard_result = self._sm.evaluate_correction_guards(diag_report)

        if not guard_result.allowed:
            self._emit("critic.correction.rejected", {
                "plan_id": plan_id,
                "critic_trace_id": diag_report.critic_trace_id,
                "reason": guard_result.reason,
                "failed_guard": guard_result.failed_guard.value if guard_result.failed_guard else "",
            })
            raise RuntimeError(f"Correction guard rejected: {guard_result.reason}")

        payload = self._correction_engine.propose_correction(diag_report)
        payload.trace_id = plan_id
        payload.critic_trace_id = diag_report.critic_trace_id

        ok, _ = self._sm.transition(DiagnosisState.CORRECT, diagnosis=diag_report)
        if not ok:
            raise RuntimeError("Failed to transition to CORRECT state")

        self._correction_store[plan_id] = payload
        self._correlator.record_correlation(plan_id, "g1_planner", diag_report.critic_trace_id)

        self._emit("critic.correction.proposed", {
            "plan_id": plan_id,
            "critic_trace_id": diag_report.critic_trace_id,
            "patch_type": payload.patch_type.value,
            "estimated_risk": payload.estimated_risk,
            "rollback_safe": payload.rollback_safe,
        })

        return {
            "patch_type": payload.patch_type.value,
            "affected_nodes": list(payload.affected_nodes),
            "estimated_risk": payload.estimated_risk,
            "rollback_safe": payload.rollback_safe,
            "trace_id": payload.trace_id,
            "critic_trace_id": payload.critic_trace_id,
        }

    # ── evaluate_runtime ────────────────────────────────────────

    def evaluate_runtime(  # LAW-12
        self,
        review_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        plan_ids = review_context.get("plan_ids", [])
        critic_trace_id = self._correlator.generate_trace_id(
            "_".join(plan_ids) if plan_ids else "runtime",
            review_context,
        )

        snapshot = self._reviewer.review(review_context, critic_trace_id)

        self._review_store[critic_trace_id] = snapshot

        self._emit("critic.runtime.reviewed", {
            "critic_trace_id": critic_trace_id,
            "signal": snapshot.signal.value,
            "max_latency_ms": snapshot.max_latency_ms,
            "determinism_violation": snapshot.determinism_violation_detected,
        })

        if snapshot.determinism_violation_detected:
            dhash = self._cached_determinism_hashes.get(critic_trace_id, "")
            self._emit("critic.drift.detected", {
                "critic_trace_id": critic_trace_id,
                "plan_ids": plan_ids,
                "expected_hash": dhash,
                "actual_hash": review_context.get("actual_hash", ""),
            })

        return {
            "signal": snapshot.signal.value,
            "max_latency_ms": snapshot.max_latency_ms,
            "p95_latency_ms": snapshot.p95_latency_ms,
            "slowest_node": snapshot.slowest_node,
            "resource_leak_detected": snapshot.resource_leak_detected,
            "determinism_violation_detected": snapshot.determinism_violation_detected,
            "optimization_suggestions": snapshot.optimization_suggestions,
        }

    # ── publish_assessment ──────────────────────────────────────

    def publish_assessment(  # LAW-8 LAW-20-22
        self,
        plan_id: str,
        report: Dict[str, Any],
    ) -> None:
        severity = report.get("severity_level", "info")
        critic_trace_id = report.get("critic_trace_id", "")

        if severity in ("error", "critical") and self._event_bus is not None:
            self._emit("critic.escalation.triggered", {
                "plan_id": plan_id,
                "critic_trace_id": critic_trace_id,
                "reason": f"Severity {severity} triggered escalation",
                "report": report,
            })
            if self._sm.transition(DiagnosisState.ESCALATE, severity=severity)[0]:
                pass

        self._emit("critic.assessment.published", {
            "plan_id": plan_id,
            "critic_trace_id": critic_trace_id,
            "severity": severity,
        })

        self._correlator.propagate_to_f4(plan_id, critic_trace_id)

    # ── Escalate ────────────────────────────────────────────────

    def escalate(  # LAW-7
        self,
        plan_id: str,
        severity: str = "critical",
        risk: float = 0.9,
    ) -> Dict[str, Any]:
        result = self._sm.transition(
            DiagnosisState.ESCALATE,
            severity=severity,
            risk=risk,
        )
        if not result[0]:
            raise RuntimeError(f"Escalation guard: {result[1]}")

        self._emit("critic.escalation.triggered", {
            "plan_id": plan_id,
            "critic_trace_id": self._correlator.correlation_for(plan_id, "g2_critic"),
            "reason": f"Escalation: severity={severity}, risk={risk:.2f}",
        })

        return {"plan_id": plan_id, "state": "escalated"}

    # ── Internal helpers ────────────────────────────────────────

    def _emit(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            try:
                self._event_bus.publish(topic, payload)
            except Exception:
                logger.warning("Failed to emit %s", topic, exc_info=True)

    def reset(self) -> None:
        self._diagnosis_store.clear()
        self._correction_store.clear()
        self._review_store.clear()
        self._cached_determinism_hashes.clear()
        self._sm.reset()
        self._correlator.reset()
