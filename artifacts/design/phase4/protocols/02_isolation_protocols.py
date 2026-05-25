"""Phase 4 — Official Protocol Definitions for Runtime Isolation Layer.

DESIGN ONLY — No runtime logic. These are typing.Protocol definitions
conforming to DEVELOPER.md §15.15b and Architecture Canon §16.

Each protocol maps to a component in the isolation architecture:
  IIsolationRuntime     → 4.5 — Bridge between Engine, Sandbox, Security, Resources, IO
  ICapabilityGuard      → 4.2 — Security validation (pre-execution)
  IResourceEnforcer     → 4.4 — Resource governance (pre-check + mid-flight)
  ISandboxExecutor      → 4.1 — Subprocess execution + kill-safe
  IIOPolicyEngine       → 4.3 — IO allow/deny control

RULE 1 enforcement: ExecutionEngine MUST route through IIsolationRuntime.
RULE 3 enforcement: execute() follows capability → resources → sandbox → execute → telemetry.
RULE 4 enforcement: All sandbox executors MUST support kill(timeout) with SIGKILL fallback.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ─────────────────────────────────────────────────────────────────────
# 4.1 — ISandboxExecutor
# ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class ISandboxExecutor(Protocol):
    """Subprocess execution with isolation, timeout, and kill-safe semantics.

    Law: Every execution MUST be killable (RULE 4).
    Law: Subprocess is the OS boundary — only SandboxExecutor may call subprocess.Popen.
    Ref: DEVELOPER.md §15.15b §4.1
    Ref: Canon LAW 10 (Workers are unreliable)
    """

    def execute(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: Any,  # SandboxContext — see models/03_security_resource_models.py
    ) -> Dict[str, Any]:
        """Execute tool in isolated subprocess.

        Args:
            tool_name: Name of the tool to execute.
            inputs: Input parameters.
            context: SandboxContext with resource limits, FS/network modes.

        Returns:
            Dict with keys: status, result/error, elapsed.

        Raises:
            ExecutionTimeoutError: If execution exceeds context.timeout.
            ResourceLimitExceeded: If resource limits breached.
            SandboxViolationError: If sandbox rules violated.
        """
        ...

    def execute_direct(
        self,
        runner: Any,
        execution_input: Any,
        context: Any,
        exec_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a callable in a thread with timeout (non-subprocess fallback).

        Args:
            runner: Callable to execute.
            execution_input: Input to the callable.
            context: SandboxContext with resource limits.
            exec_id: Optional execution identifier for kill().

        Returns:
            Dict with keys: status, result/error, elapsed.
        """
        ...

    def kill(self, exec_id: str) -> bool:
        """Kill a running execution by ID.

        For subprocess: SIGKILL → proc.kill() → proc.wait(5.0).
        For threads: Sets cancel event flag.

        Args:
            exec_id: Execution identifier.

        Returns:
            True if execution was found and killed, False otherwise.
        """
        ...


# ─────────────────────────────────────────────────────────────────────
# 4.2 — ICapabilityGuard
# ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class ICapabilityGuard(Protocol):
    """Pre-execution security validation — NO capability → NO execution.

    Law: Every tool MUST have a registered capability before execution.
    Law: Capability defines network/filesystem/subprocess/cpu/memory permissions.
    Ref: DEVELOPER.md §15.15b §4.2
    Ref: Canon RULE 3 (Capability First)
    """

    def validate(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
    ) -> Any:  # Capability — see models/03_security_resource_models.py
        """Validate tool against capability registry.

        Args:
            tool_name: Name of the tool to validate.
            inputs: Input parameters (used for context-aware validation).

        Returns:
            Capability object with allowed permissions.

        Raises:
            CapabilityViolation: If no capability registered or inputs violate restrictions.
        """
        ...


