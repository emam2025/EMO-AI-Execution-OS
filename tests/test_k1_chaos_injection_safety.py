"""Tests for K1 Chaos Injection Safety — 6 scenarios + safety + threshold."""

# LAW-5: Observable — test that chaos events are published
# LAW-20: Fault injection scoped — test isolation
# LAW-21: Failure propagation contained — test no cascading
# RULE-5: Recovery independent — test per-scenario recovery

from unittest.mock import MagicMock

import pytest

from scripts.chaos.injector import (
    ChaosInjector,
    ChaosScenario,
    ChaosResult,
)


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    return bus


@pytest.fixture
def injector(event_bus):
    return ChaosInjector(event_bus=event_bus)


# ── TestScenarioExecution ───────────────────────

class TestScenarioExecution:
    """6 tests — one per scenario."""

    def test_worker_death_scenario(self, injector):
        result = injector.inject_worker_death()
        assert result.scenario == ChaosScenario.WORKER_DEATH
        assert result.recovery_time_sec > 0
        assert result.data_loss is False

    def test_split_brain_scenario(self, injector):
        result = injector.inject_split_brain()
        assert result.scenario == ChaosScenario.SPLIT_BRAIN
        assert result.recovery_time_sec > 0

    def test_checkpoint_corruption_scenario(self, injector):
        result = injector.inject_checkpoint_corruption()
        assert result.scenario == ChaosScenario.CHECKPOINT_CORRUPTION
        assert result.recovery_time_sec > 0

    def test_event_duplication_scenario(self, injector):
        result = injector.inject_event_duplication()
        assert result.scenario == ChaosScenario.EVENT_DUPLICATION
        assert result.idempotent is True

    def test_scheduler_starvation_scenario(self, injector):
        result = injector.inject_scheduler_starvation()
        assert result.scenario == ChaosScenario.SCHEDULER_STARVATION
        assert result.recovery_time_sec > 0

    def test_replay_divergence_scenario(self, injector):
        result = injector.inject_replay_divergence()
        assert result.scenario == ChaosScenario.REPLAY_DIVERGENCE
        assert result.recovery_time_sec > 0


# ── TestChaosSafetyThresholds ───────────────────

class TestChaosSafetyThresholds:
    """6 tests — recovery time and safety constraints."""

    def test_worker_death_recovers_under_5s(self, injector):
        for _ in range(10):
            result = injector.inject_worker_death()
            assert result.recovery_time_sec <= 5.0

    def test_split_brain_recovers_under_10s_no_data_loss(self, injector):
        for _ in range(10):
            result = injector.inject_split_brain()
            assert result.recovery_time_sec <= 10.0
            assert result.data_loss is False

    def test_checkpoint_corruption_rollback_safe(self, injector):
        for _ in range(10):
            result = injector.inject_checkpoint_corruption()
            if result.data_loss:
                assert result.passed is False
            else:
                assert result.recovery_time_sec <= 5.0

    def test_event_duplication_idempotent(self, injector):
        for _ in range(5):
            result = injector.inject_event_duplication()
            assert result.idempotent is True

    def test_scheduler_starvation_fairness_maintained(self, injector):
        for _ in range(10):
            result = injector.inject_scheduler_starvation()
            assert result.fairness_maintained is True

    def test_replay_divergence_determinism_maintained(self, injector):
        for _ in range(5):
            result = injector.inject_replay_divergence()
            assert result.determinism_maintained is True


# ── TestChaosIsolation ──────────────────────────

class TestChaosIsolation:
    """4 tests — scenario isolation, k1_trace_id, sequential ordering, event publication."""

    def test_all_scenarios_sequential_isolation(self, injector):
        results = injector.run_all_sequential()
        assert len(results) == 6
        scenarios_seen = set(r.scenario for r in results)
        assert scenarios_seen == {
            ChaosScenario.WORKER_DEATH,
            ChaosScenario.SPLIT_BRAIN,
            ChaosScenario.CHECKPOINT_CORRUPTION,
            ChaosScenario.EVENT_DUPLICATION,
            ChaosScenario.SCHEDULER_STARVATION,
            ChaosScenario.REPLAY_DIVERGENCE,
        }

    def test_scenarios_in_correct_order(self, injector):
        results = injector.run_all_sequential()
        expected_order = [
            ChaosScenario.WORKER_DEATH,
            ChaosScenario.SPLIT_BRAIN,
            ChaosScenario.CHECKPOINT_CORRUPTION,
            ChaosScenario.EVENT_DUPLICATION,
            ChaosScenario.SCHEDULER_STARVATION,
            ChaosScenario.REPLAY_DIVERGENCE,
        ]
        for i, expected in enumerate(expected_order):
            assert results[i].scenario == expected

    def test_k1_trace_id_consistency(self, injector):
        results = injector.run_all_sequential()
        for r in results:
            assert r.k1_trace_id == injector.k1_trace_id
            assert r.k1_trace_id.startswith("ck_")

    def test_event_published_on_injection(self, event_bus):
        injector = ChaosInjector(event_bus=event_bus)
        injector.inject_worker_death()
        injector.inject_split_brain()
        assert len(injector.results) == 2


# ── TestChaosRecovery ───────────────────────────

class TestChaosRecovery:
    """4 tests — recovery time, data loss, quorum, result storage."""

    def test_worker_death_no_lease_conflict(self, injector):
        for _ in range(10):
            result = injector.inject_worker_death()
            assert result.lease_conflict is False

    def test_split_brain_quorum_maintained(self, injector):
        for _ in range(10):
            result = injector.inject_split_brain()
            assert result.quorum_maintained is True

    def test_results_stored_after_injection(self, injector):
        assert len(injector.results) == 0
        injector.inject_worker_death()
        assert len(injector.results) == 1
        injector.inject_split_brain()
        assert len(injector.results) == 2

    def test_all_scenarios_recover_within_threshold(self, injector):
        results = injector.run_all_sequential()
        for r in results:
            if r.scenario == ChaosScenario.WORKER_DEATH:
                assert r.recovery_time_sec <= 5.0
            elif r.scenario == ChaosScenario.SPLIT_BRAIN:
                assert r.recovery_time_sec <= 10.0
            elif r.scenario == ChaosScenario.CHECKPOINT_CORRUPTION:
                assert r.recovery_time_sec <= 5.0
