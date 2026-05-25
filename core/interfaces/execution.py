from typing import Protocol, TYPE_CHECKING, Dict, Any, List

if TYPE_CHECKING:
    from ..execution_engine import DependencyGraph, PlanNode

class IDAGOptimizer(Protocol):
    def optimize(self, dag: "DependencyGraph") -> "DependencyGraph":
        ...
