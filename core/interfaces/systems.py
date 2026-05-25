from typing import Protocol, TYPE_CHECKING, Dict, Any, List, Optional, Set

if TYPE_CHECKING:
    from ..execution_engine import DependencyGraph, PlanNode

class ICostTracker(Protocol):
    def record(self, cost: Any) -> None:
        ...
    def estimate_cost(self, node: "PlanNode") -> float:
        ...

class IDAGSizeLimiter(Protocol):
    def check(self, dag: "DependencyGraph") -> List[str]:
        ...

class ICheckpointManager(Protocol):
    def save(self, session_id: str, dag: "DependencyGraph", node_id: str, result: Dict[str, Any]) -> None:
        ...
    def restore(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...
