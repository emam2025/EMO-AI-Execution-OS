"""3.8.2.1 — Runtime Graph Builder.

Builds a RuntimeExecutionGraph from events, execution traces, retries,
and dispatch flows. This graph represents the ACTUAL runtime architecture
— what really executed, in what order, with what dependencies.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeExecutionNode:
    tool: str = ""
    event_type: str = ""
    session_id: str = ""
    trace_id: str = ""
    timestamp: float = 0.0
    duration: float = 0.0
    success: bool = True
    error: str = ""
    dependencies: List[str] = field(default_factory=list)


@dataclass
class RuntimeExecutionGraph:
    nodes: Dict[str, RuntimeExecutionNode] = field(default_factory=dict)
    edges: List[Dict[str, str]] = field(default_factory=list)
    session_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": {
                tid: {
                    "tool": n.tool,
                    "event_type": n.event_type,
                    "session_id": n.session_id,
                    "duration": n.duration,
                    "success": n.success,
                    "error": n.error,
                    "dependencies": n.dependencies,
                }
                for tid, n in self.nodes.items()
            },
            "edges": self.edges,
            "session_count": self.session_count,
        }


class RuntimeGraphBuilder:
    """Builds RuntimeExecutionGraph from raw event streams.

    Processes lists of ExecutionEvent-like dicts and reconstructs
    the runtime execution graph — which tools called which, in what
    order, with what success/failure outcomes.
    """

    def __init__(self):
        self._graph = RuntimeExecutionGraph()

    def build(self, events: List[Dict[str, Any]]) -> RuntimeExecutionGraph:
        graph = RuntimeExecutionGraph()

        session_trace: Dict[str, List[str]] = defaultdict(list)
        current_node: Dict[str, Optional[str]] = {}

        for event in events:
            event_id = self._extract(event, "event_id", "")
            event_type = self._extract(event, "event_type", "")
            payload = self._extract(event, "payload", {})
            trace_id = self._extract(event, "trace_id", "")
            session_id = self._extract(event, "session_id", "")
            timestamp = self._extract(event, "timestamp", 0.0)

            tool = payload.get("tool", "")
            node_id = payload.get("node_id", "")

            if not tool and not node_id:
                continue

            key = tool or node_id

            success = event_type in ("NODE_COMPLETED", "EXECUTION_COMPLETED")
            error = payload.get("error", "")

            duration = 0.0
            if event_type == "NODE_COMPLETED":
                ts_index = current_node.get(key)
                if ts_index:
                    duration = timestamp - ts_index

            if event_type in ("NODE_STARTED", "RETRY_DECISION"):
                current_node[key] = timestamp

            deps = list(session_trace.get(session_id, []))
            node = RuntimeExecutionNode(
                tool=key,
                event_type=event_type,
                session_id=session_id,
                trace_id=trace_id,
                timestamp=timestamp,
                duration=duration,
                success=success,
                error=error,
                dependencies=deps,
            )
            graph.nodes[event_id] = node

            if key and session_id and key not in session_trace[session_id]:
                session_trace[session_id].append(key)

            if deps:
                for dep in deps[-3:]:
                    graph.edges.append({
                        "source": dep,
                        "target": key,
                        "type": "runtime_dependency",
                    })

        graph.session_count = len(set(
            self._extract(e, "session_id", "") for e in events
        ))
        self._graph = graph
        return graph

    @property
    def graph(self) -> RuntimeExecutionGraph:
        return self._graph

    @staticmethod
    def _extract(event, key: str, default=None):
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)
