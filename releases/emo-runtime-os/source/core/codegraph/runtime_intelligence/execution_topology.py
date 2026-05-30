"""3.8.1.2 — Execution Topology.

Builds execution-order graphs from event traces, enabling analysis of
execution paths, concurrency patterns, and runtime dependency chains.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExecutionEdge:
    source_event_id: str = ""
    target_event_id: str = ""
    transition_type: str = ""  # e.g. "completed→started", "failed→retry"
    latency: float = 0.0


@dataclass
class ExecutionGraph:
    session_id: str = ""
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[ExecutionEdge] = field(default_factory=list)
    trace_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "nodes": {k: dict(v) for k, v in self.nodes.items()},
            "edges": [
                {"source": e.source_event_id,
                 "target": e.target_event_id,
                 "type": e.transition_type,
                 "latency": e.latency}
                for e in self.edges
            ],
            "trace_count": self.trace_count,
        }


class ExecutionTopology:
    """Builds execution graphs from flat event sequences.

    Reads session-scoped events from an event list (e.g. EventStore.replay)
    and reconstructs the execution topology — which events followed which,
    with transition latencies.
    """

    def __init__(self):
        self._graphs: Dict[str, ExecutionGraph] = {}

    def build(self, events: List[Dict[str, Any]]) -> ExecutionGraph:
        if not events:
            return ExecutionGraph()
        session_id = events[0].get("session_id", "") if isinstance(events[0], dict) else getattr(events[0], "session_id", "")
        graph = ExecutionGraph(session_id=session_id)

        prev_event_id = None
        prev_timestamp = None

        for event in events:
            event_id = self._extract(event, "event_id")
            event_type = self._extract(event, "event_type")
            timestamp = self._extract(event, "timestamp")
            payload = self._extract(event, "payload", {})

            graph.nodes[event_id] = {
                "event_type": event_type,
                "timestamp": timestamp,
                "tool": payload.get("tool", ""),
                "node_id": payload.get("node_id", ""),
                "status": payload.get("status", ""),
            }
            graph.trace_count += 1

            if prev_event_id is not None and prev_timestamp is not None:
                graph.edges.append(ExecutionEdge(
                    source_event_id=prev_event_id,
                    target_event_id=event_id,
                    transition_type=f"{prev_type}→{event_type}",
                    latency=timestamp - prev_timestamp,
                ))

            prev_event_id = event_id
            prev_timestamp = timestamp
            prev_type = event_type

        self._graphs[session_id] = graph
        return graph

    def get_graph(self, session_id: str) -> Optional[ExecutionGraph]:
        return self._graphs.get(session_id)

    @staticmethod
    def _extract(event, key: str, default=None):
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)
