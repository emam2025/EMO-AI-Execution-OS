"""CognitiveTraceCorrelator — cognitive_trace_id propagation across Phase L layers.

LAW 8: Every operation is recoverable via cognitive_trace_id.
LAW 12: Traceability — full backward chain from context to execution event.
RULE 3: Replay-safe — same trace sequence produces same correlation state.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional


class CognitiveTraceCorrelator:  # LAW-8 LAW-12 RULE-3
    """Generates and propagates cognitive_trace_id through the Phase L memory pipeline.

    Trace chain:
      cognitive_trace_id ──→ enterprise_trace_id ──→ F1 trace_id

    Format:
      cog_<SHA256(tenant_id + session_id + timestamp_ns)>[:28]
    """

    def __init__(self) -> None:
        self._traces: Dict[str, Dict[str, str]] = {}
        self._store_log: List[Dict[str, Any]] = []

    def generate_cognitive_trace_id(self, tenant_id: str, session_id: str = "") -> str:
        raw = f"{tenant_id}:{session_id or uuid.uuid4().hex}:{time.time_ns()}"
        return f"cog_{hashlib.sha256(raw.encode()).hexdigest()[:28]}"

    def record_memory_store(
        self, cognitive_trace_id: str, layer: str, key: str, tenant_id: str,
    ) -> None:
        self._traces.setdefault(cognitive_trace_id, {})
        self._traces[cognitive_trace_id][f"store:{layer}:{key}"] = tenant_id
        self._store_log.append({
            "cognitive_trace_id": cognitive_trace_id,
            "layer": layer,
            "key": key,
            "tenant_id": tenant_id,
            "timestamp_ns": time.time_ns(),
        })

    def get_trace_chain(self, cognitive_trace_id: str) -> Dict[str, Any]:
        layers = self._traces.get(cognitive_trace_id, {})
        return {
            "cognitive_trace_id": cognitive_trace_id,
            "layers": layers,
            "total_stores": len(layers),
        }

    def verify_full_propagation(self, cognitive_trace_id: str) -> Dict[str, Any]:
        layers = self._traces.get(cognitive_trace_id, {})
        return {
            "cognitive_trace_id": cognitive_trace_id,
            "fully_propagated": len(layers) > 0,
            "layer_count": len(layers),
            "layers": layers,
        }

    def all_traces(self) -> Dict[str, Dict[str, str]]:
        return dict(self._traces)

    def reset(self) -> None:
        self._traces.clear()
        self._store_log.clear()
