"""Phase G1 — SwarmCoordinator implementation.  # RULE-1 # RULE-6

Coordinates swarm intelligence for multi-intent planning.
Assigns roles to worker intents and merges results via consensus.

Ref: Canon RULE 1 (Determinism), RULE 6 (Autonomy Constraints)
Ref: artifacts/design/g1/02_models.md §4
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.planning_models import SwarmIntent

logger = logging.getLogger("emo_ai.orchestration.swarm_coordinator")


class SwarmCoordinator:  # RULE-6
    """Coordinates swarm intelligence for plan synthesis.

    Assigns roles to worker intents, resolves conflicts via
    confidence-weighted consensus, and returns merged results.

    All methods are deterministic (sorted inputs, no randomness).
    """

    CONSENSUS_CONFIDENCE_THRESHOLD = 0.6

    def resolve(  # RULE-1
        self,
        intents: List[SwarmIntent],
    ) -> List[SwarmIntent]:
        if not intents:
            return []

        merged: Dict[str, List[SwarmIntent]] = {}
        for intent in intents:
            key = intent.tool_name or "unknown"
            if key not in merged:
                merged[key] = []
            merged[key].append(intent)

        result: List[SwarmIntent] = []
        for tool_name, group in merged.items():
            consensus = self._weighted_consensus(group)
            if consensus is not None and (
                consensus.confidence or 0.0
            ) >= self.CONSENSUS_CONFIDENCE_THRESHOLD:
                result.append(consensus)
        return result

    def assign_role(  # RULE-6
        self,
        intent: SwarmIntent,
    ) -> str:
        if intent.confidence and intent.confidence >= 0.8:
            return "leader"
        elif intent.confidence and intent.confidence >= 0.5:
            return "contributor"
        return "observer"

    def _weighted_consensus(  # RULE-1
        self,
        group: List[SwarmIntent],
    ) -> Optional[SwarmIntent]:
        if not group:
            return None
        sorted_group = sorted(
            group,
            key=lambda i: i.confidence if i.confidence is not None else 0.0,
            reverse=True,
        )
        return sorted_group[0]

    def reset(self) -> None:
        pass
