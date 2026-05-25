# Phase G5 — Multi-Agent Runtime: Agent Lifecycle & Coordination State Machine
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 11 (No Global State), LAW 23 (Service Ownership), LAW 24 (Dispatcher Ownership)
Ref: Canon LAW 25 (Message Boundaries), LAW 26 (Lifecycle Ownership), LAW 27 (One Service per Domain)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.15a
Ref: ROADMAP Phase G5

---

## 1. Agent Lifecycle State Map

```
                          ┌──────────────────────────────────────┐
                          │               IDLE                    │
                          │  (agent spec received, not spawned)   │
                          └────────────┬─────────────────────────┘
                                       │
                                       ▼
                          ┌──────────────────────────────────────┐
                          │            SPAWNING                   │
                          │  (resources allocated, domain         │
                          │   assigned, checkpoint created)       │
                          └────────────┬──────────────────────────┘
                                       │
                              ┌────────┴────────┐
                              ▼                 ▼
                    ┌──────────────────┐  ┌──────────────────────┐
                    │    RUNNING       │  │    TERMINATED         │
                    │ (healthy, active)│  │ (spawn failed)       │
                    └───┬──────┬───────┘  └──────────────────────┘
                        │      │
                   ┌────┘      └────┐
                   ▼                ▼
          ┌──────────────┐  ┌──────────────┐
          │   PAUSED     │  │  DEGRADED    │
          │ (suspended,  │  │ (unhealthy   │
          │  checkpoint) │  │  but alive)  │
          └──────┬───────┘  └──────┬───────┘
                 │                 │
                 └──────┬──────────┘
                        ▼
                 ┌──────────────┐
                 │  TERMINATED  │
                 │ (final       │
                 │  checkpoint) │
                 └──────────────┘
```

### Transition Table

| From | To | Guard | Description |
|------|----|-------|-------------|
| IDLE | SPAWNING | `guard_spec_valid` | AgentSpec has capability_profile + domain + resource_quota |
| IDLE | TERMINATED | `guard_spec_invalid` | Spec missing mandatory fields |
| SPAWNING | RUNNING | `guard_spawn_success` | Resources allocated, domain assigned, heartbeat started |
| SPAWNING | TERMINATED | `guard_spawn_failed` | Resource allocation failed |
| RUNNING | PAUSED | `guard_can_pause` | Agent is healthy; no critical in-flight tasks |
| RUNNING | DEGRADED | `guard_health_degraded` | Heartbeat missed OR resource usage exceeds 90% |
| RUNNING | TERMINATED | `guard_termination` | Lifecycle expired OR supervisor command |
| PAUSED | RUNNING | `guard_can_resume` | Checkpoint valid, resources still allocated |
| PAUSED | TERMINATED | `guard_pause_timeout` | Pause duration exceeds policy limit |
| DEGRADED | RUNNING | `guard_recovered` | Health restored, intervention complete |
| DEGRADED | TERMINATED | `guard_unrecoverable` | Health check failed consecutively |
| TERMINATED | (terminal) | — | Final checkpoint written; resources freed |

---

## 2. Isolation Guards Matrix (LAW 23-27, RULE 4)

| # | Guard | Condition | Violation Response |
|---|-------|-----------|-------------------|
| I1 | `domain_ownership` | Each agent belongs to exactly one domain (LAW 27) | Block spawn; emit `AgentDomainViolation` |
| I2 | `no_direct_memory_reference` | All inter-agent communication via EventBus messages (LAW 25) | Block operation; emit `AgentDirectReferenceViolation` |
| I3 | `state_scoped_to_instance` | Agent state is scoped to AgentInstance (LAW 11) | Block operation; emit `AgentGlobalStateViolation` |
| I4 | `dispatcher_owned_negotiation` | All contract negotiations owned by Dispatcher (LAW 24) | Block direct negotiation; emit `AgentUnauthorizedNegotiation` |
| I5 | `resources_within_domain` | Agent resource consumption stays within domain quota | Scale back; emit `AgentResourceViolation` |
| I6 | `snapshot_isolation` | Paused agent state is frozen; no mutations until resume | Block pause-side-effect; emit `AgentStateMutationWhilePaused` |
| I7 | `termination_checkpoint` | Terminated agent has a final checkpoint (RULE 5) | Block terminate; emit `AgentMissingFinalCheckpoint` |

