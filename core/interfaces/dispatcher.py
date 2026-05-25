"""D8.1 — IExecutionDispatcher: tool resolution + execution routing.

OWNERSHIP: execution routing
  - tool resolution (local/remote)
  - execution dispatch
  - remote service routing
  - contract validation before dispatch

FORBIDDEN:
  - state mutation
  - retry decisions
  - lease management
  - scheduling
"""

from typing import Any, Callable, Dict, Optional, Protocol

from core.models.dag import PlanNode, ToolSpec


class IExecutionDispatcher(Protocol):
    """Owns execution routing — nothing else."""

    def resolve_tool(self, tool_name: str) -> Optional[ToolSpec]:
        """Resolve a tool name to its specification."""

    def can_dispatch(self, tool_name: str) -> bool:
        """Check if the tool can be dispatched (local or remote)."""

    def dispatch_local(
        self,
        node: PlanNode,
        runner: Callable,
        timeout: float,
    ) -> Dict[str, Any]:
        """Execute a node locally with timeout."""

    def dispatch_remote(
        self,
        node: PlanNode,
        service_registry: Any,
    ) -> Dict[str, Any]:
        """Route execution to a remote service."""

    def validate_contract(
        self,
        spec: ToolSpec,
        inputs: Dict[str, Any],
    ) -> list[str]:
        """Validate inputs against tool contract. Return violations."""

    def validate_output(
        self,
        spec: ToolSpec,
        result: Dict[str, Any],
    ) -> list[str]:
        """Validate outputs against tool contract. Return violations."""
