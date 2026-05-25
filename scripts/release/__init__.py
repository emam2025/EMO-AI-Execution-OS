"""Phase FINAL — Release Certification Package.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Release certification, baseline freeze, validation, and certificate generation
for v4.7.0-prod-ready. All operations carry release_trace_id (LAW 12).

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from scripts.release.release_state_machine import (
    ReleaseStateMachine,
    ReleaseState,
    ReleaseTransition,
    FreezeGuardResult,
    evaluate_freeze_guard_canon_compliance,
    evaluate_freeze_guard_zero_regressions,
    evaluate_freeze_guard_critical_guards,
    evaluate_freeze_guard_architecture_drift,
    evaluate_freeze_guard_baseline_locked,
)
from scripts.release.certification_aggregator import CertificationAggregator
from scripts.release.baseline_freezer import BaselineFreezer
from scripts.release.release_validator import ReleaseValidator
from scripts.release.certificate_engine import CertificateEngine

__all__ = [
    "ReleaseStateMachine",
    "ReleaseState",
    "ReleaseTransition",
    "FreezeGuardResult",
    "evaluate_freeze_guard_canon_compliance",
    "evaluate_freeze_guard_zero_regressions",
    "evaluate_freeze_guard_critical_guards",
    "evaluate_freeze_guard_architecture_drift",
    "evaluate_freeze_guard_baseline_locked",
    "CertificationAggregator",
    "BaselineFreezer",
    "ReleaseValidator",
    "CertificateEngine",
]
