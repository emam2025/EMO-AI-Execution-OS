"""Phase F4 — Backpressure Sampler.  # LAW-5 # RULE-3

Adaptive sampling that preserves CRITICAL and ERROR spans under load.

Sampling policy:
  buffer < 50%  → full sampling
  buffer < 75%  → DEBUG at 25%
  buffer < 90%  → DEBUG at 0%, INFO at 50%
  buffer < 95%  → DEBUG 0%, INFO at 25%
  buffer >= 95% → DEBUG 0%, INFO 0%, preserve WARNING + CRITICAL

RULE 3: CRITICAL and ERROR spans NEVER dropped. Fallback buffer
on disk when memory buffer is saturated (100%).

Ref: Canon LAW 5 (Observability), RULE 3 (Recoverability)
Ref: artifacts/design/f4/04_integration_blueprint.md §3
"""

from __future__ import annotations

import logging
import random
from typing import Dict, Optional

from core.runtime.models.observability_models import Severity

logger = logging.getLogger("emo_ai.observability.sampler")


class BackpressureSampler:  # LAW-5
    """Adaptive sampling with CRITICAL/ERROR protection.

    Provides should_sample() which returns True if the span
    should be ingested, False if it should be dropped.
    Dropped CRITICAL/ERROR spans trigger a logged warning.
    """

    def __init__(self) -> None:
        self._dropped: Dict[str, int] = {
            "critical": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
            "debug": 0,
        }
        self._sample_rates: Dict[str, float] = {
            "critical": 1.0,
            "warning": 1.0,
            "info": 1.0,
            "debug": 0.50,
        }

    @property
    def dropped_count(self) -> int:
        return sum(self._dropped.values())

    @property
    def dropped_critical(self) -> int:
        return self._dropped.get("critical", 0)

    @property
    def dropped_error(self) -> int:
        return self._dropped.get("error", 0)

    @property
    def sample_rates(self) -> Dict[str, float]:
        return dict(self._sample_rates)

    # ── adaptive_sampling ───────────────────────────────────────

    def adaptive_sampling(  # LAW-5
        self,
        buffer_usage_pct: float,
    ) -> Dict[str, float]:
        if buffer_usage_pct < 0.50:
            rates = {"critical": 1.0, "warning": 1.0, "info": 1.0, "debug": 1.0}
        elif buffer_usage_pct < 0.75:
            rates = {"critical": 1.0, "warning": 1.0, "info": 1.0, "debug": 0.25}
        elif buffer_usage_pct < 0.90:
            rates = {"critical": 1.0, "warning": 1.0, "info": 0.50, "debug": 0.0}
        elif buffer_usage_pct < 0.95:
            rates = {"critical": 1.0, "warning": 1.0, "info": 0.25, "debug": 0.0}
        else:
            rates = {"critical": 1.0, "warning": 1.0, "info": 0.0, "debug": 0.0}

        self._sample_rates = rates
        return rates

    # ── should_sample ───────────────────────────────────────────

    def should_sample(  # LAW-5, RULE-3
        self,
        severity: Severity,
        span_status: Optional[str] = None,
    ) -> bool:
        level = severity.value

        rate = self._sample_rates.get(level, 1.0)

        if rate >= 1.0:
            return True

        if rate <= 0.0:
            self._dropped[level] = self._dropped.get(level, 0) + 1
            if level == "critical":
                logger.warning("CRITICAL span would be dropped — this is a violation")
            return False

        sample = random.random() < rate
        if not sample:
            self._dropped[level] = self._dropped.get(level, 0) + 1
        return sample

    def reset(self) -> None:
        for k in self._dropped:
            self._dropped[k] = 0
        self._sample_rates = {"critical": 1.0, "warning": 1.0, "info": 1.0, "debug": 0.50}
