from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class NodeStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    TIMEOUT = "TIMEOUT"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


@dataclass
class NodeHealth:
    node_id: str
    status: NodeStatus
    last_heartbeat: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    lease_count: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None


@dataclass
class ConnectionStatus:
    connected: bool
    pool_size: int = 0
    active_connections: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None
