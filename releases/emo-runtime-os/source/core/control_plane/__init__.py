"""Phase 6 — Control Plane: cognitive decision layer.

4 core subsystems:
  6.1 — SystemStateBrain (global truth model)
  6.2 — Reconciler (self-healing loop)
  6.3 — ExecutionOrchestrator (decision engine)
  6.4 — HealthManager (health + topology monitoring)

Orchestrated by ControlPlaneBrain.
"""

from core.control_plane.brain import ControlPlaneBrain
from core.control_plane.health import HealthManager, HealthReport, TopologyEvent
from core.control_plane.orchestrator import ExecutionOrchestrator, NodeScore
from core.control_plane.reconciler import Reconciler, DesiredState, Correction
from core.control_plane.state.system_state import (
    SystemStateBrain,
    WorkerInfo,
    ExecutionInfo,
    NodeInfo,
    FailureCluster,
    LoadMetrics,
)

__all__ = [
    "ControlPlaneBrain",
    "SystemStateBrain",
    "WorkerInfo",
    "ExecutionInfo",
    "NodeInfo",
    "FailureCluster",
    "LoadMetrics",
    "Reconciler",
    "DesiredState",
    "Correction",
    "ExecutionOrchestrator",
    "NodeScore",
    "HealthManager",
    "HealthReport",
    "TopologyEvent",
]
