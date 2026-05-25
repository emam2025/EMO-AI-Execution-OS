"""Phase F3 — Quota Arbitrator implementation.  # LAW-10 # LAW-11

Implements IQuotaArbitrator: check_quota, consume_usage, enforce_limit,
refund_on_failure.

Three-tier quota: execution, worker, global.
Soft limit warns, hard limit rejects.

Ref: Canon LAW 10 (Resource limits), LAW 11 (No global state), RULE 2 (Reversibility)
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from core.runtime.models.resource_scheduler_models import (
    PriorityTier,
    QuotaPolicy,
    QuotaType,
    QuotaUsage,
    ResourceRequest,
)

logger = logging.getLogger("emo_ai.resource_scheduler.quota")


class QuotaArbitrator:  # ←→ IQuotaArbitrator
    """Enforces resource quotas at execution, worker, and global levels.

    LAW 10: Hard limit enforced — consumption ≥ hard_limit → reject.
    LAW 11: No global state — per-instance quotas.
    RULE 2: refund_on_failure reverses consumption.
    RULE 5: consume_usage is idempotent per execution_id.
    """

    def __init__(self) -> None:
        self._usages: Dict[str, QuotaUsage] = {}
        self._cooldowns: Dict[str, float] = {}

    # ── check_quota ───────────────────────────────────────────

    def check_quota(  # LAW-10
        self,
        execution_id: str,
        request: ResourceRequest,
        policy: QuotaPolicy,
    ) -> bool:
        now = time.time()
        cooldown_until = self._cooldowns.get(execution_id, 0.0)
        if now < cooldown_until:
            logger.debug("Cooldown active for %s", execution_id)
            return False

        usage = self._usages.get(execution_id, QuotaUsage(
            execution_id=execution_id,
            cpu_used=0.0,
            mem_used=0,
        ))

        new_cpu = usage.cpu_used + request.cpu_cores
        new_mem = usage.mem_used + request.memory_mb

        if policy.type == QuotaType.EXECUTION:
            if new_cpu > policy.hard_limit or new_mem > policy.hard_limit:
                return False

        if policy.type == QuotaType.GLOBAL:
            if new_cpu > policy.hard_limit:
                return False

        return True

    # ── consume_usage ─────────────────────────────────────────

    def consume_usage(  # LAW-10, RULE-5
        self,
        execution_id: str,
        request: ResourceRequest,
    ) -> QuotaUsage:
        if execution_id in self._usages:
            logger.debug("Usage already recorded for %s (idempotent)", execution_id)
            return self._usages[execution_id]

        usage = QuotaUsage(
            execution_id=execution_id,
            cpu_used=request.cpu_cores,
            mem_used=request.memory_mb,
            gpu_used=request.gpu_memory_mb,
            io_used=request.io_bandwidth,
            percentage=0.0,
        )
        self._usages[execution_id] = usage
        return usage

    # ── enforce_limit ─────────────────────────────────────────

    def enforce_limit(  # LAW-10
        self,
        execution_id: str,
        usage: QuotaUsage,
        policy: QuotaPolicy,
    ) -> bool:
        cpu_pct = (usage.cpu_used / max(policy.limit, 1)) * 100.0

        if cpu_pct >= policy.hard_limit:
            self._cooldowns[execution_id] = time.time() + policy.cooldown_sec
            logger.warning("Hard limit hit for %s: %.1f%%", execution_id, cpu_pct)
            return False

        if cpu_pct >= policy.soft_limit:
            logger.info("Soft limit warning for %s: %.1f%%", execution_id, cpu_pct)

        usage.percentage = min(100.0, cpu_pct)
        return True

    # ── refund_on_failure ─────────────────────────────────────

    def refund_on_failure(  # RULE-2, RULE-3
        self,
        execution_id: str,
        usage: QuotaUsage,
    ) -> QuotaUsage:
        if execution_id in self._usages:
            del self._usages[execution_id]

        refunded = QuotaUsage(
            execution_id=execution_id,
            cpu_used=0.0,
            mem_used=0,
            gpu_used=0,
            percentage=0.0,
        )
        logger.info("Quota refunded for %s", execution_id)
        return refunded

    @property
    def active_usage(self) -> Dict[str, QuotaUsage]:
        return dict(self._usages)

    def reset(self) -> None:
        self._usages.clear()
        self._cooldowns.clear()
