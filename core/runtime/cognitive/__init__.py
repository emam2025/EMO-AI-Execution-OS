"""Phase G — Cognitive Orchestration package.

Exports:
  - CognitiveOrchestrator:  Plan → Critique → Optimize → Submit facade
  - SwarmRouter:            Capability/load-based routing + health monitoring

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 13
"""

from core.runtime.cognitive.orchestrator_facade import CognitiveOrchestrator
from core.runtime.cognitive.swarm_router import SwarmRouter

__all__ = [
    "CognitiveOrchestrator",
    "SwarmRouter",
]
