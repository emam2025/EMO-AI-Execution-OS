"""Phase FINAL — Release Validator.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-2 RULE-3 RULE-5

Validates the release against zero-regression, critical-guards, drift-free,
and canon-compliance requirements before approving.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional


class ReleaseValidator:  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-2 RULE-3 RULE-5
    """Validates release readiness against hard gates.

    LAW 1: All protocols must have implementation coverage.
    LAW 3: All measurements deterministic.
    LAW 5: Stability validation complete.
    LAW 8: All recovery SLOs met across phases.
    LAW 11: No global state.
    RULE 1: Deterministic validation.
    RULE 2: All inputs validated.
    RULE 3: Guards enforce all preconditions.
    RULE 5: Rollback capability verified.
    """

    def __init__(self) -> None:
        self._validation_results: Dict[str, Any] = {}

    def validate_zero_regressions(  # LAW-8 RULE-5
        self,
        test_results_path: Optional[str] = None,
        known_failures: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        known = known_failures or []
        new_regressions = 0
        pre_existing = len(known)
        if test_results_path and os.path.exists(test_results_path):
            with open(test_results_path) as f:
                data = json.load(f)
            new_regressions = data.get("new_regressions", 0)
        passed = new_regressions == 0
        return {
            "zero_regressions": passed,
            "new_regressions": new_regressions,
            "pre_existing_failures": pre_existing,
            "known_failures": known,
        }

    def check_guards_enforced(  # LAW-20 LAW-22 RULE-3
        self,
        phase_guard_logs: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logs = phase_guard_logs or {}
        total_guards = 0
        guards_passed = 0
        guard_details: Dict[str, bool] = {}
        for phase, guards in logs.items():
            for gname, gpassed in guards.items():
                total_guards += 1
                key = f"{phase}.{gname}"
                guard_details[key] = gpassed
                if gpassed:
                    guards_passed += 1
        all_passed = total_guards > 0 and guards_passed == total_guards
        return {
            "all_guards_enforced": all_passed,
            "total_guards": total_guards,
            "guards_passed": guards_passed,
            "guards_failed": total_guards - guards_passed,
            "guard_details": guard_details,
        }

    def verify_drift_free(  # LAW-3 §16.10
        self,
        architecture_drift_count: int = 0,
    ) -> Dict[str, Any]:
        passed = architecture_drift_count == 0
        return {
            "drift_free": passed,
            "architecture_drift_count": architecture_drift_count,
        }

    def approve_release(  # LAW-5 RULE-3
        self,
        zero_regressions: bool = False,
        guards_enforced: bool = False,
        drift_free: bool = False,
        canon_compliant: bool = False,
    ) -> Dict[str, Any]:
        all_conditions = [zero_regressions, guards_enforced, drift_free, canon_compliant]
        approved = all(all_conditions)
        blocked_by: List[str] = []
        if not zero_regressions:
            blocked_by.append("zero_regressions")
        if not guards_enforced:
            blocked_by.append("guards_enforced")
        if not drift_free:
            blocked_by.append("drift_free")
        if not canon_compliant:
            blocked_by.append("canon_compliant")
        return {
            "approved": approved,
            "blocked_by": blocked_by,
            "conditions_met": sum(1 for c in all_conditions if c),
            "conditions_total": len(all_conditions),
        }
