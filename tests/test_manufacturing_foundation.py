"""Tests for Manufacturing Foundation.

8 tests covering domain models, policies, and connector read-only interfaces.

Ref: RC17.1.1 — Manufacturing Domain Models & Policies
"""

import pytest

from core.governance.manufacturing_policies import (
    ManufacturingPolicy,
    ManufacturingPolicyType,
    get_default_manufacturing_policies,
)
from core.models.manufacturing import (
    FleetVehicle,
    LineStatus,
    MaintenanceWorkOrder,
    QualityCheck,
    QualityResult,
    ProductionLine,
    RouteStatus,
    SupplyRoute,
    VehicleStatus,
    Warehouse,
    WorkOrderStatus,
)


# ── Model Immutability Tests ────────────────────────────────


def test_production_line_is_frozen():
    """ProductionLine dataclass must be immutable."""
    line = ProductionLine(name="Line-1", status=LineStatus.RUNNING)
    with pytest.raises(AttributeError):
        line.name = "Modified"


def test_warehouse_is_frozen():
    """Warehouse dataclass must be immutable."""
    warehouse = Warehouse(name="WH-1", location="Building A")
    with pytest.raises(AttributeError):
        warehouse.name = "Modified"


def test_fleet_vehicle_is_frozen():
    """FleetVehicle dataclass must be immutable."""
    vehicle = FleetVehicle(type="truck", status=VehicleStatus.ACTIVE)
    with pytest.raises(AttributeError):
        vehicle.type = "Modified"


def test_maintenance_work_order_is_frozen():
    """MaintenanceWorkOrder dataclass must be immutable."""
    order = MaintenanceWorkOrder(asset_id="asset-001", priority="high")
    with pytest.raises(AttributeError):
        order.priority = "Modified"


# ── Policy Tests ────────────────────────────────────────────


def test_line_shutdown_requires_approval():
    """LINE_SHUTDOWN_APPROVAL policy must require approval."""
    policies = get_default_manufacturing_policies()
    shutdown_policies = [
        p for p in policies
        if p.policy_type == ManufacturingPolicyType.LINE_SHUTDOWN_APPROVAL
    ]

    assert len(shutdown_policies) >= 1
    assert all(p.requires_approval for p in shutdown_policies)


def test_osha_safety_policies_exist():
    """OSHA safety policies must be defined."""
    policies = get_default_manufacturing_policies()
    osha_policies = [
        p for p in policies
        if p.policy_type == ManufacturingPolicyType.OSHA_SAFETY
    ]

    assert len(osha_policies) >= 2
    assert all(p.severity in ("high", "critical") for p in osha_policies)


# ── Connector Read-Only Tests ───────────────────────────────


def test_connectors_have_no_write_methods():
    """OPC-UA, MQTT, Modbus connectors must be read-only."""
    import inspect
    from core.interfaces.connectors import (
        IModbusConnector,
        IMQTTConnector,
        IOPCUAConnector,
    )

    # Check OPC-UA
    opcua_methods = [m for m in dir(IOPCUAConnector) if not m.startswith("_")]
    assert "write" not in opcua_methods
    assert "execute" not in opcua_methods

    # Check MQTT
    mqtt_methods = [m for m in dir(IMQTTConnector) if not m.startswith("_")]
    assert "write" not in mqtt_methods
    assert "execute" not in mqtt_methods

    # Check Modbus
    modbus_methods = [m for m in dir(IModbusConnector) if not m.startswith("_")]
    assert "write" not in modbus_methods
    assert "execute" not in modbus_methods


# ── Integration Test ─────────────────────────────────────────


def test_policy_evaluation_blocks_direct_shutdown():
    """Direct line shutdown without approval must be flagged by policy."""
    policies = get_default_manufacturing_policies()

    # Find shutdown policy
    shutdown_policy = next(
        p for p in policies
        if p.policy_type == ManufacturingPolicyType.LINE_SHUTDOWN_APPROVAL
    )

    # Verify it blocks direct action
    assert shutdown_policy.requires_approval is True
    assert shutdown_policy.action_pattern == "line_shutdown"
    assert shutdown_policy.severity == "critical"
