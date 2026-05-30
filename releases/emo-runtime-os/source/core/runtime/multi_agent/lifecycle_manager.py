"""Phase G5 — Agent Lifecycle Manager.  # LAW-26 LAW-27 RULE-4 RULE-5

Concrete implementation of IAgentLifecycleManager.

Ref: Canon LAW 26 (Lifecycle Ownership), LAW 27 (One Service per Domain)
Ref: Canon RULE 4 (Isolation), RULE 5 (Recovery)
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.models.multiagent_models import (
    AgentLifecycleState,
    AgentSpec,
    HealthStatus,
    TrustLevel,
)
from core.runtime.multi_agent.lifecycle_state_machine import LifecycleStateMachine

logger = logging.getLogger("emo_ai.multiagent.lifecycle_manager")


class AgentLifecycleManager:  # LAW-26 LAW-27 RULE-4 RULE-5
    """Manages agent lifecycle: spawn, monitor, pause, terminate."""

    def __init__(self, state_machine: Optional[LifecycleStateMachine] = None) -> None:
        self._sm = state_machine or LifecycleStateMachine()
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._domains: Dict[str, str] = {}

    # ── Properties ──────────────────────────────────────────────

    @property
    def state_machine(self) -> LifecycleStateMachine:
        return self._sm

    # ── spawn_agent ─────────────────────────────────────────────

    def spawn_agent(  # LAW-26 LAW-27
        self, spec: Dict[str, Any], mission_trace_id: str = "",
    ) -> Dict[str, Any]:
        domain = spec.get("domain", "")
        if domain in self._domains:
            return {
                "agent_id": "",
                "spawn_status": "failed",
                "assigned_domain": domain,
                "checkpoint_ref": "",
                "mission_trace_id": mission_trace_id,
            }

        ok, _ = self._sm.transition(AgentLifecycleState.SPAWNING, spec=spec)
        if not ok:
            return {
                "agent_id": "",
                "spawn_status": "failed",
                "assigned_domain": domain,
                "checkpoint_ref": "",
                "mission_trace_id": mission_trace_id,
            }

        agent_id = f"agent_{uuid.uuid4().hex[:12]}"
        checkpoint_ref = f"ckpt_{hashlib.sha256(agent_id.encode()).hexdigest()[:16]}"

        ok, _ = self._sm.transition(AgentLifecycleState.RUNNING, resources_allocated=True)
        if not ok:
            self._sm.force_set(AgentLifecycleState.TERMINATED)
            return {
                "agent_id": agent_id,
                "spawn_status": "failed",
                "assigned_domain": domain,
                "checkpoint_ref": "",
                "mission_trace_id": mission_trace_id,
            }

        self._agents[agent_id] = {
            "agent_id": agent_id,
            "spec": spec,
            "state": AgentLifecycleState.RUNNING.value,
            "health": HealthStatus.HEALTHY.value,
            "last_heartbeat_ns": time.time_ns(),
            "checkpoint_ref": checkpoint_ref,
            "assigned_domain": domain,
            "mission_trace_id": mission_trace_id,
            "resource_usage": {"cpu_sec": 0.0, "memory_mb": 0.0, "fd_count": 0},
        }
        self._domains[domain] = agent_id

        return {
            "agent_id": agent_id,
            "spawn_status": "spawning",
            "assigned_domain": domain,
            "checkpoint_ref": checkpoint_ref,
            "mission_trace_id": mission_trace_id,
        }

    # ── monitor_health ──────────────────────────────────────────

    def monitor_health(  # LAW-26
        self, agent_id: str,
    ) -> Dict[str, Any]:
        agent = self._agents.get(agent_id)
        if agent is None:
            return {"agent_id": agent_id, "state": AgentLifecycleState.TERMINATED.value,
                    "health": HealthStatus.UNREACHABLE.value, "last_heartbeat_ns": 0, "resource_usage": {}}

        state = agent["state"]
        health = agent["health"]

        if state == AgentLifecycleState.RUNNING.value:
            now = time.time_ns()
            elapsed = (now - agent.get("last_heartbeat_ns", now)) / 1e9
            if elapsed > 30:
                health = HealthStatus.DEGRADED.value
                agent["health"] = health

        return {
            "agent_id": agent_id,
            "state": state,
            "health": health,
            "last_heartbeat_ns": agent.get("last_heartbeat_ns", 0),
            "resource_usage": dict(agent.get("resource_usage", {})),
        }

    # ── pause_agent ─────────────────────────────────────────────

    def pause_agent(  # LAW-26 RULE-5
        self, agent_id: str,
    ) -> Dict[str, Any]:
        agent = self._agents.get(agent_id)
        if agent is None:
            return {"agent_id": agent_id, "state": AgentLifecycleState.TERMINATED.value,
                    "checkpoint_ref": "", "pause_timestamp_ns": 0}

        ok, _ = self._sm.transition(AgentLifecycleState.PAUSED,
                                     has_checkpoint=True, has_inflight=False)
        if not ok:
            return {"agent_id": agent_id, "state": agent["state"],
                    "checkpoint_ref": agent.get("checkpoint_ref", ""), "pause_timestamp_ns": 0}

        agent["state"] = AgentLifecycleState.PAUSED.value
        paused_at = time.time_ns()

        return {
            "agent_id": agent_id,
            "state": AgentLifecycleState.PAUSED.value,
            "checkpoint_ref": agent.get("checkpoint_ref", ""),
            "pause_timestamp_ns": paused_at,
        }

    # ── terminate_agent ─────────────────────────────────────────

    def terminate_agent(  # LAW-26 RULE-5
        self, agent_id: str, reason: str = "",
    ) -> Dict[str, Any]:
        agent = self._agents.get(agent_id)
        if agent is None:
            return {"agent_id": agent_id, "state": AgentLifecycleState.TERMINATED.value,
                    "final_checkpoint_ref": "", "resources_released": [],
                    "mission_trace_id": ""}

        self._sm.force_set(AgentLifecycleState.TERMINATED)

        domain = agent.get("assigned_domain", "")
        if domain in self._domains:
            del self._domains[domain]

        agent["state"] = AgentLifecycleState.TERMINATED.value
        resources = ["cpu", "memory", "fds"]

        result = {
            "agent_id": agent_id,
            "state": AgentLifecycleState.TERMINATED.value,
            "final_checkpoint_ref": agent.get("checkpoint_ref", ""),
            "resources_released": resources,
            "mission_trace_id": agent.get("mission_trace_id", ""),
        }

        del self._agents[agent_id]
        return result

    # ── Helpers ─────────────────────────────────────────────────

    def is_registered(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def agent_count(self) -> int:
        return len(self._agents)

    def reset(self) -> None:
        self._agents.clear()
        self._domains.clear()
        self._sm.reset()
