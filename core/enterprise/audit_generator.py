"""AuditGenerator — Per-tenant activity export.

Generates structured audit trails from EventStore and ActionJournal.
Exports as JSON for further processing or compliance.

LAW 5: All audit events are observable.
LAW 12: Every audit entry is traceable via trace_id.
CORE FREEZE: Read-only aggregator — no modifications to core runtime.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


class AuditGenerator:
    """Generates per-tenant audit reports from EventStore.

    Read-only aggregator. Does not modify any core runtime state.
    """

    def __init__(self, event_store: Any = None, action_journal: Any = None) -> None:
        self._event_store = event_store
        self._action_journal = action_journal

    def export_audit_log(self, tenant_id: str, since_ts: Optional[float] = None) -> List[Dict[str, Any]]:
        """Export audit log for a tenant.

        Args:
            tenant_id: Tenant to export.
            since_ts: Optional minimum timestamp filter.

        Returns:
            List of audit entries matching the tenant.
        """
        if self._event_store is None:
            return []

        events = self._event_store.replay()
        filtered = [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "timestamp": e.timestamp,
                "source": e.source,
                "payload": e.payload,
                "trace_id": e.trace_id,
            }
            for e in events
            if e.session_id == tenant_id
        ]

        if since_ts is not None:
            filtered = [e for e in filtered if e["timestamp"] >= since_ts]

        return filtered

    def export_to_json(self, tenant_id: str, filepath: str) -> None:
        """Export audit log to a JSON file.

        Args:
            tenant_id: Tenant to export.
            filepath: Output JSON file path.
        """
        log = self.export_audit_log(tenant_id)
        with open(filepath, "w") as f:
            json.dump({"tenant_id": tenant_id, "entry_count": len(log), "entries": log}, f, indent=2)

    def summarize(self, tenant_id: str) -> Dict[str, Any]:
        """Generate a summary of tenant activity.

        Returns:
            Dict with counts of events by type.
        """
        log = self.export_audit_log(tenant_id)
        type_counts: Dict[str, int] = {}
        for entry in log:
            etype = entry["event_type"]
            type_counts[etype] = type_counts.get(etype, 0) + 1
        return {
            "tenant_id": tenant_id,
            "total_events": len(log),
            "by_type": type_counts,
        }
