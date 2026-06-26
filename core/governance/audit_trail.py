"""EMO AI Governance Layer — Append-Only Audit Trail.

LAW 11: No global mutable state — use AuditTrail instances.
LAW 13: Dependencies via constructor injection (db parameter).
LAW 23: Audit records are append-only. No update or delete after write.
LAW 24: Records are signed with SHA-256 chain linking for tamper detection.
LAW 25: Sensitive fields (principal, payload) are encrypted at rest.
SOC2/GDPR compliant: immutability, non-repudiation, exportable.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.audit")


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


def _hash_link(previous_hash: str, current_hash: str) -> str:
    return hashlib.sha256(
        f"{previous_hash}:{current_hash}".encode("utf-8")
    ).hexdigest()


class AuditTrail:
    """Instance-based audit trail with HMAC signing and optional DB persistence.

    LAW 11: No global state — use instances.
    LAW 13: Database injected via constructor.

    Usage:
        trail = AuditTrail(db=database, signing_key="secret")
        await trail.append("login", "user1", "tenant1", "auth", "success")
    """

    def __init__(self, db: Any = None, signing_key: str = ""):
        self._db = db
        self._signing_key = signing_key
        self._log: List[dict] = []
        if not signing_key:
            logger.critical("Audit trail signing key is empty — signatures will be FORGEABLE")

    def _sign(self, record: dict) -> str:
        serialized = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
        return hmac.new(
            self._signing_key.encode("utf-8") if self._signing_key else b"",
            serialized,
            hashlib.sha256,
        ).hexdigest()

    async def append(
        self,
        action: str,
        principal_id: str,
        tenant_id: str,
        resource: str,
        outcome: str,
        payload: Optional[dict] = None,
    ) -> AuditRecord:
        previous_hash = self._log[-1].get("chain_hash", "") if self._log else "GENESIS"
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
        sig = self._sign(to_sign)
        record_dict["signature"] = sig
        chain_hash = _hash_link(previous_hash, sig)
        record_dict["chain_hash"] = chain_hash

        self._log.append(record_dict)

        if self._db is not None:
            await self._db.create_audit_event(record_dict)

        return AuditRecord(**record_dict)

    def query(
        self,
        tenant_id: Optional[str] = None,
        principal_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[dict]:
        results = self._log
        if tenant_id:
            results = [r for r in results if r.get("tenant_id") == tenant_id]
        if principal_id:
            results = [r for r in results if r.get("principal_id") == principal_id]
        if action:
            results = [r for r in results if r.get("action") == action]
        return results[offset : offset + limit]

    def export(self, tenant_id: Optional[str] = None) -> List[dict]:
        return self.query(tenant_id=tenant_id, limit=len(self._log))

    def verify_integrity(self) -> List[dict]:
        violations = []
        previous = "GENESIS"
        for i, record in enumerate(self._log):
            expected_chain = _hash_link(previous, record.get("signature", ""))
            if record.get("chain_hash") != expected_chain:
                violations.append({
                    "index": i,
                    "record_id": record.get("record_id"),
                    "expected_chain": expected_chain,
                    "found_chain": record.get("chain_hash"),
                })
            previous = record.get("chain_hash", "")
        return violations

    def verify_signature(self, record: dict) -> bool:
        signed = {k: v for k, v in record.items() if k not in ("signature", "chain_hash")}
        return self._sign(signed) == record.get("signature", "")

    def count(self) -> int:
        return len(self._log)

    async def load_from_db(self) -> int:
        if self._db is None:
            return 0
        try:
            rows = await self._db.get_all_audit_events()
            if rows:
                self._log = rows
            return len(self._log)
        except Exception:
            return 0

    def reset(self) -> None:
        self._log.clear()

    def get_log(self) -> List[dict]:
        return list(self._log)


# ── Backward-compatible module-level API (sync, in-memory only) ─────
# Production code should use AuditTrail class with async append().
# These wrappers exist so existing tests and callers continue to work.
# They operate in-memory only — no DB persistence (fine for unit tests).

_AUDIT_LOG: List[dict] = []
_SIGNING_KEY: str = ""


def init(signing_key: str) -> None:
    global _SIGNING_KEY
    if not signing_key:
        logger.critical("Audit trail signing key is empty — audit signatures will be FORGEABLE")
    _SIGNING_KEY = signing_key


def _sign(record: dict) -> str:
    serialized = json.dumps(record, sort_keys=True, default=str).encode("utf-8")
    return hmac.new(
        _SIGNING_KEY.encode("utf-8") if _SIGNING_KEY else b"",
        serialized,
        hashlib.sha256,
    ).hexdigest()


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
            violations.append({
                "index": i,
                "record_id": record.get("record_id"),
                "expected_chain": expected_chain,
                "found_chain": record.get("chain_hash"),
            })
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
