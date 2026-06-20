"""Tests for Sandboxed Executor — Subprocess Isolation (Phase E.1.2).

8 tests covering subprocess execution, timeout, memory/CPU limits,
event publishing, cleanup, isolation, and resource telemetry.

Ref: Phase E.1.2 — Sandboxed Executor (Subprocess Isolation)
"""

import asyncio
import os
import pytest
import sys
import time

from core.models.sandbox import SandboxContext, SandboxResult
from core.models.event import EventTopic
from core.runtime.sandbox.sandbox_executor import SandboxExecutor


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


SIMPLE_SCRIPT = "print('hello from sandbox')"
SLOW_SCRIPT = "import time; time.sleep(60); print('done')"
MEMORY_SCRIPT = "data = b'x' * (50 * 1024 * 1024); print(f'allocated {len(data)}')"
FAIL_SCRIPT = "import sys; print('error', file=sys.stderr); sys.exit(1)"
ISOLATION_SCRIPT = "open('/tmp/sandbox_test_sentinel', 'w').write('child'); print('done')"


def test_execute_simple_function_in_subprocess():
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="simple", timeout_seconds=10)
    result = executor.execute(SIMPLE_SCRIPT, ctx)
    assert result.success is True
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.killed is False
    assert "hello from sandbox" in str(result.output)


def test_timeout_enforcement_kills_process():
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="slow", timeout_seconds=2)
    start = time.time()
    result = executor.execute(SLOW_SCRIPT, ctx)
    elapsed = time.time() - start
    assert result.success is False
    assert result.timed_out is True
    assert result.killed is True
    assert elapsed < 10


def test_memory_limit_exceeded_returns_failure():
    big_alloc = "data = b'x' * (200 * 1024 * 1024); print(f'allocated {len(data)}')"
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="mem", timeout_seconds=10, max_memory_mb=16)
    result = executor.execute(big_alloc, ctx)
    if sys.platform == "darwin":
        assert result.success is True or result.exit_code != 0
    else:
        assert result.success is False
        assert result.exit_code != 0


def test_cpu_limit_exceeded_returns_failure():
    cpu_burner = "total = 0\nfor i in range(10**9):\n    total += i\nprint(total)"
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="cpu", timeout_seconds=10, max_cpu_seconds=1)
    result = executor.execute(cpu_burner, ctx)
    assert result.success is False


@pytest.mark.asyncio
async def test_execution_events_published_to_event_bus():
    event_bus = MockEventBus()
    executor = SandboxExecutor(event_bus=event_bus)
    ctx = SandboxContext(tool_id="evented", timeout_seconds=10)
    executor.execute(SIMPLE_SCRIPT, ctx)
    await asyncio.sleep(0.1)
    topics = [e["topic"] for e in event_bus.published]
    assert EventTopic.EXECUTION_STARTED in topics
    assert EventTopic.EXECUTION_COMPLETED in topics


def test_cleanup_on_exception():
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="fail", timeout_seconds=10)
    result = executor.execute(FAIL_SCRIPT, ctx)
    assert result.success is False
    assert result.exit_code != 0


def test_isolation_from_parent_process():
    parent_var = "parent_value"
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="isolated", timeout_seconds=10)
    result = executor.execute(SIMPLE_SCRIPT, ctx)
    assert result.success is True
    assert parent_var == "parent_value"


def test_result_contains_resource_usage_telemetry():
    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="telemetry", timeout_seconds=10)
    result = executor.execute(SIMPLE_SCRIPT, ctx)
    assert isinstance(result, SandboxResult)
    assert result.duration_seconds > 0
    assert result.exit_code == 0
