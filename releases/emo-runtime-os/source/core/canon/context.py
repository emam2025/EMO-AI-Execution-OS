from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ValidationContext:
    graph: Any = None
    file_path: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    node_metadata: Dict[str, Any] = field(default_factory=dict)
    runtime_events: List[Any] = field(default_factory=list)
    coupling_score: Optional[float] = None
    risk_score: Optional[float] = None
    event_bus: Any = None
    drift_detector: Any = None
    runtime_intelligence: Any = None
    execution_core: Any = None
    execution_runtime: Any = None
    scheduler: Any = None
    dispatcher: Any = None
    retry_handler: Any = None
    state_store: Any = None
    lease_manager: Any = None
    failure_propagation_policy: Any = None
    evolution_approval_func: Any = None
    evolution_audit_log: Any = None
    evolution_rollback_func: Any = None