# ─────────────────────────────────────────────────────────────────────
# 4.4 — IResourceEnforcer
# ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class IResourceEnforcer(Protocol):
    """Resource governance — pre-check + mid-flight enforcement + telemetry.

    Three-phase lifecycle:
      1. check_before_scheduling() — pre-execution quota validation.
      2. enforce() — mid-flight resource limit check.
      3. finish() — telemetry archiving + quota release.

    Law: No execution may proceed if quotas would be exceeded.
    Law: All resource usage MUST be tracked and archived.
    Ref: DEVELOPER.md §15.15b §4.4
    Ref: Canon LAW 10 (Workers are unreliable — must enforce bounds)
    """

    def check_before_scheduling(
        self,
        execution_id: str,
        tool: str,
        estimated_cpu: float = 0.0,
        estimated_memory: int = 0,
    ) -> None:
        """Pre-check if execution can proceed.

        Args:
            execution_id: Unique execution identifier.
            tool: Tool name.
            estimated_cpu: Estimated CPU seconds required.
            estimated_memory: Estimated memory bytes required.

        Raises:
            QuotaExceeded: If global or worker quotas would be exceeded.
        """
        ...

    def enforce(
        self,
        execution_id: str,
        cpu: float = 0.0,
        memory: int = 0,
        wall_time: float = 0.0,
    ) -> bool:
        """Enforce resource limits during execution.

        Args:
            execution_id: Unique execution identifier.
            cpu: Current CPU seconds consumed.
            memory: Current memory bytes consumed.
            wall_time: Current wall-clock time in seconds.

        Returns:
            True if execution should continue, False if should be killed.
        """
        ...

    def finish(self, execution_id: str) -> None:
        """Finalize resource tracking and archive telemetry.

        Args:
            execution_id: Unique execution identifier to finalize.
        """
        ...


