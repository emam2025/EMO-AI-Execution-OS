"""Phase I1 — Distributed Queue Implementation.  # LAW-1 LAW-5 LAW-11 RULE-2 RULE-5

Implements IDistributedQueue protocol with in-memory message routing,
priority ordering, DLQ routing, and publish/ack semantics.

Ref: Canon LAW 1 (Interface Authority), LAW 5 (Observability)
Ref: Canon LAW 11 (No Global State)
Ref: Canon RULE 2 (No Uncontrolled IO), RULE 5 (Recovery)
Ref: artifacts/design/i1/protocols/01_infra_protocols.py
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
from core.runtime.models.infra_models import DLQStatus, MessagePriority


class DistributedQueue:  # LAW-1 LAW-5 LAW-11 RULE-2 RULE-5
    """In-memory distributed task queue with priority, DLQ, and observability.

    LAW 11: Queue is a service boundary — no shared global state.
    RULE 2: Payload validated before enqueue.
    RULE 5: Failed messages routed to DLQ after max_retries.
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
        max_retries: int = 3,
    ) -> None:
        self._event_bus = event_bus or InMemoryEventBus()
        self._max_retries = max_retries
        self._messages: Dict[str, Dict[str, Any]] = {}
        self._queues: Dict[str, List[str]] = defaultdict(list)  # topic -> [msg_ids]
        self._dlq: List[str] = []
        self._inflight: Dict[str, str] = {}  # msg_id -> worker_group

    def _compute_payload_hash(self, payload: Dict[str, Any]) -> str:  # RULE-1
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _publish_event(self, action: str, msg_id: str, topic: str, infra_trace_id: str, **extra: Any) -> None:
        event = ExecutionEvent(
            event_id=uuid.uuid4().hex[:16],
            event_type=f"QUEUE_{action.upper()}",
            source="DistributedQueue",
            payload={
                "msg_id": msg_id,
                "topic": topic,
                "infra_trace_id": infra_trace_id,
                **extra,
            },
            timestamp=time.time(),
        )
        if topic.startswith("runtime."):
            self._event_bus.publish(topic, event)
        self._event_bus.publish("runtime.infra.queue", event)

    def enqueue(  # LAW-11 RULE-2
        self,
        task: Dict[str, Any],
        topic: str,
        priority: int = 0,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not isinstance(task, dict):
            return {"error": "Task must be a dict"}

        msg_id = f"msg_{uuid.uuid4().hex[:16]}"
        payload_hash = self._compute_payload_hash(task)
        now_ns = time.time_ns()

        msg = {
            "msg_id": msg_id,
            "topic": topic,
            "payload": task,
            "payload_hash": payload_hash,
            "priority": priority,
            "retry_count": 0,
            "max_retries": self._max_retries,
            "dlq_status": DLQStatus.NONE,
            "enqueued_at_ns": now_ns,
            "visible_at_ns": now_ns,
            "delivery_count": 0,
            "worker_group": "",
            "infra_trace_id": infra_trace_id,
        }
        self._messages[msg_id] = msg
        self._queues[topic].append(msg_id)

        self._publish_event("enqueue", msg_id, topic, infra_trace_id, payload_hash=payload_hash)

        return {
            "msg_id": msg_id,
            "topic": topic,
            "enqueued_at_ns": now_ns,
            "payload_hash": payload_hash,
        }

    def dequeue(  # LAW-5
        self,
        worker_group: str,
        topics: Optional[List[str]] = None,
        batch_size: int = 1,
        infra_trace_id: str = "",
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        now_ns = time.time_ns()

        target_topics = topics if topics is not None else list(self._queues.keys())

        candidates: List[Dict[str, Any]] = []
        for topic in target_topics:
            for msg_id in list(self._queues.get(topic, [])):
                if msg_id in self._inflight:
                    continue
                msg = self._messages.get(msg_id)
                if msg is None:
                    continue
                if msg["visible_at_ns"] > now_ns:
                    continue
                candidates.append(msg)

        candidates.sort(key=lambda m: (-m["priority"], m["enqueued_at_ns"]))

        for msg in candidates[:batch_size]:
            msg_id = msg["msg_id"]
            self._inflight[msg_id] = worker_group
            msg["delivery_count"] += 1
            msg["worker_group"] = worker_group

            self._publish_event(
                "dequeue", msg_id, msg["topic"], infra_trace_id,
                worker_group=worker_group,
            )

            result.append({
                "msg_id": msg_id,
                "topic": msg["topic"],
                "payload": msg["payload"],
                "payload_hash": msg["payload_hash"],
                "priority": msg["priority"],
                "enqueued_at_ns": msg["enqueued_at_ns"],
                "delivery_count": msg["delivery_count"],
            })

        return result

    def acknowledge(  # RULE-5
        self,
        msg_id: str,
        worker_group: str,
        infra_trace_id: str = "",
    ) -> bool:
        msg = self._messages.get(msg_id)
        if msg is None:
            return False

        inflight_group = self._inflight.get(msg_id)
        if inflight_group is not None and inflight_group != worker_group:
            return False

        topic = msg["topic"]
        if msg_id in self._queues.get(topic, []):
            self._queues[topic].remove(msg_id)
        self._inflight.pop(msg_id, None)
        self._messages.pop(msg_id, None)

        self._publish_event("acknowledge", msg_id, topic, infra_trace_id, worker_group=worker_group)
        return True

    def requeue_on_nack(  # RULE-5
        self,
        msg_id: str,
        worker_group: str,
        reason: str = "",
        delay_sec: float = 0.0,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        msg = self._messages.get(msg_id)
        if msg is None:
            return {"requeue_ok": False, "retry_count": 0, "dlq_routed": False}

        inflight_group = self._inflight.get(msg_id)
        if inflight_group is not None and inflight_group != worker_group:
            return {"requeue_ok": False, "retry_count": 0, "dlq_routed": False}

        self._inflight.pop(msg_id, None)
        msg["retry_count"] += 1
        dlq_routed = False

        if msg["retry_count"] >= self._max_retries:
            msg["dlq_status"] = DLQStatus.ROUTED
            self._dlq.append(msg_id)
            dlq_routed = True
        else:
            delay_ns = int(delay_sec * 1_000_000_000)
            msg["visible_at_ns"] = time.time_ns() + delay_ns

        self._publish_event(
            "nack" if not dlq_routed else "dlq_routed",
            msg_id, msg["topic"], infra_trace_id,
            worker_group=worker_group, reason=reason, dlq_routed=dlq_routed,
        )

        return {
            "requeue_ok": True,
            "retry_count": msg["retry_count"],
            "dlq_routed": dlq_routed,
        }

    @property
    def queue_depth(self) -> Dict[str, int]:
        return {topic: len(ids) for topic, ids in self._queues.items()}

    @property
    def dlq_depth(self) -> int:
        return len(self._dlq)

    def purge_topic(self, topic: str) -> int:
        count = len(self._queues.get(topic, []))
        for msg_id in list(self._queues.get(topic, [])):
            self._messages.pop(msg_id, None)
            self._inflight.pop(msg_id, None)
        self._queues[topic] = []
        return count
