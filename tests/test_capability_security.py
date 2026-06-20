"""Tests for Capability Security Model & IO Policy Engine (Phase E.1.1).

6 tests covering default deny, capability validation, file/network policy,
and security violation event publishing.

Ref: Phase E.1.1 — Capability Security Model & IO Policy Engine
"""

import asyncio
import pytest

from core.models.security import (
    Capability,
    CapabilityManifest,
    SecurityViolation,
    ViolationAction,
)
from core.security.capability_guard import CapabilityGuard
from core.security.io_policy_engine import IOPolicyEngine
from core.models.event import EventTopic


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# --- Tests ---


def test_default_deny_unregistered_tool():
    guard = CapabilityGuard()
    result = guard.check("unknown_tool", [Capability.NETWORK_OUTBOUND])
    assert result is False
    assert len(guard.get_violations()) == 1
    assert guard.get_violations()[0].tool_id == "unknown_tool"
    assert "not registered" in guard.get_violations()[0].reason


def test_explicit_allow_valid_capability():
    guard = CapabilityGuard()
    manifest = CapabilityManifest(
        tool_id="web_fetch",
        allowed_capabilities=(Capability.NETWORK_OUTBOUND, Capability.FILESYSTEM_READ),
        max_cpu_seconds=10.0,
        max_memory_mb=256,
    )
    guard.register_manifest("web_fetch", manifest)
    result = guard.check("web_fetch", [Capability.NETWORK_OUTBOUND])
    assert result is True
    assert len(guard.get_violations()) == 0


def test_block_unauthorized_capability():
    guard = CapabilityGuard()
    manifest = CapabilityManifest(
        tool_id="reader",
        allowed_capabilities=(Capability.FILESYSTEM_READ,),
    )
    guard.register_manifest("reader", manifest)
    result = guard.check("reader", [Capability.FILESYSTEM_WRITE])
    assert result is False
    violations = guard.get_violations()
    assert len(violations) == 1
    assert violations[0].requested_capability == "filesystem_write"
    assert violations[0].action_taken == ViolationAction.BLOCKED


def test_io_policy_blocks_unauthorized_file_access():
    engine = IOPolicyEngine(allowed_paths=["/tmp/sandbox", "/data/readonly"])
    result = engine.check_file_access("tool-1", "/etc/passwd", "read")
    assert result is False
    violations = engine.get_violations()
    assert len(violations) == 1
    assert "/etc/passwd" in violations[0].reason


def test_io_policy_blocks_unauthorized_network_access():
    engine = IOPolicyEngine(allowed_domains=["api.example.com", "cdn.example.com"])
    result = engine.check_network_access("tool-1", "https://evil.com/steal")
    assert result is False
    violations = engine.get_violations()
    assert len(violations) == 1
    assert "evil.com" in violations[0].reason


@pytest.mark.asyncio
async def test_security_violation_publishes_event():
    event_bus = MockEventBus()
    guard = CapabilityGuard(event_bus=event_bus)
    guard.check("unknown_tool", [Capability.SUBPROCESS])
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.SECURITY_VIOLATION
    assert published["event"].payload["tool_id"] == "unknown_tool"
    assert published["event"].payload["requested_capability"] == "any"
    assert published["event"].payload["action_taken"] == "blocked"
