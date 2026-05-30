"""
Multi-Agent Society Coordination — 10 tests.

Validates:
  - task negotiation produces fair allocation
  - swarm coordination state management
  - tenant boundary enforcement (LAW-24)
  - cross-tenant allocation blocked
"""

import pytest
from releases.big_emo.core.self_governance.society_manager import MultiAgentSocietyManager


class TestTaskNegotiation:
    def test_negotiate_task_returns_allocation_plan(self):
        manager = MultiAgentSocietyManager()
        agents = [
            {"agent_id": "a1", "name": "parser", "capabilities": ["nlp"], "current_load": 2, "tenant_id": "t1"},
            {"agent_id": "a2", "name": "builder", "capabilities": ["build"], "current_load": 5, "tenant_id": "t1"},
        ]
        task = {"task_id": "t-1", "required_capability": "nlp", "estimated_load": 3}
        plan = manager.negotiate_task(agents, task, tenant_id="t1")
        assert plan.allocation_id
        assert plan.tenant_id == "t1"
        assert plan.task_id == "t-1"
        assert len(plan.agent_assignments) > 0

    def test_allocation_favours_lower_load_agent(self):
        manager = MultiAgentSocietyManager()
        agents = [
            {"agent_id": "a1", "name": "worker1", "capabilities": ["build"], "current_load": 1, "tenant_id": "t1"},
            {"agent_id": "a2", "name": "worker2", "capabilities": ["build"], "current_load": 9, "tenant_id": "t1"},
        ]
        task = {"task_id": "t-2", "required_capability": "build", "estimated_load": 3}
        plan = manager.negotiate_task(agents, task, tenant_id="t1")
        assert plan.agent_assignments[0]["agent_id"] == "a1"

    def test_negotiate_requires_tenant(self):
        manager = MultiAgentSocietyManager()
        with pytest.raises(ValueError, match="tenant_id"):
            manager.negotiate_task([{"agent_id": "a1"}], {"task_id": "t1"}, tenant_id="")

    def test_negotiate_empty_agents_raises(self):
        manager = MultiAgentSocietyManager()
        with pytest.raises(ValueError, match="agent list"):
            manager.negotiate_task([], {"task_id": "t1"}, tenant_id="t1")


class TestSwarmCoordination:
    def test_coordinate_swarm_returns_state(self):
        manager = MultiAgentSocietyManager()
        agents = [{"agent_id": "a1", "name": "w", "capabilities": ["build"], "current_load": 1, "tenant_id": "t1"}]
        task = {"task_id": "t-3", "required_capability": "build", "estimated_load": 1}
        plan = manager.negotiate_task(agents, task, tenant_id="t1")
        state = manager.coordinate_swarm({
            "allocation_id": plan.allocation_id,
            "agent_assignments": plan.agent_assignments,
        }, tenant_id="t1")
        assert state.swarm_id
        assert state.active_agents == 1
        assert state.consensus_status == "consensus_reached"

    def test_coordinate_empty_assignments(self):
        manager = MultiAgentSocietyManager()
        state = manager.coordinate_swarm({"allocation_id": "a1", "agent_assignments": []}, tenant_id="t1")
        assert state.active_agents == 0
        assert state.consensus_status == "pending"

    def test_coordinate_requires_tenant(self):
        manager = MultiAgentSocietyManager()
        with pytest.raises(ValueError, match="tenant_id"):
            manager.coordinate_swarm({"agent_assignments": []}, tenant_id="")


class TestTenantBoundaries:
    def test_enforce_tenant_boundaries_passes(self):
        manager = MultiAgentSocietyManager()
        result = manager.enforce_tenant_boundaries({
            "tenant_id": "t1",
            "agent_assignments": [{"agent_id": "a1"}],
        }, tenant_id="t1")
        assert result is True

    def test_cross_tenant_allocation_blocked(self):
        manager = MultiAgentSocietyManager()
        agents = [
            {"agent_id": "a1", "name": "w", "capabilities": ["build"], "current_load": 1, "tenant_id": "t1"},
        ]
        task = {"task_id": "t-4", "required_capability": "build", "estimated_load": 1}
        with pytest.raises(ValueError, match="different tenant"):
            # Inject an agent with wrong tenant_id to trigger guard
            agents.append({"agent_id": "a2", "name": "x", "capabilities": ["build"], "current_load": 1, "tenant_id": "t2"})
            manager.negotiate_task(agents, task, tenant_id="t1")
