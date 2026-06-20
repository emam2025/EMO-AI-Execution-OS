"""Tests for RC17.3.2 — Energy Safety Policies (NERC-CIP).

Covers:
- NERC-CIP Default Deny for control writes
- Trust level enforcement
- Approval gating for critical energy operations
- Audit trail for safety decisions
- SAFETY_VIOLATION event publishing
"""

import asyncio

import pytest

from core.models.energy_policy import (
    DEFAULT_NERC_CIP_POLICIES,
    EnergyActionType,
    EnergyRiskLevel,
    EnergySafetyDecision,
    NERCCIPPolicy,
)
from core.models.event import EventTopic
from core.governance.energy_safety import EnergySafetyGate


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# ── NERC-CIP Default Deny ──────────────────────────────────────────────────


def test_nerc_cip_denies_control_write_by_default():
    """NERC-CIP: control_write is denied by Default Deny (no approval)."""
    gate = EnergySafetyGate()
    decision = gate.evaluate(EnergyActionType.CONTROL_WRITE)
    assert decision.allowed is False
    assert "Default Deny" in decision.reason or "insufficient" in decision.reason
    assert decision.action_type == EnergyActionType.CONTROL_WRITE
    assert decision.requires_approval is True


def test_nerc_cip_denies_grid_shutdown_without_trust():
    """NERC-CIP: grid_shutdown denied for UNVERIFIED trust."""
    gate = EnergySafetyGate()
    decision = gate.evaluate(EnergyActionType.GRID_SHUTDOWN, trust_level="UNVERIFIED")
    assert decision.allowed is False
    assert "Trust level insufficient" in decision.reason


def test_nerc_cip_allows_observe_for_any_trust():
    """NERC-CIP: observe is always allowed."""
    gate = EnergySafetyGate()
    for trust in ["UNVERIFIED", "VERIFIED", "TRUSTED"]:
        decision = gate.evaluate(EnergyActionType.OBSERVE, trust_level=trust)
        assert decision.allowed is True


def test_nerc_cip_allows_analyze_for_any_trust():
    """NERC-CIP: analyze is always allowed."""
    gate = EnergySafetyGate()
    for trust in ["UNVERIFIED", "VERIFIED", "TRUSTED"]:
        decision = gate.evaluate(EnergyActionType.ANALYZE, trust_level=trust)
        assert decision.allowed is True


def test_nerc_cip_allows_recommend_for_any_trust():
    """NERC-CIP: recommend is always allowed."""
    gate = EnergySafetyGate()
    for trust in ["UNVERIFIED", "VERIFIED", "TRUSTED"]:
        decision = gate.evaluate(EnergyActionType.RECOMMEND, trust_level=trust)
        assert decision.allowed is True


# ── Trust Level Enforcement ────────────────────────────────────────────────


def test_nerc_cip_simulate_requires_verified():
    """NERC-CIP: simulate requires VERIFIED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.SIMULATE, "UNVERIFIED").allowed is False
    assert gate.evaluate(EnergyActionType.SIMULATE, "VERIFIED").allowed is True
    assert gate.evaluate(EnergyActionType.SIMULATE, "TRUSTED").allowed is True


def test_nerc_cip_control_write_requires_trusted():
    """NERC-CIP: control_write requires TRUSTED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.CONTROL_WRITE, "UNVERIFIED").allowed is False
    assert gate.evaluate(EnergyActionType.CONTROL_WRITE, "VERIFIED").allowed is False
    assert gate.evaluate(EnergyActionType.CONTROL_WRITE, "TRUSTED").allowed is True


def test_nerc_cip_grid_shutdown_requires_trusted():
    """NERC-CIP: grid_shutdown requires TRUSTED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.GRID_SHUTDOWN, "TRUSTED").allowed is True
    assert gate.evaluate(EnergyActionType.GRID_SHUTDOWN, "VERIFIED").allowed is False


def test_nerc_cip_load_shedding_requires_trusted():
    """NERC-CIP: load_shedding requires TRUSTED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.LOAD_SHEDDING, "TRUSTED").allowed is True
    assert gate.evaluate(EnergyActionType.LOAD_SHEDDING, "VERIFIED").allowed is False


def test_nerc_cip_plant_start_requires_trusted():
    """NERC-CIP: plant_start requires TRUSTED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.PLANT_START, "TRUSTED").allowed is True
    assert gate.evaluate(EnergyActionType.PLANT_START, "VERIFIED").allowed is False


def test_nerc_cip_plant_stop_requires_trusted():
    """NERC-CIP: plant_stop requires TRUSTED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.PLANT_STOP, "TRUSTED").allowed is True
    assert gate.evaluate(EnergyActionType.PLANT_STOP, "VERIFIED").allowed is False


