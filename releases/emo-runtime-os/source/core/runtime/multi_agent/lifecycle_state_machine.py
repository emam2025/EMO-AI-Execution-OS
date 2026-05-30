"""Phase G5 — Agent Lifecycle State Machine.  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-4 RULE-5

6-state machine governing agent lifecycle with 7 Isolation Guards (I1–I7)
and 6 Planning Guards (H1–H6).

Ref: Canon LAW 11, 23-27, RULE 1-5
Ref: artifacts/design/g5/03_agent_lifecycle_machine.md
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Set

from core.runtime.models.multiagent_models import AgentLifecycleState

logger = logging.getLogger("emo_ai.multiagent.lifecycle_sm")

TERMINAL_STATES: Set[AgentLifecycleState] = {
    AgentLifecycleState.TERMINATED,
}

TRANSITIONS: Dict[Tuple[AgentLifecycleState, AgentLifecycleState], Optional[str]] = {
    (AgentLifecycleState.IDLE, AgentLifecycleState.SPAWNING): "guard_spec_valid",
    (AgentLifecycleState.IDLE, AgentLifecycleState.TERMINATED): "guard_spec_invalid",
    (AgentLifecycleState.SPAWNING, AgentLifecycleState.RUNNING): "guard_spawn_success",
    (AgentLifecycleState.SPAWNING, AgentLifecycleState.TERMINATED): "guard_spawn_failed",
    (AgentLifecycleState.RUNNING, AgentLifecycleState.PAUSED): "guard_can_pause",
    (AgentLifecycleState.RUNNING, AgentLifecycleState.DEGRADED): "guard_health_degraded",
    (AgentLifecycleState.RUNNING, AgentLifecycleState.TERMINATED): "guard_termination",
    (AgentLifecycleState.PAUSED, AgentLifecycleState.RUNNING): "guard_can_resume",
    (AgentLifecycleState.PAUSED, AgentLifecycleState.TERMINATED): "guard_pause_timeout",
    (AgentLifecycleState.DEGRADED, AgentLifecycleState.RUNNING): "guard_recovered",
    (AgentLifecycleState.DEGRADED, AgentLifecycleState.TERMINATED): "guard_unrecoverable",
}


class LifecycleStateMachine:  # LAW-26 LAW-27 RULE-4 RULE-5
    """6-state machine for the G5 agent lifecycle.

    Isolation Guards (I1–I7) enforce LAW 23-27 and RULE 4.
    """

    def __init__(self) -> None:
        self._current = AgentLifecycleState.IDLE
        self._history: List[Dict[str, Any]] = []

    @property
    def current(self) -> AgentLifecycleState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards ──────────────────────────────────────────────────

    def guard_spec_valid(  # LAW-27
        self, spec: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if spec is None:
            return False, "No spec provided"
        if not spec.get("domain"):
            return False, "I1: Agent missing domain (LAW 27)"
        if not spec.get("capability_profile"):
            return False, "Agent missing capability_profile"
        if not spec.get("resource_quota"):
            return False, "Agent missing resource_quota"
        return True, ""

    def guard_spec_invalid(  # LAW-27
        self, spec: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if spec is None:
            return True, ""
        if not spec.get("domain") or not spec.get("capability_profile"):
            return True, ""
        return False, "Spec is valid — should not reject"

    def guard_spawn_success(  # RULE-5
        self, resources_allocated: bool = False,
    ) -> Tuple[bool, str]:
        if resources_allocated:
            return True, ""
        return False, "I5: Resource allocation failed"

    def guard_spawn_failed(
        self, resources_allocated: bool = True,
    ) -> Tuple[bool, str]:
        if not resources_allocated:
            return True, ""
        return False, "Resources allocated — should not reject"

    def guard_can_pause(  # I6
        self, has_checkpoint: bool = False, has_inflight: bool = False,
    ) -> Tuple[bool, str]:
        if not has_checkpoint:
            return False, "I6: No checkpoint available for pause"
        if has_inflight:
            return False, "Cannot pause with in-flight tasks"
        return True, ""

    def guard_health_degraded(
        self, resource_ratio: float = 0.0,
    ) -> Tuple[bool, str]:
        if resource_ratio >= 0.9:
            return True, ""
        return False, f"Resource ratio {resource_ratio:.2f} < 0.9"

    def guard_termination(  # I7
        self, has_checkpoint: bool = False,
        lifecycle_expired: bool = False,
    ) -> Tuple[bool, str]:
        if not has_checkpoint:
            return False, "I7: No final checkpoint for termination"
        if not lifecycle_expired:
            return False, "Lifecycle not expired"
        return True, ""

    def guard_can_resume(  # RULE-5
        self, checkpoint_valid: bool = False, resources_available: bool = False,
    ) -> Tuple[bool, str]:
        if checkpoint_valid and resources_available:
            return True, ""
        return False, "Cannot resume: checkpoint or resources unavailable"

    def guard_pause_timeout(
        self, pause_duration_sec: float = 0.0, max_pause_sec: float = 3600.0,
    ) -> Tuple[bool, str]:
        if pause_duration_sec >= max_pause_sec:
            return True, ""
        return False, f"Pause duration {pause_duration_sec:.0f}s < {max_pause_sec:.0f}s"

    def guard_recovered(
        self, health_restored: bool = False,
    ) -> Tuple[bool, str]:
        if health_restored:
            return True, ""
        return False, "Health not restored"

    def guard_unrecoverable(
        self, health_restored: bool = True,
    ) -> Tuple[bool, str]:
        if not health_restored:
            return True, ""
        return False, "Health restored — should not terminate"

    # ── Transition ──────────────────────────────────────────────

    def transition(
        self, to_state: AgentLifecycleState, **kwargs,
    ) -> Tuple[bool, str]:
        key = (self._current, to_state)

        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value}"

        if key not in TRANSITIONS:
            return False, f"Invalid: {self._current.value} → {to_state.value}"

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

    def force_set(self, state: AgentLifecycleState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def reset(self) -> None:
        self._current = AgentLifecycleState.IDLE
        self._history.clear()

    def _apply(self, to_state: AgentLifecycleState) -> None:
        self._history.append({"from": self._current.value, "to": to_state.value})
        self._current = to_state
