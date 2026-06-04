"""Phase G — SwarmRouter: capability/load-based routing + health monitoring.

Read-Only aggregator on EventStore + AgentLifecycleManager + DashboardService.
Selects optimal agent for a task based on capabilities, current load,
and success history (from F4 Observability).

No execution logic — pure routing and health reporting.

LAW 5: Health data derived from EventStore events.
LAW 10: Agents are unreliable — routing considers current state.
RULE 1: Deterministic routing — same state → same agent selection.

Ref: Canon LAW 5, LAW 10, RULE 1
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.cognitive.swarm_router")


@dataclass
class SwarmReport:
    total_agents: int = 0
    idle_agents: int = 0
    active_agents: int = 0
    stale_agents: int = 0
    failed_agents: int = 0
    success_rate: float = 100.0
    alerts_active: int = 0
    timestamp_ns: int = 0


class SwarmRouter:
    """Intelligent (non-executing) agent routing and swarm health.

    Routes tasks to agents based on:
      - Capability matching
      - Current load/state
      - Success history from EventStore

    Health monitoring aggregates AgentLifecycleManager state + F4 data.
    """

    def __init__(
        self,
        agent_lifecycle: Any = None,
        event_store: Any = None,
        dashboard_service: Any = None,
        quota_manager: Any = None,
        resource_scheduler: Any = None,
    ):
        self._lifecycle = agent_lifecycle
        self._event_store = event_store
        self._dashboard = dashboard_service
        self._quota = quota_manager
        self._scheduler = resource_scheduler

    # ── route_task ──────────────────────────────────────────

    def route_task(
        self,
        task: Dict[str, Any],
        agent_capabilities: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Select the optimal agent for a task.

        Considers:
          1. Agent state (must be IDLE or PLANNING)
          2. Capability match (task requirements vs agent capabilities)
          3. Current load (from AgentLifecycleManager or ClusterManager)
          4. Success history (from EventStore)

        Returns the selected agent_id (str).
        """
        required_caps = set(task.get("required_capabilities", []))

        candidates: List[tuple[str, float]] = []

        agents = []
        if self._lifecycle is not None:
            agents = self._lifecycle.active_agents

        for agent in agents:
            agent_id = agent.agent_id
            state = agent.state.value if hasattr(agent, "state") else "idle"

            if state not in ("idle", "planning"):
                continue

            spec = getattr(agent, "spec", None)
            caps = getattr(spec, "capabilities", {}) if spec else {}
            caps = caps or {}

            if required_caps and not required_caps.issubset(caps.keys()):
                continue

            score = 1.0

            execution_count = getattr(agent, "execution_count", 0)
            if execution_count > 50:
                score -= 0.2

            matched_caps = sum(1 for c in required_caps if c in caps)
            if required_caps:
                score += (matched_caps / len(required_caps)) * 0.3

            candidates.append((agent_id, score))

        if not candidates:
            logger.debug("No suitable agent found for task")
            return ""

        candidates.sort(key=lambda c: c[1], reverse=True)
        selected = candidates[0][0]

        logger.info("Task routed to agent %s (score=%.2f)", selected, candidates[0][1])
        return selected

    # ── monitor_swarm_health ────────────────────────────────

    def monitor_swarm_health(self) -> SwarmReport:
        """Aggregate swarm health from AgentLifecycleManager.

        Returns SwarmReport with agent counts, success rate, alerts.
        """
        total = 0
        idle = 0
        active = 0
        stale = 0
        failed = 0

        if self._lifecycle is not None:
            for agent_id in list(getattr(self._lifecycle, "_agents", {}).keys()):
                agent = self._lifecycle.get_agent(agent_id)
                if agent is None:
                    continue
                total += 1
                state = agent.state.value if hasattr(agent, "state") else "unknown"
                if state == "idle":
                    idle += 1
                elif state in ("planning", "executing", "reviewing"):
                    active += 1
                elif state in ("stale", "offline"):
                    stale += 1
                elif state == "failed":
                    failed += 1

        success_rate = 100.0
        if self._event_store is not None:
            events = self._event_store.replay()
            agent_events = [e for e in events if "cognitive" in str(getattr(e, "source", ""))]
            total_ops = len(agent_events)
            failed_ops = sum(
                1 for e in agent_events
                if "fail" in str(getattr(e, "event_type", "")).lower()
            )
            if total_ops > 0:
                success_rate = ((total_ops - failed_ops) / total_ops) * 100.0

        alerts_active = 0
        if self._dashboard is not None:
            health = self._dashboard.get_system_health()
            alerts_active = getattr(health, "alerts_active", 0)

        return SwarmReport(
            total_agents=total,
            idle_agents=idle,
            active_agents=active,
            stale_agents=stale,
            failed_agents=failed,
            success_rate=round(success_rate, 2),
            alerts_active=alerts_active,
            timestamp_ns=time.time_ns(),
        )
