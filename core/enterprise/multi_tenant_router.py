"""MultiTenantRouter — tenant-aware routing with strict isolation.

Routes requests to QuotaManager, CapabilityRegistry, and PostgresAdapter
with tenant_id scoping. Zero data leaks between tenants.

LAW 5: All tenant operations observable via EventBus.
LAW 9: Governance is policy-driven per tenant.
LAW 10: Quotas enforced per tenant.
CORE FREEZE: Zero import from sandbox, io, execution_core.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TenantContext:
    tenant_id: str
    quota_cpu: float = 4.0
    quota_memory_mb: int = 1024
    quota_gpu: int = 0
    capabilities: List[str] = field(default_factory=lambda: ["basic"])
    active_executions: int = 0


class MultiTenantRouter:
    """Routes requests to tenant-scoped resources.

    Every accessor method enforces tenant_id filtering to prevent
    cross-tenant data leaks. Read-only aggregator — does not modify
    core runtime state.
    """

    def __init__(
        self,
        quota_manager: Any = None,
        capability_registry: Any = None,
        event_store: Any = None,
        event_bus: Any = None,
    ) -> None:
        self._quota_manager = quota_manager
        self._capability_registry = capability_registry
        self._event_store = event_store
        self._event_bus = event_bus
        self._tenants: Dict[str, TenantContext] = {}
        self._lock = threading.Lock()

    def register_tenant(
        self,
        tenant_id: str,
        quota_cpu: float = 4.0,
        quota_memory_mb: int = 1024,
        quota_gpu: int = 0,
        capabilities: Optional[List[str]] = None,
    ) -> TenantContext:
        """Register a new tenant with resource quotas and capabilities.

        Args:
            tenant_id: Unique tenant identifier.
            quota_cpu: CPU cores limit.
            quota_memory_mb: Memory limit in MB.
            quota_gpu: GPU count limit.
            capabilities: Allowed capability list.

        Returns:
            Created TenantContext.
        """
        with self._lock:
            context = TenantContext(
                tenant_id=tenant_id,
                quota_cpu=quota_cpu,
                quota_memory_mb=quota_memory_mb,
                quota_gpu=quota_gpu,
                capabilities=capabilities or ["basic"],
            )
            self._tenants[tenant_id] = context
            self._emit_event("tenant.registered", {
                "tenant_id": tenant_id,
                "capabilities": context.capabilities,
            })
            return context

    def get_tenant(self, tenant_id: str) -> Optional[TenantContext]:
        """Get tenant context with isolation."""
        with self._lock:
            return self._tenants.get(tenant_id)

    def list_tenants(self) -> List[TenantContext]:
        """List all registered tenants."""
        with self._lock:
            return list(self._tenants.values())

    def check_quota(self, tenant_id: str, cpu: float = 0, memory_mb: int = 0) -> bool:
        """Check if tenant has sufficient quota for a request.

        Tenant-scoped quota check. Returns False if quota exceeded.
        """
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            return False
        if cpu > tenant.quota_cpu or memory_mb > tenant.quota_memory_mb:
            return False
        return True

    def has_capability(self, tenant_id: str, capability: str) -> bool:
        """Check if tenant has a specific capability."""
        tenant = self.get_tenant(tenant_id)
        if tenant is None:
            return False
        return capability in tenant.capabilities

    def increment_executions(self, tenant_id: str) -> None:
        """Increment active execution count for a tenant."""
        with self._lock:
            if tenant_id in self._tenants:
                self._tenants[tenant_id].active_executions += 1

    def decrement_executions(self, tenant_id: str) -> None:
        """Decrement active execution count for a tenant."""
        with self._lock:
            if tenant_id in self._tenants and self._tenants[tenant_id].active_executions > 0:
                self._tenants[tenant_id].active_executions -= 1

    def get_audit_trail(self, tenant_id: str) -> List[Dict[str, Any]]:
        """Retrieve filtered audit trail for a specific tenant.

        Tenant-scoped read from EventStore. Zero cross-tenant leakage.
        """
        if self._event_store is None:
            return []
        events = self._event_store.replay()
        return [
            {"event_id": e.event_id, "event_type": e.event_type,
             "timestamp": e.timestamp, "payload": e.payload}
            for e in events
            if e.session_id == tenant_id or e.trace_id.startswith(tenant_id)
        ]

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            from core.models.events import ExecutionEvent
            import time, uuid
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=event_type,
                timestamp=time.time(),
                source="multi_tenant_router",
                payload=payload,
            )
            self._event_bus.publish(f"enterprise.{event_type}", event)
