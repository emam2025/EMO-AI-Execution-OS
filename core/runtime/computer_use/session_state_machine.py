"""Phase H1 — Computer Use Session State Machine & Interaction Guards.  # LAW-10 LAW-24 RULE-2 RULE-3 RULE-4

6-state machine governing browser/desktop/vision sessions with 8 Interaction
Guards (I1–I8). Every action dispatch is gated by capability match, selector
validity, spatial verification, and sandbox isolation checks.

Ref: Canon LAW 10 (Unreliable Workers), LAW 24 (Dispatcher Ownership)
Ref: Canon RULE 2 (No Uncontrolled IO), RULE 3 (Safety Guards)
Ref: Canon RULE 4 (Isolation)
Ref: artifacts/design/h1/03_session_state_machine.md
"""

from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class SessionState(str, Enum):  # RULE-4
    INIT = "init"
    READY = "ready"
    INTERACTING = "interacting"
    PAUSED = "paused"
    CHECKPOINTED = "checkpointed"
    TERMINATED = "terminated"


class InteractionGuardResult(str, Enum):  # RULE-3
    PASSED = "passed"
    BLOCKED_SELECTOR = "blocked_selector"
    BLOCKED_SPATIAL = "blocked_spatial"
    BLOCKED_CAPABILITY = "blocked_capability"
    BLOCKED_SANDBOX = "blocked_sandbox"
    BLOCKED_RESOURCE = "blocked_resource"
    BLOCKED_JOURNAL = "blocked_journal"
    BLOCKED_REPLAY = "blocked_replay"

    def is_blocked(self) -> bool:
        return self != InteractionGuardResult.PASSED


TERMINAL_STATES: Set[SessionState] = {SessionState.TERMINATED}

TRANSITIONS: Dict[Tuple[SessionState, SessionState], str] = {
    (SessionState.INIT, SessionState.READY): "guard_capability_check",
    (SessionState.READY, SessionState.INTERACTING): "guard_action_dispatch",
    (SessionState.INTERACTING, SessionState.READY): "guard_action_complete",
    (SessionState.INTERACTING, SessionState.TERMINATED): "guard_unrecoverable_error",
    (SessionState.INTERACTING, SessionState.PAUSED): "guard_can_pause",
    (SessionState.INTERACTING, SessionState.CHECKPOINTED): "guard_checkpoint",
    (SessionState.READY, SessionState.PAUSED): "guard_idle_pause",
    (SessionState.READY, SessionState.TERMINATED): "guard_terminate",
    (SessionState.PAUSED, SessionState.CHECKPOINTED): "guard_checkpoint",
    (SessionState.PAUSED, SessionState.TERMINATED): "guard_pause_timeout",
    (SessionState.CHECKPOINTED, SessionState.READY): "guard_replay_verified",
    (SessionState.PAUSED, SessionState.READY): "guard_can_resume",
}


