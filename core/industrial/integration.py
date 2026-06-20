"""Industrial Intelligence Fabric — Control Plane Integration.

Bridges Industrial OS with Control Plane for tenant/org validation and resource tracking.

Ref: RC16.9.4 — Industrial ↔ Control Plane Integration
Ref: LAW 9 (Governance Independence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.industrial import AssetType

if TYPE_CHECKING:
    from core.interfaces.control_plane import (
        IOrganizationManager,
        IResourceManager,
        ITenantManager,
    )
    from core.interfaces.industrial import IAssetManager, ITwinManager

from core.interfaces.industrial import IIndustrialIntegration


class IndustrialIntegration(IIndustrialIntegration):
    """Integrates Industrial OS with Control Plane."""

    def __init__(
        self,
        asset_manager: IAssetManager,
        twin_manager: ITwinManager,
        tenant_manager: Optional[ITenantManager] = None,
        org_manager: Optional[IOrganizationManager] = None,
        resource_manager: Optional[IResourceManager] = None,
    ) -> None:
        self._am = asset_manager
        self._tm = twin_manager
        self._tenant_mgr = tenant_manager
        self._org_mgr = org_manager
        self._rm = resource_manager
        self._asset_to_resource: Dict[str, str] = {}  # asset_id → resource_id

    def register_asset(
        self,
        tenant_id: str,
        org_id: Optional[str],
        name: str,
        asset_type: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Register industrial asset with Control Plane validation."""
        # Step 1: Validate tenant exists (if tenant_manager provided)
        if self._tenant_mgr is not None:
            tenant = self._tenant_mgr.get_tenant(tenant_id)
            if tenant is None:
                return {
                    "success": False,
                    "asset_id": None,
                    "resource_id": None,
                    "error": f"Tenant not found: {tenant_id}",
                }

        # Step 2: Validate org exists (if org_manager provided)
        if self._org_mgr is not None and org_id is not None:
            org = self._org_mgr.get_org(org_id)
            if org is None:
                return {
                    "success": False,
                    "asset_id": None,
                    "resource_id": None,
                    "error": f"Organization not found: {org_id}",
                }

        # Step 3: Create asset
        try:
            asset = self._am.create_asset(
                name=name,
                asset_type=asset_type,
                metadata={**metadata, "tenant_id": tenant_id, "org_id": org_id},
            )
        except ValueError as e:
            return {
                "success": False,
                "asset_id": None,
                "resource_id": None,
                "error": str(e),
            }

        # Step 4: Register as resource (if resource_manager provided)
        resource_id = None
        if self._rm is not None:
            try:
                resource = self._rm.create_resource(
                    org_id=org_id or "unknown",
                    tenant_id=tenant_id,
                    name=f"IndustrialAsset:{name}",
                    type="asset",  # Will be ResourceType.ASSET if defined
                    quota={"max_events": 10000},
                )
                resource_id = resource.id
                self._asset_to_resource[asset.id] = resource_id
            except Exception as e:
                # Asset created but resource failed — log but don't fail
                pass

        return {
            "success": True,
            "asset_id": asset.id,
            "resource_id": resource_id,
            "error": None,
        }

    def unregister_asset(self, asset_id: str) -> Dict[str, Any]:
        """Unregister asset from both Industrial and Control Plane."""
        # Step 1: Delete asset (cascade deletes relationships)
        asset_deleted = self._am.delete_asset(asset_id)

        # Step 2: Clear twin state
        self._tm.clear_state(asset_id)

        # Step 3: Decommission resource (if tracked)
        resource_id = self._asset_to_resource.get(asset_id)
        resource_decommissioned = False
        if resource_id and self._rm is not None:
            resource_decommissioned = self._rm.decommission_resource(resource_id)
            del self._asset_to_resource[asset_id]

        return {
            "success": asset_deleted,
            "asset_deleted": asset_deleted,
            "twin_cleared": True,
            "resource_decommissioned": resource_decommissioned,
        }

    def get_asset_with_tenant(self, asset_id: str) -> Dict[str, Any]:
        """Get asset with tenant/org info."""
        asset = self._am.get_asset(asset_id)
        if asset is None:
            return {"exists": False, "asset": None, "tenant": None, "org": None}

        tenant_info = None
        if self._tenant_mgr is not None:
            tenant = self._tenant_mgr.get_tenant(asset.tenant_id)
            if tenant:
                tenant_info = {"id": tenant.id, "name": tenant.name, "status": tenant.status}

        org_info = None
        if self._org_mgr is not None and asset.org_id:
            org = self._org_mgr.get_org(asset.org_id)
            if org:
                org_info = {"id": org.id, "name": org.name, "type": org.type}

        return {
            "exists": True,
            "asset": {
                "id": asset.id,
                "name": asset.name,
                "type": asset.asset_type.value,
                "status": asset.status,
            },
            "tenant": tenant_info,
            "org": org_info,
        }
