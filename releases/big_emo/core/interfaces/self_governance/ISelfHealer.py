"""
Self-Healer Protocol — ISelfHealer (Interface Only).

Defines the contract for detecting operational anomalies and applying
recovery actions. No implementation, no execution.

LAW-8:  no cross-tenant anomaly or recovery cross-contamination.
LAW-22: recovery_actions must be documented and bounded.
LAW-23: anomaly detection must feed into the audit trail.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Protocol, runtime_checkable


@runtime_checkable
class AnomalyReport(Protocol):
    """Read-only view of a detected anomaly."""

    report_id: str
    tenant_id: str
    source_service: str
    anomaly_type: str
    severity: str
    mitigation: str


@runtime_checkable
class RecoveryAction(Protocol):
    """Read-only view of a recovery action."""

    action_id: str
    tenant_id: str
    target_service: str
    correction_steps: List[str]
    validator_signature: str


class ISelfHealer(ABC):
    """Contract for detecting anomalies and applying corrections.

    Every correction must be signed and bounded. No unbounded autonomy.
    """

    @abstractmethod
    def detect_anomaly(
        self,
        telemetry_stream: Dict[str, Any],
        tenant_id: str,
    ) -> AnomalyReport:
        """Detect operational anomalies from telemetry data.

        Args:
            telemetry_stream: Dict containing service metrics, error rates, latency.
            tenant_id:        LAW-6 mandatory tenant scope.

        Returns:
            AnomalyReport with severity and mitigation suggestion.
        """
        ...

    @abstractmethod
    def apply_correction(
        self,
        report: Dict[str, Any],
        tenant_id: str,
    ) -> RecoveryAction:
        """Apply a recovery action based on an anomaly report.

        The resulting RecoveryAction must include a validator_signature
        and bounded correction_steps.

        Args:
            report:     AnomalyReport dict to act upon.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            RecoveryAction with signed correction steps.
        """
        ...
