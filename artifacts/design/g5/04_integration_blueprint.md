# Phase G5 — Multi-Agent Runtime: Integration Blueprint
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 11 (No Global State), LAW 23-27 (Service Ownership)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.15a
Ref: ROADMAP Phase G5

---

## 1. System Architecture

```
                              ┌─────────────────────────────────────┐
                              │         G5 Multi-Agent Runtime       │
                              │                                      │
                              │  ┌──────────────────────────────┐   │
          G1.synthesize() ────┼─►│   IHierarchicalPlanner        │   │
                              │  │  decompose_intent()           │   │
                              │  │  assign_subgoals()            │   │
                              │  │  merge_results()              │   │
                              │  │  validate_coherence()         │   │
                              │  └──────────┬───────────────────┘   │
                              │             │                        │
                              │  ┌──────────▼───────────────────┐   │
            G3 Opt ──────────┼─►│   IAgentContractEngine         │   │
                              │  │  negotiate_capabilities()     │   │
                              │  │  validate_contract_terms()    │   │
                              │  │  sign_agreement()             │   │
                              │  │  breach_detection()           │   │
                              │  └──────────┬───────────────────┘   │
                              │             │                        │
                    ┌─────────┼─────────────┼──────────┐             │
                    │         │             │          │             │
                    ▼         ▼             ▼          ▼             │
              ┌─────────────────────────────────────────────┐        │
              │            ISwarmCoordinator                 │        │
              │  broadcast_task → resolve_conflicts          │        │
              │  sync_consensus → distribute_load            │        │
              └──────┬──────┬──────┬──────┬──────┬──────────┘        │
                     │      │      │      │      │                    │
                     ▼      ▼      ▼      ▼      ▼                    │
              ┌─────────────────────────────────────────────┐        │
              │         IAgentLifecycleManager               │        │
              │  spawn → monitor → pause → terminate         │        │
              └──────┬──────┬──────┬──────┬──────┬──────────┘        │
                     │      │      │      │      │                    │
                     ▼      ▼      ▼      ▼      ▼                    │
              ┌─────────────────────────────────────────────┐        │
              │        Agent Instances (Domain-scoped)       │        │
              │  Agent-A  │  Agent-B  │  Agent-C  │  ...    │        │
              └──────────┴──────────┴──────────┴───────────┘        │
                              │                                      │
                              └──────────────────────────────────────┘
                                         │
              ┌───────────────────────────┼───────────────────────────┐
              │                           │                           │
              ▼                           ▼                           ▼
      ┌──────────────┐          ┌──────────────────┐       ┌────────────────┐
      │   F2 Control │          │  EventBus         │       │  Phase 4       │
      │   Plane      │◄─────────┤  (all inter-agent │       │  Sandbox       │
      │   (scale)    │          │   communication)  │       │  (isolation)   │
      └──────────────┘          └──────────────────┘       └────────────────┘
```

## 2. Data Flow

### 2.1 G1 Planner → G5 Hierarchical Planner

```
G1 Planner                    G5 IHierarchicalPlanner
─────────                     ────────────────────────
  │                                     │
  │  planner.plan(intent)                │
  │  ────────────────────────────────►   │
  │                                     │
  │  ┌─ decompose_intent(intent)        │
  │  │   → subgoals + dep_graph         │
  │  │                                  │
  │  │   For each subgoal:              │
  │  │   └─ assign_subgoals()           │
  │  │       → agent assignments        │
  │  │                                  │
  │  ◄───────────────────────────────── │
  │  return {decomposition, assignments} │
```

### 2.2 G5 Contract Engine → G3 Optimizer

When agent capabilities need optimisation or budget renegotiation:

```
G5 IAgentContractEngine          G3 Optimizer Agent
──────────────────────           ──────────────────
  │                                     │
  │  negotiate_capabilities(req, offer)  │
  │  ────────────────────────────────►   │
  │  ◄─────────────────────────────────  │
  │  return {match_score, gaps, excess}  │
  │                                     │
  │  validate_contract_terms(terms)      │
  │  ────────────────────────────────►   │
  │  ◄─────────────────────────────────  │
  │  return {valid, violations}          │
```

### 2.3 G5 Swarm Coordinator → G2 Critic Agent

After swarm execution, results flow to G2 for critique:

```
G5 ISwarmCoordinator           G2 Critic Agent
───────────────────            ────────────────
  │                                     │
  │  (swarm execution completes)        │
  │  ────────────────────────────────►   │
  │  merged_output + trace_id            │
  │                                     │
  │  ◄─────────────────────────────────  │
  │  critic_assessment                   │
  │                                     │
  │  If assessment.findings:              │
  │  └─ resolve_conflicts(findings)      │
```

