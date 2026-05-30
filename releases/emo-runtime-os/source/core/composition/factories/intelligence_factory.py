"""IntelligenceFactory — Pure wiring for AI intelligence components.

Constructs CodeGraph bridge, retrieval layer, feedback loops, agents
(as data, not as running actors), and the swarm coordinator.

ZERO business logic. ZERO conditional runtime decisions.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("emo_ai.factory.intelligence")


def build_codegraph_bridge(
    gq: Any = None,
    gre: Any = None,
    drift_detector: Any = None,
    event_bus: Any = None,
) -> dict:
    """Construct CodeGraph bridge + drift detector + runtime integration.

    Returns a dict with keys: codegraph_runtime, drift_detector, event_subscriber.
    """
    from core.codegraph.bridge import CodeGraphEventSubscriber
    from core.codegraph.drift import CodeGraphDriftDetector, DriftDetector, DriftStore
    from core.codegraph.integration import CodeGraphRuntime

    rt = CodeGraphRuntime(gq=gq, gre=gre)
    dd = CodeGraphDriftDetector(
        detector=DriftDetector(),
        store=DriftStore(),
        drift_threshold=0.15,
    )
    subscriber = CodeGraphEventSubscriber(event_bus=event_bus, drift_detector=dd)

    return {
        "codegraph_runtime": rt,
        "drift_detector": dd,
        "event_subscriber": subscriber,
    }


def build_critic_feedback_loop(max_critic_signals: int = 5) -> Any:
    from core.runtime.orchestration.critic_feedback_loop import CriticFeedbackLoop

    return CriticFeedbackLoop(max_critic_signals=max_critic_signals)


def build_dag_synthesizer() -> Any:
    from core.runtime.orchestration.dag_synthesizer import DAGSynthesizer

    return DAGSynthesizer()


def build_swarm_coordinator() -> Any:
    from core.runtime.orchestration.swarm_coordinator import SwarmCoordinator

    return SwarmCoordinator()


def build_trace_correlator() -> Any:
    from core.runtime.orchestration.trace_correlator import TraceCorrelator

    return TraceCorrelator()


def build_planner_agent(
    swarm_coordinator: Any = None,
    critic_feedback_loop: Any = None,
    trace_correlator: Any = None,
    strict_planning_mode: bool = False,
) -> Any:
    from core.runtime.orchestration.planner_agent import PlannerAgent
    from core.runtime.orchestration.planning_state_machine import (
        PlanningStateMachine,
    )

    return PlannerAgent(
        swarm_coordinator=swarm_coordinator,
        critic_feedback_loop=critic_feedback_loop,
        trace_correlator=trace_correlator,
        state_machine=PlanningStateMachine(),
    )


def build_critic_agent(strict_critic_mode: bool = False) -> Any:
    from core.runtime.orchestration.critic_agent import CriticAgent

    return CriticAgent(strict_mode=strict_critic_mode)


def build_optimizer_agent(strict_optimizer_mode: bool = False) -> Any:
    from core.runtime.orchestration.optimizer_agent import OptimizerAgent

    return OptimizerAgent(strict_mode=strict_optimizer_mode)


def build_tool_synthesizer(strict_synthesis_mode: bool = False) -> Any:
    from core.runtime.orchestration.tool_synthesizer import ToolSynthesizer

    return ToolSynthesizer(strict_mode=strict_synthesis_mode)
