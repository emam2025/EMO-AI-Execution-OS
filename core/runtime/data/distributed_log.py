"""Phase I2 — Distributed Log Implementation.  # LAW-5 LAW-11 LAW-21 RULE-2 RULE-4 RULE-5

Implements IDistributedLog protocol with append-only streaming, segment
compaction, and replica synchronisation.

Ref: Canon LAW 5 (Observability), LAW 11 (No Global State)
Ref: Canon LAW 21 (Failure Propagation)
Ref: Canon RULE 2 (No Uncontrolled IO), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: artifacts/design/i2/protocols/01_data_infra_protocols.py
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional

from core.interfaces.event_bus import IEventBus
from core.runtime.event_bus import InMemoryEventBus
from core.models.events import ExecutionEvent
from core.runtime.data.acid_state_machine import ACIDStateMachine, GuardianResult


class DistributedLog:  # LAW-5 LAW-11 LAW-21 RULE-2 RULE-4 RULE-5
    """In-memory append-only log with segment compaction and replica sync.

    LAW 11: Log streams are service boundaries — no shared state.
    RULE 2: Payload validated before append.
    RULE 4: Replicas are isolated — sync is non-blocking.
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._event_bus = event_bus or InMemoryEventBus()
        self._entries: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._offsets: Dict[str, int] = defaultdict(int)
        self._segments: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._replica_offsets: Dict[str, Dict[str, int]] = defaultdict(dict)

    def _compute_hash(self, payload: Dict[str, Any]) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:16]

    def _publish_event(self, action: str, stream: str, data_trace_id: str, **extra: Any) -> None:
        event = ExecutionEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=f"LOG_{action.upper()}",
            source="DistributedLog",
            payload={"stream": stream, "data_trace_id": data_trace_id, **extra},
            timestamp=time.time(),
        )
        self._event_bus.publish("runtime.data.log", event)

    def append_entry(  # LAW-11 RULE-2
        self,
        stream: str,
        payload: Dict[str, Any],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            return {"entry_id": "", "stream": stream, "offset": 0,
                    "timestamp_ns": 0, "payload_hash": "", "error": "Payload must be a dict"}

        offset = self._offsets[stream]
        entry_id = f"log_{uuid.uuid4().hex[:16]}"
        now_ns = time.time_ns()
        payload_hash = self._compute_hash(payload)

        entry = {
            "entry_id": entry_id,
            "stream": stream,
            "offset": offset,
            "payload": payload,
            "payload_hash": payload_hash,
            "timestamp_ns": now_ns,
            "data_trace_id": data_trace_id,
        }
        self._entries[stream].append(entry)
        self._offsets[stream] = offset + 1

        self._publish_event("append", stream, data_trace_id,
                            entry_id=entry_id, offset=offset, payload_hash=payload_hash)

        return {
            "entry_id": entry_id,
            "stream": stream,
            "offset": offset,
            "timestamp_ns": now_ns,
            "payload_hash": payload_hash,
        }

    def read_range(  # LAW-5
        self,
        stream: str,
        start_offset: int,
        end_offset: int,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        all_entries = self._entries.get(stream, [])
        filtered = [
            e for e in all_entries
            if start_offset <= e["offset"] <= end_offset
        ]
        has_more = any(e["offset"] > end_offset for e in all_entries)

        return {
            "entries": filtered,
            "stream": stream,
            "count": len(filtered),
            "has_more": has_more,
        }

    def compact_segments(  # RULE-5
        self,
        stream: str,
        retention_sec: float,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        now_ns = time.time_ns()
        all_entries = self._entries.get(stream, [])
        before = len(all_entries)

        retained = [
            e for e in all_entries
            if (now_ns - e["timestamp_ns"]) / 1e9 <= retention_sec
        ]
        removed = before - len(retained)
        bytes_before = sum(len(json.dumps(e, default=str).encode()) for e in all_entries)
        bytes_after = sum(len(json.dumps(e, default=str).encode()) for e in retained)
        bytes_reclaimed = bytes_before - bytes_after

        self._entries[stream] = retained

        self._publish_event("compact", stream, data_trace_id,
                            entries_removed=removed, bytes_reclaimed=bytes_reclaimed)

        return {
            "compacted": True,
            "segments_removed": removed,
            "entries_removed": removed,
            "bytes_reclaimed": max(0, bytes_reclaimed),
        }

    def sync_replicas(  # LAW-21 RULE-4
        self,
        stream: str,
        target_nodes: List[str],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        current_offset = self._offsets.get(stream, 0)
        nodes_synced = 0
        entries_synced = 0
        max_lag_ms = 0.0

        for node in target_nodes:
            remote_offset = self._replica_offsets[stream].get(node, 0)
            lag = current_offset - remote_offset
            entries_to_sync = lag

            if entries_to_sync > 0:
                nodes_synced += 1
                entries_synced += entries_to_sync
                self._replica_offsets[stream][node] = current_offset
                lag_ms = 0.0
            else:
                lag_ms = 0.0

            max_lag_ms = max(max_lag_ms, lag_ms)

        self._publish_event("sync", stream, data_trace_id,
                            nodes_synced=nodes_synced, entries_synced=entries_synced)

        return {
            "synced": nodes_synced == len(target_nodes),
            "nodes_synced": nodes_synced,
            "entries_synced": entries_synced,
            "lag_ms": max_lag_ms,
        }
