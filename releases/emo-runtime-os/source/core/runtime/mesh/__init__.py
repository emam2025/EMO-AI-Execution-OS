"""GAP 1 — Service Mesh Runtime Layer.

Phase 5 adds distributed runtime: remote transport, distributed
registry, and multi-node mesh.

Service Mesh Runtime adds mesh-aware DAG execution routing:
  MeshExecutionRuntime + MeshWorker — routes execution through the mesh.
"""

from core.runtime.mesh.mesh_protocol import (
    MeshEnvelope,
    MeshMessageType,
    MeshProtocol,
)
from core.runtime.mesh.service_registry import (
    ServiceRegistry,
    ServiceInstance,
    ServiceStatus,
)
from core.runtime.mesh.service_mesh import (
    ServiceMesh,
    ServiceNotAvailable,
    MeshRoutingError,
)
from core.runtime.mesh.failure_propagator import FailurePropagator
from core.runtime.mesh.mesh_execution_runtime import MeshExecutionRuntime
from core.runtime.mesh.mesh_worker import MeshWorker
from core.runtime.mesh.remote import (
    MeshNode,
    PeerNode,
    DistributedRegistry,
    RemoteTransportClient,
    RemoteTransportServer,
    RemoteTransportError,
    envelope_to_dict,
    dict_to_envelope,
    envelope_to_json,
    json_to_envelope,
)

__all__ = [
    "MeshEnvelope",
    "MeshMessageType",
    "MeshProtocol",
    "ServiceRegistry",
    "ServiceInstance",
    "ServiceStatus",
    "ServiceMesh",
    "ServiceNotAvailable",
    "MeshRoutingError",
    "FailurePropagator",
    # Service Mesh Runtime
    "MeshExecutionRuntime",
    "MeshWorker",
    # Phase 5 — Distributed Runtime
    "MeshNode",
    "PeerNode",
    "DistributedRegistry",
    "RemoteTransportClient",
    "RemoteTransportServer",
    "RemoteTransportError",
    "envelope_to_dict",
    "dict_to_envelope",
    "envelope_to_json",
    "json_to_envelope",
]
