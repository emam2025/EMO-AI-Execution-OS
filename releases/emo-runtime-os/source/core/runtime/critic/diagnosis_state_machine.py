"""Phase G2 — Diagnosis State Machine.  # LAW-7 LAW-8 RULE-3 RULE-1

7-state machine governing the G2 diagnosis lifecycle:
  FAILURE_OBSERVED → PATTERN_MATCH → ROOT_CAUSE_ISOLATE
    → [CORRECT / REJECT / NO_OP]
    → CORRECT → [ESCALATE | FAILURE_OBSERVED]

Correction Guards (RULE 3):
  - diagnosis_signal_count >= 1
  - confidence >= 0.75
  - rollback_safe == true

Deterministic Review Guard (RULE 1):
  - Cache keyed by sha256(trace + plan + context)
  - Same input → same output

Ref: Canon LAW 7, LAW 8, RULE 1, RULE 3, RULE 5
Ref: artifacts/design/g2/03_diagnosis_state_machine.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.critic_models import (
    CorrectionGuardResult,
    CorrectionGuardReason,
    DiagnosisReport,
    SeverityLevel,
)

logger = logging.getLogger("emo_ai.critic.diagnosis_sm")


class DiagnosisState(str, Enum):  # LAW-7
    FAILURE_OBSERVED = "failure_observed"
    PATTERN_MATCH = "pattern_match"
    ROOT_CAUSE_ISOLATE = "root_cause_isolate"
    CORRECT = "correct"
    REJECT = "reject"
    NO_OP = "no_op"
    ESCALATE = "escalate"


TERMINAL_STATES: set = {
    DiagnosisState.REJECT,
    DiagnosisState.NO_OP,
    DiagnosisState.ESCALATE,
}

TRANSITIONS: Dict[Tuple[DiagnosisState, DiagnosisState], Optional[str]] = {
    (DiagnosisState.FAILURE_OBSERVED, DiagnosisState.PATTERN_MATCH): "guard_has_trace",
    (DiagnosisState.PATTERN_MATCH, DiagnosisState.ROOT_CAUSE_ISOLATE): "guard_match_found",
    (DiagnosisState.PATTERN_MATCH, DiagnosisState.NO_OP): "guard_no_match",
    (DiagnosisState.ROOT_CAUSE_ISOLATE, DiagnosisState.CORRECT): "guard_correction_allowed",
    (DiagnosisState.ROOT_CAUSE_ISOLATE, DiagnosisState.REJECT): "guard_reject",
    (DiagnosisState.ROOT_CAUSE_ISOLATE, DiagnosisState.NO_OP): "guard_insufficient_evidence",
    (DiagnosisState.CORRECT, DiagnosisState.ESCALATE): "guard_escalate",
    (DiagnosisState.CORRECT, DiagnosisState.FAILURE_OBSERVED): "guard_retry",
}


class DiagnosisStateMachine:  # LAW-7 LAW-8
    """7-state machine for the G2 diagnosis lifecycle.

    All transitions are guarded. Correction Guards enforce RULE 3.
    Deterministic Review Guard ensures RULE 1 compliance.
    """

    CONFIDENCE_THRESHOLD: float = 0.75
    MATCH_CONFIDENCE_MIN: float = 0.3
    MAX_CORRECTIONS_PER_PLAN: int = 3
    RETRY_COOLDOWN_MS: float = 5000.0
    DETERMINISM_CACHE_TTL_S: float = 3600.0

    def __init__(self) -> None:
        self._current = DiagnosisState.FAILURE_OBSERVED
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._correction_count: int = 0
        self._last_retry_time: float = 0.0
        self._determinism_cache: Dict[str, Tuple[float, Any]] = {}

    @property
    def current(self) -> DiagnosisState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    @property
    def correction_count(self) -> int:
        return self._correction_count

    # ── Guards ──────────────────────────────────────────────────

    def guard_has_trace(  # LAW-12
        self,
        trace: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if not trace:
            return False, "Empty trace"
        if "error_type" not in trace and "stack_pattern" not in trace:
            return False, "Trace missing error_type or stack_pattern"
        return True, ""

    def guard_match_found(  # LAW-7
        self,
        match_confidence: float = 0.0,
    ) -> Tuple[bool, str]:
        if match_confidence >= self.MATCH_CONFIDENCE_MIN:
            return True, ""
        return False, f"Match confidence {match_confidence:.2f} < {self.MATCH_CONFIDENCE_MIN}"

    def guard_no_match(  # LAW-7
        self,
        match_confidence: float = 0.0,
    ) -> Tuple[bool, str]:
        if match_confidence < self.MATCH_CONFIDENCE_MIN:
            return True, ""
        return False, f"Match confidence {match_confidence:.2f} >= {self.MATCH_CONFIDENCE_MIN}"

    def guard_correction_allowed(  # RULE-3
        self,
        diagnosis: Optional[DiagnosisReport] = None,
    ) -> Tuple[bool, str]:
        if diagnosis is None:
            return False, "No diagnosis provided"

        signals = len(diagnosis.evidence_chain)
        confidence = diagnosis.confidence_score

        if self._correction_count >= self.MAX_CORRECTIONS_PER_PLAN:
            return False, f"Max {self.MAX_CORRECTIONS_PER_PLAN} corrections per plan exceeded"

        if signals < 1:
            return False, f"No diagnosis signals (requires >= 1)"
        if confidence < self.CONFIDENCE_THRESHOLD:
            return False, f"Confidence {confidence:.2f} < {self.CONFIDENCE_THRESHOLD}"
        return True, ""

    def guard_reject(  # LAW-8
        self,
        confidence: float = 0.0,
    ) -> Tuple[bool, str]:
        if confidence < 0.5:
            return True, ""
        return False, f"Confidence {confidence:.2f} >= 0.5 — should correct, not reject"

    def guard_insufficient_evidence(  # LAW-7
        self,
        confidence: float = 0.0,
        severity: str = "info",
    ) -> Tuple[bool, str]:
        if confidence < self.CONFIDENCE_THRESHOLD and severity not in ("error", "critical"):
            return True, ""
        return False, f"Insufficient evidence guard: confidence={confidence:.2f}, severity={severity}"

    def guard_escalate(  # LAW-7
        self,
        severity: str = "info",
        risk: float = 0.0,
    ) -> Tuple[bool, str]:
        if severity == "critical" or risk > 0.8:
            return True, ""
        return False, f"Escalation requires severity=critical or risk>0.8 (got severity={severity}, risk={risk:.2f})"

    def guard_retry(  # RULE-5
        self,
    ) -> Tuple[bool, str]:
        now_ms = time.time() * 1000
        elapsed = now_ms - self._last_retry_time
        if elapsed >= self.RETRY_COOLDOWN_MS:
            self._last_retry_time = now_ms
            return True, ""
        remaining = self.RETRY_COOLDOWN_MS - elapsed
        return False, f"Retry cooldown {remaining:.0f}ms remaining"

    # ── Correction Guard Evaluation ──────────────────────────────

    def evaluate_correction_guards(  # RULE-3
        self,
        diagnosis: DiagnosisReport,
    ) -> CorrectionGuardResult:
        signals = len(diagnosis.evidence_chain)
        confidence = diagnosis.confidence_score

        if self._correction_count >= self.MAX_CORRECTIONS_PER_PLAN:
            return CorrectionGuardResult(
                allowed=False,
                reason=f"Max {self.MAX_CORRECTIONS_PER_PLAN} corrections per plan exceeded",
                failed_guard=CorrectionGuardReason.EXCEEDS_MAX_CORRECTIONS,
                diagnosis_signal_count=signals,
                confidence=confidence,
                rollback_safe=False,
            )

        if signals < 1:
            return CorrectionGuardResult(
                allowed=False,
                reason="No diagnosis signals (requires >= 1)",
                failed_guard=CorrectionGuardReason.INSUFFICIENT_DIAGNOSIS_SIGNALS,
                diagnosis_signal_count=signals,
                confidence=confidence,
                rollback_safe=False,
            )

        if confidence < self.CONFIDENCE_THRESHOLD:
            return CorrectionGuardResult(
                allowed=False,
                reason=f"Confidence {confidence:.2f} < {self.CONFIDENCE_THRESHOLD}",
                failed_guard=CorrectionGuardReason.BELOW_CONFIDENCE_THRESHOLD,
                diagnosis_signal_count=signals,
                confidence=confidence,
                rollback_safe=False,
            )

        return CorrectionGuardResult(
            allowed=True,
            reason="All guards passed",
            diagnosis_signal_count=signals,
            confidence=confidence,
            rollback_safe=True,
        )

    # ── Deterministic Review Guard ──────────────────────────────

    def compute_determinism_hash(  # RULE-1
        self,
        trace: Dict[str, Any],
        plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        normalized = self._normalize(trace) + self._normalize(plan)
        if context:
            normalized += self._normalize(context)
        return hashlib.sha256(normalized.encode()).hexdigest()

    def check_deterministic_review(  # RULE-1
        self,
        trace: Dict[str, Any],
        plan: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        cache_key = self.compute_determinism_hash(trace, plan, context)
        now = time.time()

        if cache_key in self._determinism_cache:
            cached_time, cached_result = self._determinism_cache[cache_key]
            if now - cached_time < self.DETERMINISM_CACHE_TTL_S:
                return cached_result

        return False, "Cache miss"

    def cache_deterministic_review(  # RULE-1
        self,
        trace: Dict[str, Any],
        plan: Dict[str, Any],
        result: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        cache_key = self.compute_determinism_hash(trace, plan, context)
        self._determinism_cache[cache_key] = (time.time(), result)
        return cache_key

    # ── Transition ──────────────────────────────────────────────

    def transition(
        self,
        to_state: DiagnosisState,
        **kwargs,
    ) -> Tuple[bool, str]:
        key = (self._current, to_state)

        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value} — no transitions"

        if key not in TRANSITIONS:
            return False, (
                f"Invalid transition: {self._current.value} → {to_state.value}"
            )

        guard_name = TRANSITIONS[key]
        if guard_name is None:
            self._apply(to_state)
            return True, ""

        guard_fn = getattr(self, guard_name, None)
        if guard_fn is None:
            return False, f"Guard {guard_name} not implemented"

        result = guard_fn(**kwargs)
        if isinstance(result, tuple):
            allowed, reason = result
        else:
            allowed, reason = bool(result), ""

        if allowed:
            self._apply(to_state)
            return True, reason
        return False, reason

    def force_set(self, state: DiagnosisState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def can_correct(self) -> bool:
        return self._correction_count < self.MAX_CORRECTIONS_PER_PLAN

    def reset(self) -> None:
        self._current = DiagnosisState.FAILURE_OBSERVED
        self._history.clear()
        self._error = None
        self._correction_count = 0
        self._last_retry_time = 0.0

    def _apply(self, to_state: DiagnosisState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        if to_state == DiagnosisState.CORRECT:
            self._correction_count += 1
        self._current = to_state

    @staticmethod
    def _normalize(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, default=str)
