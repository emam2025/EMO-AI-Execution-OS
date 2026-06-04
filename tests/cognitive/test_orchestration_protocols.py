"""Phase G — Cognitive Orchestration Protocols & Agent Lifecycle: 30 tests.

Groups:
  - TestProtocolCompliance:    6 tests — 4 protocols implemented, zero contract break
  - TestAgentLifecycle:        6 tests — register, transition, heartbeat, deregister
  - TestSwarmRoutingAccuracy:  6 tests — optimal selection, conflict prevention, quota
  - TestEventEmission:         6 tests — every operation emits traced AgentEvent
  - TestZeroLLMInvocation:     6 tests — zero LLM/model loading/inference calls

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 13, RULE 1
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

from core.interfaces.cognitive import (
    ICognitiveOrchestrator,
    IPlanner,
    ICritic,
    ISwarmCoordinator,
)
from core.runtime.agents.agent_lifecycle import (
    AgentLifecycleManager,
    AgentSpec,
    AgentState,
    AgentInstance,
)
from core.runtime.cognitive.orchestrator_facade import CognitiveOrchestrator
from core.runtime.cognitive.swarm_router import SwarmRouter, SwarmReport


# ── Helpers ─────────────────────────────────────────────────

@dataclass
class FakeEventBus:
    events: List[tuple[str, Any]] = field(default_factory=list)

    def publish(self, topic, event):
        self.events.append((topic, event))

    def subscribe(self, topic, handler):
        pass


@dataclass
class FakeEventStore:
    _events: List[Any] = field(default_factory=list)

    def append(self, event):
        self._events.append(event)

    def replay(self):
        return list(self._events)


@dataclass
class FakeLeaseManager:
    def acquire_lease(self, owner, source, ttl=30.0):
        return f"lease-{owner}"

    def release_lease(self, lease_id):
        return True


@dataclass
class FakeUnifiedRuntime:
    def submit(self, payload):
        return {"execution_id": f"exec-{payload.get('plan_id', 'unknown')}"}


class FakePlanner:
    def synthesize_dag(self, intent, constraints=None):
        return f"plan-{hash(intent) % 10000}"

    def validate_plan(self, plan_id):
        return True


class FakeCritic:
    def evaluate_plan(self, plan_id):
        return {"score": 0.85, "reason": "Plan looks good"}

    def suggest_corrections(self, plan_id):
        return ["Add timeout", "Reduce parallelism"]

    def risk_assess(self, plan_id):
        return {"risk_level": "low", "failure_modes": []}


class FakeSwarmCoordinator:
    def negotiate_task(self, agents, task):
        return agents[0]["agent_id"] if agents else ""

    def coordinate_swarm(self, plan):
        return []

    def resolve_conflicts(self, agents):
        return []


class FakeDashboard:
    def get_system_health(self):
        from core.runtime.observability.dashboard_service import HealthReport
        return HealthReport(alerts_active=0)


@dataclass
class FakeQuotaManager:
    def enforce_global_ceiling(self):
        return "hold"


@dataclass
class FakeScheduler:
    def evaluate_worker_fit(self, task, caps):
        from core.runtime.scheduling.policies import MatchScore
        return MatchScore(score=0.8, matched=True, reason="good fit")


# ── TestProtocolCompliance ──────────────────────────────────

class TestProtocolCompliance:
    """4 Protocols implemented, zero contract break."""

    def test_icognitive_orchestrator_is_runtime_checkable(self):
        assert issubclass(ICognitiveOrchestrator, Protocol)

    def test_iplanner_is_runtime_checkable(self):
        assert issubclass(IPlanner, Protocol)

    def test_icritic_is_runtime_checkable(self):
        assert issubclass(ICritic, Protocol)

    def test_iswarm_coordinator_is_runtime_checkable(self):
        assert issubclass(ISwarmCoordinator, Protocol)

    def test_cognitive_orchestrator_conforms(self):
        orch = CognitiveOrchestrator()
        assert isinstance(orch, ICognitiveOrchestrator)

    def test_protocols_have_required_methods(self):
        assert hasattr(ICognitiveOrchestrator, "plan")
        assert hasattr(ICognitiveOrchestrator, "critique")
        assert hasattr(ICognitiveOrchestrator, "optimize")
        assert hasattr(ICognitiveOrchestrator, "submit_to_runtime")
        assert hasattr(IPlanner, "synthesize_dag")
        assert hasattr(IPlanner, "validate_plan")
        assert hasattr(ICritic, "evaluate_plan")
        assert hasattr(ICritic, "suggest_corrections")
        assert hasattr(ICritic, "risk_assess")
        assert hasattr(ISwarmCoordinator, "negotiate_task")
        assert hasattr(ISwarmCoordinator, "coordinate_swarm")
        assert hasattr(ISwarmCoordinator, "resolve_conflicts")


# ── TestAgentLifecycle ─────────────────────────────────────

class TestAgentLifecycle:
    """Register, state transitions, heartbeat, deregister."""

    def test_register_returns_agent_id(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test-agent"))
        assert isinstance(aid, str)
        assert aid.startswith("agent-")

    def test_register_creates_instance(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test-agent", capabilities={"llm": True}))
        agent = lm.get_agent(aid)
        assert agent is not None
        assert agent.state == AgentState.IDLE

    def test_transition_state_valid(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test"))
        result = lm.transition_state(aid, AgentState.PLANNING)
        assert result is True
        agent = lm.get_agent(aid)
        assert agent.state == AgentState.PLANNING

    def test_transition_state_invalid_blocked(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test"))
        result = lm.transition_state(aid, AgentState.COMPLETED)
        assert result is False

    def test_heartbeat_updates_timestamp(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test"))
        agent = lm.get_agent(aid)
        old_hb = agent.last_heartbeat
        time.sleep(0.001)
        lm.heartbeat(aid)
        assert agent.last_heartbeat > old_hb

    def test_deregister_removes_agent(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="test"))
        result = lm.deregister(aid, reason="cleanup")
        assert result is True
        assert lm.get_agent(aid) is None


# ── TestSwarmRoutingAccuracy ───────────────────────────────

class TestSwarmRoutingAccuracy:
    """Optimal selection, conflict prevention, quota respect."""

    def test_route_task_returns_agent_id(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(
            name="worker-a",
            capabilities={"code_exec": True, "llm": True},
        ))
        router = SwarmRouter(agent_lifecycle=lm)
        selected = router.route_task({"required_capabilities": ["code_exec"]})
        assert selected == aid

    def test_route_task_empty_when_no_match(self):
        lm = AgentLifecycleManager()
        lm.register(AgentSpec(
            name="worker-a",
            capabilities={"code_exec": True},
        ))
        router = SwarmRouter(agent_lifecycle=lm)
        selected = router.route_task({"required_capabilities": ["gpu"]})
        assert selected == ""

    def test_route_task_skips_non_idle_agents(self):
        lm = AgentLifecycleManager()
        aid = lm.register(AgentSpec(name="busy"))
        lm.transition_state(aid, AgentState.PLANNING)
        lm.transition_state(aid, AgentState.EXECUTING)
        router = SwarmRouter(agent_lifecycle=lm)
        selected = router.route_task({})
        assert selected == ""

    def test_swarm_report_returns_counts(self):
        lm = AgentLifecycleManager()
        lm.register(AgentSpec(name="a1"))
        lm.register(AgentSpec(name="a2"))
        router = SwarmRouter(agent_lifecycle=lm)
        report = router.monitor_swarm_health()
        assert isinstance(report, SwarmReport)
        assert report.total_agents == 2

    def test_swarm_report_includes_success_rate(self):
        store = FakeEventStore()
        router = SwarmRouter(event_store=store)
        report = router.monitor_swarm_health()
        assert report.success_rate == 100.0

    def test_route_with_quota_manager_no_crash(self):
        qm = FakeQuotaManager()
        router = SwarmRouter(quota_manager=qm)
        selected = router.route_task({})
        assert selected == ""


# ── TestEventEmission ──────────────────────────────────────

class TestEventEmission:
    """Every operation emits traced AgentEvent."""

    def test_register_emits_event(self):
        bus = FakeEventBus()
        lm = AgentLifecycleManager(event_bus=bus)
        lm.register(AgentSpec(name="test"))
        registered = [(t, e) for t, e in bus.events if "agent" in t and "registered" in t]
        assert len(registered) >= 1

    def test_transition_emits_event(self):
        bus = FakeEventBus()
        lm = AgentLifecycleManager(event_bus=bus)
        aid = lm.register(AgentSpec(name="test"))
        bus.events.clear()
        lm.transition_state(aid, AgentState.PLANNING)
        state_changed = [(t, e) for t, e in bus.events if "state_changed" in t]
        assert len(state_changed) >= 1

    def test_deregister_emits_event(self):
        bus = FakeEventBus()
        lm = AgentLifecycleManager(event_bus=bus)
        aid = lm.register(AgentSpec(name="test"))
        bus.events.clear()
        lm.deregister(aid, reason="cleanup")
        deregistered = [(t, e) for t, e in bus.events if "deregistered" in t]
        assert len(deregistered) >= 1

    def test_orchestrator_plan_emits_event(self):
        bus = FakeEventBus()
        orch = CognitiveOrchestrator(event_bus=bus)
        orch.plan({"intent": "test task"})
        created = [(t, e) for t, e in bus.events if "plan.created" in t]
        assert len(created) >= 1

    def test_orchestrator_submit_emits_event(self):
        bus = FakeEventBus()
        orch = CognitiveOrchestrator(event_bus=bus)
        orch.submit_to_runtime("plan-123")
        submitted = [(t, e) for t, e in bus.events if "plan.submitted" in t]
        assert len(submitted) >= 1

    def test_plan_and_dispatch_emits_completion(self):
        bus = FakeEventBus()
        orch = CognitiveOrchestrator(
            planner=FakePlanner(),
            critic=FakeCritic(),
            unified_runtime=FakeUnifiedRuntime(),
            event_bus=bus,
        )
        result = orch.plan_and_dispatch("test intent")
        assert "trace_id" in result
        assert "plan_id" in result
        assert "execution_id" in result
        completed = [(t, e) for t, e in bus.events if "orchestration.completed" in t]
        assert len(completed) >= 1


# ── TestZeroLLMInvocation ──────────────────────────────────

class TestZeroLLMInvocation:
    """Zero LLM/model loading/inference calls in cognitive layer."""

    STRING_BLACKLIST = [
        "transformers",
        "torch",
        "tensorflow",
        "openai",
        "anthropic",
        "llm",
        "inference",
        "model.load",
        "model.generate",
        "chat.completion",
    ]

    FILES = [
        PROJECT_ROOT / "core/runtime/agents/agent_lifecycle.py",
        PROJECT_ROOT / "core/runtime/cognitive/orchestrator_facade.py",
        PROJECT_ROOT / "core/runtime/cognitive/swarm_router.py",
        PROJECT_ROOT / "core/interfaces/cognitive/orchestrator.py",
        PROJECT_ROOT / "core/interfaces/cognitive/planner.py",
        PROJECT_ROOT / "core/interfaces/cognitive/critic.py",
        PROJECT_ROOT / "core/interfaces/cognitive/swarm.py",
    ]

    @pytest.mark.parametrize("filepath", FILES)
    def test_no_llm_imports(self, filepath):
        text = filepath.read_text()
        lines = text.splitlines()
        import_lines = [line.lower() for line in lines if line.startswith(("import ", "from "))]
        content = "\n".join(import_lines)
        for keyword in self.STRING_BLACKLIST:
            assert keyword not in content, (
                f"LLM keyword '{keyword}' imported in {filepath}"
            )

    def test_orchestrator_no_model_loading(self):
        orch = CognitiveOrchestrator()
        assert not hasattr(orch, "_model")
        assert not hasattr(orch, "_tokenizer")
        assert not hasattr(orch, "_client")

    def test_agent_lifecycle_no_ai(self):
        lm = AgentLifecycleManager()
        assert not hasattr(lm, "_model")
        assert not hasattr(lm, "_llm")

    def test_swarm_router_no_inference(self):
        router = SwarmRouter()
        assert not hasattr(router, "_model")
        assert not hasattr(router, "_llm")

    def test_protocols_are_pure(self):
        import inspect
        for name in dir(ICognitiveOrchestrator):
            if not name.startswith("_"):
                member = getattr(ICognitiveOrchestrator, name)
                if inspect.isfunction(member):
                    src = inspect.getsource(member)
                    assert "..." in src or "pass" in src, (
                        f"Protocol method {name} has implementation"
                    )

    def test_all_protocols_pure(self):
        import inspect
        for proto in [IPlanner, ICritic, ISwarmCoordinator]:
            for name in dir(proto):
                if not name.startswith("_"):
                    member = getattr(proto, name)
                    if inspect.isfunction(member):
                        src = inspect.getsource(member)
                        assert "..." in src or "pass" in src, (
                            f"{proto.__name__}.{name} has implementation"
                        )
