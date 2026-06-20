"""Isolation Runtime Interface — Integration Layer Protocol.

Defines the protocol for the unified isolation runtime that bridges
CapabilityGuard, IOPolicyEngine, and SandboxExecutor.

Ref: Phase E.1.3 — IsolationRuntime Integration Layer
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Protocol

if TYPE_CHECKING:
    from core.models.sandbox import SandboxResult
    from core.models.security import CapabilityManifest


class IIsolationRuntime(Protocol):
    """Bridge between ExecutionEngine and Sandbox/Security/IO layers.

    Enforces the full execution pipeline:
    CapabilityGuard → IOPolicyEngine → SandboxExecutor → Event Publishing
    """

    async def execute_tool(
        self, tool_id: str, script: str, inputs: Dict[str, Any]
    ) -> SandboxResult: ...

    def register_tool_manifest(
        self, tool_id: str, manifest: CapabilityManifest
    ) -> None: ...

    def configure_io_policy(
        self, allowed_paths: List[str], allowed_domains: List[str]
    ) -> None: ...
