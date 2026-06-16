"""F1 — Runtime API Request/Response Models.

Pure frozen dataclasses for the Unified Runtime API.
No business logic, no execution.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 1, LAW 12, LAW 13
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RuntimeSubmitRequest:
    """Request to submit a DAG for execution."""

    dag: Any
    timeout: float = 300.0
    retries: int = 3
    strategy: str = "balanced"
    trace_id: str = ""


@dataclass(frozen=True)
class RuntimeSubmitResponse:
    """Response after submitting a DAG."""

    execution_id: str
    status: str
    lease_id: str
    trace_id: str = ""


@dataclass(frozen=True)
class RuntimeObserveRequest:
    """Request to observe an execution."""

    execution_id: str
    trace_id: str = ""


@dataclass(frozen=True)
class RuntimeObserveResponse:
    """Response containing current execution state."""

    status: str
    progress: float
    current_node: str
    events: List[Dict[str, Any]] = field(default_factory=list)
    trace_id: str = ""
