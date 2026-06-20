"""Tests for Manufacturing Agents (RC17.1.2).

5 agents × multiple tests: LineSupervisor, WarehouseOptimizer, FleetDispatcher,
MaintenanceScheduler, QualityInspector.
"""

import pytest

from core.agents.manufacturing.fleet_dispatcher import FleetDispatcherAgent
from core.agents.manufacturing.line_supervisor import LineSupervisorAgent
from core.agents.manufacturing.maintenance_scheduler import MaintenanceSchedulerAgent
from core.agents.manufacturing.quality_inspector import QualityInspectorAgent
from core.agents.manufacturing.warehouse_optimizer import WarehouseOptimizerAgent
from core.agents.approval_integration import AgentApprovalGate
from core.models.agent import AgentIdentity
from core.models.manufacturing import (
    FleetVehicle,
    LineStatus,
    ProductionLine,
    QualityCheck,
    QualityResult,
    SupplyRoute,
    VehicleStatus,
    Warehouse,
    WorkOrderStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_identity(name: str, agent_type: str) -> AgentIdentity:
    return AgentIdentity(
        id=f"agent-{name}",
        tenant_id="tenant-1",
        org_id=None,
        name=name,
        agent_type=agent_type,
    )


@pytest.fixture
def approval_gate() -> AgentApprovalGate:
    return AgentApprovalGate()


@pytest.fixture
def line_supervisor(approval_gate) -> LineSupervisorAgent:
    identity = _make_identity("line-sup-1", "manufacturing.line_supervisor")
    agent = LineSupervisorAgent(identity=identity, approval_gate=approval_gate)
    agent.activate()
    return agent


@pytest.fixture
def warehouse_optimizer(approval_gate) -> WarehouseOptimizerAgent:
    identity = _make_identity("wh-opt-1", "manufacturing.warehouse_optimizer")
    agent = WarehouseOptimizerAgent(identity=identity, approval_gate=approval_gate)
    agent.activate()
    return agent


@pytest.fixture
def fleet_dispatcher(approval_gate) -> FleetDispatcherAgent:
    identity = _make_identity("fleet-disp-1", "manufacturing.fleet_dispatcher")
    agent = FleetDispatcherAgent(identity=identity, approval_gate=approval_gate)
    agent.activate()
    return agent


@pytest.fixture
def maintenance_scheduler(approval_gate) -> MaintenanceSchedulerAgent:
    identity = _make_identity("maint-sched-1", "manufacturing.maintenance_scheduler")
    agent = MaintenanceSchedulerAgent(identity=identity, approval_gate=approval_gate)
    agent.activate()
    return agent


@pytest.fixture
def quality_inspector(approval_gate) -> QualityInspectorAgent:
    identity = _make_identity("qi-insp-1", "manufacturing.quality_inspector")
    agent = QualityInspectorAgent(identity=identity, approval_gate=approval_gate)
    agent.activate()
    return agent


# ── LineSupervisorAgent Tests ─────────────────────────────────────────────────


class TestLineSupervisorAgent:

    def test_lifecycle_transitions(self, line_supervisor):
        line_supervisor.suspend("maintenance")
        assert line_supervisor.audit.action_log[-1]["action"] == "agent.suspend"
        line_supervisor.activate()
        line_supervisor.terminate("done")
        assert line_supervisor.audit.action_log[-1]["action"] == "agent.terminate"

    def test_read_line_status_no_approval(self, line_supervisor):
        result = line_supervisor.execute("read_line_status", {"line_id": "l1"})
        assert result["status"] == "completed"

    def test_shutdown_line_requires_approval(self, line_supervisor):
        line = ProductionLine(id="l1", name="Line-1", status=LineStatus.RUNNING)
        line_supervisor.register_line(line)
        result = line_supervisor.shutdown_line("l1")
        assert result["status"] == "denied"

    def test_emergency_stop_requires_approval(self, line_supervisor):
        result = line_supervisor.execute("emergency_stop", {"line_id": "l1"})
        assert result["status"] == "denied"

    def test_can_perform(self, line_supervisor):
        allowed = line_supervisor.can_perform("read_line_status", {})
        assert allowed["allowed"] is True
        assert allowed["requires_approval"] is False
        denied = line_supervisor.can_perform("line_shutdown", {})
        assert denied["requires_approval"] is True

    def test_audit_trail_recorded(self, line_supervisor):
        line_supervisor.execute("read_line_status", {"line_id": "l1"})
        actions = [a["action"] for a in line_supervisor.audit.action_log]
        assert "agent.read_line_status.executed" in actions


# ── WarehouseOptimizerAgent Tests ─────────────────────────────────────────────


class TestWarehouseOptimizerAgent:

    def test_lifecycle_transitions(self, warehouse_optimizer):
        warehouse_optimizer.suspend("low season")
        assert warehouse_optimizer.audit.action_log[-1]["action"] == "agent.suspend"
        warehouse_optimizer.activate()
        warehouse_optimizer.terminate("retired")
        assert warehouse_optimizer.audit.action_log[-1]["action"] == "agent.terminate"

    def test_read_inventory_no_approval(self, warehouse_optimizer):
        result = warehouse_optimizer.execute("read_inventory", {"warehouse_id": "w1"})
        assert result["status"] == "completed"

    def test_reorder_stock_requires_approval(self, warehouse_optimizer):
        wh = Warehouse(id="w1", name="WH-1", location="Building A")
        warehouse_optimizer.register_warehouse(wh)
        result = warehouse_optimizer.reorder_stock("w1")
        assert result["status"] == "denied"

    def test_can_perform(self, warehouse_optimizer):
        allowed = warehouse_optimizer.can_perform("read_inventory", {})
        assert allowed["allowed"] is True
        approval_needed = warehouse_optimizer.can_perform("reorder_stock", {})
        assert approval_needed["requires_approval"] is True

    def test_warehouse_registered(self, warehouse_optimizer):
        wh = Warehouse(id="w2", name="WH-2", location="Building B")
        warehouse_optimizer.register_warehouse(wh)
        level = warehouse_optimizer.get_inventory_level("w2")
        assert level == 0.0


# ── FleetDispatcherAgent Tests ────────────────────────────────────────────────


class TestFleetDispatcherAgent:

    def test_lifecycle_transitions(self, fleet_dispatcher):
        fleet_dispatcher.suspend("fleet grounded")
        assert fleet_dispatcher.audit.action_log[-1]["action"] == "agent.suspend"
        fleet_dispatcher.activate()
        fleet_dispatcher.terminate("fleet retired")
        assert fleet_dispatcher.audit.action_log[-1]["action"] == "agent.terminate"

    def test_read_fleet_status_no_approval(self, fleet_dispatcher):
        result = fleet_dispatcher.execute("read_fleet_status", {"vehicle_id": "v1"})
        assert result["status"] == "completed"

    def test_dispatch_vehicle_requires_approval(self, fleet_dispatcher):
        v = FleetVehicle(id="v1", type="truck", status=VehicleStatus.ACTIVE)
        fleet_dispatcher.register_vehicle(v)
        result = fleet_dispatcher.dispatch_vehicle("v1")
        assert result["status"] == "denied"

    def test_override_route_requires_approval(self, fleet_dispatcher):
        r = SupplyRoute(id="r1", origin="A", destination="B")
        fleet_dispatcher.register_route(r)
        result = fleet_dispatcher.override_route("r1")
        assert result["status"] == "denied"

    def test_can_perform(self, fleet_dispatcher):
        allowed = fleet_dispatcher.can_perform("read_fleet_status", {})
        assert allowed["allowed"] is True
        approval_needed = fleet_dispatcher.can_perform("dispatch_vehicle", {})
        assert approval_needed["requires_approval"] is True

    def test_vehicle_registered(self, fleet_dispatcher):
        v = FleetVehicle(id="v2", type="van")
        fleet_dispatcher.register_vehicle(v)
        status = fleet_dispatcher.get_vehicle_status("v2")
        assert status == VehicleStatus.ACTIVE


# ── MaintenanceSchedulerAgent Tests ───────────────────────────────────────────


class TestMaintenanceSchedulerAgent:

    def test_lifecycle_transitions(self, maintenance_scheduler):
        maintenance_scheduler.suspend("off-season")
        assert maintenance_scheduler.audit.action_log[-1]["action"] == "agent.suspend"
        maintenance_scheduler.activate()
        maintenance_scheduler.terminate("done")
        assert maintenance_scheduler.audit.action_log[-1]["action"] == "agent.terminate"

    def test_read_work_orders_no_approval(self, maintenance_scheduler):
        result = maintenance_scheduler.execute("read_work_orders", {})
        assert result["status"] == "completed"

    def test_approve_work_order_requires_approval(self, maintenance_scheduler):
        order = maintenance_scheduler.create_work_order("asset-1", "high")
        result = maintenance_scheduler.approve_work_order(order.id)
        assert result["status"] == "denied"

    def test_create_work_order_no_approval(self, maintenance_scheduler):
        order = maintenance_scheduler.create_work_order("asset-2", "low")
        assert order.priority == "low"
        assert order.status == WorkOrderStatus.PENDING

    def test_get_pending_orders(self, maintenance_scheduler):
        maintenance_scheduler.create_work_order("asset-3", "medium")
        maintenance_scheduler.create_work_order("asset-4", "high")
        pending = maintenance_scheduler.get_pending_orders()
        assert len(pending) == 2
        assert all(o.status == WorkOrderStatus.PENDING for o in pending)

    def test_can_perform(self, maintenance_scheduler):
        allowed = maintenance_scheduler.can_perform("read_work_orders", {})
        assert allowed["allowed"] is True
        approval_needed = maintenance_scheduler.can_perform("approve_work_order", {})
        assert approval_needed["requires_approval"] is True


# ── QualityInspectorAgent Tests ───────────────────────────────────────────────


class TestQualityInspectorAgent:

    def test_lifecycle_transitions(self, quality_inspector):
        quality_inspector.suspend("lab closed")
        assert quality_inspector.audit.action_log[-1]["action"] == "agent.suspend"
        quality_inspector.activate()
        quality_inspector.terminate("retired")
        assert quality_inspector.audit.action_log[-1]["action"] == "agent.terminate"

    def test_read_quality_checks_no_approval(self, quality_inspector):
        result = quality_inspector.execute("read_quality_checks", {})
        assert result["status"] == "completed"

    def test_quarantine_batch_requires_approval(self, quality_inspector):
        check = QualityCheck(
            id="qc-1",
            production_line_id="line-1",
            result=QualityResult.FAIL,
            defects_found=5,
        )
        quality_inspector.record_quality_check(check)
        result = quality_inspector.quarantine_batch("qc-1")
        assert result["status"] == "denied"

    def test_record_quality_check(self, quality_inspector):
        check = QualityCheck(
            id="qc-2",
            production_line_id="line-2",
            result=QualityResult.PASS,
            defects_found=0,
        )
        quality_inspector.record_quality_check(check)
        failed = quality_inspector.get_failed_checks()
        assert len(failed) == 0

    def test_get_failed_checks(self, quality_inspector):
        pass_check = QualityCheck(id="qc-p", result=QualityResult.PASS)
        fail_check = QualityCheck(id="qc-f", result=QualityResult.FAIL, defects_found=3)
        quality_inspector.record_quality_check(pass_check)
        quality_inspector.record_quality_check(fail_check)
        failed = quality_inspector.get_failed_checks()
        assert len(failed) == 1
        assert failed[0].id == "qc-f"

    def test_can_perform(self, quality_inspector):
        allowed = quality_inspector.can_perform("read_quality_checks", {})
        assert allowed["allowed"] is True
        approval_needed = quality_inspector.can_perform("quarantine_batch", {})
        assert approval_needed["requires_approval"] is True
