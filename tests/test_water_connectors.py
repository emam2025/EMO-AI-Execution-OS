"""Tests for RC17.4.2 — Water Connectors (Read-Only V1).

6 tests covering:
- WaterSCADAConnector read_tags success/failure
- WaterModbusConnector read_registers success/failure
- WaterSCADAConnector async read
- WaterModbusConnector async read
- ConnectorError raised on missing tag/register
- Read-only enforcement (no write methods)
"""

from __future__ import annotations

import asyncio
import pytest

from core.connectors.water.water_scada_connector import WaterSCADAConnector
from core.connectors.water.water_modbus_connector import WaterModbusConnector
from core.connectors.manufacturing.connector_error import ConnectorError


# ── Test 1: WaterSCADAConnector read_tags success ─────────────────────────


def test_water_scada_read_tags_success():
    """WaterSCADAConnector reads pre-populated tags successfully."""
    connector = WaterSCADAConnector(endpoint_url="scada://plant-001:502")
    connector.set_tag_value("flow_rate", 120.5)
    connector.set_tag_value("pressure_psi", 45.0)

    results = connector.read_tags(["flow_rate", "pressure_psi"])

    assert results["flow_rate"] == 120.5
    assert results["pressure_psi"] == 45.0
    assert len(results) == 2


# ── Test 2: WaterSCADAConnector read_tags failure ─────────────────────────


def test_water_scada_read_tags_failure():
    """WaterSCADAConnector raises ConnectorError for missing tag."""
    connector = WaterSCADAConnector()
    connector.set_tag_value("flow_rate", 120.5)

    with pytest.raises(ConnectorError) as exc_info:
        connector.read_tags(["flow_rate", "nonexistent_tag"])

    assert exc_info.value.connector_type == "water_scada"
    assert "nonexistent_tag" in str(exc_info.value)


# ── Test 3: WaterModbusConnector read_registers success ───────────────────


def test_water_modbus_read_registers_success():
    """WaterModbusConnector reads pre-populated registers successfully."""
    connector = WaterModbusConnector(host="sensor-hub", port=502)
    connector.set_register_value("ph_001", 7.2)
    connector.set_register_value("turbidity_001", 0.5)

    results = connector.read_registers(["ph_001", "turbidity_001"])

    assert results["ph_001"] == 7.2
    assert results["turbidity_001"] == 0.5
    assert len(results) == 2


# ── Test 4: WaterModbusConnector read_registers failure ───────────────────


def test_water_modbus_read_registers_failure():
    """WaterModbusConnector raises ConnectorError for missing register."""
    connector = WaterModbusConnector()
    connector.set_register_value("ph_001", 7.2)

    with pytest.raises(ConnectorError) as exc_info:
        connector.read_registers(["ph_001", "nonexistent_register"])

    assert exc_info.value.connector_type == "water_modbus"
    assert "nonexistent_register" in str(exc_info.value)


# ── Test 5: WaterSCADAConnector async read ────────────────────────────────


def test_water_scada_read_tags_async():
    """WaterSCADAConnector async read_tags_async works correctly."""
    connector = WaterSCADAConnector()
    connector.set_tag_value("chlorine_ppm", 1.0)

    async def run_async():
        return await connector.read_tags_async(["chlorine_ppm"])

    results = asyncio.run(run_async())
    assert results["chlorine_ppm"] == 1.0


# ── Test 6: Read-only enforcement ─────────────────────────────────────────


def test_water_connectors_readonly_enforcement():
    """Water connectors have no write/control methods."""
    scada = WaterSCADAConnector()
    modbus = WaterModbusConnector()

    # Verify no write methods exist
    assert not hasattr(scada, "write_tag")
    assert not hasattr(scada, "write_control")
    assert not hasattr(scada, "execute_command")
    assert not hasattr(modbus, "write_register")
    assert not hasattr(modbus, "write_coil")
    assert not hasattr(modbus, "execute_command")
