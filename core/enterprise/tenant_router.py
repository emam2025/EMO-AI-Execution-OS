"""Phase J2/K3 — Tenant Router Implementation.  # LAW-1 LAW-9 LAW-11 LAW-12 LAW-23 RULE-2 RULE-3

Implements ITenantRouter protocol. Routes requests through Tenant Isolation
Boundary with isolation_policy=STRICT enforcement, quota guards, and
enterprise_trace_id propagation.

LAW 9: Governance is policy-driven — isolation decisions use tenant context.
LAW 11: Router state is instance-scoped (tenant registry).
LAW 12: All operations carry enterprise_trace_id for back-traceability.
LAW 23: Each tenant owns its isolation boundary — STRICT blocks cross-access.
RULE 3: G-L1 enforced on every cross-tenant access attempt.

Ref: artifacts/design/j2/protocols/01_enterprise_protocols.py §ITenantRouter
Ref: EXEC-DIRECTIVE-024 §1 (Multi-Layer Tenant Isolation)
"""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

from core.enterprise.isolation_state_machine import IsolationStateMachine, RoutingTransition
from core.enterprise.trace_correlator import EnterpriseTraceCorrelator


MAX_QUOTA_VIOLATIONS_BEFORE_SUSPEND = 3


class TenantRouter:  # LAW-1 LAW-9 LAW-11 LAW-12 LAW-23 RULE-2 RULE-3
    def __init__(
        self,
        trace_correlator: Optional[EnterpriseTraceCorrelator] = None,
        state_machine: Optional[IsolationStateMachine] = None,
        strict_enterprise_mode: bool = False,
        event_bus: Any = None,
    ) -> None:
        self._trace_correlator = trace_correlator or EnterpriseTraceCorrelator()
        self._state_machine = state_machine or IsolationStateMachine()
        self._strict_enterprise_mode = strict_enterprise_mode
        self._event_bus = event_bus
        self._tenants: Dict[str, Dict[str, Any]] = {}
        self._quotas: Dict[str, Dict[str, Decimal]] = {}
        self._violations: Dict[str, int] = {}
        self._leakage_attempts: List[Dict[str, Any]] = []

    def register_tenant(self, tenant_id: str, isolation_policy: str = "strict",
                        quotas: Optional[Dict[str, Decimal]] = None) -> None:
        self._tenants[tenant_id] = {
            "tenant_id": tenant_id,
            "isolation_policy": isolation_policy,
            "active": True,
            "quota_violations": 0,
        }
        self._quotas[tenant_id] = {k: v for k, v in (quotas or {}).items()}

    def _publish_event(self, action: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            self._event_bus.publish(
                "enterprise.routing",
                ExecutionEvent(
                    event_id=f"entr_{int(time.time() * 1000000)}",
                    event_type="STATE_TRANSITION",
                    timestamp=time.time(),
                    source="TenantRouter",
                    payload={"action": action, **payload},
                ),
            )
        except Exception:
            pass

    async def route_request(self, tenant_id: str, request: Dict[str, Any],
                            enterprise_trace_id: str) -> Dict[str, Any]:
        tenant = self._tenants.get(tenant_id)
        if not tenant:
            return {"routed": False, "target_layer": "", "isolation_mode": "",
                    "quota_remaining": {}, "trace_id": enterprise_trace_id, "blocked_by": ["unknown_tenant"]}

        if not tenant.get("active", False):
            return {"routed": False, "target_layer": "", "isolation_mode": "",
                    "quota_remaining": {}, "trace_id": enterprise_trace_id, "blocked_by": ["tenant_inactive"]}

        target_tenant_id = request.get("target_tenant", tenant_id)
        target_tenant = self._tenants.get(target_tenant_id, {})
        target_isolation = target_tenant.get("isolation_policy", "strict")

        if target_isolation == "strict" and tenant_id != target_tenant_id:
            self._publish_event("cross_tenant_access_blocked", {
                "tenant_id": tenant_id, "target_tenant": target_tenant_id,
                "enterprise_trace_id": enterprise_trace_id,
            })
            return {"routed": False, "target_layer": "", "isolation_mode": target_isolation,
                    "quota_remaining": {}, "trace_id": enterprise_trace_id, "blocked_by": ["cross_tenant_blocked"]}

        self._state_machine.reset()
        self._state_machine.transition(RoutingTransition.T1, enterprise_trace_id=enterprise_trace_id)
        self._state_machine.transition(RoutingTransition.T2, enterprise_trace_id=enterprise_trace_id)

        validate_inputs = {
            "requesting_tenant": tenant_id, "target_tenant": target_tenant_id,
            "shared_resource_flag": request.get("shared_resource_flag", False),
            "scope_verified": request.get("scope_verified", False),
            "target_isolation_policy": target_isolation,
        }
        t3_result = self._state_machine.transition(
            RoutingTransition.T3, validate_inputs, enterprise_trace_id,
        )

        if t3_result.get("blocked_by"):
            self._state_machine.transition(RoutingTransition.T4, enterprise_trace_id=enterprise_trace_id)
            self._publish_event("TenantRouteBlocked", {
                "tenant_id": tenant_id, "blocked_by": t3_result["blocked_by"],
                "enterprise_trace_id": enterprise_trace_id,
            })
            return {"routed": False, "target_layer": "", "isolation_mode": target_isolation,
                    "quota_remaining": {}, "trace_id": enterprise_trace_id,
                    "blocked_by": t3_result.get("blocked_by", [])}

        quota_remaining = self._get_quota_status(tenant_id)
        target_layer = "f1_unified_api"
        self._publish_event("TenantRequestRouted", {
            "tenant_id": tenant_id, "target_layer": target_layer,
            "isolation_mode": target_isolation, "enterprise_trace_id": enterprise_trace_id,
        })
        self._trace_correlator.propagate_to_router(enterprise_trace_id, tenant_id)

        return {"routed": True, "target_layer": target_layer, "isolation_mode": target_isolation,
                "quota_remaining": {k: float(v) for k, v in quota_remaining.items()},
                "trace_id": enterprise_trace_id, "blocked_by": []}

    async def validate_tenant_scope(self, tenant_id: str, target_tenant_id: str,
                                     shared_resource_flag: bool, scope_verified: bool,
                                     enterprise_trace_id: str) -> Dict[str, Any]:
        tenant = self._tenants.get(target_tenant_id, {})
        policy = tenant.get("isolation_policy", "strict")
        allowed = (tenant_id == target_tenant_id) or (shared_resource_flag and scope_verified and policy != "strict")
        if not allowed and tenant_id != target_tenant_id:
            self._leakage_attempts.append({
                "tenant_id": tenant_id, "target": target_tenant_id,
                "timestamp_ns": time.time_ns(), "enterprise_trace_id": enterprise_trace_id,
            })
        return {"allowed": allowed, "isolation_mode": policy,
                "reason": f"cross_tenant_allowed={allowed}", "trace_id": enterprise_trace_id}

    async def enforce_quota(self, tenant_id: str, resource_type: str,
                             requested_units: Decimal, enterprise_trace_id: str) -> Dict[str, Any]:
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = {}
        available = self._quotas[tenant_id].get(resource_type, Decimal("0"))
        exceeded = requested_units > available
        if not exceeded:
            self._quotas[tenant_id][resource_type] = available - requested_units
        else:
            v = self._violations.get(tenant_id, 0) + 1
            self._violations[tenant_id] = v
            if v >= MAX_QUOTA_VIOLATIONS_BEFORE_SUSPEND and tenant_id in self._tenants:
                self._tenants[tenant_id]["active"] = False
        return {"allowed": not exceeded, "quota_before": float(available),
                "quota_after": float(available - requested_units if not exceeded else available),
                "exceeded": exceeded, "trace_id": enterprise_trace_id}

    async def publish_routing_event(self, tenant_id: str, action: str,
                                     payload: Dict[str, Any], enterprise_trace_id: str) -> None:
        self._publish_event(action, {"tenant_id": tenant_id, "enterprise_trace_id": enterprise_trace_id, **payload})

    def get_leakage_attempts(self) -> List[Dict[str, Any]]:
        return list(self._leakage_attempts)

    def get_violations(self) -> Dict[str, int]:
        return dict(self._violations)

    def _get_quota_status(self, tenant_id: str) -> Dict[str, Decimal]:
        return dict(self._quotas.get(tenant_id, {}))
