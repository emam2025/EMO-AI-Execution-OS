"""EMO CLI — command-line interface for the EMO AI Runtime.

All commands route through UnifiedRuntimeAPI. Zero execution logic.
Usage: emo submit <dag> | emo status <ticket> | emo cancel <ticket>
       emo replay <execution_id> | emo logs <trace_id> | emo health

CORE FREEZE: No imports from execution_core, sandbox, io, resources.
Zero import statements referencing those modules.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class EmoCLI:
    """CLI command handler. Every method routes to UnifiedRuntimeAPI.

    LAW 13: No direct execution — all calls go through UnifiedRuntime.
    """

    def __init__(self, runtime_api: Any, dashboard_service: Any = None) -> None:
        self._api = runtime_api
        self._dashboard = dashboard_service

    def submit(self, dag: Dict[str, Any]) -> str:
        """Submit a DAG for execution. Returns ticket ID."""
        result = self._api.submit(dag=dag)
        return result.ticket_id

    def status(self, ticket_id: str) -> Dict[str, Any]:
        """Get execution status by ticket ID."""
        result = self._api.observe(ticket_id=ticket_id)
        return {
            "ticket_id": ticket_id,
            "state": getattr(result, "state", "unknown"),
            "status": getattr(result, "status", "unknown"),
        }

    def cancel(self, ticket_id: str, force: bool = False) -> Dict[str, Any]:
        """Cancel an active execution."""
        result = self._api.cancel(ticket_id=ticket_id, force=force)
        return {"ticket_id": ticket_id, "cancelled": True}

    def replay(self, execution_id: str) -> Dict[str, Any]:
        """Replay an execution deterministically."""
        result = self._api.replay(execution_id=execution_id)
        return {"execution_id": execution_id, "replay_id": result.replay_id}

    def logs(self, trace_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve execution logs by trace_id."""
        if self._dashboard is not None:
            return self._dashboard.get_events(trace_id=trace_id, limit=limit)
        return []

    def health(self) -> Dict[str, Any]:
        """Get system health status."""
        if self._dashboard is not None:
            return self._dashboard.get_system_health()
        return {"status": "unknown", "message": "Dashboard service unavailable"}