# ─────────────────────────────────────────────────────────────────────
# 4.3 — IIOPolicyEngine
# ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class IIOPolicyEngine(Protocol):
    """IO allow/deny policy engine — all IO MUST pass through this.

    Controls three domains:
      - Network: outbound request filtering (DNS/URL).
      - Filesystem: path whitelist, read/write restrictions.
      - Operations: tool-scoped IO policy (max size, rate limits).

    Law: No IO operation may bypass policy check (RULE 2).
    Ref: DEVELOPER.md §15.15b §4.3
    Ref: Canon RULE 2 (No uncontrolled IO)
    """

    def check(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if an IO operation is permitted.

        Args:
            tool: Tool name requesting the operation.
            operation: Operation type (e.g. "network.get", "file.read", "file.write").
            target: URL, domain, or filesystem path.
            size: Payload size in bytes for size-limited operations.

        Raises:
            IOViolation: If operation is not permitted.
        """
        ...

    def allow(self, tool: str, operation: str) -> None:
        """Allow a specific operation for a tool."""
        ...

    def block(self, tool: str, operation: str) -> None:
        """Block a specific operation for a tool."""
        ...


# ─────────────────────────────────────────────────────────────────────
# 4.5 — IIsolationRuntime (BRIDGE)
# ─────────────────────────────────────────────────────────────────────

@runtime_checkable
class IIsolationRuntime(Protocol):
    """IsolationRuntime — the single bridge between ExecutionEngine and all isolation layers.

    Execution flow (RULE 3):
      1. validate capabilities        → ICapabilityGuard.validate()
      2. enforce resources (pre-check) → IResourceEnforcer.check_before_scheduling()
      3. create sandbox               → SandboxManager.create_sandbox()
      4. execute                      → ISandboxExecutor.execute()
      5. capture telemetry            → IResourceEnforcer.finish()

    Law: ExecutionEngine MUST NOT call subprocess/threadpool/IO directly.
    Law: All execution MUST route through IIsolationRuntime.execute().
    Ref: DEVELOPER.md §15.15b §4.5
    Ref: Canon RULE 1 (No Direct Execution)
    Ref: Canon RULE 3 (Capability First)
    Ref: Canon RULE 4 (Everything is Killable)
    """

    def execute(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        runner: Any = None,
        sandbox_context: Any = None,
    ) -> Dict[str, Any]:
        """Execute a tool with full isolation.

        Args:
            tool_name: Tool to execute.
            inputs: Input parameters.
            runner: Optional callable (for in-process fallback via execute_direct).
            sandbox_context: Optional SandboxContext overrides.

        Returns:
            Execution result dict.
        """
        ...

    def check_io(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if IO operation is permitted (delegates to IIOPolicyEngine)."""
        ...

    def check_network(self, tool: str, url: str) -> None:
        """Check if network request is permitted (delegates to NetworkIsolation)."""
        ...

    def check_filesystem_read(self, tool: str, path: str) -> str:
        """Check if file can be read (delegates to FilesystemIsolation)."""
        ...

    def check_filesystem_write(self, tool: str, path: str) -> str:
        """Check if file can be written (delegates to FilesystemIsolation)."""
        ...

    def shutdown(self) -> None:
        """Shutdown all isolation components (sandbox cleanup, resource flush)."""
        ...


# ─────────────────────────────────────────────────────────────────────
# Protocol conformance verification helpers
# ─────────────────────────────────────────────────────────────────────

def verify_protocol_conformance() -> Dict[str, bool]:
    """Verify that all runtime types conform to their protocols."""
    # Ensure project root is on sys.path for conformance check
    _project_root = __file__.replace("artifacts/design/phase4/protocols/02_isolation_protocols.py", "")
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    results: Dict[str, bool] = {}

    try:
        from core.runtime.isolation.isolation_runtime import IsolationRuntime
        results["IsolationRuntime : IIsolationRuntime"] = isinstance(
            IsolationRuntime, type
        ) and hasattr(IsolationRuntime, "execute")
    except ImportError as e:
        results[f"IsolationRuntime (import error: {e})"] = False

    try:
        from core.runtime.sandbox.sandbox_executor import SandboxExecutor
        results["SandboxExecutor : ISandboxExecutor"] = hasattr(
            SandboxExecutor, "execute"
        ) and hasattr(SandboxExecutor, "kill")
    except ImportError as e:
        results[f"SandboxExecutor (import error: {e})"] = False

    try:
        from core.security.capabilities.capability_guard import CapabilityGuard
        results["CapabilityGuard : ICapabilityGuard"] = hasattr(
            CapabilityGuard, "validate"
        )
    except ImportError as e:
        results[f"CapabilityGuard (import error: {e})"] = False

    try:
        from core.runtime.resources.resource_enforcer import ResourceEnforcer
        results["ResourceEnforcer : IResourceEnforcer"] = (
            hasattr(ResourceEnforcer, "check_before_scheduling")
            and hasattr(ResourceEnforcer, "enforce")
            and hasattr(ResourceEnforcer, "finish")
        )
    except ImportError as e:
        results[f"ResourceEnforcer (import error: {e})"] = False

    try:
        from core.runtime.io.io_policy_engine import IOPolicyEngine
        results["IOPolicyEngine : IIOPolicyEngine"] = (
            hasattr(IOPolicyEngine, "check")
            and hasattr(IOPolicyEngine, "allow")
            and hasattr(IOPolicyEngine, "block")
        )
    except ImportError as e:
        results[f"IOPolicyEngine (import error: {e})"] = False

    return results


if __name__ == "__main__":
    import json

    results = verify_protocol_conformance()
    print("=" * 60)
    print("Protocol Conformance Verification")
    print("=" * 60)
    all_pass = True
    for key, value in results.items():
        status = "✅" if value else "❌"
        print(f"  {status}  {key}")
        if not value:
            all_pass = False
    print()
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"Result: {passed}/{total} passed")
    print(f"Overall: {'ALL CONFORMANT' if all_pass else 'GAPS DETECTED'}")

    # Write conformance report
    import pathlib
    output_path = pathlib.Path(__file__).parent / "02_protocol_conformance.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport → {output_path}")
