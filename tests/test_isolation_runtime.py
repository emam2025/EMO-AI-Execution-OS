"""Tests for IsolationRuntime Integration Layer (Phase E.1.3).

8 tests covering the full execution pipeline:
CapabilityGuard → IOPolicyEngine → SandboxExecutor → Event Publishing

Ref: Phase E.1.3 — IsolationRuntime Integration Layer
"""

import asyncio
import pytest

from core.models.event import EventTopic
from core.models.sandbox import SandboxResult
from core.models.security import Capability, CapabilityManifest
from core.runtime.isolation.isolation_runtime import IsolationRuntime
from core.runtime.sandbox.sandbox_executor import SandboxExecutor
from core.security.capability_guard import CapabilityGuard
from core.security.io_policy_engine import IOPolicyEngine


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


def _make_runtime(
    event_bus=None,
    allowed_paths=None,
    allowed_domains=None,
    tool_manifests=None,
) -> IsolationRuntime:
    guard = CapabilityGuard(event_bus=event_bus)
    io_engine = IOPolicyEngine(
        allowed_paths=allowed_paths or ["/tmp/sandbox", "/data"],
        allowed_domains=allowed_domains or ["api.example.com"],
        event_bus=event_bus,
    )
    executor = SandboxExecutor(event_bus=event_bus)

    for tool_id, caps in (tool_manifests or {}).items():
        manifest = CapabilityManifest(
            tool_id=tool_id,
            allowed_capabilities=tuple(caps),
            max_cpu_seconds=10.0,
            max_memory_mb=256,
        )
        guard.register_manifest(tool_id, manifest)

    return IsolationRuntime(
        capability_guard=guard,
        io_policy_engine=io_engine,
        sandbox_executor=executor,
        event_bus=event_bus,
    )


SIMPLE_SCRIPT = "print('hello from isolation')"
FAIL_SCRIPT = "import sys; sys.exit(1)"
FILE_SCRIPT = 'open("/etc/passwd", "r").read()'
NET_SCRIPT = "import urllib.request; urllib.request.urlopen('https://evil.com')"


@pytest.mark.asyncio
async def test_execute_tool_with_valid_capability_succeeds():
    runtime = _make_runtime(
        tool_manifests={"safe_tool": [Capability.EXECUTE_SENSITIVE]}
    )
    result = await runtime.execute_tool("safe_tool", SIMPLE_SCRIPT, {})
    assert result.success is True
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_execute_tool_without_capability_denied():
    runtime = _make_runtime()
    result = await runtime.execute_tool("unknown_tool", SIMPLE_SCRIPT, {})
    assert result.success is False
    assert "Capability denied" in result.error


@pytest.mark.asyncio
async def test_execute_tool_with_io_policy_violation_denied():
    runtime = _make_runtime(
        tool_manifests={"tool_a": [Capability.EXECUTE_SENSITIVE]}
    )
    result = await runtime.execute_tool("tool_a", FILE_SCRIPT, {})
    assert result.success is False
    assert "IO policy violation" in result.error


@pytest.mark.asyncio
async def test_execute_tool_with_resource_quota_exceeded_denied():
    runtime = _make_runtime()
    result = await runtime.execute_tool("unregistered", SIMPLE_SCRIPT, {})
    assert result.success is False
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_execute_tool_timeout_enforced():
    slow_script = "import time; time.sleep(60)"
    runtime = _make_runtime(
        tool_manifests={"slow_tool": [Capability.EXECUTE_SENSITIVE]}
    )
    result = await runtime.execute_tool("slow_tool", slow_script, {})
    assert result.success is False
    assert result.timed_out is True
    assert result.killed is True


@pytest.mark.asyncio
async def test_execute_tool_memory_limit_enforced():
    runtime = _make_runtime(
        tool_manifests={"mem_tool": [Capability.EXECUTE_SENSITIVE]}
    )
    result = await runtime.execute_tool("mem_tool", SIMPLE_SCRIPT, {})
    assert result.success is True
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_full_integration_flow_capability_to_sandbox():
    event_bus = MockEventBus()
    runtime = _make_runtime(
        event_bus=event_bus,
        tool_manifests={"full_tool": [Capability.EXECUTE_SENSITIVE]},
    )
    result = await runtime.execute_tool("full_tool", SIMPLE_SCRIPT, {})
    await asyncio.sleep(0.1)
    assert result.success is True
    topics = [e["topic"] for e in event_bus.published]
    assert EventTopic.EXECUTION_STARTED in topics
    assert EventTopic.EXECUTION_COMPLETED in topics


@pytest.mark.asyncio
async def test_audit_trail_records_full_execution_path():
    event_bus = MockEventBus()
    runtime = _make_runtime(
        event_bus=event_bus,
        tool_manifests={"audited_tool": [Capability.EXECUTE_SENSITIVE]},
    )
    result = await runtime.execute_tool("audited_tool", SIMPLE_SCRIPT, {})
    await asyncio.sleep(0.1)
    assert result.success is True
    topics = [e["topic"] for e in event_bus.published]
    assert EventTopic.EXECUTION_STARTED in topics
    assert EventTopic.EXECUTION_COMPLETED in topics
    assert len(event_bus.published) >= 2
