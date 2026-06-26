"""Drift detector — architecture temporal stability monitor.

Compares two DriftSnapshots and classifies architectural
degradation severity.
"""

from typing import Any, Dict, List, Optional

from core.codegraph.drift.metrics import (
    compute_coupling_delta,
    compute_risk_delta,
)
from core.codegraph.drift.store import DriftStore


class DriftDetector:
    """Core drift detection engine.

    Compares two snapshots and produces a DriftReport with
    delta metrics and severity classification.
    """

    SEVERITY_THRESHOLDS = {
        "CRITICAL": 0.5,
        "HIGH": 0.25,
        "MEDIUM": 0.1,
        "LOW": 0.0,
    }

    def detect(
        self,
        old_snap: Dict[str, Any],
        new_snap: Dict[str, Any],
    ) -> Dict[str, Any]:
        coupling_delta = compute_coupling_delta(
            old_snap.get("coupling_score", 0.0),
            new_snap.get("coupling_score", 0.0),
        )
        risk_delta = compute_risk_delta(
            old_snap.get("risk_score", 0.0),
            new_snap.get("risk_score", 0.0),
        )
        entropy_delta = (
            new_snap.get("dependency_entropy", 0.0)
            - old_snap.get("dependency_entropy", 0.0)
        )

        severity = self._classify_severity(coupling_delta, risk_delta, entropy_delta)
        violations = self._detect_violations(coupling_delta, risk_delta)

        return {
            "from_version": old_snap.get("version", "unknown"),
            "to_version": new_snap.get("version", "unknown"),
            "coupling_delta": round(coupling_delta, 4),
            "risk_delta": round(risk_delta, 4),
            "entropy_delta": round(entropy_delta, 4),
            "severity": severity,
            "violations": violations,
        }

    def _classify_severity(
        self,
        coupling_delta: float,
        risk_delta: float,
        entropy_delta: float,
    ) -> str:
        score = abs(coupling_delta) + abs(risk_delta) + abs(entropy_delta)
        for severity, threshold in sorted(
            self.SEVERITY_THRESHOLDS.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            if score >= threshold:
                return severity
        return "LOW"

    def _detect_violations(
        self,
        coupling_delta: float,
        risk_delta: float,
    ) -> List[str]:
        violations: List[str] = []
        if coupling_delta > 0.2:
            violations.append("COUPLING_DEGRADATION")
        if risk_delta > 0.2:
            violations.append("RISK_INCREASE")
        return violations


class CodeGraphDriftDetector:
    """Orchestration layer for drift detection.

    Loads the previous snapshot, runs detection against a new
    snapshot, persists the new snapshot, and returns the report.
    """

    def __init__(
        self,
        store: DriftStore,
        detector: Optional[DriftDetector] = None,
    ) -> None:
        self._store = store
        self._detector = detector or DriftDetector()

    def run(
        self,
        old_version: str,
        new_snapshot: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        old_snap = self._store.load(old_version)
        if old_snap is None:
            return None

        report = self._detector.detect(old_snap, new_snapshot)

        # Persist the new snapshot for future comparisons
        self._store.save(new_snapshot)

        return report
