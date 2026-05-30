"""Phase 5 — Distributed Runtime (remote mesh)."""

from core.runtime.mesh.remote.serialization import (
    envelope_to_dict,
    dict_to_envelope,
    envelope_to_json,
    json_to_envelope,
)
from core.runtime.mesh.remote.transport import (
    RemoteTransportClient,
    RemoteTransportServer,
    RemoteTransportError,
)
from core.runtime.mesh.remote.discovery import (
    DistributedRegistry,
    PeerNode,
)
from core.runtime.mesh.remote.node import MeshNode

__all__ = [
    "envelope_to_dict",
    "dict_to_envelope",
    "envelope_to_json",
    "json_to_envelope",
    "RemoteTransportClient",
    "RemoteTransportServer",
    "RemoteTransportError",
    "DistributedRegistry",
    "PeerNode",
    "MeshNode",
]
