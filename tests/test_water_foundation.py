"""Tests for RC17.4.1 — Water Domain Models & Safety Policies.

6 tests covering:
- Water models are frozen dataclasses
- WHO/EPA policy denies CONTROL_WRITE by default
- PUMP_SHUTDOWN requires TRUSTED approval
- Sensor read-only integrity
- Unknown action default deny
- Policy evaluation blocks unauthorized VALVE_OVERRIDE
"""

from __future__ import annotations

import pytest

from core.models.water import (
    TreatmentPlant,
    PumpStation,
    WaterQualitySensor,
    WaterActionType,
    WaterSafetyDecision,
)
from core.governance.water_policies import (
    WaterPolicy,
    WaterSafetyGate,
    DEFAULT_WATER_POLICIES,
)


# ── Test 1: Water models are frozen ────────────────────────────────────────


def test_water_models_are_frozen():
    """All water domain models must be frozen (immutable)."""
    plant = TreatmentPlant(
        asset_id="plant-001",
        name="Main Treatment Plant",
        capacity_mld=500.0,
    )
    with pytest.raises(AttributeError):
        plant.capacity_mld = 1000.0

    pump = PumpStation(
        asset_id="pump-001",
        name="North Pump Station",
        pump_count=4,
    )
    with pytest.raises(AttributeError):
        pump.active_pumps = 2

    sensor = WaterQualitySensor(
        asset_id="sensor-001",
        location="River Intake",
        ph_level=7.2,
    )
    with pytest.raises(AttributeError):
        sensor.ph_level = 9.0


# ── Test 2: WHO/EPA denies CONTROL_WRITE by default ───────────────────────


def test_who_epa_denies_control_write_by_default():
    """WHO/EPA policy blocks CONTROL_WRITE by default (even for TRUSTED)."""
    gate = WaterSafetyGate()

    decision = gate.evaluate(
        action_type=WaterActionType.CONTROL_WRITE,
        trust_level="TRUSTED",
    )

    assert decision.allowed is False
    assert decision.violation_type == "policy_denied"
    assert decision.requires_approval is True


# ── Test 3: PUMP_SHUTDOWN requires TRUSTED approval ───────────────────────


def test_pump_shutdown_requires_trusted_approval():
    """PUMP_SHUTDOWN blocked for UNVERIFIED/VERIFIED, requires approval for TRUSTED."""
    gate = WaterSafetyGate()

    # UNVERIFIED → blocked (trust insufficient)
    d1 = gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "UNVERIFIED")
    assert d1.allowed is False
    assert d1.violation_type == "trust_insufficient"

    # VERIFIED → blocked (trust insufficient)
    d2 = gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "VERIFIED")
    assert d2.allowed is False
    assert d2.violation_type == "trust_insufficient"

    # TRUSTED → policy denies but requires approval
    d3 = gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "TRUSTED")
    assert d3.allowed is False
    assert d3.violation_type == "policy_denied"
    assert d3.requires_approval is True


# ── Test 4: Sensor read-only integrity ────────────────────────────────────


def test_sensor_read_only_integrity():
    """WaterQualitySensor data is read-only and values are preserved."""
    sensor = WaterQualitySensor(
        asset_id="sensor-001",
        location="River Intake",
        ph_level=7.2,
        turbidity_ntu=0.5,
        chlorine_ppm=1.0,
    )

    assert sensor.ph_level == 7.2
    assert sensor.turbidity_ntu == 0.5
    assert sensor.chlorine_ppm == 1.0
    assert sensor.status == "active"

    # Frozen — cannot modify
    with pytest.raises(AttributeError):
        sensor.ph_level = 14.0

    # Values unchanged after failed modification attempt
    assert sensor.ph_level == 7.2


# ── Test 5: Unknown action default deny ───────────────────────────────────


def test_unknown_action_default_deny():
    """Unknown action types are denied by Default Deny policy."""
    gate = WaterSafetyGate()

    decision = gate.evaluate(
        action_type="UNKNOWN_ACTION_TYPE",
        trust_level="TRUSTED",
    )

    assert decision.allowed is False
    assert decision.violation_type == "unknown_action"
    assert "Default Deny" in decision.reason


# ── Test 6: Policy evaluation blocks unauthorized VALVE_OVERRIDE ───────────


def test_policy_evaluation_blocks_unauthorized_valve_override():
    """VALVE_OVERRIDE blocked for UNVERIFIED, requires approval for TRUSTED."""
    gate = WaterSafetyGate()

    # UNVERIFIED → blocked
    d1 = gate.evaluate(WaterActionType.VALVE_OVERRIDE, "UNVERIFIED")
    assert d1.allowed is False
    assert d1.violation_type == "trust_insufficient"

    # TRUSTED → policy denies, requires approval
    d2 = gate.evaluate(WaterActionType.VALVE_OVERRIDE, "TRUSTED")
    assert d2.allowed is False
    assert d2.violation_type == "policy_denied"
    assert d2.requires_approval is True

    # Audit log records both decisions
    log = gate.get_audit_log()
    assert len(log) == 2
    assert log[0]["action_type"] == "valve_override"
    assert log[0]["allowed"] is False
    assert log[1]["action_type"] == "valve_override"
    assert log[1]["allowed"] is False
