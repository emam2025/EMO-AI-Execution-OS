"""Phase J3 — Production Readiness Layer.  # LAW-3 LAW-5 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Chaos Engineering, Load Testing, Stability Validation, and Readiness Certification.
All operations carry readiness_trace_id for end-to-end traceability (LAW 8).
Every state transition is gated by Recovery Guards (G-C1–G-C3, G-D1).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.13 (Chaos Engineering), §16 (Production Readiness)
Ref: artifacts/design/j3/protocols/01_readiness_protocols.py
Ref: artifacts/design/j3/models/02_chaos_and_load_models.py
"""

from core.readiness.readiness_state_machine import (
    ReadinessStateMachine,
    ChaosState,
    ChaosTransition,
    LoadState,
    LoadTransition,
    CertificationGateState,
    CertificationGateTransition,
    GuardResult,
    evaluate_g_c1_pre_fault_health,
    evaluate_g_c2_degradation_budget,
    evaluate_g_c3_recovery_verification,
    evaluate_g_d1_deterministic_load,
)
from core.readiness.trace_correlator import ReadinessTraceCorrelator
from core.readiness.chaos_injector import ChaosInjector
from core.readiness.load_orchestrator import LoadOrchestrator
from core.readiness.stability_validator import StabilityValidator
from core.readiness.certification_gate import CertificationGate

__all__ = [
    "ReadinessStateMachine",
    "ChaosState",
    "ChaosTransition",
    "LoadState",
    "LoadTransition",
    "CertificationGateState",
    "CertificationGateTransition",
    "GuardResult",
    "evaluate_g_c1_pre_fault_health",
    "evaluate_g_c2_degradation_budget",
    "evaluate_g_c3_recovery_verification",
    "evaluate_g_d1_deterministic_load",
    "ReadinessTraceCorrelator",
    "ChaosInjector",
    "LoadOrchestrator",
    "StabilityValidator",
    "CertificationGate",
]
