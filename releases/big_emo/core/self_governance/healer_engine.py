"""
Self-Healer Engine — ISelfHealer implementation.

Detects anomalies from telemetry streams, applies bounded corrective
actions, and logs recoveries with signatures. No execution.
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from releases.big_emo.core.interfaces.self_governance.ISelfHealer import ISelfHealer
from releases.big_emo.core.models.self_governance import (
    AnomalyReport as AnomalyReportModel,
    AnomalySeverity,
    RecoveryAction as RecoveryActionModel,
)


@dataclass
class AnomalyReportData:
    report_id: str = ""
    tenant_id: str = ""
    source_service: str = ""
    anomaly_type: str = ""
    severity: str = "medium"
    mitigation: str = ""


@dataclass
class RecoveryActionData:
    action_id: str = ""
    tenant_id: str = ""
    target_service: str = ""
    correction_steps: List[str] = field(default_factory=list)
    validator_signature: str = ""


@dataclass
class RecoveryLog:
    log_id: str = ""
    tenant_id: str = ""
    anomaly_report_id: str = ""
    recovery_action_id: str = ""
    validator_signature: str = ""
    timestamp: float = 0.0


class _AnomalyDetector:
    """Internal anomaly detection logic."""

    ANOMALY_PATTERNS = {
        "error_rate_spike": {"severity": AnomalySeverity.HIGH, "mitigation": "scale or restart"},
        "latency_increase": {"severity": AnomalySeverity.MEDIUM, "mitigation": "reroute or optimise"},
        "memory_pressure": {"severity": AnomalySeverity.CRITICAL, "mitigation": "scale up or evict"},
        "cpu_saturation": {"severity": AnomalySeverity.HIGH, "mitigation": "scale out"},
        "connection_drop": {"severity": AnomalySeverity.MEDIUM, "mitigation": "reconnect or failover"},
        "auth_failure_surge": {"severity": AnomalySeverity.CRITICAL, "mitigation": "block and audit"},
    }

    @staticmethod
    def detect(telemetry: dict) -> tuple[str, AnomalySeverity, str]:
        metrics = telemetry.get("metrics", telemetry)
        for signal in _AnomalyDetector.ANOMALY_PATTERNS:
            if metrics.get(signal, 0) > 0:
                pattern = _AnomalyDetector.ANOMALY_PATTERNS[signal]
                return signal, pattern["severity"], pattern["mitigation"]
        return "normal", AnomalySeverity.LOW, "no action needed"


class SelfHealerEngine(ISelfHealer):
    """Detects anomalies and applies bounded corrective actions.

    LAW-6: every public method requires tenant_id.
    LAW-22: bounded recovery — no unauthorised corrections.
    """

    def __init__(self) -> None:
        self._reports: Dict[str, AnomalyReportModel] = {}
        self._logs: Dict[str, RecoveryLog] = {}

    def detect_anomaly(
        self,
        telemetry_stream: Dict[str, Any],
        tenant_id: str,
    ) -> AnomalyReportData:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        anomaly_type, severity, mitigation = _AnomalyDetector.detect(telemetry_stream)
        report_id = f"anom-{uuid.uuid4().hex[:16]}"
        report = AnomalyReportData(
            report_id=report_id,
            tenant_id=tenant_id,
            source_service=telemetry_stream.get("source_service", "unknown"),
            anomaly_type=anomaly_type,
            severity=severity.value,
            mitigation=mitigation,
        )
        model_report = AnomalyReportModel(
            report_id=report_id,
            tenant_id=tenant_id,
            source_service=report.source_service,
            anomaly_type=anomaly_type,
            severity=severity,
            mitigation=mitigation,
        )
        self._reports[report_id] = model_report
        return report

    def apply_correction(
        self,
        report: Dict[str, Any],
        tenant_id: str,
    ) -> RecoveryActionData:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        severity_val = report.get("severity", "low")
        mitigation = report.get("mitigation", "no action")
        anomaly_type = report.get("anomaly_type", "normal")
        steps = self._generate_correction_steps(severity_val, anomaly_type, mitigation)
        action_id = f"rec-{uuid.uuid4().hex[:16]}"
        sig = hashlib.sha256(
            json.dumps({"action_id": action_id, "steps": steps}, sort_keys=True).encode()
        ).hexdigest()[:32]
        action = RecoveryActionData(
            action_id=action_id,
            tenant_id=tenant_id,
            target_service=report.get("source_service", "unknown"),
            correction_steps=steps,
            validator_signature=sig,
        )
        model_action = RecoveryActionModel(
            action_id=action_id,
            tenant_id=tenant_id,
            target_service=action.target_service,
            correction_steps=steps,
            validator_signature=sig,
        )
        self._validate_signature_required(model_action)
        return action

    def log_recovery(
        self,
        action: Dict[str, Any],
        signature: str,
        tenant_id: str,
    ) -> RecoveryLog:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        log = RecoveryLog(
            log_id=f"rl-{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            anomaly_report_id=action.get("report_id", ""),
            recovery_action_id=action.get("action_id", ""),
            validator_signature=signature,
            timestamp=time.time(),
        )
        self._logs[log.log_id] = log
        return log

    def get_report(
        self,
        report_id: str,
        tenant_id: str,
    ) -> AnomalyReportModel:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        report = self._reports.get(report_id)
        if not report or report.tenant_id != tenant_id:
            raise KeyError(f"Report not found: {report_id}")
        return report

    def _generate_correction_steps(self, severity: str, anomaly_type: str, mitigation: str) -> List[str]:
        common = [f"log_anomaly:{anomaly_type}", f"apply_mitigation:{mitigation}"]
        if severity in ("high", "critical"):
            return ["halt_affected_service"] + common + ["notify_operator"]
        return common + ["monitor_for_recurrence"]

    @staticmethod
    def _validate_signature_required(action: RecoveryActionModel) -> None:
        if not action.validator_signature:
            raise ValueError("validator_signature is required on every RecoveryAction (LAW-22)")
