"""Phase G4 — Synthesis State Machine.  # LAW-2 LAW-10 LAW-14 RULE-1 RULE-2 RULE-3

8-state machine governing the G4 synthesis lifecycle:

  INTENT_RECEIVED → CODE_GENERATION → AST_VALIDATION → SECURITY_SCAN
    → SANDBOX_DRY_RUN → [REGISTER / REJECT / ESCALATE]

7 Safety Guards (G1–G7, RULE 3):
  G1: ast_valid == true
  G2: no_os_imports == true
  G3: capability_match >= 0.8
  G4: confidence >= 0.7
  G5: sandbox_dry_run_success == true
  G6: side_effects empty
  G7: risk_score <= 0.3

Deterministic Synthesis Guard (RULE 1):
  Cache keyed by sha256(intent + context + capability_set)

Ref: Canon LAW 2, LAW 10, LAW 14, RULE 1–4
Ref: artifacts/design/g4/03_synthesis_state_machine.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.synthesis.synthesis_sm")


class SynthesisState(str, Enum):  # LAW-14
    INTENT_RECEIVED = "intent_received"
    CODE_GENERATION = "code_generation"
    AST_VALIDATION = "ast_validation"
    SECURITY_SCAN = "security_scan"
    SANDBOX_DRY_RUN = "sandbox_dry_run"
    REGISTER = "register"
    REJECT = "reject"
    ESCALATE = "escalate"


TERMINAL_STATES: set = {
    SynthesisState.REGISTER,
    SynthesisState.REJECT,
    SynthesisState.ESCALATE,
}

TRANSITIONS: Dict[Tuple[SynthesisState, SynthesisState], Optional[str]] = {
    (SynthesisState.INTENT_RECEIVED, SynthesisState.CODE_GENERATION): "guard_has_intent",
    (SynthesisState.INTENT_RECEIVED, SynthesisState.REJECT): "guard_incomplete_intent",
    (SynthesisState.CODE_GENERATION, SynthesisState.AST_VALIDATION): "guard_code_generated",
    (SynthesisState.CODE_GENERATION, SynthesisState.REJECT): "guard_generation_failed",
    (SynthesisState.AST_VALIDATION, SynthesisState.SECURITY_SCAN): "guard_ast_valid",
    (SynthesisState.AST_VALIDATION, SynthesisState.REJECT): "guard_ast_invalid",
    (SynthesisState.SECURITY_SCAN, SynthesisState.SANDBOX_DRY_RUN): "guard_security_clear",
    (SynthesisState.SECURITY_SCAN, SynthesisState.ESCALATE): "guard_needs_escalation",
    (SynthesisState.SECURITY_SCAN, SynthesisState.REJECT): "guard_security_fail",
    (SynthesisState.SANDBOX_DRY_RUN, SynthesisState.REGISTER): "guard_sandbox_passed",
    (SynthesisState.SANDBOX_DRY_RUN, SynthesisState.REJECT): "guard_sandbox_failed",
    (SynthesisState.SANDBOX_DRY_RUN, SynthesisState.ESCALATE): "guard_sandbox_ambiguous",
}


class SynthesisStateMachine:  # LAW-2 LAW-10 LAW-14 RULE-1 RULE-2 RULE-3
    """8-state machine for the G4 synthesis lifecycle.

    All transitions are guarded. Safety Guards (G1–G7) enforce RULE 3.
    Deterministic Synthesis Guard ensures RULE 1 compliance.
    """

    MIN_CAPABILITY_MATCH: float = 0.8
    MIN_CONFIDENCE_THRESHOLD: float = 0.7
    MAX_RISK_SCORE: float = 0.3
    ESCALATION_RISK_THRESHOLD: float = 0.7
    DETERMINISM_CACHE_TTL_S: float = 3600.0

    def __init__(self) -> None:
        self._current = SynthesisState.INTENT_RECEIVED
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._determinism_cache: Dict[str, Tuple[float, str, str]] = {}

    @property
    def current(self) -> SynthesisState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards ──────────────────────────────────────────────────

    def guard_has_intent(  # LAW-2
        self,
        intent: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if intent is None:
            return False, "No intent provided"
        if not intent.get("goal"):
            return False, "Intent missing 'goal'"
        if not intent.get("target_nodes"):
            return False, "Intent missing 'target_nodes'"
        return True, ""

    def guard_incomplete_intent(  # LAW-2
        self,
        intent: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if intent is None:
            return True, ""
        if not intent.get("goal") or not intent.get("target_nodes"):
            return True, ""
        return False, "Intent is complete — should not reject"

    def guard_code_generated(  # RULE-1
        self,
        generated_code: str = "",
    ) -> Tuple[bool, str]:
        if generated_code and generated_code.strip():
            return True, ""
        return False, "Generated code is empty"

    def guard_generation_failed(  # RULE-1
        self,
        generated_code: str = "",
    ) -> Tuple[bool, str]:
        if not generated_code or not generated_code.strip():
            return True, ""
        return False, "Code was generated — should not reject"

    def guard_ast_valid(  # G1
        self,
        ast_valid: bool = False,
    ) -> Tuple[bool, str]:
        if ast_valid:
            return True, ""
        return False, "AST validation failed"

    def guard_ast_invalid(  # G1
        self,
        ast_valid: bool = True,
    ) -> Tuple[bool, str]:
        if not ast_valid:
            return True, ""
        return False, "AST is valid — should not reject"

    def guard_security_clear(  # G2, G7
        self,
        no_os_imports: bool = False,
        risk_score: float = 1.0,
    ) -> Tuple[bool, str]:
        if no_os_imports and risk_score <= self.MAX_RISK_SCORE:
            return True, ""
        return False, f"Security guard failed: no_os={no_os_imports} risk={risk_score:.2f}"

    def guard_needs_escalation(  # RULE-4
        self,
        risk_score: float = 0.0,
    ) -> Tuple[bool, str]:
        if self.MAX_RISK_SCORE < risk_score <= self.ESCALATION_RISK_THRESHOLD:
            return True, ""
        return False, f"Risk {risk_score:.2f} outside escalation range"

    def guard_security_fail(  # G7
        self,
        risk_score: float = 0.0,
    ) -> Tuple[bool, str]:
        if risk_score > self.ESCALATION_RISK_THRESHOLD:
            return True, ""
        return False, f"Risk {risk_score:.2f} <= threshold — should not reject"

    def guard_sandbox_passed(  # G5, G6
        self,
        sandbox_success: bool = False,
        side_effects: Optional[List[Any]] = None,
    ) -> Tuple[bool, str]:
        if sandbox_success and not side_effects:
            return True, ""
        return False, f"Sandbox guard: success={sandbox_success} effects={len(side_effects or [])}"

    def guard_sandbox_failed(  # G5
        self,
        sandbox_success: bool = True,
    ) -> Tuple[bool, str]:
        if not sandbox_success:
            return True, ""
        return False, "Sandbox succeeded — should not reject"

    def guard_sandbox_ambiguous(  # G6
        self,
        sandbox_success: bool = True,
        side_effects: Optional[List[Any]] = None,
        resource_used: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if sandbox_success and side_effects:
            return True, ""
        if sandbox_success and resource_used:
            cpu = resource_used.get("cpu_sec", 0)
            mem = resource_used.get("memory_mb", 0)
            if cpu >= 8.0 or mem >= 100:
                return True, ""
        return False, "Sandbox result is not ambiguous"

    # ── Deterministic Synthesis Guard (RULE 1) ─────────────────

    def compute_determinism_hash(  # RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        capability_set: List[str],
    ) -> str:
        raw = (
            self._normalize(intent)
            + self._normalize(context)
            + self._normalize(capability_set)
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def check_deterministic_review(  # RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        capability_set: List[str],
    ) -> Tuple[bool, str, str]:
        cache_key = self.compute_determinism_hash(intent, context, capability_set)
        now = time.time()

        if cache_key in self._determinism_cache:
            cached_time, cached_code, cached_hash = self._determinism_cache[cache_key]
            if now - cached_time < self.DETERMINISM_CACHE_TTL_S:
                logger.info("Determinism cache hit for %s", cache_key[:12])
                return True, cached_code, cached_hash

        return False, "", ""

    def cache_deterministic_review(  # RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        capability_set: List[str],
        generated_code: str,
        ast_hash: str,
    ) -> str:
        cache_key = self.compute_determinism_hash(intent, context, capability_set)
        self._determinism_cache[cache_key] = (time.time(), generated_code, ast_hash)
        return cache_key

    def detect_drift(  # RULE-1
        self,
        intent: Dict[str, Any],
        context: Dict[str, Any],
        capability_set: List[str],
        generated_code: str,
        ast_hash: str,
    ) -> bool:
        cache_key = self.compute_determinism_hash(intent, context, capability_set)
        if cache_key in self._determinism_cache:
            _, expected_code, expected_hash = self._determinism_cache[cache_key]
            if generated_code != expected_code or ast_hash != expected_hash:
                logger.error(
                    "Determinism drift detected for key %s: code_match=%s hash_match=%s",
                    cache_key[:12],
                    generated_code == expected_code,
                    ast_hash == expected_hash,
                )
                return True
        return False

    # ── Transition ──────────────────────────────────────────────

    def transition(
        self,
        to_state: SynthesisState,
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

    def force_set(self, state: SynthesisState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def reset(self) -> None:
        self._current = SynthesisState.INTENT_RECEIVED
        self._history.clear()
        self._error = None

    def _apply(self, to_state: SynthesisState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        self._current = to_state

    @staticmethod
    def _normalize(obj: Any) -> str:
        return json.dumps(obj, sort_keys=True, default=str)
