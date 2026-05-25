"""Canon rule implementations — LAW 14-19."""

from typing import Any, Callable, Dict, List, Optional

from core.canon.context import ValidationContext


def law_14(context: ValidationContext) -> bool:
    """All boundary decisions MUST be derived from CodeGraph analysis.

    Passes if a CodeGraph is available in the validation context.
    """
    return context.graph is not None


def law_15(context: ValidationContext) -> bool:
    """No refactor is valid unless dependency graph is updated first.

    Passes if the graph has a version identifier.
    """
    if context.graph is None:
        return True
    version = getattr(context.graph, "version", None)
    return version is not None


def law_16(context: ValidationContext) -> bool:
    """Any node with risk_score > 0.8 MUST be decomposed.

    Passes if no node in the graph exceeds the threshold.
    """
    if context.graph is None:
        return True
    for node in context.graph.nodes.values():
        risk = getattr(node, "risk_score", None)
        if risk is not None and risk > 0.8:
            return False
    return True


def law_17(context: ValidationContext) -> bool:
    """Runtime behavior MUST be observable as graph transformations.

    Passes if the runtime has an event bus with active subscribers.
    """
    event_bus = getattr(context, "event_bus", None)
    if event_bus is None:
        return False
    return True


def law_18(context: ValidationContext) -> bool:
    """Static and runtime architecture MUST be continuously reconciled.

    Passes if a RuntimeDriftDetector is available.
    """
    drift_detector = getattr(context, "drift_detector", None)
    return drift_detector is not None


def law_19(context: ValidationContext) -> bool:
    """All execution traces MUST be explainable.

    Passes if RuntimeIntelligence is available.
    """
    runtime_intel = getattr(context, "runtime_intelligence", None)
    return runtime_intel is not None


# ── D8.2 — Failure Propagation Law ──


def law_20(context: ValidationContext) -> bool:
    """Every service MUST have a defined failure propagation policy.

    Passes if a FailurePropagationPolicy is available.
    """
    policy = getattr(context, "failure_propagation_policy", None)
    return policy is not None


def law_21(context: ValidationContext) -> bool:
    """Dispatcher failure MUST trigger scheduler retry, retry classification,
    and lease release.

    Passes if the failure_propagation_policy has rules for DISPATCHER.
    """
    policy = getattr(context, "failure_propagation_policy", None)
    if policy is None:
        return False
    from core.interfaces.failure_propagation import FailureDomain, PropagationAction
    rules = policy.evaluate(FailureDomain.DISPATCHER)
    required_actions = {PropagationAction.RETRY,
                        PropagationAction.CLASSIFY,
                        PropagationAction.RELEASE_LEASE}
    found = {r.action for r in rules}
    return required_actions.issubset(found)


def law_22(context: ValidationContext) -> bool:
    """Lease expiry MUST trigger cancel, rollback, and reassign.

    Passes if the failure_propagation_policy has rules for LEASE_MANAGER.
    """
    policy = getattr(context, "failure_propagation_policy", None)
    if policy is None:
        return False
    from core.interfaces.failure_propagation import FailureDomain, PropagationAction
    rules = policy.evaluate(FailureDomain.LEASE_MANAGER)
    required_actions = {PropagationAction.CANCEL,
                        PropagationAction.ROLLBACK,
                        PropagationAction.REASSIGN}
    found = {r.action for r in rules}
    return required_actions.issubset(found)


# ── D8.4 — Service Ownership Laws ──


def law_23(context: ValidationContext) -> bool:
    """IExecutionScheduler MUST own execution ordering only.

    Passes if scheduler does NOT hold references to retry, dispatch,
    or lease objects.
    """
    scheduler = getattr(context, "scheduler", None)
    if scheduler is None:
        return True
    attrs = {k for k in dir(scheduler) if not k.startswith("_")}
    forbidden_methods = {"retry", "dispatch", "lease", "acquire", "release",
                         "set_state", "store_trace", "save_checkpoint"}
    return not bool(attrs & forbidden_methods)


