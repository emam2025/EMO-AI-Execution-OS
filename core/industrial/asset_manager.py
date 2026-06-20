"""Industrial Intelligence Fabric — Asset Manager.

Manages industrial assets and their relationships.

Ref: RC16.9.2 — AssetManager Implementation
Ref: LAW 2 (Interface Authority)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid

from core.models.industrial import (
    AssetHierarchy,
    AssetRelationship,
    AssetType,
    IndustrialAsset,
    RelationshipType,
)

if TYPE_CHECKING:
    from core.interfaces.control_plane import IOrganizationManager, ITenantManager

from core.interfaces.industrial import IAssetManager


class AssetManager(IAssetManager):
    """Manages industrial assets and their relationships."""

    def __init__(
        self,
        tenant_manager: Optional[ITenantManager] = None,
        org_manager: Optional[IOrganizationManager] = None,
    ) -> None:
        self._assets: Dict[str, IndustrialAsset] = {}
        self._relationships: Dict[str, AssetRelationship] = {}
        self._tm = tenant_manager
        self._om = org_manager

    def create_asset(
        self, name: str, asset_type: str, metadata: Dict[str, Any]
    ) -> IndustrialAsset:
        """Create a new industrial asset."""
        # Validate asset_type
        try:
            atype = AssetType(asset_type)
        except ValueError:
            raise ValueError(
                f"Invalid asset_type: {asset_type}. "
                f"Must be one of {[e.value for e in AssetType]}"
            )

        asset = IndustrialAsset(
            id=str(uuid.uuid4()),
            name=name,
            asset_type=atype,
            tenant_id=metadata.get("tenant_id", "unknown"),
            org_id=metadata.get("org_id"),
            metadata={
                k: v for k, v in metadata.items() if k not in ["tenant_id", "org_id"]
            },
        )
        self._assets[asset.id] = asset
        return asset

    def get_asset(self, asset_id: str) -> Optional[IndustrialAsset]:
        """Get asset by ID."""
        return self._assets.get(asset_id)

    def list_assets(self, asset_type: Optional[str] = None) -> List[IndustrialAsset]:
        """List all assets, optionally filtered by type."""
        assets = list(self._assets.values())
        if asset_type is not None:
            try:
                atype = AssetType(asset_type)
                assets = [a for a in assets if a.asset_type == atype]
            except ValueError:
                return []
        return assets

    def add_relationship(
        self, source_id: str, target_id: str, rel_type: str
    ) -> AssetRelationship:
        """Add a relationship between two assets."""
        # Validate assets exist
        if source_id not in self._assets:
            raise ValueError(f"Source asset not found: {source_id}")
        if target_id not in self._assets:
            raise ValueError(f"Target asset not found: {target_id}")

        # Validate relationship type
        try:
            rtype = RelationshipType(rel_type)
        except ValueError:
            raise ValueError(
                f"Invalid relationship type: {rel_type}. "
                f"Must be one of {[e.value for e in RelationshipType]}"
            )

        rel = AssetRelationship(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            relationship_type=rtype,
        )
        self._relationships[rel.id] = rel
        return rel

    def get_hierarchy(self, root_id: str) -> AssetHierarchy:
        """Get the hierarchical structure of assets."""
        if root_id not in self._assets:
            raise ValueError(f"Root asset not found: {root_id}")

        # BFS traversal to build hierarchy
        assets: List[IndustrialAsset] = []
        relationships: List[AssetRelationship] = []
        visited = set()
        queue = [root_id]
        depth = 0

        while queue:
            level_size = len(queue)
            for _ in range(level_size):
                current_id = queue.pop(0)
                if current_id in visited:
                    continue
                visited.add(current_id)

                asset = self._assets.get(current_id)
                if asset:
                    assets.append(asset)

                    # Find children (CONTAINS relationships)
                    for rel in self._relationships.values():
                        if (
                            rel.source_id == current_id
                            and rel.relationship_type == RelationshipType.CONTAINS
                        ):
                            relationships.append(rel)
                            if rel.target_id not in visited:
                                queue.append(rel.target_id)
            depth += 1

        return AssetHierarchy(
            root_id=root_id,
            assets=assets,
            relationships=relationships,
            depth=depth,
        )

    def get_relationships(self, asset_id: str) -> List[AssetRelationship]:
        """Get all relationships for an asset (as source or target)."""
        return [
            rel
            for rel in self._relationships.values()
            if rel.source_id == asset_id or rel.target_id == asset_id
        ]

    def delete_asset(self, asset_id: str) -> bool:
        """Delete an asset and its relationships."""
        if asset_id not in self._assets:
            return False

        # Delete all relationships involving this asset
        rels_to_delete = [
            rel_id
            for rel_id, rel in self._relationships.items()
            if rel.source_id == asset_id or rel.target_id == asset_id
        ]
        for rel_id in rels_to_delete:
            del self._relationships[rel_id]

        del self._assets[asset_id]
        return True
