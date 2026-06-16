"""D8.2 — Failure Propagation Model Tests.

Verifies enums, frozen dataclasses, and propagation rules.
Pure data contracts — no execution logic tested.

Ref: DEVELOPER.md §15.15a D8.2
Ref: Canon LAW 20-22
"""

from core.models.failure_propagation import (
    ConsistencyLevel,
    FailureContext,
    FailureMode,
    PropagationRule,
)


class TestFailureModeEnum:
    def test_failure_mode_enum_completeness(self) -> None:
        expected = {"RETRY", "FALLBACK", "CIRCUIT_BREAK", "FAIL_FAST", "DEGRADE"}
        actual = {m.name for m in FailureMode}
        assert actual == expected


class TestConsistencyLevelEnum:
    def test_consistency_level_enum_completeness(self) -> None:
        expected = {"STRONG", "EVENTUAL", "NONE"}
        actual = {c.name for c in ConsistencyLevel}
        assert actual == expected


class TestPropagationRules:
    def test_propagation_rule_dispatcher_fails(self) -> None:
        rule = PropagationRule(
            source_domain="Dispatcher",
            effect_on="Scheduler",
            action="Scheduler retries failed tool call",
            failure_mode=FailureMode.RETRY,
            consistency_level=ConsistencyLevel.EVENTUAL,
        )
        assert rule.source_domain == "Dispatcher"
        assert rule.failure_mode == FailureMode.RETRY

    def test_propagation_rule_lease_expires(self) -> None:
        rule = PropagationRule(
            source_domain="LeaseManager",
            effect_on="Scheduler",
            action="Cancel execution and reassign lease",
            failure_mode=FailureMode.FAIL_FAST,
            consistency_level=ConsistencyLevel.STRONG,
        )
        assert rule.source_domain == "LeaseManager"
        assert rule.action == "Cancel execution and reassign lease"

    def test_propagation_rule_state_store_fails(self) -> None:
        rule = PropagationRule(
            source_domain="StateStore",
            effect_on="Scheduler",
            action="Degrade to in-memory buffer",
            failure_mode=FailureMode.DEGRADE,
            consistency_level=ConsistencyLevel.NONE,
        )
        assert rule.failure_mode == FailureMode.DEGRADE
        assert rule.consistency_level == ConsistencyLevel.NONE


class TestFailureContextImmutability:
    def test_failure_context_immutability(self) -> None:
        ctx = FailureContext(
            source_service="Dispatcher",
            target_service="Scheduler",
            error_type="ConnectionTimeout",
            timestamp=1000.0,
        )
        try:
            ctx.source_service = "Modified"
            assert False, "Frozen dataclass should raise FrozenInstanceError"
        except AttributeError:
            pass
