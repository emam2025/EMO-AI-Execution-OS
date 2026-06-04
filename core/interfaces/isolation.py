"""Phase 4.5 — IIsolationRuntime Protocol.

Defines the contract for the isolation runtime bridge (RULE 1, RULE 3).
All execution MUST go through this interface.

Ref: DEVELOPER.md §15.15b §4.5
Ref: Canon RULE 1 (No Direct Execution)
Ref: Canon RULE 3 (Capability First)
Ref: Canon RULE 4 (Everything is Killable)
Ref: Canon LAW 10 (Workers are unreliable)
Ref: Canon LAW 13 (No direct service calls)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol

from core.runtime.sandbox.sandbox_context import SandboxContext
from core.runtime.isolation.capability_guard import CapabilityGuard
from core.runtime.isolation.resource_enforcer import ResourceEnforcer
from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.isolation.io_policy_engine import IOPolicyEngine
from core.runtime.io.network_isolation import NetworkIsolation
from core.runtime.io.filesystem_isolation import FilesystemIsolation
from core.runtime.sandbox.sandbox_manager import SandboxManager


class IIsolationRuntime(Protocol):
    """Protocol for the isolation runtime bridge.

    Every execution MUST pass through this layer (RULE 1).
    RULE 3 flow: capability -> resources -> sandbox -> execute -> telemetry.
    RULE 4: Everything is killable (timeout + RLIMIT + SIGKILL).
    """

    # -- Sub-component access --

    sandbox_manager: SandboxManager
    """Sandbox lifecycle manager."""

    capability_guard: CapabilityGuard
    """Pre-execution capability validation."""

    resource_enforcer: ResourceEnforcer
    """Three-phase resource governance."""

    sandbox_executor: SandboxExecutor
    """Kill-safe subprocess execution."""

    io_policy_engine: IOPolicyEngine
    """IO allow/deny policy engine."""

    network_isolation: NetworkIsolation
    """Outbound network request control."""

    filesystem_isolation: FilesystemIsolation
    """Filesystem access control."""

    # -- Core execution --

    def execute(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        runner: Optional[Callable] = None,
        sandbox_context: Optional[SandboxContext] = None,
    ) -> Dict[str, Any]:
        """Execute a tool with full isolation.

        RULE 3 execution flow:
          1. Validate capabilities
          2. Enforce resources (pre-check)
          3. Create sandbox
          4. Execute in sandbox
          5. Capture telemetry

        Args:
            tool_name: Name of the tool to execute.
            inputs: Input parameters.
            runner: Optional callable for in-process fallback.
            sandbox_context: Optional SandboxContext overrides.

        Returns:
            Execution result dict with status, result/error, elapsed.
        """

    # -- IO policy checks (RULE 2) --

    def check_io(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if an IO operation is permitted.

        RULE 2: All IO MUST pass through policy check.
        Raises IOViolation if not permitted.
        """

    def check_network(self, tool: str, url: str) -> None:
        """Check if a network request is permitted.

        Raises NetworkBlocked if not permitted.
        """

    def check_filesystem_read(self, tool: str, path: str) -> str:
        """Check if a file can be read.

        Returns the resolved path.
        Raises FileAccessViolation if not permitted.
        """

    def check_filesystem_write(self, tool: str, path: str) -> str:
        """Check if a file can be written.

        Returns the resolved path.
        Raises FileAccessViolation if not permitted.
        """

    # -- Lifecycle --

    def shutdown(self) -> None:
        """Shutdown all isolation components.

        RULE 4: No resource leaks -- destroy all sandboxes.
        """
