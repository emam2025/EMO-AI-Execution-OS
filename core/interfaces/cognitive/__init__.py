"""Phase G — Cognitive Orchestration Protocol interfaces.

Defines 4 typing.Protocol interfaces for the orchestration layer:
  - ICognitiveOrchestrator: Top-level routing facade
  - IPlanner:               DAG synthesis and validation
  - ICritic:                Plan evaluation and risk assessment
  - ISwarmCoordinator:      Multi-agent task negotiation

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 13
Ref: ROADMAP Phase G
"""

from core.interfaces.cognitive.orchestrator import ICognitiveOrchestrator
from core.interfaces.cognitive.planner import IPlanner
from core.interfaces.cognitive.critic import ICritic
from core.interfaces.cognitive.swarm import ISwarmCoordinator

__all__ = [
    "ICognitiveOrchestrator",
    "IPlanner",
    "ICritic",
    "ISwarmCoordinator",
]
