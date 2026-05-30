"""RuntimeFactory — Pure wiring for ExecutionEngine, UnifiedRuntime, ControlPlane, ResourceScheduler.

LAW 13: This factory is the ONLY place (besides CompositionRoot) that may
call ExecutionEngine(...) or UnifiedRuntime(...). It contains ZERO business
logic, ZERO policy evaluation, ZERO conditional runtime decisions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.factory.runtime")


def build_unified_runtime(
    scheduler: Any = None,
    state_store: Any = None,
    dispatcher: Any = None,
    retry_handler: Any = None,
    lease_manager: Any = None,
    event_bus: Any = None,
    failure_matrix: Any = None,
    sandbox_manager: Any = None,
    isolation_runtime: Any = None,
    strict_api_mode: bool = False,
) -> Any:
    """Construct a UnifiedRuntime from already-wired D8 services."""
    from core.runtime.api.unified_runtime_api import UnifiedRuntime

    return UnifiedRuntime(
        scheduler=scheduler,
        state_store=state_store,
        dispatcher=dispatcher,
        retry_handler=retry_handler,
        lease_manager=lease_manager,
        event_bus=event_bus,
        failure_matrix=failure_matrix,
        sandbox_manager=sandbox_manager,
        isolation_runtime=isolation_runtime,
        strict_api_mode=strict_api_mode,
    )


def build_control_plane(
    event_bus: Any = None,
    cooldown_seconds: int = 0,
    required_consecutive: int = 2,
    health_supervisor: Any = None,
    reconciliation_loop: Any = None,
    worker_drainer: Any = None,
    worker_drain_max_wait_sec: float = 300.0,
) -> Any:
    """Construct a ControlPlane instance (Phase F2) — pure wiring, zero policy.

    Mirrors original root.py construction exactly.
    """
    from core.runtime.control_plane.control_plane import ControlPlane
    from core.runtime.control_plane.autoscaler import Autoscaler
    from core.runtime.control_plane.health_supervisor import HealthSupervisor
    from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
    from core.runtime.control_plane.worker_drainer import WorkerDrainer
    from core.runtime.control_plane.oscillation_guard import (
        CooldownTimer,
        HysteresisEvaluator,
        ConsecutiveCycleTracker,
    )

    return ControlPlane(
        autoscaler=Autoscaler(
            cooldown_timer=CooldownTimer(cooldown_seconds=cooldown_seconds),
            hysteresis=HysteresisEvaluator(),
            cycle_tracker=ConsecutiveCycleTracker(required_consecutive=required_consecutive),
        ),
        health_supervisor=health_supervisor or HealthSupervisor(event_bus=event_bus),
        reconciliation_loop=reconciliation_loop or ReconciliationLoop(),
        worker_drainer=worker_drainer or WorkerDrainer(max_drain_wait_sec=worker_drain_max_wait_sec),
    )


def build_resource_scheduler(
    quota_arbitrator: Any = None,
    fairness_engine: Any = None,
    topology_mapper: Any = None,
    state_machine: Any = None,
    starvation_handler: Any = None,
) -> Any:
    """Construct a ResourceScheduler — pure wiring, zero policy.

    Mirrors original root.py construction exactly.
    """
    from core.runtime.resource_scheduler.resource_scheduler import ResourceScheduler
    from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
    from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
    from core.runtime.resource_scheduler.topology_mapper import TopologyMapper
    from core.runtime.resource_scheduler.allocation_state_machine import (
        AllocationStateMachine,
    )
    from core.runtime.resource_scheduler.starvation_handler import StarvationHandler

    return ResourceScheduler(
        quota_arbitrator=quota_arbitrator or QuotaArbitrator(),
        fairness_engine=fairness_engine or FairnessEngine(),
        topology_mapper=topology_mapper or TopologyMapper(),
        state_machine=state_machine or AllocationStateMachine(),
        starvation_handler=starvation_handler or StarvationHandler(),
    )


def build_execution_engine(
    tool_registry: Any = None,
    memory: Any = None,
    worker_pool_size: int = 4,
    cache: Any = None,
    service_registry: Any = None,
    optimizer: Any = None,
    cost_tracker: Any = None,
    size_limiter: Any = None,
    checkpoint_manager: Any = None,
    contract_validator: Any = None,
    compliance_validator: Any = None,
    event_bus: Any = None,
    canon_validator: Any = None,
    codegraph: Any = None,
    isolation_runtime: Any = None,
    strict_isolation: bool = False,
) -> Any:
    """Construct an ExecutionEngine — the ONLY construction point (LAW 13)."""
    from core.execution_engine import ExecutionEngine

    if strict_isolation and isolation_runtime is None:
        raise RuntimeError(
            "LAW 13 VIOLATION: ExecutionEngine cannot be built without "
            "IsolationRuntime. Enable by setting strict_isolation=True "
            "and passing isolation_runtime."
        )

    return ExecutionEngine(
        tool_registry=tool_registry or {},
        memory=memory,
        worker_pool_size=worker_pool_size,
        cache=cache,
        service_registry=service_registry,
        optimizer=optimizer,
        cost_tracker=cost_tracker,
        size_limiter=size_limiter,
        checkpoint_manager=checkpoint_manager,
        contract_validator=contract_validator,
        compliance_validator=compliance_validator,
        event_bus=event_bus,
        canon_validator=canon_validator,
        codegraph=codegraph,
    )


def build_agent_lifecycle_manager(
    planner_agent: Any = None,
    critic_agent: Any = None,
    optimizer_agent: Any = None,
    tool_synthesizer: Any = None,
    swarm_coordinator: Any = None,
    trace_correlator: Any = None,
    agent_registry: Any = None,
    strict_swarm_mode: bool = False,
) -> Any:
    """Construct an AgentLifecycleManager wiring 5 agents + registry."""
    from core.runtime.orchestration.agent_lifecycle_manager import (
        AgentLifecycleManager,
    )

    return AgentLifecycleManager(
        planner=planner_agent,
        critic=critic_agent,
        optimizer=optimizer_agent,
        synthesizer=tool_synthesizer,
        swarm=swarm_coordinator,
        correlator=trace_correlator,
        agent_registry=agent_registry,
        strict_swarm_mode=strict_swarm_mode,
    )
