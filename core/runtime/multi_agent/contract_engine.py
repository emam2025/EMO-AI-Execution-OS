"""Phase G5 — Agent Contract Engine.  # LAW-24 LAW-25 RULE-3

Manages capability negotiation and contract lifecycle between agents.

All negotiation flows through the Dispatcher (LAW 24) via
stateless protocol calls (LAW 25) — no direct agent-to-agent refs.

Ref: Canon LAW 24 (Dispatcher Ownership), LAW 25 (Message Boundaries)
Ref: Canon RULE 3 (Safety Guards)
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional, Set

from core.runtime.models.multiagent_models import (
    BreachSeverity,
    ContractAgreementStatus,
)

logger = logging.getLogger("emo_ai.multiagent.contract_engine")


class AgentContractEngine:  # LAW-24 LAW-25 RULE-3
    """Manages capability negotiation, contract signing, and breach detection."""

    def __init__(self) -> None:
        self._contracts: Dict[str, Dict[str, Any]] = {}

    # ── negotiate_capabilities ──────────────────────────────────

    def negotiate_capabilities(  # LAW-24
        self, req: Dict[str, Any], offer: Dict[str, Any], mission_trace_id: str = "",
    ) -> Dict[str, Any]:
        req_caps = set(req.get("requested_caps", []))
        offer_caps = set(offer.get("offered_caps", []))

        matched = req_caps & offer_caps
        gaps = req_caps - offer_caps
        excess = offer_caps - req_caps
        score = len(matched) / max(len(req_caps | offer_caps), 1)

        return {
            "match_score": round(score, 4),
            "matched_capabilities": sorted(matched),
            "gaps": sorted(gaps),
            "excess": sorted(excess),
            "mission_trace_id": mission_trace_id,
        }

    # ── validate_contract_terms ─────────────────────────────────

    def validate_contract_terms(  # RULE-3
        self, terms: Dict[str, Any],
    ) -> Dict[str, Any]:
        violations: List[str] = []

        duration = terms.get("duration_sec", 0)
        if duration <= 0:
            violations.append("Duration must be positive")
        elif duration > 86400:
            violations.append("Duration exceeds max (86400s)")

        resource_cpu = terms.get("resource_cpu_sec", 0)
        if resource_cpu <= 0:
            violations.append("CPU quota must be positive")
        elif resource_cpu > 3600:
            violations.append("CPU quota exceeds max")

        offered = terms.get("offered_caps", [])
        profile = terms.get("agent_profile", [])
        for cap in offered:
            if cap not in profile:
                violations.append(f"Capability '{cap}' exceeds agent profile")

        valid = len(violations) == 0
        confidence = 1.0 - min(1.0, len(violations) * 0.2)

        return {
            "valid": valid,
            "violations": violations,
            "confidence": round(max(0.0, confidence), 4),
        }

    # ── sign_agreement ─────────────────────────────────────────

    def sign_agreement(  # LAW-24 LAW-25
        self, contract: Dict[str, Any], signatures: Dict[str, str],
    ) -> Dict[str, Any]:
        contract_id = f"ctr_{uuid.uuid4().hex[:16]}"
        signed_at = time.time_ns()

        self._contracts[contract_id] = {
            "contract_id": contract_id,
            "parties": contract.get("parties", []),
            "terms": contract.get("terms", {}),
            "signed_caps": contract.get("signed_caps", []),
            "status": ContractAgreementStatus.SIGNED.value,
            "signed_at_ns": signed_at,
            "expires_at_ns": signed_at + (contract.get("terms", {}).get("duration_sec", 3600) * 1_000_000_000),
            "mission_trace_id": contract.get("mission_trace_id", ""),
            "dispatcher_signature": signatures.get("dispatcher", ""),
        }

        return {
            "contract_id": contract_id,
            "status": ContractAgreementStatus.SIGNED.value,
            "signed_at_ns": signed_at,
            "mission_trace_id": contract.get("mission_trace_id", ""),
        }

    # ── breach_detection ───────────────────────────────────────

    def breach_detection(  # RULE-3
        self, contract_id: str, evidence: Dict[str, Any],
    ) -> Dict[str, Any]:
        contract = self._contracts.get(contract_id)
        if contract is None:
            return {"breached": True, "severity": BreachSeverity.HIGH.value,
                    "evidence": [{"reason": "Contract not found"}],
                    "recommended_action": "terminate"}

        breach_evidence: List[Dict[str, Any]] = []

        usage = evidence.get("capability_usage", [])
        signed_caps = set(contract.get("signed_caps", []))
        for cap in usage:
            if cap not in signed_caps:
                breach_evidence.append({"type": "capability_exceeded", "detail": f"Used '{cap}' not in contract"})

        resource = evidence.get("resource_usage", {})
        quota = evidence.get("resource_quota", {})
        for key in resource:
            if quota.get(key, 0) > 0 and resource[key] > quota[key]:
                breach_evidence.append({"type": "resource_violation", "detail": f"{key}: {resource[key]} > {quota[key]}"})

        protocol_violation = evidence.get("direct_reference", False)
        if protocol_violation:
            breach_evidence.append({"type": "direct_reference", "detail": "LAW 25: direct agent reference detected"})

        if not breach_evidence:
            return {"breached": False, "severity": BreachSeverity.LOW.value,
                    "evidence": [], "recommended_action": "none"}

        severity = BreachSeverity.HIGH if len(breach_evidence) > 2 else BreachSeverity.MEDIUM
        action = "terminate" if severity == BreachSeverity.HIGH else "renegotiate"

        contract["status"] = ContractAgreementStatus.BREACHED.value

        return {
            "breached": True,
            "severity": severity.value,
            "evidence": breach_evidence,
            "recommended_action": action,
        }

    def get_contract(self, contract_id: str) -> Optional[Dict[str, Any]]:
        return self._contracts.get(contract_id)

    def reset(self) -> None:
        self._contracts.clear()
