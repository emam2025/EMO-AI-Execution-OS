"""
R2 Read-Only Bridge — contract for reading R2 Memory traces.

Isolated interface: no direct imports from releases/memory-os/.
All operations are read-only (no delete/update methods).
LAW-6 enforced on all public methods.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional


class R2Bridge:
    """Read-only bridge to R2 Memory traces.

    WARNING: This is a simulated bridge for the protocol phase.
    In production, this would connect to R2's SQLite storage via
    a separate read-only adapter. Zero mutation capability.
    """

    def __init__(self) -> None:
        # Simulated trace store — instance-level, not global.
        self._traces: Dict[str, dict] = {}

    def ingest_trace(self, trace: dict) -> str:
        """Register a trace for testing. ONLY for test/protocol use.

        This is NOT a write path to R2. It simulates what R2 would
        provide through the bridge contract.
        """
        tid = trace.get("trace_id", trace.get("cognitive_trace_id", f"ct-{uuid.uuid4().hex[:16]}"))
        self._traces[tid] = dict(trace)
        return tid

    def fetch_trace_context(
        self,
        trace_id: str,
        tenant_id: str,
    ) -> dict:
        """Return read-only trace data scoped by tenant_id.

        LAW-6: tenant_id is mandatory.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        trace = self._traces.get(trace_id)
        if not trace:
            raise KeyError(f"Trace not found: {trace_id}")
        if trace.get("tenant_id", "") != tenant_id:
            raise KeyError(f"Trace not found for tenant: {trace_id}")
        # Return a copy to enforce read-only contract
        return dict(trace)

    def list_project_traces(
        self,
        project_id: str,
        tenant_id: str,
        limit: int = 20,
    ) -> List[dict]:
        """Return trace metadata for a project (read-only).

        LAW-11: results filtered by tenant_id + project_id.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        results: List[dict] = []
        for trace in self._traces.values():
            if trace.get("tenant_id", "") != tenant_id:
                continue
            if project_id and trace.get("project_id", "") != project_id:
                continue
            meta = {
                "trace_id": trace.get("trace_id", ""),
                "cognitive_trace_id": trace.get("cognitive_trace_id", ""),
                "project_id": trace.get("project_id", ""),
                "agent_id": trace.get("agent_id", ""),
                "outcome": trace.get("outcome", "unknown"),
                "step_count": len(trace.get("steps", [])),
                "created_at": trace.get("created_at", 0.0),
            }
            results.append(meta)
        results.sort(key=lambda m: m.get("created_at", 0.0), reverse=True)
        return results[:limit]

    def clear(self) -> None:
        """Clear all traces. TEST USE ONLY."""
        self._traces.clear()