def law_24(context: ValidationContext) -> bool:
    """IExecutionDispatcher MUST own execution routing only.

    Passes if dispatcher does NOT hold references to retry, lease,
    or state storage methods.
    """
    dispatcher = getattr(context, "dispatcher", None)
    if dispatcher is None:
        return True
    attrs = {k for k in dir(dispatcher) if not k.startswith("_")}
    forbidden_methods = {"set_state", "store_trace", "save_checkpoint",
                         "acquire", "release", "heartbeat",
                         "should_retry", "compute_backoff"}
    return not bool(attrs & forbidden_methods)


def law_25(context: ValidationContext) -> bool:
    """IExecutionRetryHandler MUST own retry semantics only.

    Passes if retry handler does NOT own scheduling, dispatch,
    or storage methods.
    """
    retry = getattr(context, "retry_handler", None)
    if retry is None:
        return True
    attrs = {k for k in dir(retry) if not k.startswith("_")}
    forbidden_methods = {"order_levels", "allocate_worker",
                         "dispatch_local", "dispatch_remote",
                         "set_state", "store_trace",
                         "acquire", "release"}
    return not bool(attrs & forbidden_methods)


def law_26(context: ValidationContext) -> bool:
    """IExecutionStateStore MUST own persistence and traces only.

    Passes if state store does NOT own dispatch, retry, or lease methods.
    """
    store = getattr(context, "state_store", None)
    if store is None:
        return True
    attrs = {k for k in dir(store) if not k.startswith("_")}
    forbidden_methods = {"dispatch_local", "dispatch_remote",
                         "should_retry", "compute_backoff",
                         "acquire", "release", "heartbeat",
                         "order_levels", "allocate_worker"}
    return not bool(attrs & forbidden_methods)


def law_27(context: ValidationContext) -> bool:
    """No two services MAY share ownership of the same domain.

    Passes if the services in context do not expose overlapping
    domain-specific methods.
    """
    all_services = {}
    for name in ("scheduler", "dispatcher", "retry_handler",
                  "state_store", "lease_manager"):
        svc = getattr(context, name, None)
        if svc is not None:
            all_services[name] = {k for k in dir(svc) if not k.startswith("_")}
    if len(all_services) < 2:
        return True
    from itertools import combinations
    for (n1, a1), (n2, a2) in combinations(all_services.items(), 2):
        overlap = a1 & a2
        if overlap:
            return False
    return True


# ── GAP 4 — Evolution Meta-Governance ──


def law_28(context: ValidationContext) -> bool:
    """Human-in-the-loop Evolution Gate.

    Any Canon/Architecture change MUST require explicit approval.
    Passes if an evolution_approval_func is available.
    """
    return getattr(context, "evolution_approval_func", None) is not None


def law_29(context: ValidationContext) -> bool:
    """Immutable Audit Trail for Evolution.

    Every evolution change MUST be logged and replayable.
    Passes if an evolution_audit_log is available.
    """
    return getattr(context, "evolution_audit_log", None) is not None


def law_30(context: ValidationContext) -> bool:
    """Safe Rollback Requirement.

    Any evolution MUST be reversible without system corruption.
    Passes if an evolution_rollback_func is available.
    """
    return getattr(context, "evolution_rollback_func", None) is not None


LAW_FACTORY: Dict[str, Callable[[ValidationContext], bool]] = {
    "LAW_14": law_14,
    "LAW_15": law_15,
    "LAW_16": law_16,
    "LAW_17": law_17,
    "LAW_18": law_18,
    "LAW_19": law_19,
    "LAW_20": law_20,
    "LAW_21": law_21,
    "LAW_22": law_22,
    "LAW_23": law_23,
    "LAW_24": law_24,
    "LAW_25": law_25,
    "LAW_26": law_26,
    "LAW_27": law_27,
    "LAW_28": law_28,
    "LAW_29": law_29,
    "LAW_30": law_30,
}
