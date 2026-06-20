"""Tests for Industrial Intelligence Fabric Domain Models.

Ref: RC16.9 — Industrial Intelligence Fabric
"""

import pytest

from core.models.industrial import (
    AssetType,
    RelationshipType,
    EventSeverity,
    IndustrialAsset,
    AssetRelationship,
    AssetHierarchy,
    OperationalEvent,
    TwinState,
)


class TestIndustrialAsset:
    """Test IndustrialAsset dataclass."""

    def test_create_asset(self):
        asset = IndustrialAsset(
            id="machine-001",
            name="CNC Machine A",
            asset_type=AssetType.MACHINE,
            tenant_id="tenant-123",
            metadata={"location": "Plant A", "capacity": 100},
        )
        assert asset.id == "machine-001"
        assert asset.name == "CNC Machine A"
        assert asset.asset_type == AssetType.MACHINE
        assert asset.status == "active"

    def test_asset_with_org(self):
        asset = IndustrialAsset(
            id="sensor-001",
            name="Temperature Sensor",
            asset_type=AssetType.SENSOR,
            tenant_id="tenant-123",
            org_id="org-456",
        )
        assert asset.org_id == "org-456"


class TestAssetRelationship:
    """Test AssetRelationship dataclass."""

    def test_create_relationship(self):
        rel = AssetRelationship(
            id="rel-001",
            source_id="plant-001",
            target_id="line-001",
            relationship_type=RelationshipType.CONTAINS,
        )
        assert rel.source_id == "plant-001"
        assert rel.target_id == "line-001"
        assert rel.relationship_type == RelationshipType.CONTAINS


class TestAssetHierarchy:
    """Test AssetHierarchy dataclass."""

    def test_create_hierarchy(self):
        plant = IndustrialAsset("plant-001", "Plant A", AssetType.PLANT, "t1")
        line = IndustrialAsset("line-001", "Line 1", AssetType.LINE, "t1")

        rel = AssetRelationship(
            "rel-001", "plant-001", "line-001", RelationshipType.CONTAINS
        )

        hierarchy = AssetHierarchy(
            root_id="plant-001",
            assets=[plant, line],
            relationships=[rel],
            depth=2,
        )

        assert hierarchy.root_id == "plant-001"
        assert len(hierarchy.assets) == 2
        assert len(hierarchy.relationships) == 1
        assert hierarchy.depth == 2


class TestOperationalEvent:
    """Test OperationalEvent dataclass."""

    def test_create_event(self):
        event = OperationalEvent(
            id="event-001",
            asset_id="machine-001",
            event_type="temperature_alert",
            severity=EventSeverity.WARNING,
            data={"temperature": 85.5, "threshold": 80.0},
        )
        assert event.asset_id == "machine-001"
        assert event.severity == EventSeverity.WARNING
        assert event.data["temperature"] == 85.5


class TestTwinState:
    """Test TwinState dataclass."""

    def test_create_twin_state(self):
        state = TwinState(
            asset_id="machine-001",
            state={"temperature": 75.0, "status": "running", "output": 95},
            version=1,
        )
        assert state.asset_id == "machine-001"
        assert state.state["temperature"] == 75.0
        assert state.version == 1

    def test_update_twin_state(self):
        state = TwinState(asset_id="machine-001", state={"temp": 70})
        state.state["temp"] = 75
        state.version += 1

        assert state.state["temp"] == 75
        assert state.version == 2


class TestEnums:
    """Test Enum definitions."""

    def test_asset_types(self):
        assert AssetType.ORGANIZATION.value == "organization"
        assert AssetType.PLANT.value == "plant"
        assert AssetType.MACHINE.value == "machine"
        assert AssetType.SENSOR.value == "sensor"

    def test_relationship_types(self):
        assert RelationshipType.CONTAINS.value == "contains"
        assert RelationshipType.DEPENDS_ON.value == "depends_on"
        assert RelationshipType.CONNECTS_TO.value == "connects_to"

    def test_event_severity(self):
        assert EventSeverity.INFO.value == "info"
        assert EventSeverity.WARNING.value == "warning"
        assert EventSeverity.ERROR.value == "error"
        assert EventSeverity.CRITICAL.value == "critical"
