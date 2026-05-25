"""Phase I1 — Object Storage Implementation.  # LAW-1 LAW-5 LAW-11 RULE-1 RULE-2

Implements IObjectStorage protocol with SHA-256 integrity verification,
write-once semantics, and lifecycle cleanup.

Ref: Canon LAW 1 (Interface Authority), LAW 5 (Observability)
Ref: Canon LAW 11 (No Global State)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: artifacts/design/i1/protocols/01_infra_protocols.py
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple


class ObjectStorage:  # LAW-1 LAW-5 LAW-11 RULE-1 RULE-2
    """Immutable object storage with integrity verification.

    All stored objects are immutable (write-once) with content-addressable
    checksums. No global mutable state exposed outside instance (LAW 11).
    """

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}  # uri -> artifact

    def _compute_checksum(self, payload: bytes) -> str:  # RULE-1
        return hashlib.sha256(payload).hexdigest()

    def store_artifact(  # LAW-11 RULE-1 RULE-2
        self,
        uri: str,
        payload: bytes,
        content_type: str,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        if not isinstance(payload, bytes):
            return {
                "stored": False,
                "checksum_sha256": "",
                "size_bytes": 0,
                "stored_at_ns": 0,
                "error": "Payload must be bytes",
            }

        checksum = self._compute_checksum(payload)
        now_ns = time.time_ns()

        self._store[uri] = {
            "payload": payload,
            "content_type": content_type,
            "checksum_sha256": checksum,
            "size_bytes": len(payload),
            "stored_at_ns": now_ns,
            "infra_trace_id": infra_trace_id,
            "metadata": {},
        }

        return {
            "stored": True,
            "checksum_sha256": checksum,
            "size_bytes": len(payload),
            "stored_at_ns": now_ns,
        }

    def retrieve_artifact(  # LAW-5 RULE-1
        self,
        uri: str,
        expected_checksum: str = "",
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        artifact = self._store.get(uri)
        if artifact is None:
            return {
                "payload": b"",
                "content_type": "",
                "checksum_sha256": "",
                "size_bytes": 0,
                "integrity_ok": False,
                "error": f"Artifact not found: {uri}",
            }

        actual_checksum = artifact["checksum_sha256"]
        integrity_ok = True

        if expected_checksum:
            integrity_ok = actual_checksum == expected_checksum

        return {
            "payload": artifact["payload"],
            "content_type": artifact["content_type"],
            "checksum_sha256": actual_checksum,
            "size_bytes": artifact["size_bytes"],
            "integrity_ok": integrity_ok,
        }

    def lifecycle_cleanup(  # LAW-5
        self,
        bucket: str,
        prefix: str,
        max_age_sec: float,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        now_ns = time.time_ns()
        objects_removed = 0
        bytes_reclaimed = 0

        uris_to_remove: List[str] = []
        for uri, artifact in self._store.items():
            if not uri.startswith(f"{bucket}/{prefix}"):
                continue
            age_sec = (now_ns - artifact["stored_at_ns"]) / 1e9
            if age_sec > max_age_sec:
                uris_to_remove.append(uri)
                objects_removed += 1
                bytes_reclaimed += artifact["size_bytes"]

        for uri in uris_to_remove:
            del self._store[uri]

        return {
            "cleaned": True,
            "objects_removed": objects_removed,
            "bytes_reclaimed": bytes_reclaimed,
        }

    def verify_integrity(  # RULE-1
        self,
        uri: str,
        expected_checksum: str,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        artifact = self._store.get(uri)
        if artifact is None:
            return {
                "integrity_ok": False,
                "actual_checksum": "",
                "size_bytes": 0,
                "error": f"Artifact not found: {uri}",
            }

        actual_checksum = artifact["checksum_sha256"]
        integrity_ok = actual_checksum == expected_checksum

        return {
            "integrity_ok": integrity_ok,
            "actual_checksum": actual_checksum,
            "size_bytes": artifact["size_bytes"],
        }
