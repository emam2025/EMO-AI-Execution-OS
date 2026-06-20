"""Pilot Guardrails Configuration Tests.

4 tests validating Pilot guardrails configuration values.

Ref: Pilot.1.3 — Pilot APIs Documentation & Guardrails Configuration
"""

import os

import pytest

from core.governance.pilot_guardrails_config import (
    PILOT_APPROVAL_RULES,
    PILOT_OEE_THRESHOLDS,
    PILOT_ROLLBACK_RULES,
    PILOT_SAFETY_LIMITS,
)


def test_pilot_oee_thresholds_are_valid():
    """OEE thresholds are realistic and within valid ranges."""
    assert 0.0 < PILOT_OEE_THRESHOLDS.overall_oee_pct < 100.0
    assert 0.0 < PILOT_OEE_THRESHOLDS.availability_pct < 100.0
    assert 0.0 < PILOT_OEE_THRESHOLDS.performance_pct < 100.0
    assert 0.0 < PILOT_OEE_THRESHOLDS.quality_pct < 100.0
    assert PILOT_OEE_THRESHOLDS.overall_oee_pct == 60.0
    assert PILOT_OEE_THRESHOLDS.quality_pct == 95.0


def test_pilot_safety_limits_trigger_alerts():
    """Safety limits are set to realistic industrial values."""
    assert PILOT_SAFETY_LIMITS.temperature_max_celsius == 95.0
    assert PILOT_SAFETY_LIMITS.vibration_max == 5.0
    assert PILOT_SAFETY_LIMITS.pressure_max_psi == 150.0
    assert PILOT_SAFETY_LIMITS.runtime_max_seconds == 3600.0
    assert PILOT_SAFETY_LIMITS.temperature_max_celsius > 50.0
    assert PILOT_SAFETY_LIMITS.vibration_max > 0.0


def test_pilot_approval_rules_enforce_human_in_loop():
    """Critical actions require human approval at L2 autonomy level."""
    assert "line_shutdown" in PILOT_APPROVAL_RULES.actions
    assert "emergency_stop" in PILOT_APPROVAL_RULES.actions
    assert "quarantine_batch" in PILOT_APPROVAL_RULES.actions
    assert PILOT_APPROVAL_RULES.required_autonomy_level == "L2"
    assert PILOT_APPROVAL_RULES.timeout_seconds > 0
    assert len(PILOT_APPROVAL_RULES.actions) >= 5


def test_pilot_apis_documentation_exists():
    """docs/PILOT_APIS.md exists and contains required sections."""
    doc_path = os.path.join(
        os.path.dirname(__file__), "..", "docs", "PILOT_APIS.md"
    )
    assert os.path.exists(doc_path), f"Documentation not found at {doc_path}"

    with open(doc_path) as f:
        content = f.read()

    assert "Manufacturing Scenario APIs" in content
    assert "Monitoring APIs" in content
    assert "Safety" in content
    assert "Event Stream APIs" in content
    assert "Guardrails Configuration" in content
    assert len(content) > 500
