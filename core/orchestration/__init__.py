"""Phase G — Cognitive Orchestration Layer.

Implements the three agent protocols defined in artifacts/design/phase_g/protocols/:
  - IPlannerAgent   → PlannerAgent
  - ICriticAgent    → CriticAgent
  - IOptimizerAgent → OptimizerAgent

References:
  - ROADMAP 🔟 FINAL — Phase G: Cognitive Orchestration
  - Canon LAW 1, 6, 9, 11, 14; RULE 1-3
  - artifacts/design/phase_g/
"""

from core.orchestration.planner_agent import PlannerAgent
from core.orchestration.critic_agent import CriticAgent
from core.orchestration.optimizer_agent import OptimizerAgent
from core.orchestration.orchestration_state_machine import (
    OrchestrationStateMachine,
    OrchestrationState,
    OrchestrationTransition,
    GuardResult,
)
from core.orchestration.trace_correlator import OrchestrationTraceCorrelator

__all__ = [
    "PlannerAgent",
    "CriticAgent",
    "OptimizerAgent",
    "OrchestrationStateMachine",
    "OrchestrationState",
    "OrchestrationTransition",
    "GuardResult",
    "OrchestrationTraceCorrelator",
]