def test_nerc_cip_maintenance_exec_requires_verified():
    """NERC-CIP: maintenance_exec requires VERIFIED trust level."""
    gate = EnergySafetyGate()
    assert gate.evaluate(EnergyActionType.MAINTENANCE_EXEC, "VERIFIED").allowed is True
    assert gate.evaluate(EnergyActionType.MAINTENANCE_EXEC, "UNVERIFIED").allowed is False


# ── Approval Gating ────────────────────────────────────────────────────────


def test_nerc_cip_control_write_requires_approval():
    """NERC-CIP: control_write always requires approval."""
    gate = EnergySafetyGate()
    decision = gate.evaluate(EnergyActionType.CONTROL_WRITE, "TRUSTED")
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_nerc_cip_grid_shutdown_requires_approval():
    """NERC-CIP: grid_shutdown always requires approval."""
    gate = EnergySafetyGate()
    decision = gate.evaluate(EnergyActionType.GRID_SHUTDOWN, "TRUSTED")
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_nerc_cip_observe_does_not_require_approval():
    """NERC-CIP: observe does not require approval."""
    gate = EnergySafetyGate()
    decision = gate.evaluate(EnergyActionType.OBSERVE, "UNVERIFIED")
    assert decision.allowed is True
    assert decision.requires_approval is False


# ── Audit Trail ────────────────────────────────────────────────────────────


def test_nerc_cip_records_audit_trail():
    """NERC-CIP: every decision is recorded in audit trail."""
    gate = EnergySafetyGate()
    gate.evaluate(EnergyActionType.OBSERVE, "UNVERIFIED")
    gate.evaluate(EnergyActionType.CONTROL_WRITE, "UNVERIFIED")
    gate.evaluate(EnergyActionType.GRID_SHUTDOWN, "TRUSTED")

    log = gate.get_audit_log()
    assert len(log) == 3
    assert log[0]["action_type"] == "observe"
    assert log[0]["allowed"] is True
    assert log[1]["action_type"] == "control_write"
    assert log[1]["allowed"] is False
    assert log[2]["action_type"] == "grid_shutdown"
    assert log[2]["allowed"] is True


# ── Unknown Action Default Deny ────────────────────────────────────────────


def test_nerc_cip_unknown_action_denied():
    """NERC-CIP: unknown action types are denied by Default Deny."""
    gate = EnergySafetyGate()
    decision = gate.evaluate("unknown_action_type")
    assert decision.allowed is False
    assert "Default Deny" in decision.reason


# ── Custom Policy Override ─────────────────────────────────────────────────


def test_nerc_cip_custom_policy_override():
    """NERC-CIP: policies can be overridden for specific action types."""
    gate = EnergySafetyGate()
    gate.set_policy(
        EnergyActionType.CONTROL_WRITE,
        NERCCIPPolicy(
            action_type=EnergyActionType.CONTROL_WRITE,
            requires_approval=False,
            min_trust_level="VERIFIED",
            risk_level=EnergyRiskLevel.CRITICAL,
            description="Custom control write policy",
        ),
    )
    decision = gate.evaluate(EnergyActionType.CONTROL_WRITE, "VERIFIED")
    assert decision.allowed is True
    assert decision.requires_approval is False


# ── Event Publishing ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_nerc_cip_violation_publishes_safety_event():
    """NERC-CIP: violations publish SAFETY_VIOLATION events."""
    event_bus = MockEventBus()
    gate = EnergySafetyGate(event_bus=event_bus)

    gate.evaluate(EnergyActionType.CONTROL_WRITE, "UNVERIFIED")
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.SAFETY_VIOLATION
    assert published["event"].payload["action_type"] == "control_write"
    assert published["event"].payload["allowed"] is False
    assert published["event"].payload["domain"] == "energy"


@pytest.mark.asyncio
async def test_nerc_cip_allowed_does_not_publish_event():
    """NERC-CIP: allowed actions do NOT publish events."""
    event_bus = MockEventBus()
    gate = EnergySafetyGate(event_bus=event_bus)

    gate.evaluate(EnergyActionType.OBSERVE, "UNVERIFIED")
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 0


# ── is_control_write Helper ────────────────────────────────────────────────


def test_is_control_write_identifies_critical_actions():
    """NERC-CIP: is_control_write correctly identifies critical actions."""
    gate = EnergySafetyGate()
    assert gate.is_control_write(EnergyActionType.CONTROL_WRITE) is True
    assert gate.is_control_write(EnergyActionType.GRID_SHUTDOWN) is True
    assert gate.is_control_write(EnergyActionType.LOAD_SHEDDING) is True
    assert gate.is_control_write(EnergyActionType.PLANT_START) is True
    assert gate.is_control_write(EnergyActionType.PLANT_STOP) is True
    assert gate.is_control_write(EnergyActionType.OBSERVE) is False
    assert gate.is_control_write(EnergyActionType.ANALYZE) is False
    assert gate.is_control_write(EnergyActionType.RECOMMEND) is False
    assert gate.is_control_write(EnergyActionType.SIMULATE) is False
