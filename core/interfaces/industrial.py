"""Industrial Intelligence Fabric — Protocols.

Defines contracts for industrial asset management and digital twin operations.

Ref: RC16.9 — Industrial Intelligence Fabric
Ref: LAW 2 (Interface Authority)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

if TYPE_CHECKING:
    from core.models.industrial import (
        AssetHierarchy,
        AssetRelationship,
        IndustrialAsset,
        OperationalEvent,
        TwinState,
    )


class IAssetManager(Protocol):
    """Manages industrial assets and their relationships."""

    def create_asset(
        self, name: str, asset_type: str, metadata: Dict[str, Any]
    ) -> IndustrialAsset:
        """Create a new industrial asset."""
        ...

    def get_asset(self, asset_id: str) -> Optional[IndustrialAsset]:
        """Get asset by ID."""
        ...

    def list_assets(self, asset_type: Optional[str] = None) -> List[IndustrialAsset]:
        """List all assets, optionally filtered by type."""
        ...

    def add_relationship(
        self, source_id: str, target_id: str, rel_type: str
    ) -> AssetRelationship:
        """Add a relationship between two assets."""
        ...

    def get_hierarchy(self, root_id: str) -> AssetHierarchy:
        """Get the hierarchical structure of assets."""
        ...


class ITwinManager(Protocol):
    """Manages digital twin state and simulation."""

    def get_twin_state(self, asset_id: str) -> TwinState:
        """Get current twin state for an asset."""
        ...

    def update_twin_state(
        self, asset_id: str, new_state: Dict[str, Any]
    ) -> TwinState:
        """Update twin state for an asset."""
        ...

    def simulate(
        self, asset_id: str, scenario: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Run a simulation scenario on a twin."""
        ...

    def record_event(self, asset_id: str, event: OperationalEvent) -> None:
        """Record an operational event."""
        ...


class IIndustrialIntegration(Protocol):
    """Bridge between Industrial Intelligence Fabric and Control Plane.

    Validates tenant/org existence, tracks resources, enforces policies.

    Ref: RC16.9.4 — Industrial ↔ Control Plane Integration
    Ref: LAW 9 (Governance Independence)
    """

    def register_asset(
        self,
        tenant_id: str,
        org_id: Optional[str],
        name: str,
        asset_type: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Register industrial asset with Control Plane validation.

        Returns:
            {
                "success": bool,
                "asset_id": Optional[str],
                "resource_id": Optional[str],
                "error": Optional[str]
            }
        """
        ...

    def unregister_asset(self, asset_id: str) -> Dict[str, Any]:
        """Unregister asset from both Industrial and Control Plane."""
        ...

    def get_asset_with_tenant(self, asset_id: str) -> Dict[str, Any]:
        """Get asset with tenant/org info."""
        ...

        ...
