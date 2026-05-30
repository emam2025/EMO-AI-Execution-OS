"""
Skill Evolution Manager — ISkillEvolutionManager implementation.

Handles tier promotion/deprecation with mandatory validator_signature,
full audit trail via SkillEvolutionRecord, and strict transition rules.
"""

from __future__ import annotations

import time
import uuid
from typing import List, Optional

from releases.skill_os.core.interfaces.skills.ISkillEvolutionManager import ISkillEvolutionManager
from releases.skill_os.core.models.skills import SkillEvolutionRecord, SkillNode, SkillTier
from releases.skill_os.core.skills.library import SkillLibrary


# ── allowed tier transitions ──────────────────────────────────

_ALLOWED_TRANSITIONS = {
    SkillTier.DRAFT: {SkillTier.VERIFIED, SkillTier.DEPRECATED},
    SkillTier.VERIFIED: {SkillTier.OPTIMIZED, SkillTier.DEPRECATED},
    SkillTier.OPTIMIZED: {SkillTier.DEPRECATED},
    SkillTier.DEPRECATED: set(),
}


class SkillEvolutionManager(ISkillEvolutionManager):
    """Manages skill lifecycle: Draft → Verified → Optimized → Deprecated.

    LAW-6: every public method requires tenant_id.
    """

    def __init__(self, library: SkillLibrary) -> None:
        self._library = library

    @staticmethod
    def _is_valid_transition(from_tier: SkillTier, to_tier: SkillTier) -> bool:
        return to_tier in _ALLOWED_TRANSITIONS.get(from_tier, set())

    def promote(
        self,
        skill_id: str,
        new_tier: SkillTier,
        tenant_id: str,
        validator_signature: str = "",
    ) -> SkillEvolutionRecord:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self._library._entry_exists(skill_id, tenant_id):
            raise KeyError(f"Skill not found: {skill_id}")
        if not validator_signature:
            raise ValueError("validator_signature is required for promotion")

        current = self._library.get(skill_id, tenant_id)
        if not self._is_valid_transition(current.tier, new_tier):
            raise ValueError(
                f"Invalid transition: {current.tier.value} → {new_tier.value}"
            )

        record = SkillEvolutionRecord(
            record_id=f"ev-{uuid.uuid4().hex[:16]}",
            skill_id=skill_id,
            tenant_id=tenant_id,
            from_tier=current.tier,
            to_tier=new_tier,
            reason=f"Promoted from {current.tier.value} to {new_tier.value}",
            validator_signature=validator_signature,
        )
        self._library._update_tier(skill_id, tenant_id, new_tier, record)
        return record

    def deprecate(
        self,
        skill_id: str,
        reason: str,
        tenant_id: str,
        validator_signature: str = "",
    ) -> SkillEvolutionRecord:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        if not self._library._entry_exists(skill_id, tenant_id):
            raise KeyError(f"Skill not found: {skill_id}")
        if not validator_signature:
            raise ValueError("validator_signature is required for deprecation")
        if not reason:
            raise ValueError("reason is required for deprecation")

        current = self._library.get(skill_id, tenant_id)
        if current.tier == SkillTier.DEPRECATED:
            raise ValueError(f"Skill is already deprecated: {skill_id}")

        record = SkillEvolutionRecord(
            record_id=f"ev-{uuid.uuid4().hex[:16]}",
            skill_id=skill_id,
            tenant_id=tenant_id,
            from_tier=current.tier,
            to_tier=SkillTier.DEPRECATED,
            reason=reason,
            validator_signature=validator_signature,
        )
        self._library._update_tier(skill_id, tenant_id, SkillTier.DEPRECATED, record)
        return record

    def get_evolution_history(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> List[SkillEvolutionRecord]:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        return self._library.get_evolution_history(skill_id, tenant_id)

    def current_tier(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> SkillTier:
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        node = self._library.get(skill_id, tenant_id)
        return node.tier
