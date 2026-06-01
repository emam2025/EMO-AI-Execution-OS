"""D8.1 — IExecutionDispatcher: tool resolution + execution routing.

LAW 24: Dispatcher owns execution routing.
FORBIDDEN: state, lease, retry, scheduling.

Source of Truth: core/runtime/services/tool_dispatcher.py::ExecutionToolDispatcher

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 24
"""

from typing import Any, Dict, Optional, Protocol, runtime_checkable


class DispatchError(Exception):
    """Raised when tool dispatch routing fails."""


class UnknownToolError(Exception):
    """Raised when tool_name is not registered."""


class ContractViolationError(Exception):
    """Raised when tool call violates its contract."""


class RoutingError(Exception):
    """Raised when service domain or method is unknown."""


@runtime_checkable
class IExecutionDispatcher(Protocol):
    """Owns execution routing — nothing else.

    Contract methods:
      register_tool(tool_name, executor, contract_schema?)
      dispatch_tool_call(tool_name, inputs, context?)  → result
      validate_contract(tool_name, inputs)  → bool
      route_service(service_domain, method, payload)  → Any
    """

    def register_tool(
        self,
        tool_name: str,
        executor: Any,
        contract_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool for dispatch."""

    def dispatch_tool_call(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Route a tool call to the appropriate execution path."""

    def validate_contract(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
    ) -> bool:
        """Validate that a tool call conforms to its contract."""

    def route_service(
        self,
        service_domain: str,
        method: str,
        payload: Dict[str, Any],
    ) -> Any:
        """Route an inter-service call to the correct service."""
