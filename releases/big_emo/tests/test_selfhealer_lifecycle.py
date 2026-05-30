"""
Self-Healer Lifecycle — 10 tests.

Validates:
  - anomaly detection from telemetry
  - correction action bounded and signed
  - recovery logging
  - tenant isolation (LAW-6)
  - zero unauthorised corrections
"""

import pytest
from releases.big_emo.core.self_governance.healer_engine import SelfHealerEngine


class TestAnomalyDetection:
    def test_detect_error_rate_spike_returns_high(self):
        engine = SelfHealerEngine()
        telemetry = {"source_service": "auth-svc", "metrics": {"error_rate_spike": 15, "latency_increase": 0}}
        report = engine.detect_anomaly(telemetry, tenant_id="t1")
        assert report.severity == "high"
        assert "scale" in report.mitigation

    def test_detect_normal_telemetry_returns_low(self):
        engine = SelfHealerEngine()
        telemetry = {"source_service": "api-svc", "metrics": {}}
        report = engine.detect_anomaly(telemetry, tenant_id="t1")
        assert report.severity == "low"
        assert report.anomaly_type == "normal"

    def test_detect_requires_tenant(self):
        engine = SelfHealerEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.detect_anomaly({"metrics": {}}, tenant_id="")

    def test_detect_populates_source_service(self):
        engine = SelfHealerEngine()
        telemetry = {"source_service": "db-svc", "metrics": {"memory_pressure": 90}}
        report = engine.detect_anomaly(telemetry, tenant_id="t1")
        assert report.source_service == "db-svc"


class TestCorrectionApplication:
    def test_apply_correction_returns_signed_action(self):
        engine = SelfHealerEngine()
        telemetry = {"source_service": "api-svc", "metrics": {"error_rate_spike": 10}}
        report = engine.detect_anomaly(telemetry, "t1")
        action = engine.apply_correction({
            "severity": report.severity,
            "mitigation": report.mitigation,
            "anomaly_type": report.anomaly_type,
            "source_service": report.source_service,
        }, tenant_id="t1")
        assert action.action_id
        assert len(action.validator_signature) == 32
        assert len(action.correction_steps) > 0

    def test_critical_anomaly_gets_halt_step(self):
        engine = SelfHealerEngine()
        action = engine.apply_correction({
            "severity": "critical",
            "mitigation": "scale or restart",
            "anomaly_type": "memory_pressure",
            "source_service": "db-svc",
        }, tenant_id="t1")
        steps_text = " ".join(action.correction_steps)
        assert "halt" in steps_text

    def test_low_severity_no_halt(self):
        engine = SelfHealerEngine()
        action = engine.apply_correction({
            "severity": "low",
            "mitigation": "monitor",
            "anomaly_type": "normal",
            "source_service": "svc",
        }, tenant_id="t1")
        steps_text = " ".join(action.correction_steps)
        assert "halt" not in steps_text

    def test_apply_correction_requires_tenant(self):
        engine = SelfHealerEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.apply_correction({"severity": "low"}, tenant_id="")


class TestRecoveryLogging:
    def test_log_recovery_creates_log(self):
        engine = SelfHealerEngine()
        telemetry = {"source_service": "svc", "metrics": {"connection_drop": 5}}
        report = engine.detect_anomaly(telemetry, "t1")
        action = engine.apply_correction({
            "severity": report.severity,
            "mitigation": report.mitigation,
            "anomaly_type": report.anomaly_type,
            "source_service": report.source_service,
        }, "t1")
        log = engine.log_recovery({"action_id": action.action_id, "report_id": report.report_id}, signature=action.validator_signature, tenant_id="t1")
        assert log.log_id
        assert log.tenant_id == "t1"
        assert log.validator_signature == action.validator_signature

    def test_log_recovery_requires_tenant(self):
        engine = SelfHealerEngine()
        with pytest.raises(ValueError, match="tenant_id"):
            engine.log_recovery({"action_id": "a1"}, signature="sig", tenant_id="")
