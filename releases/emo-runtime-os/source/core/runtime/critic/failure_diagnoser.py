"""Phase G2 — Failure Diagnoser.  # LAW-7 LAW-12 RULE-1 RULE-5

Concrete implementation of IFailureDiagnoser.

Matches failure traces against known signatures, isolates root causes,
and rates confidence deterministically (RULE 1).

Ref: Canon LAW 7, LAW 12, RULE 1, RULE 5
Ref: artifacts/design/g2/protocols/01_critic_protocols.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

from core.runtime.models.critic_models import (
    DiagnosisReport,
    FailureSignature,
    SeverityLevel,
)

logger = logging.getLogger("emo_ai.critic.failure_diagnoser")


class FailureDiagnoser:  # LAW-7 LAW-12
    """Matches failure traces against known signatures and isolates root causes.

    All methods are deterministic (RULE 1). No global state (LAW 11).
    """

    def __init__(self) -> None:
        self._signatures: Dict[str, FailureSignature] = {}

    def register_signature(self, signature: FailureSignature) -> None:
        self._signatures[signature.signature_id] = signature

    def remove_signature(self, signature_id: str) -> None:
        self._signatures.pop(signature_id, None)

    def list_signatures(self) -> List[FailureSignature]:
        return list(self._signatures.values())

    # ── analyze_error_pattern ───────────────────────────────────

    def analyze_error_pattern(  # LAW-7
        self,
        trace: Dict[str, Any],
        known_patterns: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        patterns = known_patterns or [
            {"pattern_id": s.signature_id, "regex": s.stack_pattern, "category": s.category}
            for s in self._signatures.values()
        ]

        stack = trace.get("stack_pattern", "")
        error_type = trace.get("error_type", "")

        best_match = {"matched_pattern_id": "", "category": "unknown", "match_confidence": 0.0}

        for pattern in patterns:
            regex = pattern.get("regex", "")
            if regex and re.search(regex, stack, re.IGNORECASE):
                conf = self._compute_pattern_confidence(pattern, error_type, stack)
                if conf > best_match["match_confidence"]:
                    best_match = {
                        "matched_pattern_id": pattern.get("pattern_id", ""),
                        "category": pattern.get("category", "unknown"),
                        "match_confidence": conf,
                    }

        return best_match

    # ── match_failure_signature ─────────────────────────────────

    def match_failure_signature(  # LAW-7
        self,
        error_type: str,
        stack_pattern: str,
        resource_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        best: Dict[str, Any] = {
            "signature_id": "",
            "label": "",
            "severity": "info",
            "match_score": 0.0,
        }

        for sid, sig in self._signatures.items():
            score = self._compute_signature_score(sig, error_type, stack_pattern, resource_state)
            if score > best["match_score"]:
                best = {
                    "signature_id": sid,
                    "label": sig.label,
                    "severity": sig.severity.value,
                    "match_score": score,
                }

        return best

    # ── isolate_root_cause ──────────────────────────────────────

    def isolate_root_cause(  # LAW-12
        self,
        trace: Dict[str, Any],
        signature: Dict[str, Any],
    ) -> Dict[str, Any]:
        trace_nodes = trace.get("nodes", []) if isinstance(trace, dict) else []
        sorted_nodes = sorted(
            trace_nodes,
            key=lambda n: n.get("timestamp", 0) if isinstance(n, dict) else 0,
        )

        root_cause_node = ""
        root_cause_type = "unknown"
        evidence_chain: List[Dict[str, Any]] = []

        if sorted_nodes:
            first = sorted_nodes[0] if isinstance(sorted_nodes[0], dict) else {}
            root_cause_node = first.get("node_id", "")
            root_cause_type = first.get("status", "error")

        for node in sorted_nodes[:3]:
            if isinstance(node, dict):
                evidence_chain.append({
                    "node_id": node.get("node_id", ""),
                    "timestamp": node.get("timestamp", 0),
                    "status": node.get("status", ""),
                })

        if not evidence_chain and trace.get("error_type"):
            evidence_chain.append({
                "node_id": "root",
                "timestamp": trace.get("timestamp", 0),
                "status": trace.get("error_type", "error"),
            })

        return {
            "root_cause_node": root_cause_node,
            "root_cause_type": root_cause_type,
            "evidence_chain": evidence_chain,
        }

    # ── rate_confidence ─────────────────────────────────────────

    def rate_confidence(  # RULE-1
        self,
        evidence_chain: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> float:
        if not evidence_chain:
            return 0.0

        chain_len = len(evidence_chain)
        severity_weight = 1.0
        if context and "severity" in context:
            sev = context["severity"]
            if sev in ("critical", "error"):
                severity_weight = 1.0
            elif sev == "warning":
                severity_weight = 0.85
            else:
                severity_weight = 0.5

        base = min(chain_len / 3.0, 1.0)
        return round(min(base * severity_weight, 1.0), 4)

    # ── diagnose (convenience) ──────────────────────────────────

    def diagnose(  # LAW-12
        self,
        plan_id: str,
        trace: Dict[str, Any],
        critic_trace_id: str = "",
    ) -> DiagnosisReport:
        pattern = self.analyze_error_pattern(trace)
        error_type = trace.get("error_type", "")
        stack_pattern = trace.get("stack_pattern", "")
        resource_state = trace.get("resource_state", {})
        signature = self.match_failure_signature(error_type, stack_pattern, resource_state)
        root_cause = self.isolate_root_cause(trace, signature)
        evidence = root_cause.get("evidence_chain", [])
        confidence = self.rate_confidence(evidence)

        severity = SeverityLevel.ERROR
        if signature.get("severity") in ("critical", "error", "warning", "info"):
            severity = SeverityLevel(signature["severity"])

        return DiagnosisReport(
            plan_id=plan_id,
            critic_trace_id=critic_trace_id,
            failure_trace=trace,
            root_cause=root_cause.get("root_cause_type", "unknown"),
            root_cause_node=root_cause.get("root_cause_node", ""),
            correction_suggestion=signature.get("label", ""),
            confidence_score=confidence,
            severity_level=severity,
            evidence_chain=evidence,
            matched_signature_id=pattern.get("matched_pattern_id", ""),
        )

    # ── Internal helpers (deterministic) ────────────────────────

    def _compute_pattern_confidence(
        self,
        pattern: Dict[str, Any],
        error_type: str,
        stack: str,
    ) -> float:
        score = 0.0
        if pattern.get("regex") and re.search(pattern["regex"], stack, re.IGNORECASE):
            score += 0.6
        if pattern.get("category", "").lower() in error_type.lower():
            score += 0.3
        return min(score, 1.0)

    def _compute_signature_score(
        self,
        sig: FailureSignature,
        error_type: str,
        stack_pattern: str,
        resource_state: Dict[str, Any],
    ) -> float:
        score = 0.0
        if sig.error_type and sig.error_type.lower() in error_type.lower():
            score += 0.4
        if sig.stack_pattern and re.search(sig.stack_pattern, stack_pattern, re.IGNORECASE):
            score += 0.4
        if sig.resource_state:
            match_count = sum(
                1 for k, v in sig.resource_state.items()
                if abs(resource_state.get(k, 0.0) - v) / max(v, 0.01) < 0.2
            )
            score += 0.2 * (match_count / max(len(sig.resource_state), 1))
        return min(score, 1.0)