### 2.4 G5 Lifecycle Manager → F2 Control Plane

When F2 scaling decisions affect agent count:

```
F2 Control Plane               G5 IAgentLifecycleManager
───────────────                ──────────────────────────
  │                                     │
  │  scale_agents(target_count)         │
  │  ────────────────────────────────►   │
  │                                     │
  │  ┌─ If scale up:                    │
  │  │  └─ spawn_agent(spec)            │
  │  │     for each new agent           │
  │  │                                  │
  │  └─ If scale down:                  │
  │     └─ terminate_agent(id, reason)  │
  │        for each excess agent        │
  │                                     │
  │  ◄─────────────────────────────────  │
  │  return {agent_count, status}        │
```

### 2.5 G5 → EventBus (all communication)

Every inter-agent interaction flows through EventBus. No agent directly
calls another agent's method. EventBus topics defined in §6 of
`03_agent_lifecycle_machine.md`.

```
Agent A                    EventBus                    Agent B
───────                    ────────                    ────────
  │                          │                          │
  │  publish(                │                          │
  │   "agent.task.request",  │                          │
  │   {task, caps, trace})   │                          │
  │  ──────────────────────► │                          │
  │                          │  forward to subscribers  │
  │                          │  ──────────────────────► │
  │                          │                          │
  │                          │  ◄────────────────────── │
  │                          │  publish(                │
  │                          │   "agent.task.response", │
  │                          │   {result, trace})       │
  │  ◄────────────────────── │                          │
```

---

## 3. Correlation ID Propagation (LAW 12)

### Trace Chain

```
G1 Planner          G5 Planner           G5 Contract Eng       G5 Swarm
plan_id ──────────► mission_trace_id ──► mission_trace_id ──► mission_trace_id
    │                    │                    │                    │
    │               G5 Lifecycle         G2 Critic           F2 Control
    │               mission_trace_id     mission_trace_id    mission_trace_id
    │                    │                    │                    │
    └────────────────────┼────────────────────┼────────────────────┘
                         │                    │
                    EventBus Topics:
                    agent.*, swarm.*, planning.*, contract.*
```

### ID Format

```
mission_trace_id = "msn_{sha256(intent_id + plan_id + time_ns)[:24]}"
```

### Cross-Layer Correlation Table

| Layer | Trace ID Field | Propagated To |
|-------|---------------|---------------|
| G1 Planner | plan_id | G5 via intent.context.plan_id |
| G3 Optimizer | optimizer_trace_id | G5 via contract negotiate_capabilities |
| G5 Planner | mission_trace_id | All G5 sub-protocols + agents + EventBus |
| G5 Agent Instance | mission_trace_id | lifecycle events + checkpoint |
| G2 Critic | mission_trace_id | Critique assessment |
| F2 Control Plane | mission_trace_id | Scaling decisions |
| EventBus | mission_trace_id | All agent.*, swarm.*, contract.* topics |

---

## 4. Hook Points for EventBus Topics

| Hook | Stage | Topic | Payload |
|------|-------|-------|---------|
| Intent received | HIERARCHICAL PLANNER | `planning.decomposition.started` | {intent_id, mission_trace_id} |
| Decomposition complete | HIERARCHICAL PLANNER | `planning.decomposition.completed` | {decomposition_id, subgoals[], trace_id} |
| Subgoal assigned | HIERARCHICAL PLANNER | `planning.subgoal.assigned` | {subgoal_id, agent_id, mission_trace_id} |
| Agent spawn started | LIFECYCLE → SPAWNING | `agent.lifecycle.spawning` | {agent_id, spec, mission_trace_id} |
| Agent running | LIFECYCLE → RUNNING | `agent.lifecycle.running` | {agent_id, domain, mission_trace_id} |
| Health degraded | LIFECYCLE → DEGRADED | `agent.health.degraded` | {agent_id, reason, metrics, mission_trace_id} |
| Contract negotiation | CONTRACT ENGINE | `agent.contract.negotiating` | {contract_id, parties, caps, mission_trace_id} |
| Contract signed | CONTRACT ENGINE | `agent.contract.signed` | {contract_id, signature, mission_trace_id} |
| Contract breached | CONTRACT ENGINE | `agent.contract.breached` | {incident_id, severity, evidence, mission_trace_id} |
| Swarm broadcast | SWARM COORDINATOR | `swarm.task.broadcast` | {broadcast_id, task, agent_count, mission_trace_id} |
| Conflict resolved | SWARM COORDINATOR | `swarm.conflict.resolved` | {resolution_id, winner, rationale, mission_trace_id} |
| Consensus reached | SWARM COORDINATOR | `swarm.consensus.reached` | {value, confidence, trace_id} |
| Load rebalanced | SWARM COORDINATOR | `swarm.load.rebalanced` | {reassignments[], final_balance, mission_trace_id} |
| Subgoal completed | HIERARCHICAL PLANNER | `planning.subgoal.completed` | {subgoal_id, status, output, mission_trace_id} |
| Subgoal failed | HIERARCHICAL PLANNER | `planning.subgoal.failed` | {subgoal_id, error, retry_count, mission_trace_id} |
| Merge complete | HIERARCHICAL PLANNER | `planning.merge.completed` | {decomposition_id, merged_output, mission_trace_id} |
| Incoherence detected | HIERARCHICAL PLANNER | `planning.incoherence.detected` | {decomposition_id, gaps[], mission_trace_id} |
| Determinism violation | HIERARCHICAL PLANNER | `planning.determinism.violation` | {intent_id, expected_hash, actual_hash} |

