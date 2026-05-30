"""
Skill Extraction Protocol — ISkillExtractor (Interface Only).

Defines the contract for extracting reusable skill patterns from
traces stored in R2 Memory. No implementation, no storage, no runtime
side effects.

LAW-6: every public method requires tenant_id.
LAW-11: every result is scoped by tenant_id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ISkillDraft(Protocol):
    """Minimal read-only view of a draft extracted from a trace."""

    skill_name: str
    pattern_hash: str
    confidence_score: float
    tenant_id: str
    source_trace_id: str
    blueprint_steps: List[dict]


class ISkillExtractor(ABC):
    """Contract for extracting skill drafts from execution traces.

    Implementations receive a trace_id and validate patterns.
    No mutation of R2 memory or any runtime state.
    """

    @abstractmethod
    def extract_from_trace(
        self,
        trace_id: str,
        tenant_id: str,
        project_id: str,
    ) -> ISkillDraft:
        """Analyse a cognitive trace and produce a SkillDraft.

        Args:
            trace_id:   Identifier of the source trace in R2.
            tenant_id:  LAW-6 mandatory tenant scope.
            project_id: Narrow to a single project (may be "" for all).

        Returns:
            ISkillDraft with extracted pattern and confidence.

        Raises:
            ValueError: If tenant_id is empty (LAW-6).
            TraceNotFoundError: If trace_id does not exist.
        """
        ...

    @abstractmethod
    def validate_pattern(self, pattern: dict, tenant_id: str) -> bool:
        """Validate that a pattern meets structural and safety criteria.

        Args:
            pattern:   The extracted pattern dict.
            tenant_id: LAW-6 mandatory tenant scope.

        Returns:
            True if the pattern is structurally valid.
        """
        ...

    @abstractmethod
    def list_extractable_traces(
        self,
        tenant_id: str,
        project_id: str,
        min_confidence: float = 0.0,
        limit: int = 20,
    ) -> List[str]:
        """Return trace_ids eligible for extraction.

        LAW-11: results are filtered by tenant_id + project_id.
        """
        ...
