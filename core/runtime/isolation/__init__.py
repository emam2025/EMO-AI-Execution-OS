"""Phase 4.5 — Isolation Integration Layer (BRIDGE).

Exports all isolation-layer components:
  - IsolationRuntime:      The 5-step RULE 3 bridge
  - CapabilityGuard:       Pre-execution capability validation
  - ResourceEnforcer:      Three-phase resource governance
  - SandboxExecutor:       Kill-safe subprocess execution
  - IOPolicyEngine:        IO allow/deny policy engine

Ref: DEVELOPER.md §15.15b
Ref: Architecture Canon §16 (LAW 10, 13, 23-27, RULE 1-4)
"""

from core.runtime.isolation.isolation_runtime import IsolationRuntime
from core.runtime.isolation.capability_guard import CapabilityGuard, CapabilityStatus
from core.runtime.isolation.resource_enforcer import ResourceEnforcer, ResourceLimitExceeded
from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.isolation.io_policy_engine import IOPolicyEngine

__all__ = [
    "IsolationRuntime",
    "CapabilityGuard",
    "CapabilityStatus",
    "ResourceEnforcer",
    "ResourceLimitExceeded",
    "SandboxExecutor",
    "IOPolicyEngine",
]
