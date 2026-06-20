"""Tests for Advanced Capability Security — Dynamic Sensitive Tool Classification.

6 tests covering sensitivity classification, CRITICAL tool enforcement,
backward compatibility, and audit trail for sensitive violations.

Ref: Phase E.2 — Advanced Capability Security (Dynamic Sensitive Tool Classification)
"""

import asyncio
import pytest

from core.models.security import (
    Capability,
    CapabilityManifest,
    ToolSensitivityLevel,
)
from core.security.capability_guard import CapabilityGuard
from core.security.sensitive_tool_classifier import SensitiveToolClassifier
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


def test_classify_tool_sensitivity_level():
    """E.2.1: Tool sensitivity classification stores and retrieves levels."""
    classifier = SensitiveToolClassifier()

    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)
    classifier.classify("data_reader", ToolSensitivityLevel.LOW)
    classifier.classify("config_updater", ToolSensitivityLevel.HIGH)

    assert classifier.get_classification("line_shutdown") == ToolSensitivityLevel.CRITICAL
    assert classifier.get_classification("data_reader") == ToolSensitivityLevel.LOW
    assert classifier.get_classification("config_updater") == ToolSensitivityLevel.HIGH
    assert classifier.get_classification("unknown_tool") == ToolSensitivityLevel.LOW


def test_critical_tool_requires_execute_sensitive():
    """E.2.1: CRITICAL tool without EXECUTE_SENSITIVE is denied."""
    classifier = SensitiveToolClassifier()
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)

    allowed = [Capability.SUBPROCESS]
    result = classifier.check_critical_access("line_shutdown", allowed)
    assert result is False

    violations = classifier.get_violations()
    assert len(violations) == 1
    assert violations[0]["tool_id"] == "line_shutdown"
    assert violations[0]["sensitivity_level"] == "critical"
    assert "EXECUTE_SENSITIVE" in violations[0]["reason"]


def test_critical_tool_with_execute_sensitive_allowed():
    """E.2.1: CRITICAL tool with EXECUTE_SENSITIVE is allowed."""
    classifier = SensitiveToolClassifier()
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)

    allowed = [Capability.SUBPROCESS, Capability.EXECUTE_SENSITIVE]
    result = classifier.check_critical_access("line_shutdown", allowed)
    assert result is True

    violations = classifier.get_violations()
    assert len(violations) == 0


def test_non_critical_tool_no_sensitivity_enforcement():
    """E.2.1: Non-CRITICAL tools do not require EXECUTE_SENSITIVE."""
    classifier = SensitiveToolClassifier()
    classifier.classify("data_reader", ToolSensitivityLevel.LOW)
    classifier.classify("config_updater", ToolSensitivityLevel.HIGH)

    assert classifier.check_critical_access("data_reader", [Capability.FILESYSTEM_READ]) is True
    assert classifier.check_critical_access("config_updater", [Capability.FILESYSTEM_WRITE]) is True

    violations = classifier.get_violations()
    assert len(violations) == 0


def test_guard_blocks_critical_without_classifier():
    """E.2.1: Guard blocks CRITICAL tool without EXECUTE_SENSITIVE via classifier."""
    classifier = SensitiveToolClassifier()
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)

    guard = CapabilityGuard(classifier=classifier)
    manifest = CapabilityManifest(
        tool_id="line_shutdown",
        allowed_capabilities=(Capability.SUBPROCESS, Capability.EXECUTE_SENSITIVE),
    )
    guard.register_manifest("line_shutdown", manifest)

    result = guard.check("line_shutdown", [Capability.SUBPROCESS])
    assert result is False

    guard_violations = guard.get_violations()
    classifier_violations = classifier.get_violations()
    assert len(guard_violations) == 0
    assert len(classifier_violations) == 1
    assert classifier_violations[0]["sensitivity_level"] == "critical"


def test_guard_passes_critical_with_execute_sensitive():
    """E.2.1: Guard passes CRITICAL tool when EXECUTE_SENSITIVE is requested."""
    classifier = SensitiveToolClassifier()
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)

    guard = CapabilityGuard(classifier=classifier)
    manifest = CapabilityManifest(
        tool_id="line_shutdown",
        allowed_capabilities=(Capability.SUBPROCESS, Capability.EXECUTE_SENSITIVE),
    )
    guard.register_manifest("line_shutdown", manifest)

    result = guard.check("line_shutdown", [Capability.SUBPROCESS, Capability.EXECUTE_SENSITIVE])
    assert result is True

    violations = guard.get_violations()
    classifier_violations = classifier.get_violations()
    assert len(violations) == 0
    assert len(classifier_violations) == 0


@pytest.mark.asyncio
async def test_critical_violation_publishes_security_event():
    """E.2.1: CRITICAL access denial publishes SECURITY_VIOLATION event."""
    event_bus = MockEventBus()
    classifier = SensitiveToolClassifier(event_bus=event_bus)
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)

    result = classifier.check_critical_access("line_shutdown", [Capability.SUBPROCESS])
    assert result is False
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.SECURITY_VIOLATION
    assert published["event"].payload["tool_id"] == "line_shutdown"
    assert published["event"].payload["sensitivity_level"] == "critical"
    assert published["event"].payload["action_taken"] == "blocked"


def test_backward_compatibility_existing_tools():
    """E.2.1: Existing tools work without reclassification (default LOW)."""
    classifier = SensitiveToolClassifier()
    guard = CapabilityGuard(classifier=classifier)

    manifest = CapabilityManifest(
        tool_id="web_fetch",
        allowed_capabilities=(Capability.NETWORK_OUTBOUND, Capability.FILESYSTEM_READ),
        max_cpu_seconds=10.0,
        max_memory_mb=256,
    )
    guard.register_manifest("web_fetch", manifest)

    result = guard.check("web_fetch", [Capability.NETWORK_OUTBOUND])
    assert result is True

    classifier_violations = classifier.get_violations()
    assert len(classifier_violations) == 0


def test_dynamic_reclassification_blocks_after_upgrade():
    """E.2.1: Tool upgraded to CRITICAL is blocked without EXECUTE_SENSITIVE."""
    classifier = SensitiveToolClassifier()
    guard = CapabilityGuard(classifier=classifier)

    manifest = CapabilityManifest(
        tool_id="line_shutdown",
        allowed_capabilities=(Capability.SUBPROCESS, Capability.EXECUTE_SENSITIVE),
    )
    guard.register_manifest("line_shutdown", manifest)

    classifier.classify("line_shutdown", ToolSensitivityLevel.LOW)
    assert guard.check("line_shutdown", [Capability.SUBPROCESS]) is True

    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)
    assert guard.check("line_shutdown", [Capability.SUBPROCESS]) is False

    classifier_violations = classifier.get_violations()
    assert len(classifier_violations) == 1
    assert classifier_violations[0]["sensitivity_level"] == "critical"


def test_list_classified_tools():
    """E.2.1: list_classified_tools returns all classifications."""
    classifier = SensitiveToolClassifier()
    classifier.classify("line_shutdown", ToolSensitivityLevel.CRITICAL)
    classifier.classify("data_reader", ToolSensitivityLevel.LOW)

    tools = classifier.list_classified_tools()
    assert tools["line_shutdown"] == ToolSensitivityLevel.CRITICAL
    assert tools["data_reader"] == ToolSensitivityLevel.LOW
    assert len(tools) == 2
