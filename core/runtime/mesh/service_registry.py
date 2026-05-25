"""GAP 1 — ServiceRegistry: dynamic service discovery and health tracking.

Services register themselves with capabilities and health status.
Other services discover them through the registry.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.security.capabilities import TrustLevel

logger = logging.getLogger("emo_ai.mesh.registry")


class ServiceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"


@dataclass
class ServiceInstance:
    """A single instance of a registered service."""
    service_name: str
    instance_id: str
    host: str = "localhost"
    port: int = 0
    version: str = "1.0.0"
    status: ServiceStatus = ServiceStatus.UP
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    ttl: float = 30.0
    trust_level: TrustLevel = TrustLevel.TRUSTED


class ServiceRegistry:
    """Dynamic service registry with health tracking.

    Thread-safe. Services register, heartbeat, and deregister.
    Other services query by name, capability, or health status.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._services: Dict[str, Dict[str, ServiceInstance]] = {}
        self._instance_counter: int = 0

    def register(
        self,
        service_name: str,
        host: str = "localhost",
        port: int = 0,
        version: str = "1.0.0",
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ttl: float = 30.0,
    ) -> str:
        """Register a service instance. Returns instance_id."""
        with self._lock:
            self._instance_counter += 1
            instance_id = f"{service_name}-{self._instance_counter}"
            now = time.time()
            instance = ServiceInstance(
                service_name=service_name,
                instance_id=instance_id,
                host=host,
                port=port,
                version=version,
                capabilities=capabilities or [],
                metadata=metadata or {},
                registered_at=now,
                last_heartbeat=now,
                ttl=ttl,
            )
            if service_name not in self._services:
                self._services[service_name] = {}
            self._services[service_name][instance_id] = instance
            logger.info("Registered service %s / %s", service_name, instance_id)
            return instance_id

    def deregister(self, service_name: str, instance_id: str) -> bool:
        """Remove a service instance."""
        with self._lock:
            svc_map = self._services.get(service_name)
            if svc_map and instance_id in svc_map:
                del svc_map[instance_id]
                if not svc_map:
                    del self._services[service_name]
                logger.info("Deregistered %s / %s", service_name, instance_id)
                return True
            return False

    def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Record a heartbeat. Returns False if instance not found."""
        with self._lock:
            svc_map = self._services.get(service_name)
            if svc_map and instance_id in svc_map:
                svc_map[instance_id].last_heartbeat = time.time()
                svc_map[instance_id].status = ServiceStatus.UP
                return True
            return False

    def discover(
        self,
        service_name: str,
        min_healthy: bool = True,
    ) -> List[ServiceInstance]:
        """Discover healthy instances of a service."""
        with self._lock:
            svc_map = self._services.get(service_name, {})
            results = []
            now = time.time()
            for inst in svc_map.values():
                if min_healthy:
                    elapsed = now - inst.last_heartbeat
                    if elapsed > inst.ttl:
                        inst.status = ServiceStatus.DOWN
                if inst.status == ServiceStatus.UP:
                    results.append(inst)
            return results

    def discover_by_capability(self, capability: str) -> List[ServiceInstance]:
        """Discover all services with a specific capability."""
        with self._lock:
            results = []
            now = time.time()
            for svc_map in self._services.values():
                for inst in svc_map.values():
                    if capability in inst.capabilities:
                        elapsed = now - inst.last_heartbeat
                        if elapsed <= inst.ttl:
                            results.append(inst)
            return results

    def all_services(self) -> Dict[str, List[ServiceInstance]]:
        """Return all registered services grouped by name."""
        with self._lock:
            return {
                name: list(instances.values())
                for name, instances in self._services.items()
            }

    def get_instance(
        self, service_name: str, instance_id: str,
    ) -> Optional[ServiceInstance]:
        with self._lock:
            svc_map = self._services.get(service_name, {})
            return svc_map.get(instance_id)

    def prune_expired(self) -> int:
        """Remove all expired instances. Returns count removed."""
        with self._lock:
            now = time.time()
            removed = 0
            expired_services = []
            for svc_name, svc_map in self._services.items():
                expired = [
                    iid for iid, inst in svc_map.items()
                    if now - inst.last_heartbeat > inst.ttl
                ]
                for iid in expired:
                    del svc_map[iid]
                    removed += 1
                if not svc_map:
                    expired_services.append(svc_name)
            for svc in expired_services:
                del self._services[svc]
            return removed
