from typing import Any, Callable, Dict, List, Optional, Protocol

from ..models.dag import DependencyGraph, PlanNode, ToolSpec


class IExecutionEngine(Protocol):

    def execute(
        self,
        dag: DependencyGraph,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
        tool_runner: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        """Execute a DAG and return execution results."""

    def plan(self, nodes: List[PlanNode]) -> DependencyGraph:
        """Convert plan nodes into execution graph."""

    def cancel(self, execution_id: str) -> bool:
        """Cancel running execution."""

    def status(self, execution_id: str) -> str:
        """Get execution status."""

    def register_tool(self, spec: ToolSpec) -> None:
        """Register a tool specification for use during execution."""
