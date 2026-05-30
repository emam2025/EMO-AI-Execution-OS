"""Phase G1 — Orchestration package.  # LAW-1 # LAW-3 # LAW-8 # LAW-23

Exports all G1 protocol implementations for CompositionRoot wiring.

Ref: Canon LAW 1-8, LAW 23-27, RULE 1-5
Ref: ROADMAP Phase G1
"""

from core.runtime.orchestration.planner_agent import PlannerAgent
from core.runtime.orchestration.dag_synthesizer import DAGSynthesizer
from core.runtime.orchestration.critic_feedback_loop import CriticFeedbackLoop
from core.runtime.orchestration.swarm_coordinator import SwarmCoordinator
from core.runtime.orchestration.planning_state_machine import (
    PlanningState,
    PlanningStateMachine,
)
from core.runtime.orchestration.trace_correlator import TraceCorrelator

__all__ = [
    "PlannerAgent",
    "DAGSynthesizer",
    "CriticFeedbackLoop",
    "SwarmCoordinator",
    "PlanningState",
    "PlanningStateMachine",
    "TraceCorrelator",
]
