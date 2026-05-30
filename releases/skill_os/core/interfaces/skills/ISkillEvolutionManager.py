"""
Skill Evolution Manager Protocol — ISkillEvolutionManager (Interface Only).

Defines the contract for promoting, deprecating, and tracing the
evolution lifecycle of skills: Draft → Verified → Optimized → Deprecated.

LAW-6: every public method requires tenant_id.
LAW-11: isolation by tenant_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable

from releases.skill_os.core.models.skills import SkillEvolutionRecord, SkillNode, SkillTier


class ISkillEvolutionManager(ABC):
    """Contract for managing the skill evolution lifecycle.

    No mutation of R2 memory or any runtime state.
    """

    @abstractmethod
    def promote(
        self,
        skill_id: str,
        new_tier: SkillTier,
        tenant_id: str,
        validator_signature: str = "",
    ) -> SkillEvolutionRecord:
        """Promote a skill to a higher tier.

        Args:
            skill_id:          Target skill identifier.
            new_tier:          Target tier (Draft → Verified → Optimized).
            tenant_id:         LAW-6 mandatory tenant scope.
            validator_signature: Optional cryptographic proof.

        Returns:
            SkillEvolutionRecord documenting the promotion.

        Raises:
            ValueError: If tenant_id is empty (LAW-6).
            SkillNotFoundError: If skill_id does not exist.
            InvalidTransitionError: If the tier transition is illegal.
        """
        ...

    @abstractmethod
    def deprecate(
        self,
        skill_id: str,
        reason: str,
        tenant_id: str,
    ) -> SkillEvolutionRecord:
        """Deprecate a skill, moving it to the Deprecated tier.

        Args:
            skill_id:  Target skill identifier.
            reason:    Human-readable deprecation reason.
            tenant_id: LAW-6 mandatory tenant scope.

        Returns:
            SkillEvolutionRecord documenting the deprecation.
        """
        ...

    @abstractmethod
    def get_evolution_history(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> List[SkillEvolutionRecord]:
        """Return the full evolution history for a skill.

        Results are scoped by tenant_id (LAW-11).
        """
        ...

    @abstractmethod
    def current_tier(
        self,
        skill_id: str,
        tenant_id: str,
    ) -> SkillTier:
        """Return the current tier of a skill."""
        ...
