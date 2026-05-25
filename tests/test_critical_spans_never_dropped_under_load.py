"""Phase F4 — Critical Spans Never Dropped Under Load: Tests.  # LAW-5 # RULE-3

Verifies that BackpressureSampler preserves CRITICAL and ERROR
spans at all buffer usage levels.

Ref: Canon LAW 5 (Observability), RULE 3 (Recoverability)
Ref: artifacts/design/f4/04_integration_blueprint.md §3.3
"""

import pytest

from core.runtime.observability.backpressure_sampler import BackpressureSampler
from core.runtime.models.observability_models import Severity


class TestCriticalSpansNeverDroppedUnderLoad:
    """Backpressure sampler protects CRITICAL and ERROR spans."""

    def test_critical_always_samples_at_low_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.30)
        assert sampler.should_sample(Severity.CRITICAL)
        assert sampler.dropped_critical == 0

    def test_critical_always_samples_at_moderate_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.60)
        for _ in range(100):
            assert sampler.should_sample(Severity.CRITICAL)
        assert sampler.dropped_critical == 0

    def test_critical_always_samples_at_high_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.85)
        for _ in range(100):
            assert sampler.should_sample(Severity.CRITICAL)
        assert sampler.dropped_critical == 0

    def test_critical_always_samples_at_critical_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.99)
        for _ in range(100):
            assert sampler.should_sample(Severity.CRITICAL)
        assert sampler.dropped_critical == 0

    def test_warning_always_samples_at_all_levels(self):
        sampler = BackpressureSampler()
        for pct in [0.30, 0.60, 0.85, 0.99]:
            sampler.adaptive_sampling(pct)
            assert sampler.should_sample(Severity.WARNING)

    def test_debug_dropped_at_high_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.85)
        results = [sampler.should_sample(Severity.DEBUG) for _ in range(200)]
        assert not all(results)  # at least some dropped
        assert sampler.dropped_count > 0

    def test_info_reduced_at_critical_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.99)
        results = [sampler.should_sample(Severity.INFO) for _ in range(200)]
        assert all(not r for r in results)  # all dropped at >= 95%
        assert sampler.dropped_count > 0

    def test_adaptive_sampling_rates_low_load(self):
        sampler = BackpressureSampler()
        rates = sampler.adaptive_sampling(0.30)
        assert rates["critical"] == 1.0
        assert rates["warning"] == 1.0
        assert rates["info"] == 1.0
        assert rates["debug"] == 1.0

    def test_adaptive_sampling_rates_critical_load(self):
        sampler = BackpressureSampler()
        rates = sampler.adaptive_sampling(0.99)
        assert rates["critical"] == 1.0
        assert rates["warning"] == 1.0
        assert rates["info"] == 0.0
        assert rates["debug"] == 0.0

    def test_reset_clears_dropped_counts(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.99)
        sampler.should_sample(Severity.DEBUG)
        assert sampler.dropped_count > 0
        sampler.reset()
        assert sampler.dropped_count == 0

    def test_critical_span_logs_warning_if_dropped_attempt(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.99)
        sampler._sample_rates["critical"] = 0.0  # force violation
        result = sampler.should_sample(Severity.CRITICAL)
        assert not result
        assert sampler.dropped_critical == 1
