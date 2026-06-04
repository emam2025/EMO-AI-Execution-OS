"""Phase G — AgentLifecycleManager: registry, state machine, heartbeat.

Manages the full lifecycle of cognitive agents:
  - register:       Register agent with capabilities, create initial lease
  - transition_state: Deterministic state machine (IDLE→PLANNING→EXECUTING→...)
  - heartbeat:      Track liveness, emit Agent.Stale / Agent.Offline
  - deregister:     Cleanup lease, release resources, log to Observability

LAW 5: Every state transition emits an AgentEvent.
LAW 8: All transitions are guarded — no invalid state jumps.
LAW 10: Agents are unreliable — heartbeat timeout → stale → offline.
LAW 11: No global mutable state — per-instance agent registry.

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.agents.lifecycle")


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    STALE = "stale"
    OFFLINE = "offline"
    DEREGISTERED = "deregistered"


TERMINAL_STATES = {AgentState.COMPLETED, AgentState.FAILED, AgentState.DEREGISTERED}

VALID_TRANSITIONS: Dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.PLANNING, AgentState.DEREGISTERED},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.REVIEWING, AgentState.FAILED, AgentState.DEREGISTERED},
    AgentState.EXECUTING: {AgentState.REVIEWING, AgentState.FAILED, AgentState.STALE, AgentState.DEREGISTERED},
    AgentState.REVIEWING: {AgentState.COMPLETED, AgentState.PLANNING, AgentState.FAILED, AgentState.DEREGISTERED},
    AgentState.COMPLETED: {AgentState.PLANNING, AgentState.DEREGISTERED},
    AgentState.FAILED: {AgentState.PLANNING, AgentState.DEREGISTERED},
    AgentState.STALE: {AgentState.OFFLINE, AgentState.PLANNING, AgentState.DEREGISTERED},
    AgentState.OFFLINE: {AgentState.DEREGISTERED},
    AgentState.DEREGISTERED: set(),
}


@dataclass
class AgentSpec:
    agent_id: str = ""
    name: str = ""
    version: str = "1.0.0"
    capabilities: Dict[str, Any] = field(default_factory=dict)
    max_executions: int = 100
    timeout_sec: float = 300.0


@dataclass
class AgentInstance:
    agent_id: str
    spec: AgentSpec
    state: AgentState = AgentState.IDLE
    lease_id: str = ""
    created_at: float = 0.0
    last_heartbeat: float = 0.0
    execution_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentEvent:
    agent_id: str
    event_type: str
    previous_state: str = ""
    new_state: str = ""
    timestamp_ns: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)


class AgentLifecycleManager:
    """Agent lifecycle — register, transition, heartbeat, deregister.

    LAW 5: Every state transition emits AgentEvent.
    LAW 8: Guarded state transitions — no invalid jumps.
    LAW 10: Heartbeat timeout → stale → offline → deregister.
    LAW 11: No global state — per-instance tracking.
    """

    HEARTBEAT_TIMEOUT: float = 60.0
    STALE_TIMEOUT: float = 120.0

    def __init__(
        self,
        event_bus: Any = None,
        lease_manager: Any = None,
    ):
        self._event_bus = event_bus
        self._lease_manager = lease_manager
        self._agents: Dict[str, AgentInstance] = {}
        self._event_history: List[AgentEvent] = []

    @property
    def active_agents(self) -> List[AgentInstance]:
        return [
            a for a in self._agents.values()
            if a.state not in TERMINAL_STATES
        ]

    @property
    def agent_count(self) -> int:
        return len(self.active_agents)

    def get_agent(self, agent_id: str) -> Optional[AgentInstance]:
        return self._agents.get(agent_id)

    # ── register ────────────────────────────────────────────

    def register(self, spec: AgentSpec) -> str:
        """Register a new agent.

        LAW 10: Creates an initial lease for the agent.
        LAW 5: Emits AgentRegistered event.

        Returns agent_id.
        """
        agent_id = spec.agent_id or f"agent-{uuid.uuid4().hex[:8]}"

        lease_id = ""
        if self._lease_manager is not None:
            lease = self._lease_manager.acquire_lease(
                agent_id, "AgentLifecycleManager", ttl=30.0,
            )
            if lease:
                lease_id = lease

        now = time.time()
        instance = AgentInstance(
            agent_id=agent_id,
            spec=spec,
            state=AgentState.IDLE,
            lease_id=lease_id,
            created_at=now,
            last_heartbeat=now,
        )
        self._agents[agent_id] = instance

        self._emit_event(agent_id, "registered", payload={
            "name": spec.name,
            "capabilities": spec.capabilities,
            "lease_id": lease_id,
        })

        logger.info("Agent registered: %s (lease=%s)", agent_id, lease_id)
        return agent_id

    # ── transition_state ────────────────────────────────────

    def transition_state(self, agent_id: str, new_state: AgentState) -> bool:
        """Transition an agent to a new state.

        LAW 8: Guarded — only valid transitions allowed.
        LAW 5: Emits AgentStateChanged event.

        Returns True if transition succeeded.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            logger.warning("Agent %s not found for transition", agent_id)
            return False

        if agent.state in TERMINAL_STATES:
            logger.warning("Agent %s in terminal state %s", agent_id, agent.state.value)
            return False

        allowed = VALID_TRANSITIONS.get(agent.state, set())
        if new_state not in allowed:
            logger.warning(
                "Invalid transition %s → %s for agent %s",
                agent.state.value, new_state.value, agent_id,
            )
            return False

        previous = agent.state
        agent.state = new_state
        agent.last_heartbeat = time.time()

        self._emit_event(agent_id, "state_changed", payload={
            "previous_state": previous.value,
            "new_state": new_state.value,
        })

        logger.info("Agent %s: %s → %s", agent_id, previous.value, new_state.value)
        return True

    # ── heartbeat ───────────────────────────────────────────

    def heartbeat(self, agent_id: str) -> bool:
        """Record an agent heartbeat.

        LAW 10: Tracks liveness; stale detection on check_stale().

        Returns True if agent exists.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            return False

        if agent.state in TERMINAL_STATES:
            return False

        was_stale = agent.state == AgentState.STALE
        agent.last_heartbeat = time.time()

        if was_stale:
            self.transition_state(agent_id, AgentState.IDLE)

        logger.debug("Heartbeat: %s", agent_id)
        return True

    def check_stale_agents(self) -> List[str]:
        """Find agents with expired heartbeats.

        Stale → transitions to STALE or OFFLINE.
        Returns list of stale agent IDs.
        """
        now = time.time()
        stale_ids: List[str] = []

        for agent_id, agent in list(self._agents.items()):
            if agent.state in TERMINAL_STATES:
                continue

            elapsed = now - agent.last_heartbeat

            if elapsed > self.STALE_TIMEOUT and agent.state != AgentState.OFFLINE:
                self.transition_state(agent_id, AgentState.OFFLINE)
                stale_ids.append(agent_id)
                logger.warning("Agent %s is OFFLINE (no heartbeat for %.0fs)", agent_id, elapsed)

            elif elapsed > self.HEARTBEAT_TIMEOUT and agent.state not in (AgentState.STALE, AgentState.OFFLINE):
                self.transition_state(agent_id, AgentState.STALE)
                stale_ids.append(agent_id)
                logger.warning("Agent %s is STALE (no heartbeat for %.0fs)", agent_id, elapsed)

        return stale_ids

    # ── deregister ──────────────────────────────────────────

    def deregister(self, agent_id: str, reason: str = "") -> bool:
        """Deregister an agent.

        LAW 10: Releases lease, frees resources.
        LAW 5: Emits AgentDeregistered event.
        LAW 11: Removes from local registry.

        Returns True if deregistered.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            return False

        if agent.lease_id and self._lease_manager is not None:
            try:
                self._lease_manager.release_lease(agent.lease_id)
            except Exception as e:
                logger.error("Lease release failed for %s: %s", agent_id, e)

        agent.state = AgentState.DEREGISTERED

        self._emit_event(agent_id, "deregistered", payload={
            "reason": reason,
            "lease_id": agent.lease_id,
        })

        self._agents.pop(agent_id, None)

        logger.info("Agent deregistered: %s (reason=%s)", agent_id, reason)
        return True

    # ── Event emission ──────────────────────────────────────

    def _emit_event(
        self,
        agent_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        now_ns = time.time_ns()
        event = AgentEvent(
            agent_id=agent_id,
            event_type=event_type,
            timestamp_ns=now_ns,
            payload=payload,
        )
        self._event_history.append(event)

        if self._event_bus is not None:
            try:
                from core.models.events import ExecutionEvent
                bus_event = ExecutionEvent(
                    event_id=uuid.uuid4().hex[:16],
                    event_type=event_type.upper(),
                    timestamp=time.time(),
                    source=f"AgentLifecycleManager.{agent_id}",
                    payload={
                        "agent_id": agent_id,
                        **payload,
                    },
                )
                self._event_bus.publish(f"agent.{event_type}", bus_event)
            except Exception as e:
                logger.error("Failed to emit agent event: %s", e)
