"""3.8.1.3 — Failure Topology.

Builds failure propagation graphs from event traces, enabling analysis
of retry storms, rollback cascades, and failure paths.

A failure path is a sequence: failure → retry → failure → retry → ...
or failure → rollback → rollback_successor → ...
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FailureNode:
    event_id: str = ""
    tool: str = ""
    error: str = ""
    failure_type: str = ""  # "initial_failure", "retry", "rollback", "retry_storm"
    depth: int = 0


@dataclass
class FailureEdge:
    source_event_id: str = ""
    target_event_id: str = ""
    relationship: str = ""  # "led_to_retry", "led_to_rollback", "propagated_to"
    latency: float = 0.0


@dataclass
class FailurePath:
    nodes: List[FailureNode] = field(default_factory=list)
    edges: List[FailureEdge] = field(default_factory=list)
    root_tool: str = ""
    total_latency: float = 0.0
    retry_count: int = 0
    final_outcome: str = ""  # "recovered", "failed", "rolled_back"

    def is_storm(self, threshold: int = 3) -> bool:
        """A retry storm is defined as 3+ consecutive retries."""
        return self.retry_count >= threshold


class FailureTopology:
    """Builds failure propagation graphs from execution events.

    Detects failure paths: sequences of NODE_FAILED, RETRY_DECISION,
    STATE_TRANSITION (rollback) events that form a causal chain.
    """

    def __init__(self):
        self._paths: List[FailurePath] = []

    def analyze(self, events: List[Dict[str, Any]]) -> List[FailurePath]:
        failure_events = self._filter_failure_events(events)
        if not failure_events:
            return []

        paths = self._cluster_into_paths(failure_events)
        self._paths = paths
        return paths

    def _filter_failure_events(self, events: List[Any]) -> List[Dict[str, Any]]:
        failure_types = {"NODE_FAILED", "RETRY_DECISION", "STATE_TRANSITION"}
        result = []
        for event in events:
            etype = self._extract(event, "event_type")
            if etype in failure_types:
                result.append(self._as_dict(event))
        return result

    def _cluster_into_paths(self, events: List[Dict]) -> List[FailurePath]:
        if not events:
            return []

        paths: List[FailurePath] = []
        current_path: List[FailureNode] = []
        current_edges: List[FailureEdge] = []

        for i, event in enumerate(events):
            etype = event.get("event_type", "")
            payload = event.get("payload", {})
            fn = FailureNode(
                event_id=event.get("event_id", ""),
                tool=payload.get("tool", ""),
                error=payload.get("error", ""),
                failure_type=self._classify_failure_type(etype),
                depth=i,
            )
            current_path.append(fn)

            if i > 0:
                prev = events[i - 1]
                prev_type = prev.get("event_type", "")
                rel = self._derive_relationship(prev_type, etype)
                current_edges.append(FailureEdge(
                    source_event_id=prev.get("event_id", ""),
                    target_event_id=event.get("event_id", ""),
                    relationship=rel,
                    latency=event.get("timestamp", 0.0) - prev.get("timestamp", 0.0),
                ))

            if etype == "STATE_TRANSITION":
                prev_payload = events[i - 1].get("payload", {})
                paths.append(FailurePath(
                    nodes=list(current_path),
                    edges=list(current_edges),
                    root_tool=current_path[0].tool if current_path else "",
                    retry_count=sum(1 for n in current_path if n.failure_type == "retry"),
                    total_latency=current_edges[-1].latency if current_edges else 0.0,
                    final_outcome="rolled_back",
                ))
                current_path = []
                current_edges = []

        if current_path:
            paths.append(FailurePath(
                nodes=list(current_path),
                edges=list(current_edges),
                root_tool=current_path[0].tool if current_path else "",
                retry_count=sum(1 for n in current_path if n.failure_type == "retry"),
                total_latency=current_edges[-1].latency if current_edges else 0.0,
                final_outcome="failed",
            ))

        return paths

    @property
    def paths(self) -> List[FailurePath]:
        return list(self._paths)

    def storm_paths(self, threshold: int = 3) -> List[FailurePath]:
        return [p for p in self._paths if p.is_storm(threshold)]

    @staticmethod
    def _classify_failure_type(event_type: str) -> str:
        mapping = {
            "NODE_FAILED": "initial_failure",
            "RETRY_DECISION": "retry",
            "STATE_TRANSITION": "rollback",
        }
        return mapping.get(event_type, "unknown")

    @staticmethod
    def _derive_relationship(prev_type: str, curr_type: str) -> str:
        if prev_type == "NODE_FAILED" and curr_type == "RETRY_DECISION":
            return "led_to_retry"
        if curr_type == "STATE_TRANSITION":
            return "led_to_rollback"
        return "propagated_to"

    @staticmethod
    def _extract(event, key: str, default=None):
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)

    @staticmethod
    def _as_dict(event) -> Dict[str, Any]:
        if isinstance(event, dict):
            return event
        return {
            "event_id": getattr(event, "event_id", ""),
            "event_type": getattr(event, "event_type", ""),
            "timestamp": getattr(event, "timestamp", 0.0),
            "payload": getattr(event, "payload", {}),
        }
