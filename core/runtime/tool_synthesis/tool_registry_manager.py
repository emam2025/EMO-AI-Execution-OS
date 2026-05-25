"""Phase G4 — Tool Registry Manager.  # LAW-2 LAW-14 RULE-3

Manages auto-registration of synthesised tools in the ToolRegistry,
compliance validation, rollback, and EventBus notification.

Ref: Canon LAW 2 (Interface Authority), LAW 14 (Resource Governance)
Ref: Canon RULE 3 (Safety Guards)
Ref: artifacts/design/g4/protocols/01_tool_synthesis_protocols.py
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.synthesis.tool_registry_manager")

COMPLIANCE_GUARDS: List[str] = [
    "ast_hash_matches",
    "capability_set_non_empty",
    "risk_score_within_limit",
    "sandbox_success",
    "no_side_effects",
]


class ToolRegistryManager:  # LAW-2 LAW-14 RULE-3
    """Concrete implementation of IToolRegistryManager.

    RULE 3: Registration MUST be rejected if any safety guard fails.
    LAW 2:  All registered tools MUST conform to Interface Authority.
    LAW 14: Registration metadata MUST include ast_hash for traceability.
    """

    def __init__(self) -> None:
        self._registrations: Dict[str, Dict[str, Any]] = {}
        self._rollback_tokens: Dict[str, str] = {}

    def register_synthesized_tool(
        self,
        tool_metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Register a synthesised tool in ToolRegistry.

        RULE 3: Rejects if any compliance guard fails.
        """
        compliant = self.validate_registration_compliance(tool_metadata)

        if not compliant:
            return {
                "registration_id": "",
                "status": "rejected",
                "rollback_token": "",
            }

        tool_id = tool_metadata.get("tool_id", f"syn_{uuid.uuid4().hex[:12]}")
        registration_id = f"reg_{uuid.uuid4().hex[:16]}"
        rollback_token = f"rb_{hashlib.sha256(f'{tool_id}:{registration_id}'.encode()).hexdigest()[:24]}"

        self._registrations[tool_id] = {
            "registration_id": registration_id,
            "tool_id": tool_id,
            "metadata": tool_metadata,
            "status": "registered",
        }
        self._rollback_tokens[rollback_token] = tool_id

        return {
            "registration_id": registration_id,
            "status": "registered",
            "rollback_token": rollback_token,
        }

    def validate_registration_compliance(
        self,
        tool_metadata: Dict[str, Any],
    ) -> bool:
        """Validate all registration guards pass (RULE 3).

        Guards (all MUST pass):
          - ast_hash matches generated_code
          - capability_set is non-empty
          - estimated_risk_score <= 0.3
          - sandbox_results.success == true
          - sandbox_results.side_effects list is empty
        """
        computed_hash = hashlib.sha256(
            tool_metadata.get("generated_code", "").encode()
        ).hexdigest()
        declared_hash = tool_metadata.get("ast_hash", "")

        if declared_hash and computed_hash != declared_hash:
            logger.warning("Compliance guard failed: ast_hash mismatch")
            return False

        if not tool_metadata.get("capability_set", []):
            logger.warning("Compliance guard failed: empty capability_set")
            return False

        if tool_metadata.get("estimated_risk_score", 1.0) > 0.3:
            logger.warning(
                "Compliance guard failed: risk_score %.2f > 0.3",
                tool_metadata["estimated_risk_score"],
            )
            return False

        sandbox = tool_metadata.get("sandbox_results", {})
        if not sandbox.get("success", False):
            logger.warning("Compliance guard failed: sandbox dry-run not successful")
            return False

        if sandbox.get("side_effects", []):
            logger.warning(
                "Compliance guard failed: %d side effects detected",
                len(sandbox["side_effects"]),
            )
            return False

        return True

    def publish_tool_available_event(
        self,
        tool_id: str,
        signature: Dict[str, Any],
    ) -> None:
        """Publish a tool.available event (logged; EventBus in production)."""
        logger.info(
            "Tool available: tool_id=%s signature=%s",
            tool_id,
            json.dumps(signature, default=str),
        )

    def rollback_registration(
        self,
        tool_id: str,
        rollback_token: str,
    ) -> bool:
        """Roll back a tool registration.

        Removal sequence:
          1. Remove from ToolRegistry index
          2. Log rollback event
          3. Return True on success; False if token is invalid
        """
        expected_tool = self._rollback_tokens.get(rollback_token)

        if expected_tool != tool_id:
            logger.warning(
                "Rollback failed: token %s does not match tool_id %s",
                rollback_token[:8], tool_id,
            )
            return False

        if tool_id not in self._registrations:
            logger.warning("Rollback failed: tool_id %s not registered", tool_id)
            return False

        del self._registrations[tool_id]
        del self._rollback_tokens[rollback_token]

        logger.info("Rollback succeeded: tool_id=%s unregistered", tool_id)
        return True

    def is_registered(self, tool_id: str) -> bool:
        """Check if a tool is currently registered."""
        return tool_id in self._registrations