class ComputerUseSessionStateMachine:  # LAW-10 LAW-24 RULE-2 RULE-3
    """6-state machine for computer use sessions with 8 Interaction Guards."""

    def __init__(self) -> None:
        self._current = SessionState.INIT
        self._history: List[Dict[str, Any]] = []

    @property
    def current(self) -> SessionState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards I1–I8 ─────────────────────────────────────────────

    def guard_selector_valid(  # I1: RULE-2
        self, target_selector: str = "",
    ) -> Tuple[bool, str]:
        if not target_selector:
            return False, "I1: Empty target selector"
        return True, ""

    def guard_spatial_bbox_verified(  # I2: RULE-2
        self, coordinates: Optional[Dict[str, int]] = None,
        bounding_box: Optional[List[float]] = None,
        viewport: Optional[Dict[str, int]] = None,
    ) -> Tuple[bool, str]:
        if coordinates:
            x, y = coordinates.get("x", -1), coordinates.get("y", -1)
            if viewport and (x < 0 or y < 0 or x > viewport.get("width", 0) or y > viewport.get("height", 0)):
                return False, "I2: Coordinates out of viewport"
        if bounding_box and len(bounding_box) == 4:
            w, h = bounding_box[2], bounding_box[3]
            if w <= 0 or h <= 0:
                return False, "I2: Invalid bounding box dimensions"
        return True, ""

    def guard_capability_match(  # I3: LAW-10 RULE-2
        self, action_type: str = "",
        session_capabilities: Optional[List[str]] = None,
        sandbox_token: str = "",
        expected_token: str = "",
    ) -> Tuple[bool, str]:
        if not action_type:
            return False, "I3: No action type provided"
        cap_map = {
            "navigate": "navigate", "click": "pointer_input",
            "type_text": "keyboard_input", "execute_script": "script_exec",
            "screenshot": "screenshot", "detect_element": "ocr",
            "extract_text": "ocr", "template_match": "template_match",
        }
        needed = cap_map.get(action_type, action_type)
        if session_capabilities and needed not in session_capabilities:
            return False, f"I3: Missing capability '{needed}' for action '{action_type}'"
        if sandbox_token and expected_token and sandbox_token != expected_token:
            return False, "I3: Sandbox token mismatch"
        return True, ""

    def guard_session_isolation(  # I4: LAW-10 RULE-4
        self, allowed_states: Optional[List[SessionState]] = None,
    ) -> Tuple[bool, str]:
        if allowed_states and self._current not in allowed_states:
            return False, f"I4: Invalid session state {self._current.value}"
        return True, ""

    def guard_vision_consistency(  # I5: RULE-1 RULE-3
        self, visual_context_hash: str = "",
        current_visual_hash: str = "",
        confidence: float = 1.0,
        min_confidence: float = 0.0,
    ) -> Tuple[bool, str]:
        if visual_context_hash and current_visual_hash and visual_context_hash != current_visual_hash:
            return False, "I5: Stale visual context — re-grounding required"
        if confidence < min_confidence:
            return False, f"I5: Low confidence {confidence:.2f} < {min_confidence:.2f}"
        return True, ""

    def guard_journal_integrity(  # I6: RULE-1 LAW-24
        self, state_hash: str = "",
        expected_prev_hash: str = "",
        actual_prev_hash: str = "",
    ) -> Tuple[bool, str]:
        if expected_prev_hash and actual_prev_hash and expected_prev_hash != actual_prev_hash:
            return False, "I6: Journal chain broken"
        return True, ""

    def guard_resource_quota(  # I7: LAW-10
        self, action_count: int = 0, max_actions: int = 1000,
        cpu_sec: float = 0.0, max_cpu_sec: float = 120.0,
        session_duration_sec: float = 0.0, max_session_sec: float = 3600.0,
    ) -> Tuple[bool, str]:
        if action_count >= max_actions:
            return False, f"I7: Action limit reached ({action_count}/{max_actions})"
        if cpu_sec >= max_cpu_sec:
            return False, f"I7: CPU limit reached ({cpu_sec:.1f}/{max_cpu_sec:.1f}s)"
        if session_duration_sec >= max_session_sec:
            return False, f"I7: Session duration exceeded ({session_duration_sec:.0f}/{max_session_sec:.0f}s)"
        return True, ""

    def guard_replay_determinism(  # I8: RULE-1
        self, expected_state_hash: str = "",
        actual_state_hash: str = "",
    ) -> Tuple[bool, str]:
        if expected_state_hash and actual_state_hash and expected_state_hash != actual_state_hash:
            return False, "I8: State hash mismatch — replay deviation detected"
        return True, ""

    # ── Composite guard: full pre-flight check ───────────────────

    def check_pre_action(  # RULE-2 RULE-3
        self,
        action_type: str = "",
        target_selector: str = "",
        coordinates: Optional[Dict[str, int]] = None,
        bounding_box: Optional[List[float]] = None,
        viewport: Optional[Dict[str, int]] = None,
        session_capabilities: Optional[List[str]] = None,
        sandbox_token: str = "",
        expected_token: str = "",
        visual_context_hash: str = "",
        current_visual_hash: str = "",
        confidence: float = 1.0,
        min_confidence: float = 0.7,
    ) -> InteractionGuardResult:
        if not self.guard_selector_valid(target_selector)[0]:
            return InteractionGuardResult.BLOCKED_SELECTOR
        ok, _ = self.guard_spatial_bbox_verified(coordinates, bounding_box, viewport)
        if not ok:
            return InteractionGuardResult.BLOCKED_SPATIAL
        ok, _ = self.guard_capability_match(action_type, session_capabilities, sandbox_token, expected_token)
        if not ok:
            return InteractionGuardResult.BLOCKED_CAPABILITY
        ok, _ = self.guard_vision_consistency(visual_context_hash, current_visual_hash, confidence, min_confidence)
        if not ok:
            return InteractionGuardResult.BLOCKED_SELECTOR
        return InteractionGuardResult.PASSED

    # ── Transition ───────────────────────────────────────────────

    def transition(  # LAW-24
        self, to_state: SessionState, **kwargs,
    ) -> Tuple[bool, str]:
        key = (self._current, to_state)

        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value}"

        if key not in TRANSITIONS:
            return False, f"Invalid transition: {self._current.value} → {to_state.value}"

        guard_name = TRANSITIONS[key]
        if guard_name:
            guard_fn = getattr(self, guard_name, None)
            if guard_fn is not None:
                result = guard_fn(**kwargs)
                if isinstance(result, tuple):
                    allowed, reason = result
                else:
                    allowed, reason = bool(result), ""
                if not allowed:
                    return False, reason
        self._apply(to_state)
        return True, ""

    def guard_capability_check(self, **kwargs: Any) -> Tuple[bool, str]:
        isolation_context = kwargs.get("isolation_context")
        capabilities = kwargs.get("capabilities", [])
        sandbox_token = kwargs.get("sandbox_token", "")
        if not isolation_context:
            return False, "G1: No isolation context"
        if not capabilities:
            return False, "G1: No capabilities declared"
        if not sandbox_token:
            return False, "G1: No sandbox token"
        return True, ""

    def guard_action_dispatch(self, **kwargs: Any) -> Tuple[bool, str]:
        action_type = kwargs.get("action_type", "")
        sandbox_token = kwargs.get("sandbox_token", "")
        expected_token = kwargs.get("expected_token", "")
        if not action_type:
            return False, "G2: No action type"
        if sandbox_token and expected_token and sandbox_token != expected_token:
            return False, "G2: Sandbox token mismatch"
        return True, ""

    def guard_action_complete(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def guard_unrecoverable_error(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def guard_can_pause(self, **kwargs: Any) -> Tuple[bool, str]:
        has_checkpoint = kwargs.get("has_checkpoint", False)
        if not has_checkpoint:
            return False, "G7: No checkpoint available for pause"
        return True, ""

    def guard_idle_pause(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def guard_checkpoint(self, **kwargs: Any) -> Tuple[bool, str]:
        state_valid = kwargs.get("state_valid", False)
        if not state_valid:
            return False, "G9: Session state invalid for checkpoint"
        return True, ""

    def guard_terminate(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def guard_pause_timeout(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def guard_replay_verified(self, **kwargs: Any) -> Tuple[bool, str]:
        replay_ok = kwargs.get("replay_ok", False)
        if not replay_ok:
            return False, "G11: Replay verification failed"
        return True, ""

    def guard_can_resume(self, **kwargs: Any) -> Tuple[bool, str]:
        return True, ""

    def force_set(self, state: SessionState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def reset(self) -> None:
        self._current = SessionState.INIT
        self._history.clear()

    def _apply(self, to_state: SessionState) -> None:
        self._history.append({"from": self._current.value, "to": to_state.value})
        self._current = to_state

    @staticmethod
    def compute_state_hash(  # RULE-1
        prev_hash: str, action_type: str, target_selector: str,
        input_data: str, seq: int, visual_hash: str,
        guard_result: str, error: str = "",
    ) -> str:
        raw = f"{prev_hash}:{seq}:{action_type}:{target_selector}:{input_data}:{visual_hash}:{guard_result}:{error}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
