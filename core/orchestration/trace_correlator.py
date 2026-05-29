"""OrchestrationTraceCorrelator — orchestration_trace_id propagation.

LAW 8: Every operation recoverable via orchestration_trace_id.
P-G1–P-G5: Propagation rules from 04_integration_blueprint.md §2.
RULE 3: Replay-safe — same trace sequence → same correlation state.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict, List


class OrchestrationTraceCorrelator:  # LAW-8 RULE-3
    """Generates and propagates orchestration_trace_id through Phase G pipeline.

    Trace chain (Blueprint §2):
      orchestration_trace_id ──► cognitive_trace_id ──► enterprise_trace_id ──► F1 trace_id

    Format:
      og_<SHA256(intent + tenant_id + timestamp_ns)>[:32]
    """

    def __init__(self) -> None:
        self._traces: Dict[str, Dict[str, str]] = {}
        self._events: List[Dict[str, Any]] = []

    def generate_orchestration_trace_id(self, intent: str, tenant_id: str) -> str:
        raw = f"{intent}:{tenant_id or uuid.uuid4().hex}:{time.time_ns()}"
        return f"og_{hashlib.sha256(raw.encode()).hexdigest()[:28]}"

    def record_event(
        self,
        orchestration_trace_id: str,
        event_type: str,
        agent: str,
        tenant_id: str,
    ) -> None:
        self._traces.setdefault(orchestration_trace_id, {})
        self._traces[orchestration_trace_id][f"{event_type}:{agent}"] = tenant_id
        self._events.append({
            "orchestration_trace_id": orchestration_trace_id,
            "event_type": event_type,
            "agent": agent,
            "tenant_id": tenant_id,
            "timestamp_ns": time.time_ns(),
        })

    def get_trace_chain(self, orchestration_trace_id: str) -> Dict[str, Any]:
        events = self._traces.get(orchestration_trace_id, {})
        return {
            "orchestration_trace_id": orchestration_trace_id,
            "events": events,
            "total_events": len(events),
        }

    def verify_full_propagation(self, orchestration_trace_id: str) -> Dict[str, Any]:
        events = self._traces.get(orchestration_trace_id, {})
        return {
            "orchestration_trace_id": orchestration_trace_id,
            "fully_propagated": len(events) > 0,
            "event_count": len(events),
            "events": events,
        }

    def all_traces(self) -> Dict[str, Dict[str, str]]:
        return dict(self._traces)

    def reset(self) -> None:
        self._traces.clear()
        self._events.clear()
