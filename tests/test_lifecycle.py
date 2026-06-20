"""Tests for Lifecycle Infrastructure.

6 independent tests covering graceful shutdown, health checks, and exception isolation.

Ref: P10.2 — Reliability & Graceful Lifecycle
"""

import asyncio

import pytest

from core.infrastructure.lifecycle import HealthChecker, LifecycleManager
from core.models.lifecycle import ComponentStatus


class MockComponent:
    """Mock component with shutdown methods for testing."""

    def __init__(self, name: str, should_fail: bool = False):
        self.name = name
        self.should_fail = should_fail
        self.shutdown_called = False
        self.call_order = []

    async def unsubscribe_from_events(self):
        if self.should_fail:
            raise RuntimeError(f"{self.name} shutdown failed")
        self.shutdown_called = True
        self.call_order.append(self.name)


@pytest.mark.asyncio
async def test_lifecycle_manager_start_and_shutdown():
    """Start and shutdown should transition status correctly."""
    manager = LifecycleManager()
    comp = MockComponent("comp-1")
    manager.register_component("comp-1", comp)

    await manager.start()
    assert manager.status == ComponentStatus.READY
    assert manager.get_component_status("comp-1") == ComponentStatus.READY

    await manager.shutdown()
    assert manager.status == ComponentStatus.STOPPED
    assert manager.get_component_status("comp-1") == ComponentStatus.STOPPED
    assert comp.shutdown_called is True


@pytest.mark.asyncio
async def test_graceful_shutdown_calls_components_in_reverse_order():
    """Components should be shut down in reverse registration order (LIFO)."""
    manager = LifecycleManager()
    shutdown_order = []

    class OrderTracker:
        async def unsubscribe_from_events(self):
            shutdown_order.append("first")

    class OrderTracker2:
        async def unsubscribe_from_events(self):
            shutdown_order.append("second")

    class OrderTracker3:
        async def unsubscribe_from_events(self):
            shutdown_order.append("third")

    manager.register_component("first", OrderTracker())
    manager.register_component("second", OrderTracker2())
    manager.register_component("third", OrderTracker3())

    await manager.start()
    await manager.shutdown()

    # Should be: third, second, first (LIFO)
    assert shutdown_order == ["third", "second", "first"]


@pytest.mark.asyncio
async def test_health_check_ready_when_all_components_ready():
    """Health check should return READY when all components are ready."""
    manager = LifecycleManager()
    manager.register_component("comp-1", MockComponent("comp-1"))
    manager.register_component("comp-2", MockComponent("comp-2"))

    await manager.start()

    checker = HealthChecker(manager)
    result = checker.check_readiness()

    assert result.status == ComponentStatus.READY
    assert result.message == "All components ready"


@pytest.mark.asyncio
async def test_health_check_degrading_when_one_component_fails():
    """Health check should return DEGRADING when a component is not ready."""
    manager = LifecycleManager()
    manager.register_component("comp-1", MockComponent("comp-1"))
    manager.register_component("comp-2", MockComponent("comp-2"))

    await manager.start()

    # Manually degrade one component
    manager._component_status["comp-1"] = ComponentStatus.DEGRADING

    checker = HealthChecker(manager)
    result = checker.check_readiness()

    assert result.status == ComponentStatus.DEGRADING
    assert "comp-1:degrading" in result.message


@pytest.mark.asyncio
async def test_shutdown_handles_component_exception_gracefully():
    """Failure of one component should not prevent others from shutting down."""
    manager = LifecycleManager()
    comp_ok = MockComponent("comp-ok", should_fail=False)
    comp_fail = MockComponent("comp-fail", should_fail=True)
    comp_ok2 = MockComponent("comp-ok2", should_fail=False)

    manager.register_component("comp-ok", comp_ok)
    manager.register_component("comp-fail", comp_fail)
    manager.register_component("comp-ok2", comp_ok2)

    await manager.start()
    await manager.shutdown()

    assert manager.status == ComponentStatus.STOPPED
    assert comp_ok.shutdown_called is True
    assert comp_ok2.shutdown_called is True
    assert len(manager.get_shutdown_errors()) == 1
    assert manager.get_shutdown_errors()[0]["component"] == "comp-fail"


@pytest.mark.asyncio
async def test_cannot_start_already_stopped_manager():
    """Starting a stopped manager should still work (idempotent)."""
    manager = LifecycleManager()
    comp = MockComponent("comp-1")
    manager.register_component("comp-1", comp)

    await manager.start()
    await manager.shutdown()
    assert manager.status == ComponentStatus.STOPPED

    # Start again after stop
    await manager.start()
    assert manager.status == ComponentStatus.READY
