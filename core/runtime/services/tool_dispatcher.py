"""D8.1 — ExecutionToolDispatcher: execution routing (LAW 24).

LAW 24: Dispatcher owns execution routing.
FORBIDDEN: state, lease, retry, scheduling.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 24
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger("emo_ai.services.dispatcher")


class DispatchError(Exception):
    """Raised when tool dispatch routing fails."""


class UnknownToolError(Exception):
    """Raised when tool_name is not registered."""


class ContractViolationError(Exception):
    """Raised when tool call violates its contract."""


class RoutingError(Exception):
    """Raised when service domain or method is unknown."""


class ExecutionToolDispatcher:
    """Execution routing service — owns dispatch, contract validation, routing.

    LAW 24: Dispatcher owns execution routing.
    Private state: _tool_registry, _contract_schemas, _routing_table.
    No access to scheduler, state_store, retry_handler, or lease_manager state.

    Ref: DEVELOPER.md §15.15a D8.1
    Ref: Canon LAW 24
    """

    def __init__(self) -> None:
        self._tool_registry: Dict[str, Any] = {}
        self._contract_schemas: Dict[str, Dict[str, Any]] = {}
        self._routing_table: Dict[str, str] = {}

    def register_tool(
        self,
        tool_name: str,
        executor: Any,
        contract_schema: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a tool for dispatch.

        LAW 24: Dispatcher owns the tool registry.
        """
        self._tool_registry[tool_name] = executor
        if contract_schema:
            self._contract_schemas[tool_name] = contract_schema
        if tool_name not in self._routing_table:
            self._routing_table[tool_name] = "default"

    def dispatch_tool_call(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Route a tool call to the appropriate execution path.

        LAW 24: Only Dispatcher may route tool calls.

        Args:
            tool_name: Name of the tool to dispatch.
            inputs: Input parameters for the tool.
            context: Optional execution context.

        Returns:
            Execution result dict.

        Raises:
            DispatchError: If routing fails.
            UnknownToolError: If tool_name is not registered.
        """
        if tool_name not in self._tool_registry:
            raise UnknownToolError(f"Tool '{tool_name}' is not registered")

        executor = self._tool_registry[tool_name]
        route = self._routing_table.get(tool_name, "default")

        try:
            if hasattr(executor, "execute"):
                result = executor.execute(tool_name, inputs, context)
            elif callable(executor):
                result = executor(inputs)
            else:
                raise DispatchError(
                    f"Cannot dispatch tool '{tool_name}': executor is not callable"
                )

            logger.debug("Dispatched %s via route=%s", tool_name, route)
            return {"status": "completed", "tool": tool_name, "result": result}

        except UnknownToolError:
            raise
        except DispatchError:
            raise
        except Exception as e:
            raise DispatchError(
                f"Dispatch failed for tool '{tool_name}': {e}"
            ) from e

    def validate_contract(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
    ) -> bool:
        """Validate that a tool call conforms to its contract.

        Args:
            tool_name: Name of the tool.
            inputs: Input parameters to validate.

        Returns:
            True if valid, False otherwise.

        Raises:
            ContractViolationError: If contract is violated.
        """
        schema = self._contract_schemas.get(tool_name)
        if schema is None:
            return True  # No contract defined = valid

        required = schema.get("required", [])
        for field in required:
            if field not in inputs:
                raise ContractViolationError(
                    f"Tool '{tool_name}' missing required field '{field}'"
                )

        allowed = schema.get("allowed", {})
        for key, value in inputs.items():
            if key in allowed:
                allowed_type = allowed[key]
                if not isinstance(value, allowed_type):
                    raise ContractViolationError(
                        f"Tool '{tool_name}' field '{key}' expected "
                        f"{allowed_type.__name__}, got {type(value).__name__}"
                    )

        return True

    def route_service(
        self,
        service_domain: str,
        method: str,
        payload: Dict[str, Any],
    ) -> Any:
        """Route an inter-service call to the correct service.

        LAW 24: Dispatcher owns inter-service routing.
        Uses _routing_table to resolve domains.

        Args:
            service_domain: Target service domain name.
            method: Method name to invoke.
            payload: Method arguments.

        Returns:
            Service method result.

        Raises:
            RoutingError: If service domain or method is unknown.
        """
        raise RoutingError(
            f"Routing for '{service_domain}.{method}' not implemented — "
            f"inter-service calls use EventBus for async communication"
        )
