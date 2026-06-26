"""Phase 5 — Distributed Runtime serialization.

MeshEnvelope JSON serialization for network transport.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict

from core.runtime.mesh.mesh_protocol import MeshEnvelope, MeshMessageType


def envelope_to_dict(envelope: MeshEnvelope) -> Dict[str, Any]:
    """Serialize a MeshEnvelope to a JSON-safe dict."""
    data = asdict(envelope)
    data["msg_type"] = envelope.msg_type.value
    return data


def dict_to_envelope(data: Dict[str, Any]) -> MeshEnvelope:
    """Deserialize a dict back to a MeshEnvelope."""
    return MeshEnvelope(
        msg_type=MeshMessageType(data.get("msg_type", "request")),
        service=data.get("service", ""),
        method=data.get("method", ""),
        payload=data.get("payload", {}),
        trace_id=data.get("trace_id", ""),
        correlation_id=data.get("correlation_id", ""),
        ttl=data.get("ttl", 30.0),
        priority=data.get("priority", 0),
    )


def envelope_to_json(envelope: MeshEnvelope) -> str:
    """Serialize a MeshEnvelope to JSON string."""
    return json.dumps(envelope_to_dict(envelope))


def json_to_envelope(data: str) -> MeshEnvelope:
    """Deserialize a JSON string to a MeshEnvelope."""
    return dict_to_envelope(json.loads(data))
