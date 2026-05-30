"""Phase F2 — Control Plane & Autoscaler.  # LAW-5 # LAW-8 # LAW-11

Exports:
  - ControlPlane:       Top-level orchestrator (←→ IControlPlane)
  - Autoscaler:         Scaling decision engine (←→ IAutoscaler)
  - HealthSupervisor:   Worker health & eviction (←→ IHealthSupervisor)
  - ReconciliationLoop: Observe→Compare→Act cycle (←→ IReconciliationLoop)
  - WorkerDrainer:      5-phase drain lifecycle (§15.9.3)
  - CooldownTimer, HysteresisEvaluator, ConsecutiveCycleTracker

Ref: Canon LAW 5, LAW 8, LAW 11, RULE 1-5  # RULE-1 # RULE-2 # RULE-3 # RULE-4 # RULE-5
Ref: DEVELOPER.md §15.9
"""

from core.runtime.control_plane.autoscaler import Autoscaler
from core.runtime.control_plane.control_plane import ControlPlane
from core.runtime.control_plane.health_supervisor import HealthSupervisor
from core.runtime.control_plane.oscillation_guard import (
    ConsecutiveCycleTracker,
    CooldownTimer,
    HysteresisEvaluator,
)
from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
from core.runtime.control_plane.worker_drainer import WorkerDrainer

__all__ = [
    "ControlPlane",
    "Autoscaler",
    "HealthSupervisor",
    "ReconciliationLoop",
    "WorkerDrainer",
    "CooldownTimer",
    "HysteresisEvaluator",
    "ConsecutiveCycleTracker",
]
