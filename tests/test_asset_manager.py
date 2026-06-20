"""Tests for AssetManager Implementation.

Ref: RC16.9.2 — AssetManager Implementation
"""

import pytest

from core.industrial.asset_manager import AssetManager
from core.models.industrial import AssetType, RelationshipType


@pytest.fixture
def manager():
    return AssetManager()


@pytest.fixture
def sample_assets(manager):
    """Create sample assets for testing."""
    plant = manager.create_asset("Plant A", "plant", {"tenant_id": "t1"})
    line = manager.create_asset("Line 1", "production_line", {"tenant_id": "t1"})
    machine = manager.create_asset("CNC Machine", "machine", {"tenant_id": "t1"})
    sensor = manager.create_asset("Temp Sensor", "sensor", {"tenant_id": "t1"})
    return plant, line, machine, sensor


def test_create_asset(manager):
    """Test asset creation."""
    asset = manager.create_asset(
        "Test Machine", "machine", {"tenant_id": "t1", "location": "Plant A"}
    )
    assert asset.id is not None
    assert asset.name == "Test Machine"
    assert asset.asset_type == AssetType.MACHINE
    assert asset.tenant_id == "t1"
    assert asset.metadata["location"] == "Plant A"


def test_create_asset_invalid_type(manager):
    """Test asset creation with invalid type."""
    with pytest.raises(ValueError, match="Invalid asset_type"):
        manager.create_asset("Test", "invalid_type", {})


def test_get_asset(manager, sample_assets):
    """Test getting asset by ID."""
    plant, line, machine, sensor = sample_assets
    retrieved = manager.get_asset(plant.id)
    assert retrieved is not None
    assert retrieved.name == "Plant A"


def test_get_asset_not_found(manager):
    """Test getting non-existent asset."""
    result = manager.get_asset("non-existent")
    assert result is None


def test_list_assets_all(manager, sample_assets):
    """Test listing all assets."""
    assets = manager.list_assets()
    assert len(assets) == 4


def test_list_assets_by_type(manager, sample_assets):
    """Test listing assets filtered by type."""
    machines = manager.list_assets("machine")
    assert len(machines) == 1
    assert machines[0].name == "CNC Machine"


def test_list_assets_invalid_type(manager, sample_assets):
    """Test listing assets with invalid type."""
    result = manager.list_assets("invalid_type")
    assert len(result) == 0


def test_add_relationship(manager, sample_assets):
    """Test adding relationship between assets."""
    plant, line, machine, sensor = sample_assets
    rel = manager.add_relationship(plant.id, line.id, "contains")
    assert rel.id is not None
    assert rel.source_id == plant.id
    assert rel.target_id == line.id
    assert rel.relationship_type == RelationshipType.CONTAINS


def test_add_relationship_invalid_type(manager, sample_assets):
    """Test adding relationship with invalid type."""
    plant, line, machine, sensor = sample_assets
    with pytest.raises(ValueError, match="Invalid relationship type"):
        manager.add_relationship(plant.id, line.id, "invalid_rel")


def test_add_relationship_nonexistent_asset(manager, sample_assets):
    """Test adding relationship with non-existent asset."""
    plant, line, machine, sensor = sample_assets
    with pytest.raises(ValueError, match="Source asset not found"):
        manager.add_relationship("non-existent", line.id, "contains")


def test_get_hierarchy(manager, sample_assets):
    """Test getting hierarchical structure."""
    plant, line, machine, sensor = sample_assets
    manager.add_relationship(plant.id, line.id, "contains")
    manager.add_relationship(line.id, machine.id, "contains")
    manager.add_relationship(machine.id, sensor.id, "monitors")

    hierarchy = manager.get_hierarchy(plant.id)
    assert hierarchy.root_id == plant.id
    assert len(hierarchy.assets) == 3  # plant, line, machine (sensor connected via monitors, not contains)
    assert len(hierarchy.relationships) == 2  # only CONTAINS relationships
    assert hierarchy.depth == 3  # plant → line → machine


def test_get_relationships(manager, sample_assets):
    """Test getting all relationships for an asset."""
    plant, line, machine, sensor = sample_assets
    manager.add_relationship(plant.id, line.id, "contains")
    manager.add_relationship(line.id, machine.id, "contains")
    manager.add_relationship(machine.id, sensor.id, "monitors")

    rels = manager.get_relationships(line.id)
    assert len(rels) == 2  # one as target (from plant), one as source (to machine)


def test_delete_asset(manager, sample_assets):
    """Test deleting an asset and its relationships."""
    plant, line, machine, sensor = sample_assets
    manager.add_relationship(plant.id, line.id, "contains")
    manager.add_relationship(line.id, machine.id, "contains")

    # Delete line
    result = manager.delete_asset(line.id)
    assert result is True

    # Verify line is deleted
    assert manager.get_asset(line.id) is None

    # Verify relationships involving line are deleted
    plant_rels = manager.get_relationships(plant.id)
    assert len(plant_rels) == 0  # relationship to line should be deleted

    line_rels = manager.get_relationships(line.id)
    assert len(line_rels) == 0


def test_delete_asset_not_found(manager):
    """Test deleting non-existent asset."""
    result = manager.delete_asset("non-existent")
    assert result is False
