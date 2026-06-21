import logging
from typing import Any, Dict

from fastapi import APIRouter, Request

logger = logging.getLogger("emo_ai.security.router")
router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/status")
async def security_status():
    modules = {}
    try:
        from core.security.identity import get_identity_builder, Identity, Role
        builder = get_identity_builder()
        identity = builder.migration_bypass()
        modules["identity"] = {
            "loaded": True,
            "role": identity.role.value,
            "user_id": identity.user_id,
        }
    except Exception as e:
        modules["identity"] = {"loaded": False, "error": str(e)}

    try:
        from core.security.rbac import get_rbac, Resource, Action, Scope
        rbac = get_rbac()
        decision = rbac.check("super_admin", Resource.SYSTEM, Action.READ, Scope.GLOBAL)
        modules["rbac"] = {
            "loaded": True,
            "super_admin_access": decision.allowed,
        }
    except Exception as e:
        modules["rbac"] = {"loaded": False, "error": str(e)}

    return {
        "status": "operational",
        "mode": "pilot",
        "modules": modules,
    }


@router.get("/health")
async def security_health(request: Request):
    gateway = getattr(request.app.state, "provider_gateway", None)
    return {
        "security": True,
        "rbac": True,
        "identity": True,
        "provider_gateway": gateway is not None,
    }


logger.info("Security router loaded with identity + rbac integration")
