"""Phase H1 — Computer Use Trace Correlator.  # LAW-12

Propagates session_trace_id across G5 → H1 → Phase 4 → F4 layers,
ensuring every computer use session is fully back-traceable.

Ref: Canon LAW 12 (Traceability)
Ref: artifacts/design/h1/04_integration_blueprint.md §3
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional


class ComputerUseTraceCorrelator:  # LAW-12
    """Manages session_trace_id propagation across layers."""

    def __init__(self) -> None:
        self._correlations: Dict[str, Dict[str, str]] = {}

    def generate_session_trace_id(  # LAW-12
        self, mission_trace_id: str, session_index: int = 0,
    ) -> str:
        raw = f"{mission_trace_id}:h1:{session_index}:{time.time_ns()}"
        return f"h1_{hashlib.sha256(raw.encode()).hexdigest()[:28]}"

    def record_correlation(  # LAW-12
        self, session_id: str, layer: str, session_trace_id: str,
    ) -> None:
        if session_id not in self._correlations:
            self._correlations[session_id] = {}
        self._correlations[session_id][layer] = session_trace_id

    def correlation_for(self, session_id: str, layer: str) -> str:
        return self._correlations.get(session_id, {}).get(layer, "")

    def propagate_to_g5(  # LAW-12
        self, session_id: str, session_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(session_id, "g5_swarm", session_trace_id)
        return {"session_trace_id": session_trace_id, "session_id": session_id, "target_layer": "g5_swarm"}

    def propagate_to_phase4(  # LAW-12
        self, session_id: str, session_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(session_id, "phase4_sandbox", session_trace_id)
        return {"session_trace_id": session_trace_id, "session_id": session_id, "target_layer": "phase4_sandbox"}

    def propagate_to_f4(  # LAW-12
        self, session_id: str, session_trace_id: str,
    ) -> Dict[str, str]:
        self.record_correlation(session_id, "f4_observability", session_trace_id)
        return {"session_trace_id": session_trace_id, "session_id": session_id, "target_layer": "f4_observability"}

    def trace_chain(self, session_trace_id: str) -> Dict[str, Any]:
        for sid, layers in self._correlations.items():
            for layer, tid in layers.items():
                if tid == session_trace_id:
                    return {
                        "session_id": sid,
                        "session_trace_id": session_trace_id,
                        "layers": dict(layers),
                    }
        return {}

    def resolve_session_id(self, session_trace_id: str) -> Optional[str]:
        for sid, layers in self._correlations.items():
            if session_trace_id in layers.values():
                return sid
        return None

    def reset(self) -> None:
        self._correlations.clear()
