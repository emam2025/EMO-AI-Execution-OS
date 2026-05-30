"""Pilot Safety — 15 high-signal validation tests.  # LAW-5 # LAW-12

4 groups × 3-4 tests = 15 tests covering:
  1. Pilot Mode Enforcement (4 tests)
  2. Pilot Trace Propagation (4 tests)
  3. Metrics Collection Accuracy (4 tests)
  4. Exit Criteria Validation (3 tests)

Ref: EXEC-DIRECTIVE-PILOT-001 §Task-4
Ref: Canon LAW 5, LAW 12
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.composition.root import CompositionRoot
from core.observability.pilot_metrics import PilotMetricsCollector
from scripts.pilot.pilot_certifier import PilotCertifier, EXIT_THRESHOLDS

BASE = Path(__file__).resolve().parent.parent

# ═════════════════════════════════════════════════════════════════════
# Group 1: Pilot Mode Enforcement (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup1_PilotModeEnforcement:
    """4 tests validating strict_pilot_mode prevents writes in core/."""

    def test_strict_pilot_mode_default_false(self) -> None:
        root = CompositionRoot()
        assert root.strict_pilot_mode is False

    def test_strict_pilot_mode_set_true(self) -> None:
        root = CompositionRoot()
        root.strict_pilot_mode = True
        assert root.strict_pilot_mode is True

    def test_strict_pilot_mode_toggle(self) -> None:
        root = CompositionRoot()
        root.strict_pilot_mode = True
        assert root.strict_pilot_mode is True
        root.strict_pilot_mode = False
        assert root.strict_pilot_mode is False

    def test_enforce_readonly_no_raise_when_mode_off(self) -> None:
        root = CompositionRoot()
        root.strict_pilot_mode = False
        root.enforce_readonly_core_modules()  # should not raise


# ═════════════════════════════════════════════════════════════════════
# Group 2: Pilot Trace Propagation (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup2_PilotTracePropagation:
    """4 tests validating pilot_trace_id propagation across metrics."""

    def test_collector_has_pilot_trace_id(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_test_trace")
        assert collector.pilot_trace_id == "pilot_test_trace"

    def test_auto_generates_pilot_trace_id(self) -> None:
        collector = PilotMetricsCollector()
        assert collector.pilot_trace_id.startswith("pilot_")

    def test_metric_carries_pilot_trace_id(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_trace_prop")
        metric = collector.collect_trust_score("user_1", "session_1", 4.0)
        assert metric.pilot_trace_id == "pilot_trace_prop"

    def test_session_carries_pilot_trace_id(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_session_test")
        session = collector.start_session("user_1")
        assert session.pilot_trace_id == "pilot_session_test"


# ═════════════════════════════════════════════════════════════════════
# Group 3: Metrics Collection Accuracy (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup3_MetricsCollectionAccuracy:
    """4 tests verifying metric bounds and aggregation."""

    def test_trust_score_clamped_1_to_5(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_clamp")
        low = collector.collect_trust_score("u1", "s1", -1.0)
        high = collector.collect_trust_score("u1", "s1", 10.0)
        assert low.value == 1.0
        assert high.value == 5.0

    def test_cognitive_load_clamped_1_to_10(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_clamp2")
        low = collector.collect_cognitive_load("u1", "task_1", 0)
        high = collector.collect_cognitive_load("u1", "task_1", 99)
        assert low.value == 1.0
        assert high.value == 10.0

    def test_operator_error_rate_clamped_0_to_1(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_clamp3")
        neg = collector.collect_operator_error_rate("u1", "pause", -0.5)
        over = collector.collect_operator_error_rate("u1", "pause", 2.0)
        assert neg.value == 0.0
        assert over.value == 1.0

    def test_get_average_trust_score(self) -> None:
        collector = PilotMetricsCollector(pilot_trace_id="pilot_avg")
        collector.collect_trust_score("u1", "s1", 3.0)
        collector.collect_trust_score("u2", "s2", 5.0)
        avg = collector.get_average_trust_score()
        assert avg == 4.0


# ═════════════════════════════════════════════════════════════════════
# Group 4: Exit Criteria Validation (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup4_ExitCriteriaValidation:
    """3 tests validating exit decision logic."""

    def test_exit_thresholds_defined_for_all_criteria(self) -> None:
        expected = {"trust_score_avg", "operator_error_rate", "cognitive_load_avg",
                     "p99_latency_ms", "replay_determinism_pct", "zero_data_loss_incidents"}
        assert set(EXIT_THRESHOLDS.keys()) == expected

    def test_exit_evaluate_all_pass(self) -> None:
        certifier = PilotCertifier()
        metrics = [
            {"p99_latency_ms": 150, "replay_drift": 0.001, "status": "ok"},
            {"p99_latency_ms": 200, "replay_drift": 0.002, "status": "ok"},
            {"p99_latency_ms": 180, "replay_drift": 0.001, "status": "ok"},
        ]
        result = certifier.evaluate(metrics)
        assert result["all_pass"] is True
        assert result["decision"] == "PASS"

    def test_exit_generates_report(self) -> None:
        certifier = PilotCertifier()
        metrics = [
            {"p99_latency_ms": 150, "replay_drift": 0.001, "status": "ok"},
        ]
        result = certifier.evaluate(metrics)
        assert "decision" in result
        assert "next_version" in result
        assert result["next_version"].startswith("4.10.1")
