"""Phase F3 — Topology Mapper implementation.  # LAW-10 # RULE-1

Implements ITopologyMapper: map_to_hardware, check_affinity,
validate_constraints, suggest_fallback.

Scoring algorithm: +1.0 per matched HardwareCapability,
+0.5 per matched affinity_tag, -1.0 for missing required capability.

Ref: Canon LAW 10 (Resource constraints), RULE 1 (Determinism)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from core.runtime.models.resource_scheduler_models import (
    HardwareCapability,
    ResourceOffer,
    ResourceRequest,
    TopologyMapping,
)

logger = logging.getLogger("emo_ai.resource_scheduler.topology")


class TopologyMapper:  # ←→ ITopologyMapper
    """Maps resource requests to hardware topology-aware workers.

    LAW 10: Resource constraints validated before assignment.
    RULE 1: Deterministic scoring — same inputs → same score.
    """

    # ── map_to_hardware ───────────────────────────────────────

    def map_to_hardware(  # LAW-10, RULE-1
        self,
        request: ResourceRequest,
        offers: List[ResourceOffer],
    ) -> TopologyMapping:
        best_score = -float("inf")
        best_offer: Optional[ResourceOffer] = None

        for offer in offers:
            if offer.available_cpu < request.cpu_cores:
                continue
            if offer.available_mem < request.memory_mb:
                continue
            if request.gpu_memory_mb > 0:
                if HardwareCapability.GPU_AVAILABLE not in offer.hardware_topology:
                    continue

            score = 0.0
            if request.gpu_memory_mb > 0:
                if HardwareCapability.GPU_AVAILABLE in offer.hardware_topology:
                    score += 1.0
            if request.io_bandwidth == "high" or request.io_bandwidth == "dedicated":
                if HardwareCapability.HIGH_IO in offer.hardware_topology:
                    score += 1.0
            if request.network_access:
                if HardwareCapability.NETWORK_LOCAL in offer.hardware_topology:
                    score += 1.0

            for tag in offer.affinity_tags:
                if tag in (request.execution_id, request.dag_id):
                    score += 0.5

            fragmentation = 1.0 - (
                offer.available_cpu / max(offer.total_cpu, 1)
            )
            score -= fragmentation * 0.2

            if score > best_score:
                best_score = score
                best_offer = offer

        if best_offer is None:
            return TopologyMapping(
                score=0.0,
                fallback_suggested=True,
                fallback_worker="",
            )

        return TopologyMapping(
            worker_id=best_offer.worker_id,
            score=round(best_score, 4),
            matched_capabilities=best_offer.hardware_topology.copy(),
            fallback_suggested=False,
        )

    # ── check_affinity ────────────────────────────────────────

    def check_affinity(  # LAW-10
        self,
        request: ResourceRequest,
        offer: ResourceOffer,
    ) -> bool:
        for tag in offer.affinity_tags:
            if tag in (request.execution_id, request.dag_id):
                return True
        return False

    # ── validate_constraints ──────────────────────────────────

    def validate_constraints(  # LAW-10
        self,
        request: ResourceRequest,
        offer: ResourceOffer,
    ) -> List[str]:
        violations: List[str] = []
        if offer.available_cpu < request.cpu_cores:
            violations.append(
                f"CPU {offer.available_cpu} < {request.cpu_cores}"
            )
        if offer.available_mem < request.memory_mb:
            violations.append(
                f"Memory {offer.available_mem} < {request.memory_mb}"
            )
        if request.gpu_memory_mb > 0:
            if HardwareCapability.GPU_AVAILABLE not in offer.hardware_topology:
                violations.append("GPU required but not available")
        return violations

    # ── suggest_fallback ──────────────────────────────────────

    def suggest_fallback(  # RULE-3, RULE-2
        self,
        request: ResourceRequest,
        offers: List[ResourceOffer],
    ) -> Optional[ResourceOffer]:
        for offer in offers:
            if offer.available_cpu >= request.cpu_cores:
                if offer.available_mem >= request.memory_mb:
                    return offer
        return None