### Isolation Guard Enforcement (Pseudocode)

```
def enforce_isolation(operation: str, agent: AgentInstance, context: Any) -> bool:
    if operation == "spawn":
        assert agent.domain not in existing_domains or agent.domain == "",
            "LAW 27: Domain already owned by another agent"
        assert agent.assigned_domain != "",
            "LAW 27: Agent must have a domain"

    if operation == "communicate":
        assert isinstance(context, EventBusMessage),
            "LAW 25: Communication must be EventBus messages"
        assert "agent_id" not in context.direct_references,
            "LAW 25: No direct agent references in messages"

    if operation == "negotiate":
        assert context.dispatcher_id != "",
            "LAW 24: Negotiation must be dispatcher-owned"

    if operation == "pause":
        assert agent.checkpoint_ref != "",
            "I6: Paused state must have checkpoint"
        assert not agent.dirty_state,
            "I6: No mutations after pause"

    if operation == "terminate":
        assert agent.checkpoint_ref != "",
            "I7: Final checkpoint required before termination"

    return True
```

---

## 3. Hierarchical Planning Guard (RULE 1, RULE 3)

The Hierarchical Planner MUST ensure that subgoal decompositions are
**consistent** with the parent intent and that no unnecessary re-execution
occurs when subgoals fail.

### Guard Conditions

| # | Guard | Condition | Violation Response |
|---|-------|-----------|-------------------|
| H1 | `subgoal_coverage` | All target_nodes from parent intent are addressed by ≥1 subgoal | Block assignment; emit `PlanningCoverageGap` |
| H2 | `dependency_acyclic` | Subgoal dependency graph contains no cycles | Reject decomposition; emit `PlanningCyclicDependency` |
| H3 | `capability_match` | Each subgoal assigned to an agent whose profile contains required caps | Reject assignment; emit `PlanningCapabilityMismatch` |
| H4 | `no_redundant_execution` | Completed subgoals are NOT re-executed on retry (RULE 5) | Skip completed; emit `PlanningSkippedCompletedSubgoal` |
| H5 | `coherence_threshold` | merge_results() coherence score >= 0.7 | Mark incoherent; emit `PlanningIncoherence` |
| H6 | `deterministic_decomposition` | Same parent intent → same subgoal structure (RULE 1) | Emit `PlanningDeterminismViolation` |

### Hierarchical Decomposition Guard (Pseudocode)

```
def validate_decomposition(intent: Intent, subgoals: List[Subgoal],
                            dep_graph: List[Dependency]) -> DecompositionReport:
    # H1: Coverage
    covered_nodes = set()
    for sg in subgoals:
        covered_nodes.update(sg.expected_output.get("targets", []))
    missing = set(intent.target_nodes) - covered_nodes
    if missing:
        return DecompositionReport(coherent=False, gaps=list(missing))

    # H2: Acyclic
    if has_cycle(dep_graph):
        return DecompositionReport(coherent=False, gaps=["Cyclic dependency"])

    # H3: Capability match
    for sg in subgoals:
        if sg.assigned_agent:
            agent = get_agent(sg.assigned_agent)
            required = set(sg.expected_output.get("required_caps", []))
            available = set(agent.capability_profile)
            if not required.issubset(available):
                return DecompositionReport(coherent=False,
                    gaps=[f"Agent {sg.assigned_agent} missing caps: {required - available}"])

    # H5: Coherence score
    score = compute_coherence(intent, subgoals)
    if score < 0.7:
        return DecompositionReport(coherent=False, score=score)

    return DecompositionReport(coherent=True, score=score)
```

### No-Redundant-Execution on Retry (RULE 5)

When a subgoal fails and the parent triggers a retry:

1. Check each subgoal's status.
2. If `status == COMPLETED` → skip (do not re-execute).
3. If `status == FAILED` → re-attempt up to `max_retries` (default 3).
4. If `status == CANCELLED` → check if dependency is now available.
5. Emit `PlanningRetryStatus(subgoal_id, action="skipped|retry|cancel")`.

