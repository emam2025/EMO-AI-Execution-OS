"""Phase 4.5 — IsolationRuntime: the glue layer.

This is the bridge between:
  - ExecutionRuntime (infrastructure facade)
  - SandboxExecutor (isolated execution)
  - CapabilityGuard (security validation)
  - ResourceEnforcer (resource governance)
  - IOPolicyEngine + NetworkIsolation + FilesystemIsolation (IO control)

Execution flow (RULE 3):
  1. validate capabilities
  2. enforce resources
  3. create sandbox
  4. execute
  5. capture telemetry

RULE 1 — NO DIRECT EXECUTION: ExecutionEngine NEVER executes directly.
  Must go through IsolationRuntime → SandboxExecutor.

Ref: DEVELOPER.md §15.15b §4.5
Ref: Canon RULE 1 (No Direct Execution)
Ref: Canon RULE 3 (Capability First)
Ref: Canon RULE 4 (Everything is Killable)
Ref: Canon LAW 10 (Workers are unreliable)
Ref: Canon LAW 13 (No direct service calls)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict, Optional

from core.runtime.isolation.capability_guard import (
    CapabilityGuard,
    CapabilityStatus,
)
from core.security.capabilities.capability_guard import CapabilityViolation
from core.runtime.isolation.resource_enforcer import ResourceEnforcer
from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.isolation.io_policy_engine import IOPolicyEngine
from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.runtime.sandbox.sandbox_manager import SandboxManager
from core.runtime.sandbox.sandbox_errors import (
    SandboxError,
    ExecutionTimeoutError,
    ResourceLimitExceeded,
)
from core.security.capabilities.capability_model import (
    Capability,
    AccessMode,
)
from core.runtime.io.network_isolation import NetworkIsolation, NetworkBlocked
from core.runtime.io.filesystem_isolation import (
    FilesystemIsolation,
    FileAccessViolation,
)
from core.runtime.io.io_policy_engine import IOViolation
from core.runtime.resources.quota_manager import QuotaExceeded
from core.runtime.secrets import SecretInjector, RuntimeVault

logger = logging.getLogger("emo_ai.isolation.runtime")


class IsolationRuntime:
    """Integrated isolation layer — wraps every execution in a security boundary.

    All execution MUST go through this layer (RULE 1).
    RULE 3: capability → resources → sandbox → execute → telemetry.
    RULE 4: Everything is killable (timeout + RLIMIT + SIGKILL).

    Ref: DEVELOPER.md §15.15b §4.5
    Ref: Canon LAW 13 — No direct service calls; all execution
         is routed through this bridge.
    """

    def __init__(
        self,
        sandbox_manager: Optional[SandboxManager] = None,
        capability_guard: Optional[CapabilityGuard] = None,
        resource_enforcer: Optional[ResourceEnforcer] = None,
        io_policy_engine: Optional[IOPolicyEngine] = None,
        sandbox_executor: Optional[SandboxExecutor] = None,
        network_isolation: Optional[NetworkIsolation] = None,
        filesystem_isolation: Optional[FilesystemIsolation] = None,
        vault: Optional[RuntimeVault] = None,
        secret_injector: Optional[SecretInjector] = None,
    ):
        self._sandbox_manager = sandbox_manager or SandboxManager()
        self._capability_guard = capability_guard or CapabilityGuard()
        self._resource_enforcer = resource_enforcer or ResourceEnforcer()
        self._sandbox_executor = sandbox_executor or SandboxExecutor()
        self._io_policy = io_policy_engine or IOPolicyEngine()
        self._network = network_isolation or NetworkIsolation()
        self._filesystem = filesystem_isolation or FilesystemIsolation()
        self._vault = vault or RuntimeVault()
        self._secret_injector = secret_injector or SecretInjector(self._vault)

    @property
    def sandbox_manager(self) -> SandboxManager:
        return self._sandbox_manager

    @property
    def capability_guard(self) -> CapabilityGuard:
        return self._capability_guard

    @property
    def resource_enforcer(self) -> ResourceEnforcer:
        return self._resource_enforcer

    @property
    def sandbox_executor(self) -> SandboxExecutor:
        return self._sandbox_executor

    @property
    def io_policy_engine(self) -> IOPolicyEngine:
        return self._io_policy

    @property
    def network_isolation(self) -> NetworkIsolation:
        return self._network

    @property
    def filesystem_isolation(self) -> FilesystemIsolation:
        return self._filesystem

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

        RULE 1: No direct subprocess/threadpool/IO.
        RULE 4: Every execution is killable.

        Args:
            tool_name: Name of the tool to execute.
            inputs: Input parameters.
            runner: Optional callable (for in-process fallback via execute_direct).
            sandbox_context: Optional SandboxContext overrides.

        Returns:
            Execution result dict with status, result/error, elapsed.
        """
        execution_id = uuid.uuid4().hex[:12]

        try:
            # ── Step 1: Validate capabilities (RULE 3) ──
            # LAW 10: Validate before scheduling.
            cap_result = self._capability_guard.validate(tool_name, inputs, sandbox_context)
            if isinstance(cap_result, CapabilityStatus):
                if not cap_result.allowed:
                    logger.warning(
                        "Step 1 [capabilities] %s: BLOCKED — %s",
                        tool_name, cap_result.reason,
                    )
                    return {
                        "status": "blocked",
                        "error": cap_result.reason,
                        "reason": "capability_violation",
                        "tool": tool_name,
                        "execution_id": execution_id,
                    }
                capability = cap_result.capability
            else:
                capability = cap_result
            logger.debug(
                "Step 1 [capabilities] %s: network=%s fs=%s",
                tool_name, capability.network, capability.filesystem,
            )

            # Build sandbox context from capability
            context = self._build_sandbox_context(capability, sandbox_context)

            # ── Step 2: Pre-check resources (LAW 10) ──
            self._resource_enforcer.check_before_scheduling(
                execution_id, tool_name,
                estimated_cpu=capability.max_cpu,
                estimated_memory=capability.max_memory,
            )
            logger.debug("Step 2 [resources] %s: pre-check passed", tool_name)

            # ── Step 3: Create sandbox ──
            sandbox_id = self._sandbox_manager.create_sandbox(context)
            logger.debug("Step 3 [sandbox] %s: sandbox=%s", tool_name, sandbox_id)

            # Step 3.5: Inject secrets (E3 integration)
            secret_keys = self._vault.list_secrets(scope=execution_id)
            if secret_keys:
                self._secret_injector.inject(
                    context.environment,
                    execution_id,
                    secret_keys,
                    scope=execution_id,
                )
                logger.debug(
                    "Step 3.5 [secrets] %s: injected %d secrets",
                    tool_name, len(secret_keys),
                )

            # ── Step 4: Execute in sandbox (RULE 1, RULE 4) ──
            if runner is not None:
                result = self._sandbox_executor.execute_direct(
                    runner, inputs, context, exec_id=execution_id,
                )
            else:
                result = self._sandbox_executor.execute(tool_name, inputs, context)

            logger.debug(
                "Step 4 [execute] %s: status=%s", tool_name, result.get("status"),
            )

            # ── Step 5: Capture telemetry (LAW 10) ──
            self._resource_enforcer.finish(execution_id)

            # Cleanup sandbox
            self._sandbox_manager.destroy_sandbox(sandbox_id)

            result["execution_id"] = execution_id
            result["tool"] = tool_name
            return result

        except CapabilityViolation as e:
            logger.warning("Isolation blocked [capability] %s: %s", tool_name, e)
            return {
                "status": "blocked",
                "error": str(e),
                "reason": "capability_violation",
                "tool": tool_name,
                "execution_id": execution_id,
            }
        except (QuotaExceeded, ResourceLimitExceeded) as e:
            logger.warning("Isolation blocked [resources] %s: %s", tool_name, e)
            self._resource_enforcer.finish(execution_id)
            return {
                "status": "blocked",
                "error": str(e),
                "reason": "resource_exceeded",
                "tool": tool_name,
                "execution_id": execution_id,
            }
        except (IOViolation, NetworkBlocked, FileAccessViolation) as e:
            logger.warning("Isolation blocked [io] %s: %s", tool_name, e)
            return {
                "status": "blocked",
                "error": str(e),
                "reason": "io_violation",
                "tool": tool_name,
                "execution_id": execution_id,
            }
        except SandboxError as e:
            logger.error("Isolation error [sandbox] %s: %s", tool_name, e)
            return {
                "status": "failed",
                "error": str(e),
                "reason": "sandbox_error",
                "tool": tool_name,
                "execution_id": execution_id,
            }
        except Exception as e:
            logger.exception("Isolation error %s: %s", tool_name, e)
            return {
                "status": "failed",
                "error": f"{type(e).__name__}: {e}",
                "reason": "unexpected",
                "tool": tool_name,
                "execution_id": execution_id,
            }

    def check_io(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if an IO operation is permitted.

        RULE 2: All IO MUST pass through policy check.
        Delegates to IOPolicyEngine.
        """
        self._io_policy.check(tool, operation, target, size)

    def check_network(self, tool: str, url: str) -> None:
        """Check if a network request is permitted.

        Delegates to NetworkIsolation.
        """
        self._network.check_request(tool, url)

    def check_filesystem_read(self, tool: str, path: str) -> str:
        """Check if a file can be read.

        Delegates to FilesystemIsolation.
        """
        return self._filesystem.check_read(tool, path)

    def check_filesystem_write(self, tool: str, path: str) -> str:
        """Check if a file can be written.

        Delegates to FilesystemIsolation.
        """
        return self._filesystem.check_write(tool, path)

    def shutdown(self) -> None:
        """Shutdown all isolation components.

        RULE 4: No resource leaks — destroy all sandboxes.
        """
        self._sandbox_manager.shutdown()
        logger.info("IsolationRuntime shutdown complete")

    @staticmethod
    def _build_sandbox_context(
        capability: Capability,
        overrides: Optional[SandboxContext] = None,
    ) -> SandboxContext:
        """Build a SandboxContext from a Capability with optional overrides."""
        context = SandboxContext(
            cpu_limit=capability.max_cpu,
            memory_limit=capability.max_memory,
            timeout=overrides.timeout if overrides else 30.0,
            filesystem_mode=(
                FilesystemMode.FULL
                if capability.filesystem == AccessMode.FULL
                else FilesystemMode.READ_ONLY
                if capability.filesystem == AccessMode.READ
                else FilesystemMode.NONE
            ),
            network_mode=(
                NetworkMode.FULL
                if capability.network
                else NetworkMode.BLOCKED
            ),
            allowed_paths=capability.allowed_paths,
            allowed_domains=capability.allowed_domains,
        )
        if overrides:
            if overrides.timeout and overrides.timeout < context.timeout:
                context.timeout = overrides.timeout
            if overrides.working_dir:
                context.working_dir = overrides.working_dir
        return context
