"""3.8.2.2 — Drift Classifier.

Classifies architectural drift events by severity.

Severity levels:
  INFO      — minor discrepancy, no action needed
  WARNING   — notable divergence, should be reviewed
  HIGH      — significant architectural violation, requires attention
  CRITICAL  — architecture is actively degrading, must be addressed
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class DriftEvent:
    drift_type: str = ""
    severity: str = ""
    message: str = ""
    static_value: float = 0.0
    runtime_value: float = 0.0
    delta: float = 0.0


@dataclass
class DriftReport:
    events: List[DriftEvent] = field(default_factory=list)

    @property
    def max_severity(self) -> str:
        order = {"INFO": 0, "WARNING": 1, "HIGH": 2, "CRITICAL": 3}
        if not self.events:
            return "INFO"
        return max(self.events, key=lambda e: order.get(e.severity, 0)).severity

    @property
    def is_blocking(self) -> bool:
        return self.max_severity in ("HIGH", "CRITICAL")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_severity": self.max_severity,
            "is_blocking": self.is_blocking,
            "events": [
                {
                    "drift_type": e.drift_type,
                    "severity": e.severity,
                    "message": e.message,
                    "delta": e.delta,
                }
                for e in self.events
            ],
        }


class DriftClassifier:
    """Classifies architectural drift between static and runtime graphs.

    Categories:
      1. HIDDEN_DEPENDENCY — runtime call that static graph doesn't know
      2. BOUNDARY_VIOLATION — architectural layer crossed in runtime
      3. COUPLING_EXPLOSION — runtime coupling >> static coupling
      4. FREQUENCY_ANOMALY — unexpected execution frequency
    """

    COUPLING_EXPLOSION_THRESHOLD = 0.3
    HIDDEN_DEPENDENCY_SEVERITY = "HIGH"
    BOUNDARY_VIOLATION_SEVERITY = "CRITICAL"

    def classify_node_drift(
        self,
        tool: str,
        static_coupling: float,
        runtime_coupling: float,
        is_hidden: bool = False,
        is_boundary: bool = False,
    ) -> DriftEvent:
        if is_hidden:
            return DriftEvent(
                drift_type="HIDDEN_DEPENDENCY",
                severity=self.HIDDEN_DEPENDENCY_SEVERITY,
                message=f"'{tool}' has runtime dependencies not in static graph",
                static_value=0.0,
                runtime_value=runtime_coupling,
                delta=runtime_coupling,
            )

        if is_boundary:
            return DriftEvent(
                drift_type="BOUNDARY_VIOLATION",
                severity=self.BOUNDARY_VIOLATION_SEVERITY,
                message=f"'{tool}' crossed architectural boundaries at runtime",
                static_value=static_coupling,
                runtime_value=runtime_coupling,
                delta=runtime_coupling - static_coupling,
            )

        delta = runtime_coupling - static_coupling
        if delta >= self.COUPLING_EXPLOSION_THRESHOLD or runtime_coupling > 0.8:
            return DriftEvent(
                drift_type="COUPLING_EXPLOSION",
                severity="HIGH",
                message=f"'{tool}' runtime coupling ({runtime_coupling:.2f}) >> "
                        f"static coupling ({static_coupling:.2f})",
                static_value=static_coupling,
                runtime_value=runtime_coupling,
                delta=delta,
            )

        if delta >= 0.1:
            return DriftEvent(
                drift_type="COUPLING_EXPLOSION",
                severity="WARNING",
                message=f"'{tool}' coupling increased from {static_coupling:.2f} "
                        f"to {runtime_coupling:.2f} at runtime",
                static_value=static_coupling,
                runtime_value=runtime_coupling,
                delta=delta,
            )

        return DriftEvent(
            drift_type="COUPLING_EXPLOSION",
            severity="INFO",
            message=f"'{tool}' coupling stable ({static_coupling:.2f} → {runtime_coupling:.2f})",
            static_value=static_coupling,
            runtime_value=runtime_coupling,
            delta=delta,
        )

    def classify_session(self, events: List[DriftEvent]) -> DriftReport:
        return DriftReport(events=events)
