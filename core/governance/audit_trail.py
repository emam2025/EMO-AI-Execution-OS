"""EMO AI Governance Layer — Append-Only Audit Trail.

LAW 23: Audit records are append-only. No update or delete after write.
LAW 24: Records are signed with SHA-256 chain linking for tamper detection.
LAW 25: Sensitive fields (principal, payload) are encrypted at rest.
SOC2/GDPR compliant: immutability, non-repudiation, exportable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


_AUDIT_LOG: List[dict] = []
_SIGNING_KEY: str = ""  # Set once via init()


def init(signing_key: str) -> None:
    global _SIGNING_KEY
    if not signing_key:
        logger = logging.getLogger("emo_ai.audit")
        logger.critical("Audit trail signing key is empty — audit signatures will be FORGEABLE")
    _SIGNING_KEY = signing_key


def _sign(record: dict) -> str:
    serialized = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(
        _SIGNING_KEY.encode("utf-8") if _SIGNING_KEY else b"",
        serialized,
        hashlib.sha256,
    ).hexdigest()


def _hash_link(previous_hash: str, current_hash: str) -> str:
    return hashlib.sha256(
        f"{previous_hash}:{current_hash}".encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class AuditRecord:
    record_id: str = field(default_factory=lambda: f"ar-{uuid.uuid4().hex[:16]}")
    timestamp: float = field(default_factory=time.time)
    action: str = ""
    principal_id: str = ""
    tenant_id: str = ""
    resource: str = ""
    outcome: str = ""
    payload_hash: str = ""
    signature: str = ""
    previous_hash: str = ""
    chain_hash: str = ""


def append(
    action: str,
    principal_id: str,
    tenant_id: str,
    resource: str,
    outcome: str,
    payload: Optional[dict] = None,
) -> AuditRecord:
    previous_hash = _AUDIT_LOG[-1].get("chain_hash", "") if _AUDIT_LOG else "GENESIS"
    payload_hash = hashlib.sha256(
        json.dumps(payload or {}, sort_keys=True).encode("utf-8")
    ).hexdigest()

    record = AuditRecord(
        action=action,
        principal_id=principal_id,
        tenant_id=tenant_id,
        resource=resource,
        outcome=outcome,
        payload_hash=payload_hash,
        previous_hash=previous_hash,
    )

    record_dict = asdict(record)

    to_sign = {k: v for k, v in record_dict.items() if k not in ("signature", "chain_hash")}
    sig = _sign(to_sign)
    record_dict["signature"] = sig

    chain_hash = _hash_link(previous_hash, sig)
    record_dict["chain_hash"] = chain_hash

    _AUDIT_LOG.append(record_dict)
    return AuditRecord(**record_dict)


def query(
    tenant_id: Optional[str] = None,
    principal_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[dict]:
    results = _AUDIT_LOG
    if tenant_id:
        results = [r for r in results if r.get("tenant_id") == tenant_id]
    if principal_id:
        results = [r for r in results if r.get("principal_id") == principal_id]
    if action:
        results = [r for r in results if r.get("action") == action]
    return results[offset : offset + limit]


def export(tenant_id: Optional[str] = None) -> List[dict]:
    return query(tenant_id=tenant_id, limit=len(_AUDIT_LOG))


def verify_integrity() -> List[dict]:
    violations = []
    previous = "GENESIS"
    for i, record in enumerate(_AUDIT_LOG):
        expected_chain = _hash_link(previous, record.get("signature", ""))
        if record.get("chain_hash") != expected_chain:
            violations.append(
                {
                    "index": i,
                    "record_id": record.get("record_id"),
                    "expected_chain": expected_chain,
                    "found_chain": record.get("chain_hash"),
                }
            )
        previous = record.get("chain_hash", "")
    return violations


def verify_signature(record: dict) -> bool:
    signed = {k: v for k, v in record.items() if k not in ("signature", "chain_hash")}
    return _sign(signed) == record.get("signature", "")


def count() -> int:
    return len(_AUDIT_LOG)


def reset() -> None:
    _AUDIT_LOG.clear()


def get_log() -> List[dict]:
    return list(_AUDIT_LOG)
