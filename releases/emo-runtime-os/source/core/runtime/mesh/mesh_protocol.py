"""GAP 1 — MeshProtocol: internal RPC model for service-to-service communication.

Defines the request/response contract that every mesh service speaks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class MeshMessageType(str, Enum):
    REQUEST = "request"
    RESPONSE = "response"
    STREAM = "stream"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    DISCONNECT = "disconnect"


@dataclass
class MeshEnvelope:
    """Every mesh message is wrapped in this envelope."""
    msg_type: MeshMessageType = MeshMessageType.REQUEST
    service: str = ""
    method: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    correlation_id: str = ""
    ttl: float = 30.0
    priority: int = 0


class MeshProtocol:
    """Internal RPC protocol for service mesh communication.

    Handles serialization, routing headers, and envelope lifecycle.
    """

    @staticmethod
    def create_request(
        service: str,
        method: str,
        payload: Dict[str, Any],
        trace_id: str = "",
        ttl: float = 30.0,
    ) -> MeshEnvelope:
        return MeshEnvelope(
            msg_type=MeshMessageType.REQUEST,
            service=service,
            method=method,
            payload=payload,
            trace_id=trace_id,
            ttl=ttl,
        )

    @staticmethod
    def create_response(
        request: MeshEnvelope,
        payload: Dict[str, Any],
    ) -> MeshEnvelope:
        return MeshEnvelope(
            msg_type=MeshMessageType.RESPONSE,
            service=request.service,
            method=request.method,
            payload=payload,
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
        )

    @staticmethod
    def create_error(
        request: MeshEnvelope,
        error: str,
    ) -> MeshEnvelope:
        return MeshEnvelope(
            msg_type=MeshMessageType.ERROR,
            service=request.service,
            method=request.method,
            payload={"error": error},
            trace_id=request.trace_id,
            correlation_id=request.correlation_id,
        )

    @staticmethod
    def create_heartbeat(service: str) -> MeshEnvelope:
        return MeshEnvelope(
            msg_type=MeshMessageType.HEARTBEAT,
            service=service,
        )

    @staticmethod
    def is_request(envelope: MeshEnvelope) -> bool:
        return envelope.msg_type == MeshMessageType.REQUEST

    @staticmethod
    def is_response(envelope: MeshEnvelope) -> bool:
        return envelope.msg_type == MeshMessageType.RESPONSE

    @staticmethod
    def is_error(envelope: MeshEnvelope) -> bool:
        return envelope.msg_type == MeshMessageType.ERROR