This ensures that a single subgoal failure does NOT replay the entire
swarm's work, preserving the "recoverability without replay" principle.

---

## 4. Swarm Coordination Protocol (ISwarmCoordinator)

### Conflict Resolution Policy (RULE 1)

```
def resolve_conflicts(proposals: List[Proposal]) -> Resolution:
    # 1. Sort by trust_level (CRITICAL > HIGH > MEDIUM > LOW)
    # 2. Tie-break: lexicographic agent_id
    # 3. Final tie-break: earliest timestamp
    sorted_proposals = sorted(
        proposals,
        key=lambda p: (
            trust_level_weight(p.trust_level),
            p.agent_id,
            p.timestamp_ns,
        ),
        reverse=True,
    )
    return Resolution(
        accepted=sorted_proposals[0],
        rejected=[p.agent_id for p in sorted_proposals[1:]],
        rationale=f"Selected by trust_level priority + deterministic tie-break"
    )
```

### Consensus Model

```
def sync_consensus(votes: Dict[str, Vote], threshold: float) -> Consensus:
    total = len(votes)
    if total == 0:
        return Consensus(reached=False)

    weighted = {}
    for agent_id, vote in votes.items():
        weight = trust_level_weight(vote.trust_level)
        weighted[vote.value] = weighted.get(vote.value, 0.0) + weight

    winner = max(weighted, key=weighted.get)
    total_weight = sum(weighted.values())
    participation = weighted.get(winner, 0.0) / max(total_weight, 1.0)

    return Consensus(
        reached=participation >= threshold,
        value=winner,
        participation_rate=len(votes) / max(len(assigned_agents), 1),
        confidence=participation,
    )
```

---

## 5. State Machine Parameter Summary

| Parameter | Default | Min | Max | Description |
|-----------|---------|-----|-----|-------------|
| consensus_threshold | 0.67 | 0.51 | 1.0 | Fraction of weighted votes needed |
| max_agent_runtime_sec | 3600 | 60 | 86400 | Max agent lifespan |
| auto_pause_idle_sec | 300 | 30 | 3600 | Idle time before auto-pause |
| heartbeat_interval_sec | 15 | 1 | 60 | Health check interval |
| checkpoint_interval_sec | 120 | 10 | 600 | State checkpoint interval |
| max_retries_per_subgoal | 3 | 1 | 10 | Subgoal retry limit (RULE 5) |
| coherence_min_score | 0.7 | 0.5 | 1.0 | Minimum coherence for merge |
| health_degraded_threshold | 0.9 | 0.5 | 1.0 | Resource usage ratio for DEGRADED |

---

## 6. EventBus Topics

| Topic | Emitted When |
|-------|-------------|
| `agent.lifecycle.spawning` | IDLE → SPAWNING |
| `agent.lifecycle.running` | SPAWNING → RUNNING |
| `agent.lifecycle.paused` | RUNNING → PAUSED |
| `agent.lifecycle.degraded` | RUNNING → DEGRADED |
| `agent.lifecycle.terminated` | Any → TERMINATED |
| `agent.health.degraded` | Health check detects degradation |
| `agent.health.recovered` | DEGRADED → RUNNING |
| `agent.contract.pending` | Negotiation started |
| `agent.contract.signed` | Contract signed |
| `agent.contract.breached` | Breach detected |
| `agent.contract.voided` | Contract voided |
| `swarm.task.broadcast` | Task broadcast to swarm |
| `swarm.task.completed` | Individual task completed |
| `swarm.conflict.resolved` | Conflict resolution applied |
| `swarm.consensus.reached` | Consensus achieved |
| `swarm.load.rebalanced` | Load rebalanced across agents |
| `planning.decomposition.completed` | Intent decomposed |
| `planning.subgoal.assigned` | Subgoal assigned to agent |
| `planning.subgoal.completed` | Individual subgoal completed |
| `planning.subgoal.failed` | Subgoal execution failed |
| `planning.merge.completed` | Results merged |
| `planning.incoherence.detected` | Coherence validation failed |
| `planning.determinism.violation` | Determinism hash mismatch |
