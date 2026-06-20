"""IsolationRuntime — Unified Execution Isolation Layer.

Integrates CapabilityGuard, IOPolicyEngine, and SandboxExecutor into
a single execution pipeline enforcing RULE 3:
Capability → IO Policy → Sandbox → Telemetry

Ref: Phase E.1.3 — IsolationRuntime Integration Layer
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.sandbox import SandboxContext, SandboxResult
from core.models.security import Capability, CapabilityManifest

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus
    from core.runtime.sandbox.sandbox_executor import SandboxExecutor
    from core.security.capability_guard import CapabilityGuard
    from core.security.io_policy_engine import IOPolicyEngine

logger = logging.getLogger(__name__)


class IsolationRuntime:
    """Unified isolation runtime — enforces the full execution pipeline.

    Flow: CapabilityGuard → IOPolicyEngine → SandboxExecutor → Telemetry
    Any failure at any stage returns SandboxResult(success=False) with
    a clear error message.
    """

    def __init__(
        self,
        capability_guard: CapabilityGuard,
        io_policy_engine: IOPolicyEngine,
        sandbox_executor: SandboxExecutor,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._capability_guard = capability_guard
        self._io_policy_engine = io_policy_engine
        self._sandbox_executor = sandbox_executor
        self._event_bus = event_bus

    async def execute_tool(
        self, tool_id: str, script: str, inputs: Dict[str, Any]
    ) -> SandboxResult:
        """Execute a tool through the full isolation pipeline.

        Steps:
        1. Capability Guard — check tool has required capabilities
        2. IO Policy Engine — check script doesn't violate file/network policy
        3. Sandbox Executor — execute in isolated subprocess
        """
        self._publish_event(
            "EXECUTION_STARTED",
            {"tool_id": tool_id, "phase": "isolation_runtime"},
        )

        # Step 1: Capability Guard
        required_capabilities = [Capability.EXECUTE_SENSITIVE]
        if not self._capability_guard.check(tool_id, required_capabilities):
            self._publish_event(
                "EXECUTION_FAILED",
                {"tool_id": tool_id, "reason": "capability_denied"},
            )
            return SandboxResult(
                success=False,
                error=f"Capability denied for tool '{tool_id}'",
                exit_code=-1,
            )

        # Step 2: IO Policy Engine — check script content for violations
        io_violation = self._check_script_io_policy(tool_id, script, inputs)
        if io_violation is not None:
            self._publish_event(
                "EXECUTION_FAILED",
                {"tool_id": tool_id, "reason": "io_policy_violation"},
            )
            return SandboxResult(
                success=False,
                error=io_violation,
                exit_code=-1,
            )

        # Step 3: Sandbox Execution
        context = SandboxContext(
            tool_id=tool_id,
            timeout_seconds=30.0,
            max_memory_mb=256,
            max_cpu_seconds=10.0,
            allowed_paths=tuple(self._io_policy_engine._allowed_paths),
            allowed_domains=tuple(self._io_policy_engine._allowed_domains),
        )

        try:
            result = self._sandbox_executor.execute(script, context)
        except Exception as e:
            self._publish_event(
                "EXECUTION_FAILED",
                {"tool_id": tool_id, "error": str(e)},
            )
            return SandboxResult(
                success=False,
                error=f"Sandbox execution failed: {e}",
                exit_code=-1,
            )

        # Step 4: Publish final status
        if result.success:
            self._publish_event(
                "EXECUTION_COMPLETED",
                {
                    "tool_id": tool_id,
                    "exit_code": result.exit_code,
                    "duration_seconds": result.duration_seconds,
                },
            )
        else:
            self._publish_event(
                "EXECUTION_FAILED",
                {
                    "tool_id": tool_id,
                    "error": result.error,
                    "exit_code": result.exit_code,
                },
            )

        return result

    def register_tool_manifest(
        self, tool_id: str, manifest: CapabilityManifest
    ) -> None:
        """Register a tool's capability manifest."""
        self._capability_guard.register_manifest(tool_id, manifest)

    def configure_io_policy(
        self, allowed_paths: List[str], allowed_domains: List[str]
    ) -> None:
        """Configure IO policy allowlists."""
        for path in allowed_paths:
            self._io_policy_engine.add_allowed_path(path)
        for domain in allowed_domains:
            self._io_policy_engine.add_allowed_domain(domain)

    def _check_script_io_policy(
        self, tool_id: str, script: str, inputs: Dict[str, Any]
    ) -> Optional[str]:
        """Check script and inputs against IO policy. Returns error or None."""
        import re

        # Check for filesystem access patterns in script
        path_matches = re.findall(r'open\(["\']([^"\']+)["\']', script)
        for path in path_matches:
            if not self._io_policy_engine.check_file_access(tool_id, path, "read"):
                return f"IO policy violation: file access denied for path '{path}'"

        # Check for network access patterns in script
        url_matches = re.findall(r'https?://[^\s"\'<>]+', script)
        for url in url_matches:
            if not self._io_policy_engine.check_network_access(tool_id, url):
                return f"IO policy violation: network access denied for URL '{url}'"

        # Check inputs for file/network references
        for key, value in inputs.items():
            if isinstance(value, str):
                if "/" in value and value.startswith("/"):
                    if not self._io_policy_engine.check_file_access(tool_id, value, "read"):
                        return f"IO policy violation: file access denied for input '{key}'={value}"
                if value.startswith("http"):
                    if not self._io_policy_engine.check_network_access(tool_id, value):
                        return f"IO policy violation: network access denied for input '{key}'={value}"

        return None

    def _publish_event(self, event_type: str, payload: dict) -> None:
        """Publish a telemetry event via IEventBus."""
        if self._event_bus is None:
            return
        try:
            from core.models.event import EventTopic, ExecutionEvent

            topic_map = {
                "EXECUTION_STARTED": EventTopic.EXECUTION_STARTED,
                "EXECUTION_COMPLETED": EventTopic.EXECUTION_COMPLETED,
                "EXECUTION_FAILED": EventTopic.EXECUTION_FAILED,
            }
            topic = topic_map.get(event_type)
            if topic is None:
                return

            event = ExecutionEvent(
                topic=topic,
                payload=payload,
                trace_id=f"isolation-{payload.get('tool_id', 'unknown')}",
            )
            import asyncio
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(topic, event))
        except RuntimeError:
            pass
