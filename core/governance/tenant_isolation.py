"""EMO AI Governance Layer — Tenant Isolation.

LAW 26: Every IPC call and EventBus message MUST carry a tenant_id.
LAW 27: No event or state may cross tenant boundaries.
"""

from __future__ import annotations

import enum
import threading
from typing import Any, Callable, Dict, List, Optional


class IsolationError(PermissionError):
    pass


class Namespace(enum.Enum):
    IPC_COMMAND = "ipc:command"
    EVENT_BUS = "eventbus:topic"
    STATE_STORE = "state:key"
    AUDIT_LOG = "audit:record"


_namespace_registry: Dict[str, str] = {}  # full_path -> tenant_id
_registry_lock = threading.Lock()


def register_path(namespace: Namespace, path: str, tenant_id: str) -> None:
    full = f"{namespace.value}:{path}"
    with _registry_lock:
        existing = _namespace_registry.get(full)
        if existing and existing != tenant_id:
            raise IsolationError(
                f"Path {full} already registered to tenant {existing}"
            )
        _namespace_registry[full] = tenant_id


def unregister_path(namespace: Namespace, path: str) -> bool:
    full = f"{namespace.value}:{path}"
    with _registry_lock:
        return _namespace_registry.pop(full, None) is not None


def resolve_tenant(namespace: Namespace, path: str) -> Optional[str]:
    full = f"{namespace.value}:{path}"
    return _namespace_registry.get(full)


def check_isolation(namespace: Namespace, path: str, tenant_id: str) -> bool:
    registered = resolve_tenant(namespace, path)
    if registered is None:
        return True
    return registered == tenant_id


def enforce_isolation(namespace: Namespace, path: str, tenant_id: str) -> None:
    if not check_isolation(namespace, path, tenant_id):
        raise IsolationError(
            f"Tenant {tenant_id} cannot access {namespace.value}:{path} "
            f"(owned by {resolve_tenant(namespace, path)})"
        )


class TenantScopedEventBus:
    def __init__(self, tenant_id: str, inner: Any) -> None:
        self._tenant_id = tenant_id
        self._inner = inner

    def publish(self, topic: str, event: Any) -> None:
        enforce_isolation(Namespace.EVENT_BUS, topic, self._tenant_id)
        self._inner.publish(topic, event)

    def subscribe(self, topic: str, handler: Callable) -> None:
        self._inner.subscribe(topic, handler)

    def get_events(self, topic: str, limit: int = 100) -> List[Any]:
        enforce_isolation(Namespace.EVENT_BUS, topic, self._tenant_id)
        return self._inner.get_events(topic, limit)


class TenantScopedStateStore:
    def __init__(self, tenant_id: str, inner: Dict[str, Any]) -> None:
        self._tenant_id = tenant_id
        self._inner = inner

    def get(self, key: str) -> Optional[Any]:
        enforce_isolation(Namespace.STATE_STORE, key, self._tenant_id)
        return self._inner.get(key)

    def set(self, key: str, value: Any) -> None:
        enforce_isolation(Namespace.STATE_STORE, key, self._tenant_id)
        self._inner[key] = value

    def delete(self, key: str) -> bool:
        enforce_isolation(Namespace.STATE_STORE, key, self._tenant_id)
        return self._inner.pop(key, None) is not None


class TenantRegistry:
    def __init__(self) -> None:
        self._tenants: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def register(self, tenant_id: str, metadata: Optional[dict] = None) -> None:
        with self._lock:
            if tenant_id in self._tenants:
                raise IsolationError(f"Tenant {tenant_id} already registered")
            self._tenants[tenant_id] = metadata or {}

    def unregister(self, tenant_id: str) -> bool:
        with self._lock:
            if tenant_id not in self._tenants:
                return False
            paths = [
                p for p, t in _namespace_registry.items() if t == tenant_id
            ]
            for p in paths:
                _namespace_registry.pop(p, None)
            del self._tenants[tenant_id]
            return True

    def exists(self, tenant_id: str) -> bool:
        return tenant_id in self._tenants

    def list_tenants(self) -> List[str]:
        return list(self._tenants.keys())

    def reset(self) -> None:
        with self._lock:
            self._tenants.clear()
            _namespace_registry.clear()