---

## 5. Acceptance Criteria for Integration

### 5.1 Latency Budgets

| Operation | Target | Hard Limit |
|-----------|--------|------------|
| Decompose intent (per level) | 200ms | 1000ms |
| Assign subgoals (per 10 agents) | 100ms | 500ms |
| Negotiate capabilities | 150ms | 500ms |
| Sign contract | 50ms | 200ms |
| Broadcast task (per 10 agents) | 100ms | 500ms |
| Resolve conflicts (per 10 proposals) | 50ms | 200ms |
| Sync consensus | 100ms | 300ms |
| Merge results (per 10 subgoals) | 200ms | 1000ms |
| Spawn agent | 500ms | 2000ms |
| Terminate agent | 200ms | 1000ms |

### 5.2 Idempotency Guarantees

| Operation | Idempotency Key | Behaviour |
|-----------|----------------|-----------|
| `spawn_agent` | (agent_id, domain) | Duplicate spawn returns existing AgentInstance |
| `sign_agreement` | contract_id | Duplicate sign returns existing contract |
| `broadcast_task` | broadcast_id | Duplicate broadcast returns existing broadcast_id |
| `merge_results` | decomposition_id | Same subgoal results → same merged output (RULE 1) |
| `terminate_agent` | agent_id | Already-terminated returns existing termination record |

### 5.3 Determinism Thresholds

| Metric | Threshold |
|--------|-----------|
| Same intent → same decomposition | 100% required |
| Same capability req/offer → same match_score | 100% required |
| Same proposals → same conflict resolution | 100% required |
| Same load reports → same reassignments | 100% required |
| Same parent intent → same coherence_score | ±0.05 tolerance |

### 5.4 Backpressure Handling

When EventBus or agent execution is under pressure:

| Load Level | Behaviour |
|------------|-----------|
| < 60% capacity | Normal operation |
| 60–80% capacity | Reduce heartbeat frequency; batch small tasks |
| 80–95% capacity | Pause non-critical agents; delay contract negotiation |
| > 95% capacity | Terminate lowest-priority agents; reject new spawns; emit `swarm.backpressure.engaged` |

### 5.5 Rollback on Failure

Any failure at any stage requires:

1. For spawn failures: Clean up partially allocated resources. Emit `agent.lifecycle.terminated` with reason.
2. For contract failures: Set contract status to VOIDED. Notify both parties via EventBus.
3. For subgoal failures: Retry up to `max_retries_per_subgoal` (3). On exhaustion, mark as FAILED, cascade to dependents as CANCELLED.
4. For consensus failure: Emit `swarm.consensus.failed`. Escalate to G1 Planner for re-decomposition.
5. For lifecycle failures: Final checkpoint + termination. Emit `agent.lifecycle.terminated`.

---

## 6. CompositionRoot Integration (for future implementation)

When G5 is implemented in `core/`, the CompositionRoot will gain:

```python
# In CompositionRoot.__init__:
agent_lifecycle_manager: Any = None
strict_agent_mode: bool = False

# Property:
@property
def agent_lifecycle_manager(self) -> Any:
    """Return IAgentLifecycleManager instance (Phase G5)."""

# Builder:
def _build_agent_lifecycle_manager(self) -> Any:
    from core.runtime.multiagent.lifecycle_manager import AgentLifecycleManager
    from core.runtime.multiagent.contract_engine import AgentContractEngine
    from core.runtime.multiagent.swarm_coordinator import SwarmCoordinator
    from core.runtime.multiagent.hierarchical_planner import HierarchicalPlanner
    from core.runtime.multiagent.agent_state_machine import AgentLifecycleStateMachine
    from core.runtime.multiagent.trace_correlator import MultiAgentTraceCorrelator
    # ... build and wire ...
```

This maps to the existing pattern used by G1, G2, G3, and G4 in `core/composition/root.py`.
