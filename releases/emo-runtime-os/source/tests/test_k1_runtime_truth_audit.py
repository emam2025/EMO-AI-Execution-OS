"""Tests for K1 Runtime Truth Audit — wiring, events, replay, codegraph drift."""

# LAW-5: Observable — test that audit results are published
# LAW-8: Traceable — test audit_trace_id propagation
# RULE-1: Deterministic — test that same inputs produce same audit results

import time
from unittest.mock import MagicMock

import pytest

from scripts.audit.audit_wiring import AuditWiring
from scripts.audit.audit_event_consumption import (
    AuditEventConsumption,
    REQUIRED_TOPICS,
)
from scripts.audit.audit_replay_integrity import AuditReplayIntegrity
from scripts.audit.audit_codegraph_drift import AuditCodegraphDrift


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    bus._subscriptions = {}
    return bus


@pytest.fixture
def audit_wiring(event_bus):
    return AuditWiring(event_bus=event_bus)


@pytest.fixture
def audit_events(event_bus):
    return AuditEventConsumption(event_bus=event_bus)


@pytest.fixture
def audit_replay(event_bus):
    return AuditReplayIntegrity(event_bus=event_bus)


@pytest.fixture
def mock_root():
    class MockRoot:
        def __init__(self):
            self._event_bus = "mock_event_bus"
            self._checkpoint_manager = "mock_checkpoint"
            self._contract_validator = "mock_contract"
            self._compliance_validator = "mock_compliance"
            self._cost_tracker = "mock_cost"
            self._optimizer = "mock_optimizer"
            self._engine = "mock_engine"
            self._size_limiter = "mock_size"
            self._system_auditor = "mock_auditor"
            self._load_generator = "mock_load"
            self._security_validator = "mock_security"
            self._certification_engine = "mock_cert"
            self._tenant_router = "mock_tenant"
            self._usage_meter = "mock_meter"
            self._billing_engine = "mock_billing"
            self._compliance_auditor = "mock_compliance_audit"
            self._chaos_injector = "mock_chaos"
            self._load_orchestrator = "mock_orch"
            self._stability_validator = "mock_stability"
            self._certification_gate = "mock_gate"
            self._canary_observer = "mock_canary"
            self._sdk_client = "mock_sdk"
            self._cli_runtime = "mock_cli"
            self._doc_generator = "mock_doc"
            self._api_spec_publisher = "mock_api"
            self._failover_orchestrator = "mock_failover"
            self._disaster_recovery = "mock_dr"
            self._rolling_update_manager = "mock_roll"
            self._runtime_migrator = "mock_migrate"
    return MockRoot()


# ── TestWiringAudit ─────────────────────────────

class TestWiringAudit:
    """4 tests: all wired, none fallbacks, trace_id, pass/fail."""

    def test_all_protocols_wired_with_concrete(self, audit_wiring, mock_root):
        report = audit_wiring.audit_composition_root(mock_root)
        assert report.passed is True
        assert report.none_fallbacks == 0
        assert report.wired_protocols == report.total_protocols

    def test_detects_none_fallbacks(self, audit_wiring):
        class PartialRoot:
            def __init__(self):
                self._event_bus = "mock"
                self._chaos_injector = None
        report = audit_wiring.audit_composition_root(PartialRoot())
        assert report.passed is False
        assert report.none_fallbacks > 0

    def test_trace_id_propagation(self, audit_wiring, mock_root):
        assert audit_wiring.audit_trace_id.startswith("aw_")
        report = audit_wiring.audit_composition_root(mock_root)
        assert report.audit_trace_id == audit_wiring.audit_trace_id

    def test_total_protocol_count(self, audit_wiring, mock_root):
        report = audit_wiring.audit_composition_root(mock_root)
        assert report.total_protocols >= 28


# ── TestEventConsumptionAudit ───────────────────

class TestEventConsumptionAudit:
    """4 tests: required topics, dead topics, subscriber count, trace_id."""

    def test_required_topics_defined(self):
        assert len(REQUIRED_TOPICS) >= 13

    def test_all_topics_have_subscribers(self, audit_events, event_bus):
        for topic in REQUIRED_TOPICS:
            event_bus._subscriptions[topic] = ["handler1"]
        report = audit_events.audit_topics(event_bus)
        assert report.passed is True
        assert report.dead_topics == 0

    def test_detects_dead_topics(self, audit_events, event_bus):
        report = audit_events.audit_topics(event_bus)
        assert report.dead_topics > 0
        assert report.passed is False

    def test_trace_id_propagation(self, audit_events, event_bus):
        assert audit_events.audit_trace_id.startswith("ae_")
        report = audit_events.audit_topics(event_bus)
        assert report.audit_trace_id == audit_events.audit_trace_id


# ── TestReplayIntegrityAudit ────────────────────

class TestReplayIntegrityAudit:
    """4 tests: 100% match, match rate, trace_id, avg timing."""

    def test_100_cycles_100_percent_match(self, audit_replay):
        report = audit_replay.run_100_cycles(seed=42)
        assert report.matched_cycles == 100
        assert report.match_rate == 100.0

    def test_100_cycles_pass_threshold(self, audit_replay):
        report = audit_replay.run_100_cycles(seed=99)
        assert report.passed is True
        assert report.match_rate >= 99.5

    def test_trace_id_propagation(self, audit_replay):
        assert audit_replay.audit_trace_id.startswith("ar_")
        report = audit_replay.run_100_cycles()
        assert report.audit_trace_id == audit_replay.audit_trace_id

    def test_avg_timing_under_threshold(self, audit_replay):
        report = audit_replay.run_100_cycles()
        assert report.avg_timing_ms < 100.0


# ── TestCodegraphDriftAudit ─────────────────────

class TestCodegraphDriftAudit:
    """3 tests: dead imports, orphans, trace_id."""

    def test_no_dead_imports_detected(self):
        auditor = AuditCodegraphDrift()
        report = auditor.audit_drift()
        assert report.passed is True
        assert report.dead_imports == 0

    def test_no_orphan_modules_detected(self):
        auditor = AuditCodegraphDrift()
        report = auditor.audit_drift()
        assert report.orphan_modules == 0

    def test_trace_id_propagation(self):
        auditor = AuditCodegraphDrift()
        assert auditor.audit_trace_id.startswith("ad_")
        report = auditor.audit_drift()
        assert report.audit_trace_id == auditor.audit_trace_id

    def test_all_modules_checked(self):
        auditor = AuditCodegraphDrift()
        report = auditor.audit_drift()
        assert report.total_modules >= 18
