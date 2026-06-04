"""EMO SDK — Python client for the EMO AI Runtime.

Provides programmatic access to UnifiedRuntimeAPI and ObservabilityLayer.
All calls route through the API — zero execution logic.

Usage:
    client = EmoClient(unified_runtime, tenant_id="acme")
    ticket = client.submit(dag={"nodes": [...]})
    status = client.observe(ticket.ticket_id)

CORE FREEZE: No imports from execution_core, sandbox, io, resources.
Zero import statements referencing those modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class EmoClient:
    """Python SDK client for EMO AI Runtime.

    Wraps UnifiedRuntimeAPI for programmatic access.
    All methods return raw API responses as dicts.
    """

    def __init__(
        self,
        runtime_api: Any,
        tenant_id: str = "default",
        api_key: Optional[str] = None,
        dashboard_service: Any = None,
    ) -> None:
        self._api = runtime_api
        self._dashboard = dashboard_service
        self.tenant_id = tenant_id
        self.api_key = api_key

    def submit(self, dag: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a DAG for execution.

        Args:
            dag: The DAG definition (nodes, edges, metadata).

        Returns:
            API response with ticket_id and status.
        """
        result = self._api.submit(dag=dag)
        return {"ticket_id": result.ticket_id, "status": "submitted"}

    def observe(self, ticket_id: str) -> Dict[str, Any]:
        """Get execution status and state.

        Args:
            ticket_id: Execution ticket ID.

        Returns:
            Current execution state and metadata.
        """
        result = self._api.observe(ticket_id=ticket_id)
        return {
            "ticket_id": result.ticket_id,
            "state": result.current_state,
            "progress": result.progress,
        }

    def cancel(self, ticket_id: str, force: bool = False) -> Dict[str, Any]:
        """Cancel an active execution."""
        self._api.cancel(ticket_id=ticket_id, force=force)
        return {"ticket_id": ticket_id, "cancelled": True}

    def replay(self, execution_id: str) -> Dict[str, Any]:
        """Replay an execution deterministically."""
        result = self._api.replay(execution_id=execution_id)
        return {"execution_id": execution_id, "replay_id": result.replay_id}

    def export_audit(self, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Export audit trail for a tenant.

        Args:
            tenant_id: Tenant to export. Defaults to client's tenant_id.

        Returns:
            List of audit events.
        """
        tid = tenant_id or self.tenant_id
        if self._dashboard is not None:
            return self._dashboard.get_audit_trail(tenant_id=tid)
        return []

    def health(self) -> Dict[str, Any]:
        """Get runtime health status."""
        if self._dashboard is not None:
            return self._dashboard.get_system_health()
        return {"status": "unknown"}
